"""Real marked PG17 Worker lifecycle; never business/G1 connections."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.models.data_publication import DataPublication
from app.models.job import JobRun
from app.services import job_worker as worker
from app.services.recalculation import create_recalculation_job
from sqlalchemy import text

from scripts.v14_test_database import isolated_v14_database
from tests.integration.test_business_policy_worker_pg17 import run_until_idle
from tests.integration.test_business_recalc_performance import seed


@pytest.mark.parametrize("outcome", ["SUCCESS", "FAILED", "CANCELLED"])
def test_opt_in_actual_worker_persists_scoped_diagnostics_and_resets(monkeypatch, outcome):
    from app.services.execution_diagnostics import active_diagnostics
    from app.services.factors.service import FactorService
    from app.services.job_execution import JobCancelled

    settings = get_settings()
    # Works against the old code too: exposes the missing runtime installation,
    # rather than failing merely because the new setting is not yet declared.
    monkeypatch.setitem(settings.__dict__, "worker_diagnostics_enabled", True)
    with isolated_v14_database(monkeypatch) as (factory, _):
        days = seed(factory, include_closed=False, history_days=420)
        with factory() as db:
            key = create_recalculation_job(db, start=days[-2], end=days[-1],
                evaluate_signals=False, mode="manual").id
        if outcome != "SUCCESS":
            original = FactorService.recalc

            def stop(service, *args, **kwargs):
                original(service, *args, **kwargs)
                if outcome == "CANCELLED":
                    raise JobCancelled("JOB_CANCEL_REQUESTED")
                raise ValueError("ISOLATED_FAILURE")

            monkeypatch.setattr(FactorService, "recalc", stop)
        run_until_idle(factory, monkeypatch)
        assert active_diagnostics.get() is None
        with factory() as db:
            job = db.get(JobRun, key)
            assert job.status == outcome
            report = job.job_metadata["execution_diagnostics"]
            assert report["outcome"] == outcome
            assert report["root_job_id"] == str(key)
            assert report["execution_fingerprint"]
            assert len(report["phases"]) <= 128 and len(report["recent"]) <= 32
            metrics = {(x["name"], x["phase"]) for x in report["phases"]}
            assert ("trade_status.stock_daily", "fetch") in metrics
            assert ("trade_status.compute", "compute") in metrics
            assert ("trade_status.rows", "materialize") in metrics
            assert ("stock_trade_status_daily", "store") in metrics
            assert ("recalculation.raw_prerequisites", "query") in metrics
            assert ("factors.compute", "compute") in metrics
            if outcome == "SUCCESS":
                assert any(name.startswith("publication.") for name, _ in metrics)
            else:
                assert db.get(DataPublication, key).state == "ABORTED"
            assert str(job.execution_token) not in json.dumps(report)


def test_heartbeat_commit_ack_unknown_keeps_writer_and_reusable_connection(monkeypatch):
    from app.repositories.job_run import touch_job_heartbeat
    from sqlalchemy.exc import OperationalError

    with isolated_v14_database(monkeypatch) as (factory, _):
        with factory() as db:
            row = JobRun(job_type="recalculate", status="RUNNING", worker_id="synthetic",
                         execution_token=uuid4(), heartbeat_at=datetime.now(UTC)-timedelta(hours=2),
                         job_metadata={"first_error": "preserved"})
            db.add(row)
            db.commit()
            key, token = row.id, row.execution_token
        with factory() as db:
            commit = db.commit

            def lose_ack():
                commit()
                raise OperationalError("synthetic", {}, RuntimeError("PRIVATE"),
                                       connection_invalidated=True)

            monkeypatch.setattr(db, "commit", lose_ack)
            with pytest.raises(OperationalError) as caught:
                touch_job_heartbeat(db, key, "synthetic", execution_token=token)
            assert caught.value.heartbeat_phase == "lease_commit"
            db.rollback()
            assert db.scalar(text("SELECT 1")) == 1
        with factory() as db:
            job = db.get(JobRun, key)
            assert job.status == "RUNNING" and job.job_metadata == {"first_error": "preserved"}
            assert datetime.now(UTC)-job.heartbeat_at < timedelta(seconds=10)
