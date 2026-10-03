import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from threading import Barrier

import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.models.job import JobRun
from app.models.market_data import TradeCalendar
from app.models.performance import PortfolioPerformanceReport
from app.models.portfolio import PortfolioBacktestRun, PortfolioNavDaily
from app.services.analysis_identity import (
    ACCOUNTING_VERSION,
    BACKTEST_ENGINE_VERSION,
    EXECUTION_VERSION,
    OPPORTUNITY_CALC_VERSION,
    PORTFOLIO_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.performance.application import (
    PERFORMANCE_JOB_TYPE,
    PerformanceApplicationService,
    PerformanceConflictError,
    PerformanceOwnershipError,
    PerformanceRunNotSuccessError,
)
from app.services.performance.recovery import (
    PERFORMANCE_HEARTBEAT_TIMEOUT_CODE,
    recover_stale_performance_jobs,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _run(
    db: Session,
    trade_date: date,
    *,
    nav: str | None = None,
    status: str = "SUCCESS",
    account_mode: str = "BACKTEST",
) -> PortfolioBacktestRun:
    settings = get_settings()
    portfolio = settings.portfolio_config.model_dump(mode="json")
    execution = settings.execution_config.model_dump(mode="json")
    accounting = settings.accounting_config.model_dump(mode="json")
    run = PortfolioBacktestRun(
        account_mode=account_mode,
        status=status,
        start_date=trade_date,
        end_date=trade_date,
        initial_cash=Decimal("1000000"),
        benchmark_code="000300.SH",
        algo_version=settings.algo_version,
        source_strategy_config_hash=analysis_strategy_hash(settings.strategy),
        opportunity_calc_version=OPPORTUNITY_CALC_VERSION,
        opportunity_config_hash=config_hash(settings.opportunity_config),
        portfolio_version=PORTFOLIO_VERSION,
        portfolio_config_hash=config_hash(portfolio),
        execution_version=EXECUTION_VERSION,
        execution_config_hash=config_hash(execution),
        accounting_version=ACCOUNTING_VERSION,
        accounting_config_hash=config_hash(accounting),
        backtest_engine_version=BACKTEST_ENGINE_VERSION,
        config_snapshot={
            "portfolio": portfolio,
            "execution": execution,
            "accounting": accounting,
        },
        result_summary={"final_nav": nav or "1"},
    )
    db.add(run)
    db.flush()
    if nav is not None:
        value = Decimal(nav)
        db.add(TradeCalendar(cal_date=trade_date, is_open=True, exchange="SSE"))
        db.add(
            PortfolioNavDaily(
                run_id=run.id,
                trade_date=trade_date,
                cash=value * Decimal("400000"),
                market_value=value * Decimal("600000"),
                total_assets=value * Decimal("1000000"),
                nav=value,
                gross_exposure=Decimal("0.6"),
                net_exposure=Decimal("0.6"),
                position_count=2,
                trading_cost=Decimal("5"),
            )
        )
    db.flush()
    return run


def _cleanup(engine, run_id: uuid.UUID, trade_date: date) -> None:
    with Session(engine) as db:
        db.execute(
            sa.delete(JobRun).where(
                JobRun.job_type == PERFORMANCE_JOB_TYPE,
                JobRun.job_metadata["portfolio_run_id"].as_string() == str(run_id),
            )
        )
        run = db.get(PortfolioBacktestRun, run_id)
        if run is not None:
            db.delete(run)
        db.execute(
            sa.delete(TradeCalendar).where(TradeCalendar.cal_date == trade_date)
        )
        db.commit()


def _running_job(
    db: Session,
    run_id: uuid.UUID,
    *,
    worker_id: str,
    heartbeat_at: datetime,
) -> JobRun:
    job = JobRun(
        job_type=PERFORMANCE_JOB_TYPE,
        status="RUNNING",
        step="claimed by worker",
        row_count=0,
        worker_id=worker_id,
        heartbeat_at=heartbeat_at,
        job_metadata={"portfolio_run_id": str(run_id)},
    )
    db.add(job)
    db.flush()
    return job


def test_concurrent_queue_creates_one_job_and_returns_same_active_job_id() -> None:
    engine = sa.create_engine(get_settings().database_url)
    trade_date = date(2042, 1, 2)
    with Session(engine) as db:
        run = _run(db, trade_date)
        db.commit()
        run_id = run.id
    barrier = Barrier(2)

    def queue_once() -> tuple[str, uuid.UUID]:
        with Session(engine) as db:
            barrier.wait()
            try:
                job = PerformanceApplicationService(db).queue_calculation(run_id)
                return "queued", job.id
            except PerformanceConflictError as exc:
                db.rollback()
                return "conflict", exc.job_id

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: queue_once(), range(2)))
        with Session(engine) as db:
            jobs = list(
                db.scalars(
                    select(JobRun).where(
                        JobRun.job_type == PERFORMANCE_JOB_TYPE,
                        JobRun.job_metadata["portfolio_run_id"].as_string()
                        == str(run_id),
                    )
                ).all()
            )
        assert sorted(status for status, _job_id in results) == ["conflict", "queued"]
        assert len(jobs) == 1
        assert {job_id for _status, job_id in results} == {jobs[0].id}
    finally:
        _cleanup(engine, run_id, trade_date)


def test_stale_recovery_preserves_artifact_and_allows_explicit_recalculation() -> None:
    engine = sa.create_engine(get_settings().database_url)
    trade_date = date(2042, 2, 3)
    now = datetime(2042, 2, 3, 12, tzinfo=UTC)
    with Session(engine) as db:
        run = _run(db, trade_date, nav="1.10")
        artifact = PerformanceApplicationService(db).calculate_now(run.id)
        stale = _running_job(
            db,
            run.id,
            worker_id="worker-a",
            heartbeat_at=now - timedelta(minutes=30),
        )
        db.commit()
        run_id, stale_id, artifact_id = run.id, stale.id, artifact.report.id

    try:
        with Session(engine) as db:
            assert recover_stale_performance_jobs(
                db, timeout_minutes=15, now=now
            ) == 1
            failed = db.get(JobRun, stale_id)
            assert failed.status == "FAILED"
            assert (
                failed.job_metadata["error_code"]
                == PERFORMANCE_HEARTBEAT_TIMEOUT_CODE
            )
            assert db.get(PortfolioPerformanceReport, artifact_id) is not None

        with Session(engine) as db:
            replacement = PerformanceApplicationService(db).queue_calculation(run_id)
            assert replacement.status == "QUEUED"
            assert replacement.id != stale_id
    finally:
        _cleanup(engine, run_id, trade_date)


def test_recovery_fresh_heartbeat_race_does_not_reclaim_live_worker() -> None:
    engine = sa.create_engine(get_settings().database_url)
    trade_date = date(2042, 3, 3)
    now = datetime(2042, 3, 3, 12, tzinfo=UTC)
    with Session(engine) as db:
        run = _run(db, trade_date)
        job = _running_job(
            db,
            run.id,
            worker_id="worker-a",
            heartbeat_at=now - timedelta(minutes=30),
        )
        db.commit()
        run_id, job_id = run.id, job.id

    def refresh_heartbeat(candidate_id: uuid.UUID) -> None:
        assert candidate_id == job_id
        with Session(engine) as refresh_db:
            current = refresh_db.get(JobRun, candidate_id)
            current.heartbeat_at = now
            refresh_db.commit()

    try:
        with Session(engine) as db:
            recovered = recover_stale_performance_jobs(
                db,
                timeout_minutes=15,
                now=now,
                before_lock_hook=refresh_heartbeat,
            )
            current = db.get(JobRun, job_id)
            assert recovered == 0
            assert current.status == "RUNNING"
            assert current.heartbeat_at == now
    finally:
        _cleanup(engine, run_id, trade_date)


def test_recovered_old_worker_is_fenced_and_new_worker_succeeds() -> None:
    engine = sa.create_engine(get_settings().database_url)
    trade_date = date(2042, 4, 1)
    now = datetime(2042, 4, 1, 12, tzinfo=UTC)
    with Session(engine) as db:
        run = _run(db, trade_date, nav="1.10")
        old_job = _running_job(
            db,
            run.id,
            worker_id="worker-a",
            heartbeat_at=now - timedelta(minutes=30),
        )
        db.commit()
        run_id, old_job_id = run.id, old_job.id

    def recover_before_terminal(_lease, _artifact) -> None:
        with Session(engine) as recovery_db:
            assert recover_stale_performance_jobs(
                recovery_db, timeout_minutes=15, now=now
            ) == 1

    try:
        with Session(engine) as old_worker_db:
            service = PerformanceApplicationService(
                old_worker_db, before_terminal_hook=recover_before_terminal
            )
            with pytest.raises(PerformanceOwnershipError):
                service.run_job(old_job_id)
            old_worker_db.rollback()

        with Session(engine) as db:
            assert db.get(JobRun, old_job_id).status == "FAILED"
            assert db.scalar(
                select(func.count()).select_from(PortfolioPerformanceReport).where(
                    PortfolioPerformanceReport.run_id == run_id
                )
            ) == 0
            new_job = PerformanceApplicationService(db).queue_calculation(run_id)
            new_job.status = "RUNNING"
            new_job.worker_id = "worker-b"
            new_job.heartbeat_at = now
            db.commit()
            new_job_id = new_job.id

        with Session(engine) as new_worker_db:
            PerformanceApplicationService(new_worker_db).run_job(new_job_id)

        with Session(engine) as db:
            assert db.get(JobRun, old_job_id).status == "FAILED"
            assert db.get(JobRun, new_job_id).status == "SUCCESS"
            assert db.scalar(
                select(func.count()).select_from(PortfolioPerformanceReport).where(
                    PortfolioPerformanceReport.run_id == run_id
                )
            ) == 1
        with Session(engine) as resumed_old_worker:
            with pytest.raises(PerformanceOwnershipError):
                PerformanceApplicationService(resumed_old_worker).run_job(old_job_id)
            resumed_old_worker.rollback()
    finally:
        _cleanup(engine, run_id, trade_date)


def test_retry_reuses_artifact_if_job_terminal_update_was_interrupted() -> None:
    engine = sa.create_engine(get_settings().database_url)
    trade_date = date(2042, 5, 2)
    now = datetime(2042, 5, 2, 12, tzinfo=UTC)
    with Session(engine) as db:
        run = _run(db, trade_date, nav="1.05")
        artifact = PerformanceApplicationService(db).calculate_now(run.id)
        db.commit()
        run_id, artifact_id = run.id, artifact.report.id

    try:
        with Session(engine) as db:
            retry_job = PerformanceApplicationService(db).queue_calculation(run_id)
            retry_job.status = "RUNNING"
            retry_job.worker_id = "worker-retry"
            retry_job.heartbeat_at = now
            db.commit()
            retry_job_id = retry_job.id
        with Session(engine) as db:
            result = PerformanceApplicationService(db).run_job(retry_job_id)
            job = db.get(JobRun, retry_job_id)
            assert result.reused is True
            assert result.report.id == artifact_id
            assert job.status == "SUCCESS"
            assert job.job_metadata["reused"] is True
    finally:
        _cleanup(engine, run_id, trade_date)


@pytest.mark.parametrize(
    ("status", "account_mode"),
    [("CREATED", "BACKTEST"), ("RUNNING", "BACKTEST"), ("SUCCESS", "PAPER")],
)
def test_queue_fails_fast_for_non_success_backtest(status, account_mode) -> None:
    engine = sa.create_engine(get_settings().database_url)
    trade_date = date(2042, 6, 3)
    with Session(engine) as db:
        run = _run(db, trade_date, status=status, account_mode=account_mode)
        db.commit()
        run_id = run.id
    try:
        with Session(engine) as db:
            with pytest.raises(PerformanceRunNotSuccessError):
                PerformanceApplicationService(db).queue_calculation(run_id)
            db.rollback()
        with Session(engine) as db:
            assert db.scalar(
                select(func.count()).select_from(JobRun).where(
                    JobRun.job_type == PERFORMANCE_JOB_TYPE,
                    JobRun.job_metadata["portfolio_run_id"].as_string()
                    == str(run_id),
                )
            ) == 0
    finally:
        _cleanup(engine, run_id, trade_date)
