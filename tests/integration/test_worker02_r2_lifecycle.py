"""Ordinary claimed roots with real calculators and synthetic provider replay."""

import hashlib
import json
import time
from collections import Counter
from copy import deepcopy

import pandas as pd
import pytest
from app.core.config import get_settings
from app.models.data_publication import DataPublication
from app.models.job import JobRun
from app.services.calculation_memory import process_memory_bytes
from app.services.data_publication import KEYS, MODELS
from app.services.execution_diagnostics import active_diagnostics
from app.services.job_execution import current_execution
from app.services.job_guard import create_queued_ingestion_job
from app.services.recalculation import create_recalculation_job
from sqlalchemy import event, select, text

from scripts.v14_test_database import isolated_v14_database
from tests.integration.test_business_policy_worker_pg17 import (
    SyntheticReplayProvider,
    run_until_idle,
)
from tests.integration.test_business_recalc_performance import seed


@pytest.mark.parametrize("kind", ["recalculate", "daily", "catchup"])
def test_claimed_roots_off_on_complete_publication_and_record_cost(monkeypatch, kind,
                                                                 record_property):
    from app.services import job_worker

    settings = get_settings()
    config = deepcopy(settings.app_config)
    config["app"]["scheduler"].update(max_catchup_trade_days=2, refresh_recent_trade_days=2,
                                       worker_heartbeat_interval_seconds=0.1)
    monkeypatch.setattr(settings, "app_config", config)
    results, measurements = [], []
    for enabled in (False, True):
        monkeypatch.setattr(settings, "worker_diagnostics_enabled", enabled)
        # Fresh identical physical test database per arm prevents catchup OFF from
        # satisfying ON's prerequisites or changing its publication workload.
        with isolated_v14_database(monkeypatch) as (factory, engine):
            days = seed(factory, include_closed=False, history_days=420)
            monkeypatch.setattr(job_worker, "_provider", lambda _: SyntheticReplayProvider(factory))
            with factory() as db:
                if kind == "recalculate":
                    key = create_recalculation_job(db, start=days[-2], end=days[-1],
                        evaluate_signals=False, mode="manual").id
                else:
                    key = create_queued_ingestion_job(db, kind, days[-1], step="queued",
                        metadata={"trade_date": days[-1].isoformat(),
                                  "evaluate_signals": False}).id
            counters = Counter()

            def count_sql(connection, cursor, statement, parameters, context, many,
                          counters=counters):
                verb = statement.lstrip().split(None, 1)[0].upper()
                counters["statements"] += 1
                if verb in {"INSERT", "UPDATE", "DELETE"}:
                    counters["write_statements"] += 1

            with engine.connect() as connection:
                wal_before = connection.scalar(text("SELECT pg_current_wal_lsn()"))
            memory_before = process_memory_bytes()
            wall, cpu = time.perf_counter(), time.process_time()
            event.listen(engine, "before_cursor_execute", count_sql)
            try:
                run_until_idle(factory, monkeypatch)
            finally:
                event.remove(engine, "before_cursor_execute", count_sql)
            elapsed, cpu_elapsed = time.perf_counter()-wall, time.process_time()-cpu
            memory_after = process_memory_bytes()
            with engine.connect() as connection:
                wal_delta = int(connection.scalar(text(
                    "SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), :before)"),
                    {"before": wal_before}))
            assert active_diagnostics.get() is current_execution.get() is None
            with factory() as db:
                job = db.get(JobRun, key)
                assert job.status == "SUCCESS", job.error_message
                assert db.get(DataPublication, key).state == "PUBLISHED"
                children = list(db.scalars(select(JobRun).where(JobRun.parent_job_id == key)))
                assert all(child.status == "SUCCESS" for child in children)
                report = job.job_metadata.get("execution_diagnostics")
                if enabled:
                    assert report["outcome"] == "SUCCESS"
                    assert report["root_job_id"] == str(key)
                    for phase in ("raw_preflight", "trade_status_read", "trade_status_compute",
                                  "trade_status_materialize", "trade_status_replace",
                                  "candidate_lookup", "candidate_store", "factor_compute",
                                  "publish"):
                        assert report["coverage"][phase] == "RECORDED", (kind, phase, report)
                    assert report["coverage"]["factor_window"] == "NOT_INSTRUMENTED"
                    assert {("trade_status.stock_daily", x) for x in ("query", "fetch", "frame")} \
                        <= {(x["name"], x["phase"]) for x in report["phases"]}
                else:
                    assert report is None  # Health/session facts remain independent of perf opt-in.
                frames, hashes = {}, {}
                # Explicit per-run identities/timestamps and surrogate IDs only.
                # Financial values, versions, hashes, JSON payloads and natural
                # keys all remain in the exact comparison.
                for model in MODELS:
                    excluded = {"calc_run_id", "calculated_at", "job_id", "checked_at",
                                "created_at", "updated_at"}
                    if model.__tablename__ in {"strategy_signal", "signal_forward_eval",
                                               "data_quality_daily"}:
                        excluded.add("id")
                    columns = [c for c in model.__table__.columns if c.name not in excluded]
                    rows = db.execute(select(*columns).order_by(
                        *(getattr(model, k) for k in KEYS[model.__tablename__]))).mappings().all()
                    frame = pd.DataFrame(rows, columns=[c.name for c in columns])
                    frames[model.__tablename__] = frame
                    hashes[model.__tablename__] = dict(rows=len(frame), dtypes={
                        k: str(v) for k, v in frame.dtypes.items()}, sha256=hashlib.sha256(
                            json.dumps([dict(row) for row in rows], sort_keys=True,
                                       default=str, allow_nan=False).encode()).hexdigest())
                assert not frames["stock_factor_daily"].empty
                results.append(frames)
                measurements.append(dict(enabled=enabled, wall_seconds=elapsed,
                    process_cpu_seconds=cpu_elapsed, memory_before=memory_before,
                    memory_after=memory_after,
                    memory_kind="POSIX_PROCESS_LIFETIME_HIGHWATER_NOT_RUN_PEAK",
                    sql_counts=dict(counters), cluster_wal_bytes=wal_delta,
                    wal_kind="SHARED_TEST_CLUSTER_LSN_DELTA_NOT_EXCLUSIVE_STATEMENT_COST",
                    financial=hashes, diagnostics=report,
                    root_status=job.status, publication="PUBLISHED",
                    children=sorted(child.status for child in children)))
    for table in results[0]:
        pd.testing.assert_frame_equal(results[0][table], results[1][table], check_exact=True)
        assert measurements[0]["financial"][table] == measurements[1]["financial"][table]
    assert measurements[0]["children"] == measurements[1]["children"]
    record_property("worker02_r2_cost_observations", json.dumps(measurements))
