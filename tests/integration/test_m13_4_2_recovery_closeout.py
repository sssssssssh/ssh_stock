from datetime import UTC, date, datetime, timedelta

import pytest
import sqlalchemy as sa
from app.api.v1.portfolio import backtest_progress
from app.core.db import SessionLocal
from app.models.job import JobRun
from app.models.market_data import TradeCalendar
from app.models.portfolio import PortfolioBacktestCheckpoint, PortfolioBacktestRun
from app.services.portfolio.application import PortfolioApplicationService
from app.services.portfolio.backtest_application import (
    BacktestApplicationService,
    BacktestExecutionLease,
    BacktestOwnershipError,
    BacktestRunner,
    recover_stale_backtest_jobs,
)

_ERROR_CODE = "BACKTEST_PRE_OWNERSHIP_TIMEOUT"
_ERROR_MESSAGE = (
    "worker heartbeat expired after JobRun claim but before backtest ownership "
    "lease was established; explicit resume required"
)
_TRADE_DATE = date(2026, 2, 23)


def test_pre_ownership_stale_job_is_failed_without_fabricating_checkpoint() -> None:
    name = "m13.4.2-pre-ownership-recovery"
    recovered_at = datetime.now(UTC)
    try:
        with SessionLocal() as setup:
            run, job = _pre_ownership_claim(
                setup,
                name,
                worker_id="worker-before-lease",
                heartbeat_at=recovered_at - timedelta(minutes=30),
            )
            run_id, old_job_id = run.id, job.id

        with SessionLocal() as recovery:
            assert (
                recover_stale_backtest_jobs(
                    recovery, timeout_minutes=15, now=recovered_at
                )
                == 1
            )

        with SessionLocal() as check:
            run = check.get(PortfolioBacktestRun, run_id)
            job = check.get(JobRun, old_job_id)
            checkpoint_count = check.scalar(
                sa.select(sa.func.count())
                .select_from(PortfolioBacktestCheckpoint)
                .where(PortfolioBacktestCheckpoint.run_id == run_id)
            )
            execution_job_count = check.scalar(
                sa.select(sa.func.count())
                .select_from(JobRun)
                .where(
                    JobRun.job_type == "portfolio_backtest",
                    JobRun.job_metadata["portfolio_run_id"].astext == str(run_id),
                )
            )
            assert run is not None and job is not None
            assert run.status == job.status == "FAILED"
            assert run.owner_worker_id is None
            assert run.finished_at == recovered_at
            assert job.finished_at == recovered_at
            assert run.error_message == job.error_message == _ERROR_MESSAGE
            assert run.result_summary["stage"] == "failed"
            assert run.result_summary["error_code"] == _ERROR_CODE
            assert checkpoint_count == 0
            assert execution_job_count == 1

            response = backtest_progress(run_id, db=check)
            assert response["data"]["run_status"] == "FAILED"
            assert response["data"]["job_status"] == "FAILED"
            assert response["data"]["error_code"] == _ERROR_CODE
            assert response["data"]["error_message"] == _ERROR_MESSAGE
            assert response["data"]["current_phase"] is None
    finally:
        _cleanup(name)


def test_pre_ownership_recovery_rechecks_fresh_heartbeat_under_job_lock() -> None:
    name = "m13.4.2-pre-ownership-heartbeat-race"
    recovered_at = datetime.now(UTC)
    try:
        with SessionLocal() as setup:
            run, job = _pre_ownership_claim(
                setup,
                name,
                worker_id="worker-still-alive",
                heartbeat_at=recovered_at - timedelta(minutes=30),
            )
            run_id, job_id = run.id, job.id

        def refresh_after_discovery(_: object) -> None:
            with SessionLocal() as heartbeat:
                heartbeat.execute(
                    sa.update(JobRun)
                    .where(JobRun.id == job_id)
                    .values(heartbeat_at=recovered_at)
                )
                heartbeat.commit()

        with SessionLocal() as recovery:
            assert (
                recover_stale_backtest_jobs(
                    recovery,
                    timeout_minutes=15,
                    now=recovered_at,
                    before_lock_hook=refresh_after_discovery,
                )
                == 0
            )

        with SessionLocal() as check:
            run = check.get(PortfolioBacktestRun, run_id)
            job = check.get(JobRun, job_id)
            assert run is not None and run.status == "CREATED"
            assert run.owner_worker_id is None and run.ownership_version == 0
            assert job is not None and job.status == "RUNNING"
            assert job.worker_id == "worker-still-alive"
    finally:
        _cleanup(name)


def test_explicit_resume_creates_new_job_and_fences_pre_ownership_worker() -> None:
    name = "m13.4.2-pre-ownership-resume-fencing"
    recovered_at = datetime.now(UTC)
    try:
        with SessionLocal() as setup:
            run, old_job = _pre_ownership_claim(
                setup,
                name,
                worker_id="worker-old",
                heartbeat_at=recovered_at - timedelta(minutes=30),
            )
            run_id, old_job_id = run.id, old_job.id

        with SessionLocal() as recovery:
            assert (
                recover_stale_backtest_jobs(
                    recovery, timeout_minutes=15, now=recovered_at
                )
                == 1
            )

        with SessionLocal() as resume_db:
            run, new_job = BacktestApplicationService(resume_db).resume(run_id)
            new_job_id = new_job.id
            assert new_job_id != old_job_id
            assert run.status == "FAILED"
            new_job.status = "RUNNING"
            new_job.worker_id = "worker-new"
            new_job.heartbeat_at = datetime.now(UTC)
            resume_db.commit()

        with SessionLocal() as old_worker:
            with pytest.raises(BacktestOwnershipError):
                BacktestRunner(old_worker)._claim_run(old_job_id)
            old_worker.rollback()

        with SessionLocal() as new_worker:
            run, job, lease = BacktestRunner(new_worker)._claim_run(new_job_id)
            assert lease.job_id == new_job_id
            assert lease.worker_id == "worker-new"
            assert lease.ownership_version == 1
            assert run.status == "RUNNING"
            assert run.job_id == new_job_id
            assert run.owner_worker_id == "worker-new"
            assert job.job_metadata["ownership_version"] == 1

        with SessionLocal() as old_worker:
            stale_lease = BacktestExecutionLease(
                run_id=run_id,
                job_id=old_job_id,
                worker_id="worker-old",
                ownership_version=0,
            )
            stale_runner = BacktestRunner(old_worker)
            with pytest.raises(BacktestOwnershipError):
                stale_runner._claim_run(old_job_id)
            old_worker.rollback()
            with pytest.raises(BacktestOwnershipError):
                stale_runner._run_phase(
                    stale_lease,
                    _TRADE_DATE,
                    "START_OF_DAY",
                )
            old_worker.rollback()
            with pytest.raises(BacktestOwnershipError):
                stale_runner._finish_success(stale_lease)
            old_worker.rollback()
            with pytest.raises(BacktestOwnershipError):
                stale_runner._finish_cancelled(stale_lease)
            old_worker.rollback()
            stale_runner._mark_checkpoint_failed(
                stale_lease,
                _TRADE_DATE,
                "START_OF_DAY",
                RuntimeError("stale worker checkpoint failure"),
            )
            stale_runner._mark_run_failed(
                stale_lease,
                RuntimeError("stale worker run failure"),
            )

        with SessionLocal() as check:
            run = check.get(PortfolioBacktestRun, run_id)
            assert run is not None
            assert (run.status, run.job_id, run.owner_worker_id) == (
                "RUNNING",
                new_job_id,
                "worker-new",
            )
    finally:
        _cleanup(name)


def _pre_ownership_claim(
    db: object,
    name: str,
    *,
    worker_id: str,
    heartbeat_at: datetime,
) -> tuple[PortfolioBacktestRun, JobRun]:
    if db.get(TradeCalendar, _TRADE_DATE) is None:
        db.add(
            TradeCalendar(
                cal_date=_TRADE_DATE,
                is_open=True,
                exchange="SSE",
            )
        )
    run = PortfolioApplicationService(db).create_backtest_definition(
        start_date=_TRADE_DATE, end_date=_TRADE_DATE, name=name
    )
    run, job = BacktestApplicationService(db).execute(run.id)
    job.status = "RUNNING"
    job.worker_id = worker_id
    job.heartbeat_at = heartbeat_at
    db.commit()
    return run, job


def _cleanup(name: str) -> None:
    with SessionLocal() as db:
        runs = list(
            db.execute(
                sa.select(PortfolioBacktestRun).where(
                    PortfolioBacktestRun.name == name
                )
            ).scalars()
        )
        run_ids = [str(run.id) for run in runs]
        job_ids = list(
            db.execute(
                sa.select(JobRun.id).where(
                    JobRun.job_type == "portfolio_backtest",
                    JobRun.job_metadata["portfolio_run_id"].astext.in_(run_ids),
                )
            ).scalars()
        )
        for run in runs:
            db.delete(run)
        db.flush()
        if job_ids:
            db.execute(sa.delete(JobRun).where(JobRun.id.in_(job_ids)))
        db.execute(
            sa.delete(TradeCalendar).where(TradeCalendar.cal_date == _TRADE_DATE)
        )
        db.commit()
