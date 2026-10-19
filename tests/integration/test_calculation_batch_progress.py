from uuid import uuid4

from app.models.data_publication import DataPublicationRow
from app.models.job import JobRun
from app.models.market_data import StockTradeStatusDaily
from app.repositories.job_run import touch_job_heartbeat, update_job
from app.repositories.upsert import upsert_rows
from app.services.calculation_progress import CalculationProgress, current_progress
from app.services.data_publication import PublicationWorkspace
from sqlalchemy import func, select

from tests.integration.m16_6_support import isolated_contract_database
from tests.integration.test_data_publication import candidate, sample_row, seed_published


def test_live_batches_visible_without_committing_candidates_or_publishing(monkeypatch):
    with isolated_contract_database(monkeypatch) as (factory, engine):
        old_id = seed_published(factory)
        recorder = CalculationProgress()
        context = current_progress.set(recorder)
        observed = []
        original = PublicationWorkspace._store_batch

        def store(workspace, rows):
            original(workspace, rows)
            # The callback runs inside the uncommitted candidate transaction.
            with factory() as observer:
                snapshot = recorder.snapshot()
                assert touch_job_heartbeat(observer, workspace.job_id, "publication-test",
                                           execution_token=workspace.token,
                                           calculation_progress=snapshot)
                job = observer.get(JobRun, workspace.job_id)
                observed.append(job.job_metadata["calculation_progress"])
                assert observer.scalar(select(func.count()).select_from(DataPublicationRow)) == 0
                assert observer.scalar(select(StockTradeStatusDaily.calc_run_id)) == old_id

        monkeypatch.setattr(PublicationWorkspace, "_store_batch", store)
        try:
            with candidate(factory, engine) as (db, job):
                payload = [dict(sample_row(StockTradeStatusDaily, job.id), ts_code=f"T{i:05d}.SZ")
                           for i in range(501)]
                assert upsert_rows(db, StockTradeStatusDaily, payload,
                                   ["trade_date", "ts_code"]) == 501
                assert [v["batch_index"] for v in observed] == [1, 2]
                assert [v["completed_rows"] for v in observed] == [0, 500]
                assert all(v["batch_count"] == 2 for v in observed)
                assert observed[1]["advanced_at"] is not None
                # Diagnostic commits above must not commit the business Session.
                db.rollback()
                update_job(db, job, status="FAILED", step="synthetic rollback")
                with factory() as observer:
                    finished = observer.get(JobRun, job.id)
                    assert finished.status == "FAILED"
                    assert finished.job_metadata["calculation_progress"]["completed_rows"] == 501
                    assert finished.job_metadata["publication"]["state"] == "ABORTED"
                    assert observer.scalar(
                        select(func.count()).select_from(DataPublicationRow),
                    ) == 0
                    assert observer.scalar(select(StockTradeStatusDaily.calc_run_id)) == old_id
        finally:
            current_progress.reset(context)


def test_telemetry_rejects_wrong_owner_and_token_and_never_regresses_progress(monkeypatch):
    with isolated_contract_database(monkeypatch) as (factory, engine):
        with candidate(factory, engine) as (db, job):
            recorder = CalculationProgress()
            token = current_progress.set(recorder)
            try:
                from app.services.calculation_progress import ProgressStep

                progress = ProgressStep("stock_trade_status_daily", "candidate", total_rows=500)
                progress.report("batch_complete", completed_rows=500, advanced=True)
                snapshot = recorder.snapshot()
                with factory() as observer:
                    assert not touch_job_heartbeat(observer, job.id, "wrong",
                        execution_token=job.execution_token, calculation_progress=snapshot)
                    assert not touch_job_heartbeat(observer, job.id, job.worker_id,
                        execution_token=uuid4(), calculation_progress=snapshot)
                    observer.expire_all()
                    assert "calculation_progress" not in observer.get(JobRun, job.id).job_metadata
                    assert touch_job_heartbeat(observer, job.id, job.worker_id,
                        execution_token=job.execution_token, calculation_progress=snapshot)
                    previous = observer.get(JobRun, job.id).last_progress_at
                    stale = {**snapshot, "advanced_at": "2000-01-01T00:00:00+00:00",
                             "updated_at": "2000-01-01T00:00:00+00:00", "completed_rows": 0}
                    assert touch_job_heartbeat(observer, job.id, job.worker_id,
                        execution_token=job.execution_token, calculation_progress=stale)
                    observer.expire_all()
                    assert observer.get(JobRun, job.id).last_progress_at == previous
                    assert observer.get(JobRun, job.id).job_metadata[
                        "calculation_progress"
                    ]["completed_rows"] == 500
                update_job(db, job, status="CANCELLED", step="synthetic cancellation")
                with factory() as observer:
                    assert not touch_job_heartbeat(observer, job.id, job.worker_id,
                        execution_token=job.execution_token, calculation_progress=snapshot)
            finally:
                current_progress.reset(token)
