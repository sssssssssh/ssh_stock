import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from app.core.config import get_settings
from app.models.job import JobRun
from app.models.market_data import IndexDaily, TradeCalendar
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
from app.services.performance.application import PerformanceApplicationService
from app.services.performance.risk_application import PERFORMANCE_RISK_JOB_TYPE
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class RiskCase:
    run_id: uuid.UUID
    performance_id: uuid.UUID
    dates: tuple[date, ...]
    benchmark_code: str


def seed_risk_case(
    db: Session,
    dates: tuple[date, ...],
    navs: tuple[str, ...],
    benchmark_closes: tuple[str, ...],
    *,
    benchmark_code: str,
    first_pre_close: str = "100",
) -> RiskCase:
    assert len(dates) == len(navs) == len(benchmark_closes)
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
        benchmark_code=benchmark_code,
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
    for trade_date, raw_nav in zip(dates, navs, strict=True):
        nav = Decimal(raw_nav)
        db.add(TradeCalendar(cal_date=trade_date, is_open=True, exchange="SSE"))
        db.add(
            PortfolioNavDaily(
                run_id=run.id,
                trade_date=trade_date,
                cash=nav * Decimal("400000"),
                market_value=nav * Decimal("600000"),
                total_assets=nav * Decimal("1000000"),
                nav=nav,
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
    performance = PerformanceApplicationService(db).calculate_now(run.id).report
    previous_close = first_pre_close
    for trade_date, close in zip(dates, benchmark_closes, strict=True):
        db.add(
            IndexDaily(
                trade_date=trade_date,
                ts_code=benchmark_code,
                pre_close=float(previous_close),
                close=float(close),
            )
        )
        previous_close = close
    db.flush()
    return RiskCase(run.id, performance.id, dates, benchmark_code)


def cleanup_risk_case(engine, case: RiskCase) -> None:
    with Session(engine) as db:
        db.execute(
            sa.delete(JobRun).where(
                JobRun.job_type == PERFORMANCE_RISK_JOB_TYPE,
                JobRun.job_metadata["portfolio_run_id"].as_string()
                == str(case.run_id),
            )
        )
        run = db.get(PortfolioBacktestRun, case.run_id)
        if run is not None:
            db.delete(run)
        db.execute(
            sa.delete(IndexDaily).where(
                IndexDaily.ts_code == case.benchmark_code,
                IndexDaily.trade_date.in_(case.dates),
            )
        )
        db.execute(
            sa.delete(TradeCalendar).where(TradeCalendar.cal_date.in_(case.dates))
        )
        db.commit()
