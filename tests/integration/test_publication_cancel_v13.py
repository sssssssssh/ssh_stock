"""Real PG row locks and cooperative candidate cancellation, without killing executors."""

from time import monotonic
from uuid import uuid4

import pytest
from app.api.v1.jobs import cancel_job
from app.models.data_publication import DataPublication, DataPublicationRow
from app.models.job import JobRun
from app.models.market_data import StockTradeStatusDaily
from app.repositories.job_run import update_job
from app.services.calculation_progress import CalculationProgress, ProgressStep, current_progress
from app.services.job_execution import JobCancelled, JobOwnershipLost
from app.services.job_worker import _finish_data_cancellation, _run_heartbeat_loop, claim_next_job
from sqlalchemy import func, select, update

from tests.integration.m16_6_support import isolated_contract_database
from tests.integration.test_data_publication import candidate, sample_row, seed_published


@pytest.mark.parametrize("cancel_at", ["lookup", "first_store"])
def test_cancel_reaches_candidate_batch_and_releases_slot_only_after_rollback(
    monkeypatch, cancel_at
):
    with isolated_contract_database(monkeypatch) as (factory, engine):
        old = seed_published(factory)
        recorder = CalculationProgress()
        context = current_progress.set(recorder)
        try:
            with candidate(factory, engine) as (db, job):
                ws = db.info["publication_workspace"]
                stored = []
                original_store = ws._store_batch
                original_lookup = ws._lookup_batch

                def request_cancel():
                    with factory() as observer:
                        result = cancel_job(job.id, observer)
                        assert result["meta"]["cancel_accepted"] is True
                        assert result["meta"]["cancel_completed"] is False
                        assert observer.get(JobRun, job.id).status == "RUNNING"
                        assert claim_next_job(observer, "must-not-take-over") is None

                def lookup(*args, **kwargs):
                    result = original_lookup(*args, **kwargs)
                    if cancel_at == "lookup":
                        request_cancel()
                    return result

                def store(rows):
                    original_store(rows)
                    stored.append(len(rows))
                    if cancel_at == "first_store" and len(stored) == 1:
                        request_cancel()

                monkeypatch.setattr(ws, "_lookup_batch", lookup)
                monkeypatch.setattr(ws, "_store_batch", store)
                rows = [
                    {**sample_row(StockTradeStatusDaily, job.id), "ts_code": f"V{n:06d}.SZ"}
                    for n in range(501)
                ]
                with pytest.raises(JobCancelled):
                    ws.upsert(StockTradeStatusDaily, rows, ["trade_date", "ts_code"])
                assert stored == ([] if cancel_at == "lookup" else [500])
                db.rollback()
                _finish_data_cancellation(db, job)
                with factory() as observer:
                    assert observer.get(JobRun, job.id).status == "CANCELLED"
                    assert observer.get(DataPublication, job.id).state == "ABORTED"
                    assert observer.scalar(select(StockTradeStatusDaily.calc_run_id)) == old
                    assert (
                        observer.scalar(select(func.count()).select_from(DataPublicationRow)) == 0
                    )
                    assert (
                        observer.get(JobRun, job.id).job_metadata["calculation_progress"]["phase"]
                        == "cancelled"
                    )
        finally:
            current_progress.reset(context)


def test_wrong_token_detected_before_candidate_store(monkeypatch):
    with isolated_contract_database(monkeypatch) as (factory, engine):
        old = seed_published(factory)
        with candidate(factory, engine) as (db, job):
            ws = db.info["publication_workspace"]
            original = ws._lookup_batch

            def lookup(*args, **kwargs):
                result = original(*args, **kwargs)
                with factory() as observer:
                    observer.execute(
                        update(JobRun).where(JobRun.id == job.id).values(execution_token=uuid4())
                    )
                    observer.commit()
                return result

            monkeypatch.setattr(ws, "_lookup_batch", lookup)
            with pytest.raises(JobOwnershipLost):
                ws.upsert(
                    StockTradeStatusDaily,
                    [sample_row(StockTradeStatusDaily, job.id)],
                    ["trade_date", "ts_code"],
                )
            db.rollback()
            with factory() as observer:
                assert observer.get(JobRun, job.id).status == "RUNNING"
                assert observer.scalar(select(StockTradeStatusDaily.calc_run_id)) == old
                assert observer.scalar(select(func.count()).select_from(DataPublicationRow)) == 0


def test_heartbeat_timeout_during_job_lock_does_not_break_business_session(monkeypatch):
    with isolated_contract_database(monkeypatch) as (factory, engine):
        old = seed_published(factory)
        with candidate(factory, engine) as (db, job):
            recorder = CalculationProgress()
            context = current_progress.set(recorder)
            try:
                ProgressStep("publication.tables", "publish").report("store")
                db.scalar(select(JobRun).where(JobRun.id == job.id).with_for_update(key_share=True))
                monkeypatch.setattr("app.services.job_worker.SessionLocal", factory)

                class Stop:
                    calls = 0

                    def wait(self, interval):
                        self.calls += 1
                        return self.calls > 1

                started = monotonic()
                _run_heartbeat_loop(
                    job.id,
                    job.worker_id,
                    Stop(),
                    interval_seconds=0.01,
                    execution_token=job.execution_token,
                    progress=recorder,
                )
                assert monotonic() - started < 10
                assert db.scalar(select(JobRun.status).where(JobRun.id == job.id)) == "RUNNING"
                assert db.scalar(select(StockTradeStatusDaily.calc_run_id)) == old
                db.rollback()
                update_job(db, job, status="CANCELLED")
            finally:
                current_progress.reset(context)
