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
            _assert_stale_worker_fenced(
                old_worker,
                run_id=run_id,
                job_id=old_job_id,
                worker_id="worker-old",
                ownership_version=0,
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


def test_failed_run_resume_preownership_crash_is_recovered() -> None:
    name = "m13.4.2-failed-resume-preownership"
    recovered_at = datetime.now(UTC)
    try:
        with SessionLocal() as setup:
            run, first_job, first_lease = _establish_first_lease(
                setup, name, worker_id="worker-a"
            )
            run_id = run.id
            setup.add(
                PortfolioBacktestCheckpoint(
                    run_id=run_id,
                    trade_date=_TRADE_DATE,
                    phase="START_OF_DAY",
                    phase_status="COMPLETED",
                    input_identity={"hash": "historical-input"},
                    result_identity={"hash": "historical-result"},
                    started_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                    attempt=1,
                    version=1,
                    worker_owner="worker-a",
                )
            )
            setup.commit()
            BacktestRunner(setup)._mark_run_failed(
                first_lease, RuntimeError("first generation failed")
            )
            setup.refresh(run)
            setup.refresh(first_job)
            assert run.status == first_job.status == "FAILED"
            assert run.owner_worker_id is None
            assert run.ownership_version == 1

        with SessionLocal() as resume_db:
            _, stale_job = BacktestApplicationService(resume_db).resume(run_id)
            stale_job_id = stale_job.id
            _claim_job(
                resume_db,
                stale_job,
                worker_id="worker-b",
                heartbeat_at=recovered_at - timedelta(minutes=30),
            )

        with SessionLocal() as recovery:
            assert (
                recover_stale_backtest_jobs(
                    recovery, timeout_minutes=15, now=recovered_at
                )
                == 1
            )

        with SessionLocal() as check:
            run = check.get(PortfolioBacktestRun, run_id)
            stale_job = check.get(JobRun, stale_job_id)
            checkpoints = list(
                check.execute(
                    sa.select(PortfolioBacktestCheckpoint).where(
                        PortfolioBacktestCheckpoint.run_id == run_id
                    )
                ).scalars()
            )
            assert run is not None and stale_job is not None
            assert run.status == stale_job.status == "FAILED"
            assert run.owner_worker_id is None
            assert run.ownership_version == 1
            assert run.result_summary["error_code"] == _ERROR_CODE
            assert len(checkpoints) == 1
            assert checkpoints[0].result_identity == {"hash": "historical-result"}
            response = backtest_progress(run_id, db=check)
            assert response["data"]["error_code"] == _ERROR_CODE

        with SessionLocal() as resume_db:
            _, replacement_job = BacktestApplicationService(resume_db).resume(run_id)
            replacement_job_id = replacement_job.id
            assert replacement_job_id != stale_job_id
            _claim_job(
                resume_db,
                replacement_job,
                worker_id="worker-c",
                heartbeat_at=datetime.now(UTC),
            )

        with SessionLocal() as worker_c:
            run, job, lease = BacktestRunner(worker_c)._claim_run(replacement_job_id)
            assert lease.ownership_version == 2
            assert run.status == "RUNNING"
            assert run.owner_worker_id == "worker-c"
            assert run.job_id == replacement_job_id
            assert run.ownership_version == 2
            assert job.job_metadata["ownership_version"] == 2

        with SessionLocal() as worker_b:
            _assert_stale_worker_fenced(
                worker_b,
                run_id=run_id,
                job_id=stale_job_id,
                worker_id="worker-b",
                ownership_version=1,
            )

        with SessionLocal() as check:
            run = check.get(PortfolioBacktestRun, run_id)
            checkpoint_count = check.scalar(
                sa.select(sa.func.count())
                .select_from(PortfolioBacktestCheckpoint)
                .where(PortfolioBacktestCheckpoint.run_id == run_id)
            )
            assert run is not None
            assert (run.status, run.owner_worker_id, run.ownership_version) == (
                "RUNNING",
                "worker-c",
                2,
            )
            assert checkpoint_count == 1
    finally:
        _cleanup(name)


def test_cancelled_run_resume_preownership_crash_is_recovered() -> None:
    name = "m13.4.2-cancelled-resume-preownership"
    recovered_at = datetime.now(UTC)
    try:
        with SessionLocal() as setup:
            run, _, first_lease = _establish_first_lease(
                setup, name, worker_id="worker-cancel-a"
            )
            run_id = run.id
            BacktestApplicationService(setup).cancel(run_id)
            BacktestRunner(setup)._finish_cancelled(first_lease)
            setup.refresh(run)
            assert run.status == "CANCELLED"
            assert run.owner_worker_id is None
            assert run.ownership_version == 1

        with SessionLocal() as resume_db:
            _, stale_job = BacktestApplicationService(resume_db).resume(run_id)
            stale_job_id = stale_job.id
            _claim_job(
                resume_db,
                stale_job,
                worker_id="worker-cancel-b",
                heartbeat_at=recovered_at - timedelta(minutes=30),
            )

        with SessionLocal() as recovery:
            assert (
                recover_stale_backtest_jobs(
                    recovery, timeout_minutes=15, now=recovered_at
                )
                == 1
            )

        with SessionLocal() as check:
            run = check.get(PortfolioBacktestRun, run_id)
            stale_job = check.get(JobRun, stale_job_id)
            assert run is not None and stale_job is not None
            assert run.status == stale_job.status == "FAILED"
            assert run.owner_worker_id is None
            assert run.ownership_version == 1
            assert run.result_summary["error_code"] == _ERROR_CODE

        with SessionLocal() as resume_db:
            _, replacement_job = BacktestApplicationService(resume_db).resume(run_id)
            replacement_job_id = replacement_job.id
            _claim_job(
                resume_db,
                replacement_job,
                worker_id="worker-cancel-c",
                heartbeat_at=datetime.now(UTC),
            )
            run, job, lease = BacktestRunner(resume_db)._claim_run(
                replacement_job_id
            )
            assert lease.ownership_version == 2
            assert run.ownership_version == 2
            assert run.owner_worker_id == "worker-cancel-c"
            assert job.job_metadata["ownership_version"] == 2
    finally:
        _cleanup(name)


def test_failed_resume_preownership_rechecks_fresh_heartbeat_under_job_lock() -> None:
    name = "m13.4.2-failed-resume-heartbeat-race"
    recovered_at = datetime.now(UTC)
    try:
        with SessionLocal() as setup:
            run, _, first_lease = _establish_first_lease(
                setup, name, worker_id="worker-race-a"
            )
            run_id = run.id
            BacktestRunner(setup)._mark_run_failed(
                first_lease, RuntimeError("first generation failed")
            )

        with SessionLocal() as resume_db:
            _, stale_job = BacktestApplicationService(resume_db).resume(run_id)
            stale_job_id = stale_job.id
            _claim_job(
                resume_db,
                stale_job,
                worker_id="worker-race-b",
                heartbeat_at=recovered_at - timedelta(minutes=30),
            )

        def refresh_after_discovery(_: object) -> None:
            with SessionLocal() as heartbeat:
                heartbeat.execute(
                    sa.update(JobRun)
                    .where(JobRun.id == stale_job_id)
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
            stale_job = check.get(JobRun, stale_job_id)
            assert run is not None and run.status == "FAILED"
            assert run.owner_worker_id is None and run.ownership_version == 1
            assert stale_job is not None and stale_job.status == "RUNNING"
            assert stale_job.worker_id == "worker-race-b"
    finally:
        _cleanup(name)


def _assert_stale_worker_fenced(
    db: object,
    *,
    run_id: object,
    job_id: object,
    worker_id: str,
    ownership_version: int,
) -> None:
    stale_lease = BacktestExecutionLease(
        run_id=run_id,
        job_id=job_id,
        worker_id=worker_id,
        ownership_version=ownership_version,
    )
    stale_runner = BacktestRunner(db)
    with pytest.raises(BacktestOwnershipError):
        stale_runner._claim_run(job_id)
    db.rollback()
    with pytest.raises(BacktestOwnershipError):
        stale_runner._run_phase(stale_lease, _TRADE_DATE, "START_OF_DAY")
    db.rollback()
    with pytest.raises(BacktestOwnershipError):
        stale_runner._finish_success(stale_lease)
    db.rollback()
    with pytest.raises(BacktestOwnershipError):
        stale_runner._finish_cancelled(stale_lease)
    db.rollback()
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


def _establish_first_lease(
    db: object, name: str, *, worker_id: str
) -> tuple[PortfolioBacktestRun, JobRun, BacktestExecutionLease]:
    run, job = _pre_ownership_claim(
        db,
        name,
        worker_id=worker_id,
        heartbeat_at=datetime.now(UTC),
    )
    return BacktestRunner(db)._claim_run(job.id)


def _claim_job(
    db: object,
    job: JobRun,
    *,
    worker_id: str,
    heartbeat_at: datetime,
) -> None:
    job.status = "RUNNING"
    job.worker_id = worker_id
    job.heartbeat_at = heartbeat_at
    db.commit()


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
    _claim_job(db, job, worker_id=worker_id, heartbeat_at=heartbeat_at)
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
