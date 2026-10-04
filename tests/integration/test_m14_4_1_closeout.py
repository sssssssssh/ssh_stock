import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from threading import Barrier

import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.models.job import JobRun
from app.models.market_data import IndexDaily, TradeCalendar
from app.models.performance import PortfolioPerformanceDaily, PortfolioPerformanceReport
from app.models.performance_period import (
    PortfolioPerformancePeriod,
    PortfolioPerformancePeriodReport,
)
from app.models.performance_risk import (
    PortfolioPerformanceRiskDaily,
    PortfolioPerformanceRiskReport,
)
from app.models.performance_trade import (
    PortfolioPerformanceTradeDaily,
    PortfolioPerformanceTradeEpisode,
    PortfolioPerformanceTradeReport,
)
from app.models.portfolio import PortfolioBacktestRun
from app.services.performance.analytics_bundle import (
    AnalyticsArtifactBundleResolver,
    AnalyticsBundleError,
)
from app.services.performance.analytics_read import AnalyticsReadApplicationService
from app.services.performance.analytics_series import (
    AnalyticsSeriesError,
    AnalyticsSeriesReadApplicationService,
)
from app.services.performance.period_application import (
    PERFORMANCE_PERIOD_JOB_TYPE,
    PerformancePeriodApplicationService,
    PerformancePeriodConflictError,
    PerformancePeriodOwnershipError,
)
from app.services.performance.period_recovery import (
    PERIOD_HEARTBEAT_TIMEOUT_CODE,
    recover_stale_performance_period_jobs,
)
from app.services.performance.trade_application import PerformanceTradeApplicationService
from m14_4_support import AnalyticsCase, seed_analytics_case
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def test_series_pages_all_1200_persisted_rows_and_fails_closed_on_date_gap() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2054, 1, 1) + timedelta(days=index) for index in range(1200))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            case = seed_analytics_case(db, dates[:7])
            _extend_series(db, case, dates)
            service = AnalyticsSeriesReadApplicationService(db)
            pages = [
                service.page(
                    case.run_id,
                    performance_id=case.performance_id,
                    risk_id=case.risk_id,
                    trade_id=case.trade_id,
                    period_id=None,
                    limit=500,
                    offset=offset,
                )
                for offset in (0, 500, 1000)
            ]
            rows = [row for page in pages for row in page.rows]
            assert [len(page.rows) for page in pages] == [500, 500, 200]
            assert all(page.meta.total == 1200 for page in pages)
            assert len(rows) == 1200
            assert [row.trade_date for row in rows] == list(dates)
            assert rows[-1].strategy_nav == Decimal("1.11990000")
            assert rows[-1].benchmark_nav == Decimal("1.059950000000")

            missing = db.scalar(
                select(PortfolioPerformanceRiskDaily).where(
                    PortfolioPerformanceRiskDaily.risk_id == case.risk_id,
                    PortfolioPerformanceRiskDaily.trade_date == dates[700],
                )
            )
            db.delete(missing)
            db.flush()
            with pytest.raises(AnalyticsSeriesError):
                service.page(
                    case.run_id,
                    performance_id=case.performance_id,
                    risk_id=case.risk_id,
                    trade_id=case.trade_id,
                    period_id=None,
                    limit=500,
                    offset=500,
                )
        transaction.rollback()


def test_summary_bundle_remains_pinned_after_new_risk_trade_and_period() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2058, 1, day) for day in range(1, 8))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            case = seed_analytics_case(db, dates)
            first_period = PerformancePeriodApplicationService(db).calculate_now(
                case.run_id,
                performance_id=case.performance_id,
                risk_id=case.risk_id,
                trade_id=case.trade_id,
            ).report
            pinned = AnalyticsReadApplicationService(db).summary(case.run_id)
            assert pinned.identity.risk_id == case.risk_id
            assert pinned.identity.trade_id == case.trade_id
            assert pinned.identity.period_id == first_period.id

            risk_2, trade_2 = _clone_risk_and_trade_generation(db, case)
            period_2 = PerformancePeriodApplicationService(db).calculate_now(
                case.run_id,
                performance_id=case.performance_id,
                risk_id=risk_2,
                trade_id=trade_2,
            ).report
            latest = AnalyticsReadApplicationService(db).summary(case.run_id)
            assert latest.identity.risk_id == risk_2
            assert latest.identity.trade_id == trade_2
            assert latest.identity.period_id == period_2.id

            series = AnalyticsSeriesReadApplicationService(db).page(
                case.run_id,
                performance_id=pinned.identity.performance_id,
                risk_id=pinned.identity.risk_id,
                trade_id=pinned.identity.trade_id,
                period_id=pinned.identity.period_id,
                limit=500,
                offset=0,
            )
            episode_report, _, _ = PerformanceTradeApplicationService(db).episode_page(
                case.run_id,
                performance_id=pinned.identity.performance_id,
                trade_id=pinned.identity.trade_id,
                status=None,
                ts_code=None,
                classification=None,
                limit=500,
                offset=0,
            )
            period_report, _, _ = PerformancePeriodApplicationService(db).page(
                case.run_id,
                performance_id=pinned.identity.performance_id,
                risk_id=pinned.identity.risk_id,
                trade_id=pinned.identity.trade_id,
                period_id=pinned.identity.period_id,
                period_type=None,
                limit=500,
                offset=0,
            )
            assert series.meta.risk_id == case.risk_id
            assert series.meta.trade_id == case.trade_id
            assert series.meta.period_id == first_period.id
            assert episode_report.id == case.trade_id
            assert period_report.id == first_period.id
        transaction.rollback()


def test_explicit_bundle_ids_fail_closed_across_owners() -> None:
    engine = sa.create_engine(get_settings().database_url)
    first_dates = tuple(date(2059, 1, day) for day in range(1, 8))
    second_dates = tuple(date(2059, 2, day) for day in range(1, 8))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            first = seed_analytics_case(db, first_dates)
            second = seed_analytics_case(db, second_dates)
            second_period = PerformancePeriodApplicationService(db).calculate_now(
                second.run_id,
                performance_id=second.performance_id,
                risk_id=second.risk_id,
                trade_id=second.trade_id,
            ).report
            resolver = AnalyticsArtifactBundleResolver(db)
            for requested in (
                {"risk_id": second.risk_id, "trade_id": first.trade_id},
                {"risk_id": first.risk_id, "trade_id": second.trade_id},
                {
                    "risk_id": first.risk_id,
                    "trade_id": first.trade_id,
                    "period_id": second_period.id,
                },
            ):
                with pytest.raises(AnalyticsBundleError) as exc_info:
                    resolver.resolve(
                        first.run_id,
                        performance_id=first.performance_id,
                        **requested,
                    )
                assert exc_info.value.code == "ANALYTICS_ARTIFACT_BUNDLE_MISMATCH"
        transaction.rollback()


def test_period_concurrent_queue_uses_two_sessions_and_one_active_job() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2060, 1, day) for day in range(1, 8))
    with Session(engine) as db:
        case = seed_analytics_case(db, dates)
        db.commit()
    barrier = Barrier(2)

    def queue_once() -> tuple[str, uuid.UUID | None]:
        with Session(engine) as db:
            barrier.wait()
            try:
                job, _ = PerformancePeriodApplicationService(db).queue_calculation(
                    case.run_id,
                    performance_id=case.performance_id,
                    risk_id=case.risk_id,
                    trade_id=case.trade_id,
                )
                return "queued", job.id
            except PerformancePeriodConflictError as exc:
                db.rollback()
                return "conflict", exc.job_id

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: queue_once(), range(2)))
        with Session(engine) as db:
            jobs = _period_jobs(db, case)
        assert sorted(status for status, _ in results) == ["conflict", "queued"]
        assert len(jobs) == 1
        assert {job_id for _, job_id in results} == {jobs[0].id}
    finally:
        _cleanup_case(engine, case, dates)


def test_period_recovery_fresh_heartbeat_race_preserves_live_worker() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2060, 2, day) for day in range(1, 8))
    now = datetime(2060, 2, 7, 12, tzinfo=UTC)
    with Session(engine) as db:
        case = seed_analytics_case(db, dates)
        job = _running_period_job(
            db, case, worker_id="worker-live", heartbeat_at=now - timedelta(minutes=30)
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
            assert recover_stale_performance_period_jobs(
                db,
                timeout_minutes=15,
                now=now,
                before_lock_hook=refresh_heartbeat,
            ) == 0
            current = db.get(JobRun, job_id)
            assert current.status == "RUNNING"
            assert current.heartbeat_at == now
    finally:
        _cleanup_case(engine, case, dates)


def test_period_midflight_recovery_fences_old_worker_and_replacement_succeeds() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2060, 3, day) for day in range(1, 8))
    now = datetime(2060, 3, 7, 12, tzinfo=UTC)
    with Session(engine) as db:
        case = seed_analytics_case(db, dates)
        old_job = _running_period_job(
            db, case, worker_id="worker-old", heartbeat_at=now - timedelta(minutes=30)
        )
        db.commit()
        old_job_id = old_job.id

    def recover_before_terminal(_lease, _artifact) -> None:
        with Session(engine) as recovery_db:
            assert recover_stale_performance_period_jobs(
                recovery_db, timeout_minutes=15, now=now
            ) == 1

    try:
        with Session(engine) as old_worker_db:
            service = PerformancePeriodApplicationService(
                old_worker_db, before_terminal_hook=recover_before_terminal
            )
            with pytest.raises(PerformancePeriodOwnershipError):
                service.run_job(old_job_id)
            old_worker_db.rollback()

        with Session(engine) as db:
            failed = db.get(JobRun, old_job_id)
            assert failed.status == "FAILED"
            assert failed.finished_at is not None
            assert failed.job_metadata["stage"] == "failed"
            assert failed.job_metadata["error_code"] == PERIOD_HEARTBEAT_TIMEOUT_CODE
            assert _period_report_count(db, case) == 0
            assert _period_row_count(db, case) == 0
            replacement, _ = PerformancePeriodApplicationService(db).queue_calculation(
                case.run_id,
                performance_id=case.performance_id,
                risk_id=case.risk_id,
                trade_id=case.trade_id,
            )
            replacement.status = "RUNNING"
            replacement.worker_id = "worker-new"
            replacement.heartbeat_at = now
            db.commit()
            replacement_id = replacement.id

        with Session(engine) as db:
            created = PerformancePeriodApplicationService(db).run_job(replacement_id)
            assert created.reused is False
            assert db.get(JobRun, replacement_id).status == "SUCCESS"
            assert db.get(JobRun, old_job_id).status == "FAILED"
            assert _period_report_count(db, case) == 1
            assert _period_row_count(db, case) > 0
    finally:
        _cleanup_case(engine, case, dates)


def _extend_series(db: Session, case: AnalyticsCase, dates: tuple[date, ...]) -> None:
    performance = db.get(PortfolioPerformanceReport, case.performance_id)
    risk = db.get(PortfolioPerformanceRiskReport, case.risk_id)
    run = db.get(PortfolioBacktestRun, case.run_id)
    for index, trade_date in enumerate(dates[7:], start=7):
        strategy_nav = Decimal("1") + Decimal(index) / Decimal("10000")
        benchmark_nav = Decimal("1") + Decimal(index) / Decimal("20000")
        db.add(
            PortfolioPerformanceDaily(
                performance_id=case.performance_id,
                run_id=case.run_id,
                trade_date=trade_date,
                nav=strategy_nav,
                daily_return=Decimal("0.0001"),
                cumulative_return=strategy_nav - Decimal("1"),
                running_peak_nav=strategy_nav,
                drawdown=Decimal("0"),
                drawdown_duration_days=0,
                cash_ratio=Decimal("1"),
                gross_exposure=Decimal("0"),
                net_exposure=Decimal("0"),
                position_count=0,
                trading_cost=Decimal("0"),
            )
        )
        db.add(
            PortfolioPerformanceRiskDaily(
                risk_id=case.risk_id,
                performance_id=case.performance_id,
                run_id=case.run_id,
                trade_date=trade_date,
                benchmark_reference_close=Decimal("100"),
                benchmark_close=Decimal("100"),
                benchmark_daily_return=Decimal("0.00005"),
                benchmark_nav=benchmark_nav,
                active_return=Decimal("0.00005"),
                relative_nav=strategy_nav / benchmark_nav,
                excess_cumulative_return=(strategy_nav / benchmark_nav) - Decimal("1"),
            )
        )
    performance.trade_days = len(dates)
    performance.end_date = dates[-1]
    performance.final_nav = Decimal("1.1199")
    performance.cumulative_return = Decimal("0.1199")
    risk.trade_days = len(dates)
    risk.end_date = dates[-1]
    run.end_date = dates[-1]
    db.flush()


def _clone_risk_and_trade_generation(
    db: Session, case: AnalyticsCase
) -> tuple[uuid.UUID, uuid.UUID]:
    calculated_at = datetime.now(UTC) + timedelta(minutes=1)
    risk_1 = db.get(PortfolioPerformanceRiskReport, case.risk_id)
    risk_2 = _clone_row(
        risk_1,
        id=uuid.uuid4(),
        benchmark_source_hash="b" * 64,
        risk_source_hash="r" * 64,
        calculated_at=calculated_at,
    )
    db.add(risk_2)
    db.flush()
    risk_rows = list(
        db.scalars(
            select(PortfolioPerformanceRiskDaily).where(
                PortfolioPerformanceRiskDaily.risk_id == case.risk_id
            )
        )
    )
    db.add_all([_clone_row(row, risk_id=risk_2.id) for row in risk_rows])

    trade_1 = db.get(PortfolioPerformanceTradeReport, case.trade_id)
    trade_2 = _clone_row(
        trade_1,
        id=uuid.uuid4(),
        trade_source_hash="t" * 64,
        calculated_at=calculated_at,
    )
    db.add(trade_2)
    db.flush()
    trade_daily = list(
        db.scalars(
            select(PortfolioPerformanceTradeDaily).where(
                PortfolioPerformanceTradeDaily.trade_id == case.trade_id
            )
        )
    )
    episodes = list(
        db.scalars(
            select(PortfolioPerformanceTradeEpisode).where(
                PortfolioPerformanceTradeEpisode.trade_id == case.trade_id
            )
        )
    )
    db.add_all([_clone_row(row, trade_id=trade_2.id) for row in trade_daily])
    db.add_all([_clone_row(row, trade_id=trade_2.id) for row in episodes])
    db.flush()
    return risk_2.id, trade_2.id


def _clone_row(row, **changes):
    ignored = {"created_at", "updated_at"}
    values = {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if column.name not in ignored
    }
    values.update(changes)
    return type(row)(**values)


def _running_period_job(
    db: Session,
    case: AnalyticsCase,
    *,
    worker_id: str,
    heartbeat_at: datetime,
) -> JobRun:
    job = JobRun(
        job_type=PERFORMANCE_PERIOD_JOB_TYPE,
        status="RUNNING",
        step="claimed by worker",
        row_count=0,
        worker_id=worker_id,
        heartbeat_at=heartbeat_at,
        job_metadata={
            "portfolio_run_id": str(case.run_id),
            "performance_id": str(case.performance_id),
            "risk_id": str(case.risk_id),
            "trade_id": str(case.trade_id),
            "period_version": "period_v1",
            "stage": "running",
        },
    )
    db.add(job)
    db.flush()
    return job


def _period_jobs(db: Session, case: AnalyticsCase) -> list[JobRun]:
    return list(
        db.scalars(
            select(JobRun).where(
                JobRun.job_type == PERFORMANCE_PERIOD_JOB_TYPE,
                JobRun.job_metadata["performance_id"].as_string()
                == str(case.performance_id),
                JobRun.job_metadata["risk_id"].as_string() == str(case.risk_id),
                JobRun.job_metadata["trade_id"].as_string() == str(case.trade_id),
            )
        )
    )


def _period_report_count(db: Session, case: AnalyticsCase) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(PortfolioPerformancePeriodReport)
            .where(PortfolioPerformancePeriodReport.run_id == case.run_id)
        )
        or 0
    )


def _period_row_count(db: Session, case: AnalyticsCase) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(PortfolioPerformancePeriod)
            .where(PortfolioPerformancePeriod.run_id == case.run_id)
        )
        or 0
    )


def _cleanup_case(
    engine: sa.Engine, case: AnalyticsCase, dates: tuple[date, ...]
) -> None:
    with Session(engine) as db:
        db.execute(
            sa.delete(JobRun).where(
                JobRun.job_type == PERFORMANCE_PERIOD_JOB_TYPE,
                JobRun.job_metadata["performance_id"].as_string()
                == str(case.performance_id),
            )
        )
        run = db.get(PortfolioBacktestRun, case.run_id)
        if run is not None:
            db.delete(run)
        db.execute(
            sa.delete(IndexDaily).where(
                IndexDaily.trade_date.in_(dates),
                IndexDaily.ts_code == "000300.SH",
            )
        )
        db.execute(sa.delete(TradeCalendar).where(TradeCalendar.cal_date.in_(dates)))
        db.commit()
