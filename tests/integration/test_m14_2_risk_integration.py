from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.core.db import get_db
from app.main import app
from app.models.job import JobRun
from app.models.market_data import IndexDaily
from app.models.performance_risk import (
    PortfolioPerformanceRiskDaily,
    PortfolioPerformanceRiskReport,
)
from app.repositories.performance_risk import PerformanceRiskRepository
from app.services.auth.dependencies import require_authenticated_user
from app.services.job_worker import execute_claimed_job
from app.services.performance.risk_application import PerformanceRiskApplicationService
from fastapi.testclient import TestClient
from m14_2_support import cleanup_risk_case, seed_risk_case
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def test_risk_artifact_is_idempotent_and_benchmark_revision_is_versioned() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = (date(2043, 1, 4), date(2043, 1, 5), date(2043, 1, 6))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            case = seed_risk_case(
                db,
                dates,
                ("1.01", "1.00", "1.04"),
                ("101", "102", "103"),
                benchmark_code="M142IDEMP",
            )
            service = PerformanceRiskApplicationService(db)
            first = service.calculate_now(case.run_id, case.performance_id)
            second = service.calculate_now(case.run_id, case.performance_id)
            old_id = first.report.id
            old_hash = first.report.benchmark_source_hash
            old_close = db.scalar(
                select(PortfolioPerformanceRiskDaily.benchmark_close).where(
                    PortfolioPerformanceRiskDaily.risk_id == old_id,
                    PortfolioPerformanceRiskDaily.trade_date == dates[1],
                )
            )

            assert first.reused is False
            assert second.reused is True
            assert second.report.id == old_id

            day_two = db.get(IndexDaily, (dates[1], case.benchmark_code))
            day_three = db.get(IndexDaily, (dates[2], case.benchmark_code))
            day_two.close = 104.0
            day_three.pre_close = 104.0
            db.flush()
            revised = service.calculate_now(case.run_id, case.performance_id)

            assert revised.reused is False
            assert revised.report.id != old_id
            assert revised.report.benchmark_source_hash != old_hash
            assert db.scalar(
                select(func.count())
                .select_from(PortfolioPerformanceRiskReport)
                .where(
                    PortfolioPerformanceRiskReport.performance_id
                    == case.performance_id
                )
            ) == 2
            assert db.scalar(
                select(PortfolioPerformanceRiskDaily.benchmark_close).where(
                    PortfolioPerformanceRiskDaily.risk_id == old_id,
                    PortfolioPerformanceRiskDaily.trade_date == dates[1],
                )
            ) == old_close
        transaction.rollback()


def test_risk_report_and_daily_are_atomic_on_persistence_failure() -> None:
    class FailingRepository(PerformanceRiskRepository):
        def add_daily(self, rows):
            raise RuntimeError("injected risk daily persistence failure")

    engine = sa.create_engine(get_settings().database_url)
    dates = (date(2043, 2, 1), date(2043, 2, 2))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            case = seed_risk_case(
                db,
                dates,
                ("1.00", "1.02"),
                ("100", "101"),
                benchmark_code="M142ATOMIC",
            )
            savepoint = db.begin_nested()
            service = PerformanceRiskApplicationService(
                db, repository=FailingRepository(db)
            )
            with pytest.raises(RuntimeError, match="injected"):
                service.calculate_now(case.run_id, case.performance_id)
            savepoint.rollback()

            assert db.scalar(
                select(func.count())
                .select_from(PortfolioPerformanceRiskReport)
                .where(
                    PortfolioPerformanceRiskReport.performance_id
                    == case.performance_id
                )
            ) == 0
            assert db.scalar(
                select(func.count()).select_from(PortfolioPerformanceRiskDaily)
            ) == 0
        transaction.rollback()


def _empty_risk_report(
    source: PortfolioPerformanceRiskReport, identity_suffix: str
) -> PortfolioPerformanceRiskReport:
    return PortfolioPerformanceRiskReport(
        performance_id=source.performance_id,
        run_id=source.run_id,
        risk_version=source.risk_version,
        risk_config_hash=source.risk_config_hash,
        benchmark_code=source.benchmark_code,
        benchmark_source_hash=identity_suffix.rjust(64, "0"),
        risk_source_hash=identity_suffix.rjust(64, "f"),
        status="SUCCESS",
        start_date=source.start_date,
        end_date=source.end_date,
        trade_days=source.trade_days,
        risk_free_rate_annual=source.risk_free_rate_annual,
        benchmark_initial_nav=source.benchmark_initial_nav,
        benchmark_final_nav=source.benchmark_final_nav,
        benchmark_cumulative_return=source.benchmark_cumulative_return,
        benchmark_annualized_return=source.benchmark_annualized_return,
        excess_cumulative_return=source.excess_cumulative_return,
        relative_nav_final=source.relative_nav_final,
        strategy_annualized_volatility=source.strategy_annualized_volatility,
        benchmark_annualized_volatility=source.benchmark_annualized_volatility,
        downside_deviation_annualized=source.downside_deviation_annualized,
        sharpe_ratio=source.sharpe_ratio,
        sortino_ratio=source.sortino_ratio,
        calmar_ratio=source.calmar_ratio,
        tracking_error=source.tracking_error,
        information_ratio=source.information_ratio,
        alpha_daily=source.alpha_daily,
        alpha_annualized=source.alpha_annualized,
        beta=source.beta,
        correlation=source.correlation,
        warnings=list(source.warnings),
        result_summary=dict(source.result_summary),
    )


def test_database_rejects_cross_owner_and_missing_base_date_daily_rows() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates_a = (date(2043, 3, 1), date(2043, 3, 2))
    dates_b = (date(2043, 3, 3), date(2043, 3, 4))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            case_a = seed_risk_case(
                db,
                dates_a,
                ("1", "1.01"),
                ("101", "102"),
                benchmark_code="M142FKA",
            )
            case_b = seed_risk_case(
                db,
                dates_b,
                ("1", "0.99"),
                ("99", "98"),
                benchmark_code="M142FKB",
            )
            source = PerformanceRiskApplicationService(db).calculate_now(
                case_a.run_id, case_a.performance_id
            ).report
            empty = _empty_risk_report(source, "1")
            db.add(empty)
            db.flush()

            invalid_owners = (
                (case_a.performance_id, case_b.run_id, dates_a[0]),
                (case_b.performance_id, case_a.run_id, dates_b[0]),
                (case_a.performance_id, case_a.run_id, date(2043, 3, 9)),
            )
            for performance_id, run_id, trade_date in invalid_owners:
                savepoint = db.begin_nested()
                db.add(
                    PortfolioPerformanceRiskDaily(
                        risk_id=empty.id,
                        performance_id=performance_id,
                        run_id=run_id,
                        trade_date=trade_date,
                        benchmark_reference_close=Decimal("100"),
                        benchmark_close=Decimal("101"),
                        benchmark_daily_return=Decimal("0.01"),
                        benchmark_nav=Decimal("1.01"),
                        active_return=Decimal("0"),
                        relative_nav=Decimal("1"),
                        excess_cumulative_return=Decimal("0"),
                    )
                )
                with pytest.raises(sa.exc.IntegrityError):
                    db.flush()
                savepoint.rollback()
        transaction.rollback()


@pytest.mark.parametrize(
    ("suffix", "mutation", "expected_code"),
    [
        ("MISS", "missing", "BENCHMARK_SOURCE_INCOMPLETE"),
        ("NULL", "first_pre_close_missing", "BENCHMARK_SOURCE_INVALID"),
        ("CONT", "continuity", "BENCHMARK_PRE_CLOSE_MISMATCH"),
    ],
)
def test_invalid_benchmark_source_fails_job_without_artifact(
    suffix: str, mutation: str, expected_code: str
) -> None:
    engine = sa.create_engine(get_settings().database_url)
    offset = {"MISS": 1, "NULL": 4, "CONT": 7}[suffix]
    dates = (date(2043, 4, offset), date(2043, 4, offset + 1))
    with Session(engine) as db:
        case = seed_risk_case(
            db,
            dates,
            ("1", "1.01"),
            ("101", "102"),
            benchmark_code=f"M142{suffix}",
        )
        if mutation == "missing":
            db.delete(db.get(IndexDaily, (dates[1], case.benchmark_code)))
        elif mutation == "first_pre_close_missing":
            db.get(IndexDaily, (dates[0], case.benchmark_code)).pre_close = None
        else:
            db.get(IndexDaily, (dates[1], case.benchmark_code)).pre_close = 999.0
        job = PerformanceRiskApplicationService(db).queue_calculation(
            case.run_id, case.performance_id
        )
        job.status = "RUNNING"
        job.worker_id = "risk-test-worker"
        job.heartbeat_at = datetime.now(UTC)
        db.commit()
        job_id = job.id

    try:
        with Session(engine) as db:
            execute_claimed_job(db, job_id)
        with Session(engine) as db:
            failed = db.get(JobRun, job_id)
            assert failed.status == "FAILED"
            assert failed.job_metadata["error_code"] == expected_code
            assert db.scalar(
                select(func.count())
                .select_from(PortfolioPerformanceRiskReport)
                .where(
                    PortfolioPerformanceRiskReport.performance_id
                    == case.performance_id
                )
            ) == 0
    finally:
        cleanup_risk_case(engine, case)


def test_postgresql_backed_risk_api_auth_calculate_report_and_pagination() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = (date(2043, 5, 3), date(2043, 5, 4), date(2043, 5, 5))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            case = seed_risk_case(
                db,
                dates,
                ("1", "1.02", "1.01"),
                ("101", "100", "103"),
                benchmark_code="M142API",
            )
            PerformanceRiskApplicationService(db).calculate_now(
                case.run_id, case.performance_id
            )
            client = TestClient(app)
            app.dependency_overrides[require_authenticated_user] = (
                lambda: SimpleNamespace(username="risk-api-test")
            )
            app.dependency_overrides[get_db] = lambda: db
            try:
                queued = client.post(
                    f"/api/v1/portfolio/backtests/{case.run_id}"
                    "/performance/risk/calculate",
                    json={"performance_id": str(case.performance_id)},
                )
                report = client.get(
                    f"/api/v1/portfolio/backtests/{case.run_id}/performance/risk",
                    params={"performance_id": str(case.performance_id)},
                )
                daily = client.get(
                    f"/api/v1/portfolio/backtests/{case.run_id}"
                    "/performance/risk/daily",
                    params={
                        "performance_id": str(case.performance_id),
                        "limit": 1,
                        "offset": 1,
                    },
                )
            finally:
                app.dependency_overrides.clear()

            assert queued.status_code == 202
            assert queued.json()["data"]["risk_version"] == "risk_v1"
            assert report.status_code == 200
            assert report.json()["data"]["benchmark_code"] == "M142API"
            assert daily.status_code == 200
            assert len(daily.json()["data"]) == 1
            assert daily.json()["meta"]["total"] == 3
            assert daily.json()["meta"]["offset"] == 1
        transaction.rollback()
