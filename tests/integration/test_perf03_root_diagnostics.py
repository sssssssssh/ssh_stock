"""Real isolated PG17 root parity; never uses the business database."""

import json
from time import perf_counter

import pytest
from app.core.config import get_settings
from app.models.data_publication import DataPublication
from app.models.job import JobRun
from app.services.performance_diagnostics import active_trace
from app.services.recalculation import create_recalculation_job
from sqlalchemy import select

from scripts.v14_test_database import isolated_v14_database
from tests.integration.test_business_recalc_performance import seed
from tests.integration.test_worker02_r2_lifecycle import KEYS, MODELS


@pytest.mark.parametrize("outcome,pair", [("success", 0), ("success", 1),
                                          ("success", 2), ("cancel", 0), ("error", 0)])
def test_real_root_parity_and_local_reports(monkeypatch, tmp_path, outcome, pair, record_property):
    from app.services import job_worker
    from app.services.factors.service import FactorService

    settings = get_settings()
    monkeypatch.setattr(settings, "perf_diagnostics_directory", tmp_path)
    outputs = []
    measurements = []
    original = FactorService.recalc

    def calculate(service, *args, **kwargs):
        if outcome == "cancel":
            from app.services.job_execution import JobCancelled
            raise JobCancelled("JOB_CANCEL_REQUESTED")
        if outcome == "error":
            raise ValueError("SYNTHETIC_DIAGNOSTIC_FAULT")
        return original(service, *args, **kwargs)

    monkeypatch.setattr(FactorService, "recalc", calculate)
    for enabled in (False, True):
        monkeypatch.setattr(settings, "perf_diagnostics_enabled", enabled)
        with isolated_v14_database(monkeypatch) as (factory, engine):
            days = seed(factory, include_closed=False, history_days=420)
            monkeypatch.setattr(job_worker, "SessionLocal", factory)
            with factory() as db:
                job = create_recalculation_job(db, start=days[-2], end=days[-1],
                                              evaluate_signals=False, mode="manual")
                assert job_worker.claim_next_job(db, "synthetic-perf03") == job.id
                db.refresh(job)
                began = perf_counter()
                job_worker.execute_claimed_job(db, job.id, expected_worker=job.worker_id,
                                              expected_token=job.execution_token)
                measurements.append(dict(enabled=enabled, pair=pair,
                                         wall_ms=(perf_counter()-began)*1000))
                db.expire_all()
                result = db.get(JobRun, job.id)
                ledger = db.get(DataPublication, job.id)
                assert result.status == {"success": "SUCCESS", "cancel": "CANCELLED",
                                         "error": "FAILED"}[outcome]
                assert ledger.state == ("PUBLISHED" if outcome == "success" else "ABORTED")
                financial = {}
                for model in MODELS:
                    exclude = {"calc_run_id", "calculated_at", "job_id", "checked_at",
                               "created_at", "updated_at", "id"}
                    columns = [c for c in model.__table__.columns if c.name not in exclude]
                    rows = db.execute(select(*columns).order_by(
                        *(getattr(model, k) for k in KEYS[model.__tablename__]))).all()
                    financial[model.__tablename__] = [tuple(row) for row in rows]
                outputs.append(financial)
        assert active_trace.get() is None
        reports = list(tmp_path.rglob("*.json"))
        assert len(reports) == int(enabled)
        if enabled:
            report = json.loads(reports[0].read_text())
            assert report["status"] == {"success": "success", "cancel": "cancelled",
                                        "error": "error"}[outcome]
            assert report["database_summary"]["execute_calls"] > 0
    assert outputs[0] == outputs[1]
    record_property("perf03_root_cost", json.dumps(measurements))
