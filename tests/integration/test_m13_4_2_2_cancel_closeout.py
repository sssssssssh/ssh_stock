import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Event

import pytest
import sqlalchemy as sa
from app.api.v1.portfolio import backtest_progress
from app.core.db import SessionLocal
from app.models.job import JobRun
from app.models.market_data import TradeCalendar
from app.models.portfolio import PortfolioBacktestCheckpoint, PortfolioBacktestRun
from app.services.job_worker import claim_next_job
from app.services.portfolio.application import PortfolioApplicationService
from app.services.portfolio.backtest_application import (
    BacktestApplicationService,
    BacktestOwnershipError,
    BacktestRunner,
)

_TRADE_DATE = date(2026, 2, 24)


def test_cancelled_run_resume_queued_job_can_be_cancelled_again() -> None:
    name = "m13.4.2.2-cancelled-resume-queued-cancel"
    try:
        run_id = _create_terminal_run(name, status="CANCELLED")
        job_id = _resume_job(run_id)

        with SessionLocal() as requester:
            run, job = BacktestApplicationService(requester).cancel(run_id)
            assert job is not None
            assert run.status == job.status == "CANCELLED"
            assert job.cancel_requested is True
            assert job.finished_at is not None
            assert run.owner_worker_id is None
            assert run.ownership_version == 1

        with SessionLocal() as check:
            response = backtest_progress(run_id, db=check)
            assert response["data"]["run_status"] == "CANCELLED"
            assert response["data"]["job_status"] == "CANCELLED"
            assert _checkpoint_count(check, run_id) == 0
            assert _execution_job_count(check, run_id) == 2

        with SessionLocal() as worker:
            assert claim_next_job(worker, "worker-too-late") != job_id
            with pytest.raises(BacktestOwnershipError):
                BacktestRunner(worker)._claim_run(job_id)
            worker.rollback()
    finally:
        _cleanup(name)


def test_cancelled_run_resume_running_prelease_job_can_be_cancelled_again() -> None:
    name = "m13.4.2.2-cancelled-resume-running-cancel"
    try:
        run_id = _create_terminal_run(name, status="CANCELLED")
        job_id = _resume_job(run_id, worker_id="worker-b")

        with SessionLocal() as requester:
            run, job = BacktestApplicationService(requester).cancel(run_id)
            assert job is not None
            assert run.status == job.status == "CANCELLED"
            assert job.cancel_requested is True
            assert run.owner_worker_id is None
            assert run.ownership_version == 1

        with SessionLocal() as check:
            response = backtest_progress(run_id, db=check)
            assert response["data"]["run_status"] == "CANCELLED"
            assert response["data"]["job_status"] == "CANCELLED"
            assert _checkpoint_count(check, run_id) == 0

        with SessionLocal() as old_worker:
            with pytest.raises(BacktestOwnershipError):
                BacktestRunner(old_worker)._claim_run(job_id)
            old_worker.rollback()
    finally:
        _cleanup(name)


@pytest.mark.parametrize("worker_id", [None, "worker-b"], ids=["queued", "running"])
def test_failed_run_resume_active_job_can_be_cancelled(
    worker_id: str | None,
) -> None:
    name = f"m13.4.2.2-failed-resume-{worker_id or 'queued'}-cancel"
    try:
        run_id = _create_terminal_run(name, status="FAILED")
        job_id = _resume_job(run_id, worker_id=worker_id)

        with SessionLocal() as requester:
            run, job = BacktestApplicationService(requester).cancel(run_id)
            assert job is not None and job.id == job_id
            assert run.status == job.status == "CANCELLED"
            assert job.cancel_requested is True
            assert run.owner_worker_id is None
            assert run.ownership_version == 1

        with SessionLocal() as check:
            assert _checkpoint_count(check, run_id) == 0
    finally:
        _cleanup(name)


def test_resume_cancel_race_with_claim_run_is_linearized() -> None:
    cancel_wins_name = "m13.4.2.2-race-cancel-wins"
    claim_wins_name = "m13.4.2.2-race-claim-wins"
    try:
        cancel_wins_run_id = _create_terminal_run(
            cancel_wins_name, status="CANCELLED"
        )
        cancel_wins_job_id = _resume_job(
            cancel_wins_run_id, worker_id="worker-cancel-loses"
        )
        claim_started = Event()

        def claim_after_cancel_lock() -> None:
            with SessionLocal() as worker:
                claim_started.set()
                BacktestRunner(worker)._claim_run(cancel_wins_job_id)

        with SessionLocal() as cancel_db:
            cancel_db.execute(
                sa.select(JobRun)
                .where(JobRun.id == cancel_wins_job_id)
                .with_for_update()
            ).scalar_one()
            with ThreadPoolExecutor(max_workers=1) as pool:
                claim_future = pool.submit(claim_after_cancel_lock)
                assert claim_started.wait(timeout=10)
                run, job = BacktestApplicationService(cancel_db).cancel(
                    cancel_wins_run_id
                )
                assert job is not None
                assert run.status == job.status == "CANCELLED"
                with pytest.raises(BacktestOwnershipError):
                    claim_future.result(timeout=10)

        with SessionLocal() as check:
            run = check.get(PortfolioBacktestRun, cancel_wins_run_id)
            assert run is not None and run.ownership_version == 1
            assert _checkpoint_count(check, cancel_wins_run_id) == 0

        claim_wins_run_id = _create_terminal_run(
            claim_wins_name, status="CANCELLED"
        )
        claim_wins_job_id = _resume_job(
            claim_wins_run_id, worker_id="worker-claim-wins"
        )
        cancel_started = Event()

        def cancel_after_claim_lock() -> tuple[str, str, bool]:
            cancel_started.set()
            with SessionLocal() as requester:
                run, job = BacktestApplicationService(requester).cancel(
                    claim_wins_run_id
                )
                assert job is not None
                return run.status, job.status, job.cancel_requested

        with SessionLocal() as claim_db:
            claim_db.execute(
                sa.select(JobRun)
                .where(JobRun.id == claim_wins_job_id)
                .with_for_update()
            ).scalar_one()
            with ThreadPoolExecutor(max_workers=1) as pool:
                cancel_future = pool.submit(cancel_after_claim_lock)
                assert cancel_started.wait(timeout=10)
                run, job, lease = BacktestRunner(claim_db)._claim_run(
                    claim_wins_job_id
                )
                assert run.status == job.status == "RUNNING"
                assert run.ownership_version == lease.ownership_version == 2
                assert cancel_future.result(timeout=10) == (
                    "RUNNING",
                    "RUNNING",
                    True,
                )

        with SessionLocal() as boundary:
            BacktestRunner(boundary)._finish_cancelled(lease)

        with SessionLocal() as check:
            run = check.get(PortfolioBacktestRun, claim_wins_run_id)
            job = check.get(JobRun, claim_wins_job_id)
            assert run is not None and job is not None
            assert run.status == job.status == "CANCELLED"
            assert run.ownership_version == 2
            assert _checkpoint_count(check, claim_wins_run_id) == 0
    finally:
        _cleanup(cancel_wins_name)
        _cleanup(claim_wins_name)


def _create_terminal_run(name: str, *, status: str) -> uuid.UUID:
    with SessionLocal() as db:
        if db.get(TradeCalendar, _TRADE_DATE) is None:
            db.add(
                TradeCalendar(
                    cal_date=_TRADE_DATE,
                    is_open=True,
                    exchange="SSE",
                )
            )
        run = PortfolioApplicationService(db).create_backtest_definition(
            start_date=_TRADE_DATE,
            end_date=_TRADE_DATE,
            name=name,
        )
        run, job = BacktestApplicationService(db).execute(run.id)
        job.status = "RUNNING"
        job.worker_id = f"worker-{name}"
        job.heartbeat_at = datetime.now(UTC)
        db.commit()
        _, _, lease = BacktestRunner(db)._claim_run(job.id)
        if status == "CANCELLED":
            BacktestApplicationService(db).cancel(run.id)
            BacktestRunner(db)._finish_cancelled(lease)
        elif status == "FAILED":
            BacktestRunner(db)._mark_run_failed(
                lease, RuntimeError("injected first-generation failure")
            )
        else:
            raise ValueError(f"unsupported terminal status: {status}")
        db.refresh(run)
        assert run.status == status
        assert run.owner_worker_id is None
        assert run.ownership_version == 1
        return run.id


def _resume_job(run_id: uuid.UUID, *, worker_id: str | None = None) -> uuid.UUID:
    with SessionLocal() as db:
        _, job = BacktestApplicationService(db).resume(run_id)
        if worker_id is not None:
            job.status = "RUNNING"
            job.worker_id = worker_id
            job.heartbeat_at = datetime.now(UTC)
            db.commit()
        return job.id


def _checkpoint_count(db: object, run_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            sa.select(sa.func.count())
            .select_from(PortfolioBacktestCheckpoint)
            .where(PortfolioBacktestCheckpoint.run_id == run_id)
        )
        or 0
    )


def _execution_job_count(db: object, run_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            sa.select(sa.func.count())
            .select_from(JobRun)
            .where(
                JobRun.job_type == "portfolio_backtest",
                JobRun.job_metadata["portfolio_run_id"].astext == str(run_id),
            )
        )
        or 0
    )


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
