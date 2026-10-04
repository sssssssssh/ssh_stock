import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from app.core.config import get_settings
from app.models.job import JobRun
from app.models.market_data import TradeCalendar
from app.models.portfolio import (
    PortfolioBacktestRun,
    PortfolioFill,
    PortfolioNavDaily,
    PortfolioOrder,
    PortfolioOrderAttempt,
    PortfolioPositionDaily,
)
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
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class TradeCase:
    run_id: uuid.UUID
    performance_id: uuid.UUID
    dates: tuple[date, ...]
    fill_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class _FillSpec:
    day: int
    ts_code: str
    side: str
    quantity: int
    price: str


_FILL_SPECS = (
    _FillSpec(0, "000001.SZ", "BUY", 100, "10"),
    _FillSpec(1, "000001.SZ", "BUY", 100, "12"),
    _FillSpec(1, "000002.SZ", "BUY", 100, "5"),
    _FillSpec(2, "000001.SZ", "SELL", 50, "13"),
    _FillSpec(3, "000002.SZ", "SELL", 100, "6"),
    _FillSpec(4, "000003.SZ", "BUY", 100, "8"),
    _FillSpec(5, "000001.SZ", "SELL", 150, "10"),
)


def seed_trade_case(db: Session, dates: tuple[date, ...]) -> TradeCase:
    assert len(dates) == 7
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
        result_summary={"final_nav": "1.00000000"},
    )
    db.add(run)
    db.flush()

    costs_by_day = {index: Decimal("0") for index in range(7)}
    fill_ids: list[uuid.UUID] = []
    for spec in _FILL_SPECS:
        trade_date = dates[spec.day]
        quantity = spec.quantity
        fill_price = Decimal(spec.price)
        gross = fill_price * quantity
        commission = Decimal("1")
        order = PortfolioOrder(
            run_id=run.id,
            signal_trade_date=trade_date,
            scheduled_trade_date=trade_date,
            ts_code=spec.ts_code,
            side=spec.side,
            order_type="NEXT_OPEN",
            target_quantity=quantity,
            status="EXECUTED",
            attempt_count=1,
        )
        db.add(order)
        db.flush()
        attempt = PortfolioOrderAttempt(
            order_id=order.id,
            run_id=run.id,
            attempt_trade_date=trade_date,
            attempt_no=1,
            outcome="EXECUTED",
            requested_quantity=quantity,
            fill_quantity=quantity,
            reference_price=fill_price,
            fill_price=fill_price,
            gross_amount=gross,
            commission=commission,
            stamp_tax=Decimal("0"),
            transfer_fee=Decimal("0"),
            cash_fee_total=commission,
            slippage_cost=Decimal("0"),
            total_cost=commission,
            market_snapshot={},
            account_snapshot={},
        )
        db.add(attempt)
        db.flush()
        fill = PortfolioFill(
            order_id=order.id,
            attempt_id=attempt.id,
            run_id=run.id,
            trade_date=trade_date,
            ts_code=spec.ts_code,
            side=spec.side,
            quantity=quantity,
            price=fill_price,
            reference_price=fill_price,
            gross_amount=gross,
            commission=commission,
            stamp_tax=Decimal("0"),
            transfer_fee=Decimal("0"),
            cash_fee_total=commission,
            slippage_cost=Decimal("0"),
            total_cost=commission,
        )
        db.add(fill)
        db.flush()
        fill_ids.append(fill.id)
        costs_by_day[spec.day] += commission

    snapshots = _position_snapshots(dates)
    for index, trade_date in enumerate(dates):
        db.add(TradeCalendar(cal_date=trade_date, is_open=True, exchange="SSE"))
        positions = snapshots[index]
        market_value = sum((row[4] for row in positions), Decimal("0"))
        total_assets = Decimal("1000000")
        for ts_code, quantity, avg_cost, close, value, realized, unrealized in positions:
            db.add(
                PortfolioPositionDaily(
                    run_id=run.id,
                    trade_date=trade_date,
                    ts_code=ts_code,
                    quantity=quantity,
                    available_quantity=quantity,
                    avg_cost=avg_cost,
                    close_price=close,
                    market_value=value,
                    weight=value / total_assets,
                    realized_pnl=realized,
                    unrealized_pnl=unrealized,
                    valuation_source="CLOSE",
                    adj_factor=Decimal("1"),
                )
            )
        db.add(
            PortfolioNavDaily(
                run_id=run.id,
                trade_date=trade_date,
                cash=total_assets - market_value,
                market_value=market_value,
                total_assets=total_assets,
                nav=Decimal("1"),
                daily_return=None,
                benchmark_nav=None,
                benchmark_daily_return=None,
                gross_exposure=market_value / total_assets,
                net_exposure=market_value / total_assets,
                position_count=len(positions),
                turnover=None,
                trading_cost=costs_by_day[index],
            )
        )
    db.flush()
    performance = PerformanceApplicationService(db).calculate_now(run.id).report
    return TradeCase(run.id, performance.id, dates, tuple(fill_ids))


def _position_snapshots(dates: tuple[date, ...]) -> tuple[tuple[tuple, ...], ...]:
    del dates
    a10 = (
        "000001.SZ",
        100,
        Decimal("10.01000000"),
        Decimal("10"),
        Decimal("1000"),
        Decimal("0"),
        Decimal("-1"),
    )
    a20 = (
        "000001.SZ",
        200,
        Decimal("11.01000000"),
        Decimal("12"),
        Decimal("2400"),
        Decimal("0"),
        Decimal("198"),
    )
    a15 = (
        "000001.SZ",
        150,
        Decimal("11.01000000"),
        Decimal("13"),
        Decimal("1950"),
        Decimal("98.5"),
        Decimal("298.5"),
    )
    b = (
        "000002.SZ",
        100,
        Decimal("5.01000000"),
        Decimal("5"),
        Decimal("500"),
        Decimal("0"),
        Decimal("-1"),
    )
    c8 = (
        "000003.SZ",
        100,
        Decimal("8.01000000"),
        Decimal("8"),
        Decimal("800"),
        Decimal("0"),
        Decimal("-1"),
    )
    c85 = (
        "000003.SZ",
        100,
        Decimal("8.01000000"),
        Decimal("8.5"),
        Decimal("850"),
        Decimal("0"),
        Decimal("49"),
    )
    return (
        (a10,),
        (a20, b),
        (a15, b),
        (a15,),
        (a15, c8),
        (c8,),
        (c85,),
    )


def cleanup_trade_case(engine, case: TradeCase) -> None:
    with Session(engine) as db:
        db.execute(
            sa.delete(JobRun).where(
                JobRun.job_metadata["portfolio_run_id"].as_string() == str(case.run_id),
            )
        )
        run = db.get(PortfolioBacktestRun, case.run_id)
        if run is not None:
            db.delete(run)
        db.execute(sa.delete(TradeCalendar).where(TradeCalendar.cal_date.in_(case.dates)))
        db.commit()
