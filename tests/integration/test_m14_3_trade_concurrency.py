import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Barrier

import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.models.job import JobRun
from app.models.performance_trade import PortfolioPerformanceTradeReport
from app.services.performance.risk_application import PerformanceRiskApplicationService
from app.services.performance.trade_application import (
    PERFORMANCE_TRADE_JOB_TYPE,
    PerformanceTradeApplicationService,
    PerformanceTradeConflictError,
    PerformanceTradeOwnershipError,
)
from app.services.performance.trade_recovery import (
    PERFORMANCE_TRADE_HEARTBEAT_TIMEOUT_CODE,
    recover_stale_performance_trade_jobs,
)
from m14_3_support import cleanup_trade_case, seed_trade_case
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _running_job(
    db: Session,
    *,
    run_id: uuid.UUID,
    performance_id: uuid.UUID,
    worker_id: str,
    heartbeat_at: datetime,
) -> JobRun:
    job = JobRun(
        job_type=PERFORMANCE_TRADE_JOB_TYPE,
        status="RUNNING",
        step="claimed by worker",
        row_count=0,
        worker_id=worker_id,
        heartbeat_at=heartbeat_at,
        job_metadata={
            "portfolio_run_id": str(run_id),
            "performance_id": str(performance_id),
            "trade_version": "trade_v1",
            "stage": "running",
        },
    )
    db.add(job)
    db.flush()
    return job


def test_concurrent_trade_queue_creates_one_active_job() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2046, 1, day) for day in range(4, 11))
    with Session(engine) as db:
        case = seed_trade_case(db, dates)
        db.commit()
    barrier = Barrier(2)

    def queue_once() -> tuple[str, uuid.UUID | None]:
        with Session(engine) as db:
            barrier.wait()
            try:
                job = PerformanceTradeApplicationService(db).queue_calculation(
                    case.run_id, case.performance_id
                )
                return "queued", job.id
            except PerformanceTradeConflictError as exc:
                db.rollback()
                return "conflict", exc.job_id

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: queue_once(), range(2)))
        with Session(engine) as db:
            jobs = list(
                db.scalars(
                    select(JobRun).where(
                        JobRun.job_type == PERFORMANCE_TRADE_JOB_TYPE,
                        JobRun.job_metadata["performance_id"].as_string()
                        == str(case.performance_id),
                    )
                )
            )
        assert sorted(status for status, _job_id in results) == [
            "conflict",
            "queued",
        ]
        assert len(jobs) == 1
        assert {job_id for _status, job_id in results} == {jobs[0].id}
    finally:
        cleanup_trade_case(engine, case)


def test_trade_and_risk_queue_use_independent_locks() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2046, 2, day) for day in range(1, 8))
    with Session(engine) as db:
        case = seed_trade_case(db, dates)
        db.commit()
    barrier = Barrier(2)

    def queue_trade() -> uuid.UUID:
        with Session(engine) as db:
            barrier.wait()
            return (
                PerformanceTradeApplicationService(db)
                .queue_calculation(case.run_id, case.performance_id)
                .id
            )

    def queue_risk() -> uuid.UUID:
        with Session(engine) as db:
            barrier.wait()
            return (
                PerformanceRiskApplicationService(db)
                .queue_calculation(case.run_id, case.performance_id)
                .id
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            trade_future = executor.submit(queue_trade)
            risk_future = executor.submit(queue_risk)
            assert trade_future.result(timeout=10) != risk_future.result(timeout=10)
    finally:
        cleanup_trade_case(engine, case)


def test_trade_recovery_rechecks_fresh_heartbeat_under_lock() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2046, 3, day) for day in range(1, 8))
    now = datetime(2046, 3, 7, 12, tzinfo=UTC)
    with Session(engine) as db:
        case = seed_trade_case(db, dates)
        job = _running_job(
            db,
            run_id=case.run_id,
            performance_id=case.performance_id,
            worker_id="worker-live",
            heartbeat_at=now - timedelta(minutes=30),
        )
        db.commit()
        job_id = job.id

    def refresh_heartbeat(candidate_id: uuid.UUID) -> None:
        assert candidate_id == job_id
        with Session(engine) as refresh_db:
            current = refresh_db.get(JobRun, candidate_id)
            current.heartbeat_at = now
            refresh_db.commit()

    try:
        with Session(engine) as db:
            assert (
                recover_stale_performance_trade_jobs(
                    db,
                    timeout_minutes=15,
                    now=now,
                    before_lock_hook=refresh_heartbeat,
                )
                == 0
            )
            current = db.get(JobRun, job_id)
            assert current.status == "RUNNING"
            assert current.heartbeat_at == now
    finally:
        cleanup_trade_case(engine, case)


def test_trade_recovery_fences_old_worker_and_retry_reuses() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2046, 4, day) for day in range(1, 8))
    now = datetime(2046, 4, 7, 12, tzinfo=UTC)
    with Session(engine) as db:
        case = seed_trade_case(db, dates)
        old_job = _running_job(
            db,
            run_id=case.run_id,
            performance_id=case.performance_id,
            worker_id="worker-old",
            heartbeat_at=now - timedelta(minutes=30),
        )
        db.commit()
        old_job_id = old_job.id

    def recover_before_terminal(_lease, _artifact) -> None:
        with Session(engine) as recovery_db:
            assert (
                recover_stale_performance_trade_jobs(recovery_db, timeout_minutes=15, now=now) == 1
            )

    try:
        with Session(engine) as old_worker_db:
            old_service = PerformanceTradeApplicationService(
                old_worker_db, before_terminal_hook=recover_before_terminal
            )
            with pytest.raises(PerformanceTradeOwnershipError):
                old_service.run_job(old_job_id)
            old_worker_db.rollback()

        with Session(engine) as db:
            failed = db.get(JobRun, old_job_id)
            assert failed.status == "FAILED"
            assert failed.job_metadata["error_code"] == (PERFORMANCE_TRADE_HEARTBEAT_TIMEOUT_CODE)
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(PortfolioPerformanceTradeReport)
                    .where(PortfolioPerformanceTradeReport.performance_id == case.performance_id)
                )
                == 0
            )
            replacement = PerformanceTradeApplicationService(db).queue_calculation(
                case.run_id, case.performance_id
            )
            replacement.status = "RUNNING"
            replacement.worker_id = "worker-new"
            replacement.heartbeat_at = now
            db.commit()
            replacement_id = replacement.id

        with Session(engine) as db:
            created = PerformanceTradeApplicationService(db).run_job(replacement_id)
            artifact_id = created.report.id
            assert created.reused is False

        with Session(engine) as db:
            retry = PerformanceTradeApplicationService(db).queue_calculation(
                case.run_id, case.performance_id
            )
            retry.status = "RUNNING"
            retry.worker_id = "worker-retry"
            retry.heartbeat_at = now
            db.commit()
            retry_id = retry.id
        with Session(engine) as db:
            reused = PerformanceTradeApplicationService(db).run_job(retry_id)
            assert reused.reused is True
            assert reused.report.id == artifact_id
            assert db.get(JobRun, retry_id).status == "SUCCESS"
    finally:
        cleanup_trade_case(engine, case)
