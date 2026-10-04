from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.models.job import JobRun
from app.models.performance_period import (
    PortfolioPerformancePeriod,
    PortfolioPerformancePeriodReport,
)
from app.models.performance_risk import PortfolioPerformanceRiskDaily
from app.services.performance.analytics_bundle import AnalyticsArtifactBundleResolver
from app.services.performance.analytics_compare import (
    AnalyticsCompareApplicationService,
    AnalyticsCompareError,
    AnalyticsCompareSelection,
)
from app.services.performance.analytics_read import AnalyticsReadApplicationService
from app.services.performance.period_application import (
    PerformancePeriodApplicationService,
    PerformancePeriodConflictError,
    PerformancePeriodOwnershipError,
)
from app.services.performance.period_recovery import recover_stale_performance_period_jobs
from app.services.performance.period_source import PerformancePeriodSourceError
from m14_4_support import seed_analytics_case
from sqlalchemy import func, select
from sqlalchemy.orm import Session

DATES = (
    date(2051, 12, 29),
    date(2051, 12, 30),
    date(2051, 12, 31),
    date(2052, 1, 2),
    date(2052, 1, 3),
    date(2052, 1, 4),
    date(2052, 1, 5),
)


def test_period_e2e_persists_month_year_reuses_and_context_is_bounded() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            case = seed_analytics_case(db, DATES)
            service = PerformancePeriodApplicationService(db)
            first = service.calculate_now(
                case.run_id,
                performance_id=case.performance_id,
                risk_id=case.risk_id,
                trade_id=case.trade_id,
            )
            second = service.calculate_now(
                case.run_id,
                performance_id=case.performance_id,
                risk_id=case.risk_id,
                trade_id=case.trade_id,
            )
            rows = list(
                db.scalars(
                    select(PortfolioPerformancePeriod)
                    .where(PortfolioPerformancePeriod.period_id == first.report.id)
                    .order_by(
                        PortfolioPerformancePeriod.period_type,
                        PortfolioPerformancePeriod.period_key,
                    )
                )
            )
            assert first.reused is False
            assert second.reused is True
            assert second.report.id == first.report.id
            assert first.report.month_count == 2
            assert first.report.year_count == 2
            assert len(rows) == 4
            january = next(row for row in rows if row.period_key == "2052-01")
            assert january.trade_days == 4
            assert january.closed_episode_count == 2
            assert january.closed_realized_pnl == Decimal("44.000000000000000000")
            context = AnalyticsReadApplicationService(db).context(case.run_id)
            assert context.identity.period_id == first.report.id
            assert len(context.month_periods) <= 12
            payload = context.model_dump(mode="json")
            assert "fills" not in payload
            assert "episodes" not in payload
        transaction.rollback()


def test_period_date_mismatch_fails_without_partial_artifact() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2052, 2, day) for day in range(1, 8))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            case = seed_analytics_case(db, dates)
            row = db.scalar(
                select(PortfolioPerformanceRiskDaily)
                .where(PortfolioPerformanceRiskDaily.risk_id == case.risk_id)
                .limit(1)
            )
            db.delete(row)
            db.flush()
            with pytest.raises(PerformancePeriodSourceError) as exc_info:
                PerformancePeriodApplicationService(db).calculate_now(
                    case.run_id,
                    performance_id=case.performance_id,
                    risk_id=case.risk_id,
                    trade_id=case.trade_id,
                )
            assert exc_info.value.code == "PERIOD_SOURCE_DATE_MISMATCH"
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(PortfolioPerformancePeriodReport)
                    .where(PortfolioPerformancePeriodReport.run_id == case.run_id)
                )
                == 0
            )
        transaction.rollback()


def test_bundle_latest_and_compare_preserve_request_order_then_fail_closed() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2052, 3, day) for day in range(1, 8))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            first = seed_analytics_case(db, dates)
            second = seed_analytics_case(db, dates)
            resolved = AnalyticsArtifactBundleResolver(db).resolve(first.run_id)
            assert resolved.performance.id == first.performance_id
            result = AnalyticsCompareApplicationService(db).compare(
                [
                    AnalyticsCompareSelection(second.run_id),
                    AnalyticsCompareSelection(first.run_id),
                ]
            )
            assert [row["identity"]["run_id"] for row in result["items"]] == [
                str(second.run_id),
                str(first.run_id),
            ]
            resolved_second = AnalyticsArtifactBundleResolver(db).resolve(second.run_id)
            resolved_second.risk.benchmark_code = "000905.SH"
            db.flush()
            with pytest.raises(AnalyticsCompareError) as exc_info:
                AnalyticsCompareApplicationService(db).compare(
                    [
                        AnalyticsCompareSelection(first.run_id),
                        AnalyticsCompareSelection(second.run_id),
                    ]
                )
            assert exc_info.value.code == "ANALYTICS_COMPARE_INCOMPATIBLE"
            assert "benchmark_code" in exc_info.value.mismatch_fields
        transaction.rollback()


def test_database_rejects_cross_owner_period_row() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2052, 4, day) for day in range(1, 8))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            first = seed_analytics_case(db, dates)
            second = seed_analytics_case(db, dates)
            artifact = PerformancePeriodApplicationService(db).calculate_now(
                first.run_id,
                performance_id=first.performance_id,
                risk_id=first.risk_id,
                trade_id=first.trade_id,
            )
            row = db.scalar(
                select(PortfolioPerformancePeriod)
                .where(PortfolioPerformancePeriod.period_id == artifact.report.id)
                .limit(1)
            )
            with pytest.raises(sa.exc.IntegrityError):
                with db.begin_nested():
                    db.expunge(row)
                    row.performance_id = second.performance_id
                    db.add(row)
                    db.flush()
        transaction.rollback()


def test_period_active_job_recovery_and_old_worker_fencing() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2052, 5, day) for day in range(1, 8))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            case = seed_analytics_case(db, dates)
            service = PerformancePeriodApplicationService(db)
            job, bundle = service.queue_calculation(case.run_id)
            assert bundle.performance.id == case.performance_id
            with pytest.raises(PerformancePeriodConflictError):
                service.queue_calculation(case.run_id)

            running = db.get(JobRun, job.id)
            running.status = "RUNNING"
            running.worker_id = "old-worker"
            now = datetime.now(UTC)
            running.heartbeat_at = now - timedelta(minutes=30)
            db.commit()
            assert recover_stale_performance_period_jobs(
                db, timeout_minutes=15, now=now
            ) == 1
            db.expire_all()
            assert db.get(JobRun, job.id).status == "FAILED"
            with pytest.raises(PerformancePeriodOwnershipError):
                service.run_job(job.id)
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(PortfolioPerformancePeriodReport)
                    .where(PortfolioPerformancePeriodReport.run_id == case.run_id)
                )
                == 0
            )
        transaction.rollback()
