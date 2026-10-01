from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from app.core.config import get_settings
from app.models.job import JobRun
from app.models.market_data import TradeCalendar
from app.models.performance import PortfolioPerformanceDaily, PortfolioPerformanceReport
from app.models.portfolio import PortfolioBacktestRun, PortfolioNavDaily
from app.repositories.performance import PerformanceRepository
from app.services.analysis_identity import (
    ACCOUNTING_VERSION,
    BACKTEST_ENGINE_VERSION,
    EXECUTION_VERSION,
    OPPORTUNITY_CALC_VERSION,
    PORTFOLIO_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.job_worker import execute_claimed_job
from app.services.performance.application import (
    PERFORMANCE_JOB_TYPE,
    PerformanceApplicationService,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _source_run(
    db: Session, dates: tuple[date, ...], navs: tuple[str, ...]
) -> PortfolioBacktestRun:
    settings = get_settings()
    portfolio = settings.portfolio_config.model_dump(mode="json")
    execution = settings.execution_config.model_dump(mode="json")
    accounting = settings.accounting_config.model_dump(mode="json")
    run = PortfolioBacktestRun(
        account_mode="BACKTEST",
        status="SUCCESS",
        start_date=dates[0],
        end_date=dates[-1],
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
        result_summary={"final_nav": navs[-1]},
    )
    db.add(run)
    db.flush()
    for trade_date, nav in zip(dates, navs, strict=True):
        db.add(TradeCalendar(cal_date=trade_date, is_open=True, exchange="SSE"))
        value = Decimal(nav)
        db.add(
            PortfolioNavDaily(
                run_id=run.id,
                trade_date=trade_date,
                cash=value * Decimal("400000"),
                market_value=value * Decimal("600000"),
                total_assets=value * Decimal("1000000"),
                nav=value,
                daily_return=None,
                benchmark_nav=None,
                benchmark_daily_return=None,
                gross_exposure=Decimal("0.6"),
                net_exposure=Decimal("0.6"),
                position_count=2,
                turnover=None,
                trading_cost=Decimal("5"),
            )
        )
    db.flush()
    return run


def test_postgresql_performance_artifact_is_idempotent_and_source_versioned() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = (date(2041, 1, 2), date(2041, 1, 3), date(2041, 1, 4))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            run = _source_run(db, dates, ("1", "1.1", "0.99"))
            original_nav = tuple(
                db.scalars(
                    select(PortfolioNavDaily)
                    .where(PortfolioNavDaily.run_id == run.id)
                    .order_by(PortfolioNavDaily.trade_date)
                ).all()
            )
            original_values = tuple(row.nav for row in original_nav)
            service = PerformanceApplicationService(db)

            first = service.calculate_now(run.id)
            second = service.calculate_now(run.id)

            assert first.reused is False
            assert second.reused is True
            assert first.report.id == second.report.id
            assert db.scalar(
                select(func.count()).select_from(PortfolioPerformanceReport).where(
                    PortfolioPerformanceReport.run_id == run.id
                )
            ) == 1
            assert db.scalar(
                select(func.count()).select_from(PortfolioPerformanceDaily).where(
                    PortfolioPerformanceDaily.run_id == run.id
                )
            ) == 3
            assert tuple(row.nav for row in original_nav) == original_values

            final_nav = original_nav[-1]
            final_nav.nav = Decimal("0.95")
            final_nav.total_assets = Decimal("950000")
            run.result_summary = {"final_nav": "0.95"}
            db.flush()
            changed = service.calculate_now(run.id)

            assert changed.reused is False
            assert changed.report.source_hash != first.report.source_hash
            assert db.scalar(
                select(func.count()).select_from(PortfolioPerformanceReport).where(
                    PortfolioPerformanceReport.run_id == run.id
                )
            ) == 2
        transaction.rollback()


def test_performance_report_and_daily_are_atomic_on_persistence_failure() -> None:
    class FailingRepository(PerformanceRepository):
        def add_daily(self, daily):
            raise RuntimeError("injected daily persistence failure")

    engine = sa.create_engine(get_settings().database_url)
    dates = (date(2041, 2, 3), date(2041, 2, 4))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            run = _source_run(db, dates, ("1", "1.01"))
            savepoint = db.begin_nested()
            service = PerformanceApplicationService(
                db, repository=FailingRepository(db)
            )
            try:
                service.calculate_now(run.id)
            except RuntimeError:
                savepoint.rollback()
            else:
                raise AssertionError("injected persistence failure was not raised")

            assert db.scalar(
                select(func.count()).select_from(PortfolioPerformanceReport).where(
                    PortfolioPerformanceReport.run_id == run.id
                )
            ) == 0
            assert db.scalar(
                select(func.count()).select_from(PortfolioPerformanceDaily).where(
                    PortfolioPerformanceDaily.run_id == run.id
                )
            ) == 0
        transaction.rollback()


def test_performance_job_failure_leaves_no_partial_artifact() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = (date(2041, 3, 3), date(2041, 3, 4))
    with Session(engine) as db:
        run = _source_run(db, dates, ("1", "1.01"))
        db.delete(
            db.scalar(
                select(PortfolioNavDaily).where(
                    PortfolioNavDaily.run_id == run.id,
                    PortfolioNavDaily.trade_date == dates[-1],
                )
            )
        )
        job = JobRun(
            job_type=PERFORMANCE_JOB_TYPE,
            status="RUNNING",
            step="claimed by worker",
            row_count=0,
            job_metadata={"portfolio_run_id": str(run.id)},
        )
        db.add(job)
        db.commit()
        run_id, job_id = run.id, job.id

        try:
            execute_claimed_job(db, job_id)

            failed = db.get(JobRun, job_id)
            assert failed.status == "FAILED"
            assert "PERFORMANCE_SOURCE_INCOMPLETE" in failed.error_message
            assert db.scalar(
                select(func.count()).select_from(PortfolioPerformanceReport).where(
                    PortfolioPerformanceReport.run_id == run_id
                )
            ) == 0
        finally:
            persisted_job = db.get(JobRun, job_id)
            persisted_run = db.get(PortfolioBacktestRun, run_id)
            if persisted_job is not None:
                db.delete(persisted_job)
            if persisted_run is not None:
                db.delete(persisted_run)
            db.execute(
                sa.delete(TradeCalendar).where(TradeCalendar.cal_date.in_(dates))
            )
            db.commit()


def test_performance_worker_persists_artifact_and_completes_job() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = (date(2041, 4, 1), date(2041, 4, 2))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            run = _source_run(db, dates, ("1", "1.02"))
            job = JobRun(
                job_type=PERFORMANCE_JOB_TYPE,
                status="RUNNING",
                step="claimed by worker",
                row_count=0,
                job_metadata={"portfolio_run_id": str(run.id)},
            )
            db.add(job)
            db.flush()

            execute_claimed_job(db, job.id)

            db.refresh(job)
            report = db.scalar(
                select(PortfolioPerformanceReport).where(
                    PortfolioPerformanceReport.run_id == run.id
                )
            )
            assert job.status == "SUCCESS"
            assert job.row_count == 2
            assert job.job_metadata["performance_id"] == str(report.id)
            assert db.scalar(
                select(func.count()).select_from(PortfolioPerformanceDaily).where(
                    PortfolioPerformanceDaily.performance_id == report.id
                )
            ) == 2
        transaction.rollback()
