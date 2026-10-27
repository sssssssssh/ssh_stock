"""Policy evidence and fail-closed drift on real, separately marked PG17."""

from datetime import date

import pytest
from app.core.config import get_settings
from app.models.job import JobRun
from app.repositories.job_run import start_job
from app.services import calculation_policy as cp
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from scripts.v14_test_database import isolated_v14_database
from tests.integration.test_business_recalc_performance import seed
from tests.integration.test_data_publication import candidate


@pytest.mark.parametrize("fault", [*cp.FLAGS, "source"])
def test_real_worker_rejects_drift_and_aborts_instead_of_publishing(monkeypatch, fault):
    from app.models.data_publication import DataPublication
    from app.services import job_worker
    from app.services.factors.service import FactorService
    from app.services.recalculation import create_recalculation_job

    with isolated_v14_database(monkeypatch) as (factory, engine):
        days = seed(factory, include_closed=False, history_days=420)
        settings = get_settings()
        for field in cp.FLAGS:
            monkeypatch.setattr(settings, field, True)
        monkeypatch.setattr(job_worker, "SessionLocal", factory)
        original = FactorService.recalc

        def drift(service, start, end, calc_run_id=None):
            rows = original(service, start, end, calc_run_id=calc_run_id)
            if fault == "source":
                source = cp.runtime_source()
                monkeypatch.setattr(cp, "runtime_source", lambda: {
                    **source, "source_sha256": "0" * 64,
                })
            else:
                monkeypatch.setattr(settings, fault, False)
            return rows

        monkeypatch.setattr(FactorService, "recalc", drift)
        with factory() as db:
            job = create_recalculation_job(db, start=days[-30], end=days[-1],
                                          evaluate_signals=False, mode="manual")
            assert job_worker.claim_next_job(db, "policy-regression") == job.id
            db.refresh(job)
            job_worker.execute_claimed_job(db, job.id, expected_worker=job.worker_id,
                                          expected_token=job.execution_token)
            db.expire_all()
            result = db.get(JobRun, job.id)
            assert result.status == "FAILED"
            assert "CALCULATION_POLICY_CHANGED" in result.error_message
            assert db.get(DataPublication, job.id).state == "ABORTED"
            evidence = result.job_metadata["calculation_execution"]
            assert evidence["flags"] == dict.fromkeys(cp.FLAGS, True)
            assert evidence["source"]["source_sha256"] != "0" * 64
            assert evidence["sql"]["SELECT"]["count"] > 0
            assert evidence["reads"]["factors.stock_daily"]["rows"] > 0
            assert evidence["stages"]


def test_multiple_real_child_jobs_inherit_source_and_own_request_without_wire_claim(monkeypatch):
    with isolated_v14_database(monkeypatch) as (factory, engine):
        with candidate(factory, engine) as (db, root):
            policy = cp.ExecutionPolicy.freeze(root, get_settings())
            token = cp.active_policy.set(policy)
            try:
                children = [start_job(db, "daily", date(2025, 1, d), metadata={
                    "start": f"2025-01-{d:02d}", "end": f"2025-01-{d:02d}",
                }) for d in (2, 3)]
                for child in children:
                    record = child.job_metadata["calculation_execution"]
                    assert record["root_job_id"] == str(root.id)
                    assert record["job_id"] == str(child.id)
                    assert record["source"] == policy.source
                    assert record["request"]["start"] == child.target_trade_date.isoformat()
                    assert record["fetch_scope"] == "DELIVERED_PARTITIONS_NOT_WIRE_FETCH"
            finally:
                cp.active_policy.reset(token)
                policy.close()


def test_query_timeout_is_counted_and_listener_and_transaction_recover(monkeypatch):
    with isolated_v14_database(monkeypatch) as (factory, engine):
        with factory() as db:
            job = JobRun(id=__import__("uuid").uuid4(), job_metadata={})
            policy = cp.ExecutionPolicy.freeze(job, get_settings())
            token = cp.active_policy.set(policy)
            observer = cp.QueryObserver(engine, policy)
            observer.install()
            try:
                db.execute(text("SET LOCAL statement_timeout='20ms'"))
                with pytest.raises(DBAPIError) as caught:
                    db.execute(text("SELECT pg_sleep(0.2)"))
                assert caught.value.orig.sqlstate == "57014"
                db.rollback()
                assert db.scalar(select(1)) == 1
                assert policy.sql["SELECT"]["failures"] == 1
            finally:
                observer.close()
                observer.close()
                cp.active_policy.reset(token)
            counts = policy.snapshot()["sql"]
            assert db.scalar(select(1)) == 1
            assert policy.snapshot()["sql"] == counts
