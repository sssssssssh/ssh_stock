import threading
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.domain.execution import InstrumentExecutionProfile
from app.domain.portfolio import DailyPortfolioSnapshot, PortfolioTarget, TargetPosition
from app.models.market_data import StockAdjFactor, StockTradeStatusDaily, TradeCalendar
from app.models.portfolio import (
    PortfolioBacktestRun,
    PortfolioNavDaily,
    PortfolioOrder,
    PortfolioPositionDaily,
    PortfolioRebalancePlan,
)
from app.repositories.portfolio import PortfolioRepository
from app.services.analysis_identity import (
    ACCOUNTING_VERSION,
    BACKTEST_ENGINE_VERSION,
    EXECUTION_VERSION,
    OPPORTUNITY_CALC_VERSION,
    PORTFOLIO_VERSION,
    TRADE_STATUS_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.execution.application import ExecutionApplicationService
from app.services.portfolio.account_gateway import PortfolioAccountingAccountGateway
from app.services.portfolio.accounting import (
    ACCOUNTING_SOURCE_INCOMPLETE,
    UNSUPPORTED_CORPORATE_ACTION,
    UNSUPPORTED_INACTIVE_HELD_POSITION,
    AccountingSourceError,
)
from app.services.portfolio.rebalance_application import (
    RebalanceApplicationService,
    RebalancePlanConflictError,
)
from sqlalchemy.orm import Session


def _run(start: date, end: date) -> PortfolioBacktestRun:
    settings = get_settings()
    portfolio = settings.portfolio_config.model_dump(mode="json")
    execution = settings.execution_config.model_dump(mode="json")
    accounting = settings.accounting_config.model_dump(mode="json")
    return PortfolioBacktestRun(
        account_mode="BACKTEST",
        status="RUNNING",
        start_date=start,
        end_date=end,
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
    )


def _nav(run_id: uuid.UUID, day: date, cash: str) -> PortfolioNavDaily:
    amount = Decimal(cash)
    return PortfolioNavDaily(
        run_id=run_id,
        trade_date=day,
        cash=amount,
        market_value=Decimal("0"),
        total_assets=amount,
        nav=amount / Decimal("1000000"),
        gross_exposure=Decimal("0"),
        net_exposure=Decimal("0"),
        position_count=0,
        trading_cost=Decimal("0"),
    )


def test_account_gateway_requires_exact_pretrade_snapshot() -> None:
    d0, d1, d2, d3 = (
        date(1898, 1, 2),
        date(1898, 1, 3),
        date(1898, 1, 4),
        date(1898, 1, 5),
    )
    code = "M1331G.SZ"
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            repository = PortfolioRepository(db)
            run = repository.create_run(_run(d0, d3))
            db.add_all(
                [
                    TradeCalendar(cal_date=d0, is_open=False, exchange="SSE"),
                    TradeCalendar(cal_date=d1, is_open=True, exchange="SSE"),
                    TradeCalendar(
                        cal_date=d2, is_open=True, pretrade_date=d1, exchange="SSE"
                    ),
                    TradeCalendar(
                        cal_date=d3, is_open=True, pretrade_date=d2, exchange="SSE"
                    ),
                    _nav(run.id, d1, "111"),
                    PortfolioPositionDaily(
                        run_id=run.id,
                        trade_date=d2,
                        ts_code=code,
                        quantity=250,
                        available_quantity=0,
                        avg_cost=Decimal("10"),
                        close_price=Decimal("10"),
                        market_value=Decimal("2500"),
                        weight=Decimal("0.5"),
                        unrealized_pnl=Decimal("0"),
                        realized_pnl=Decimal("0"),
                        valuation_source="RAW_CLOSE",
                        adj_factor=Decimal("1"),
                    ),
                    StockAdjFactor(trade_date=d2, ts_code=code, adj_factor=1),
                    StockAdjFactor(trade_date=d3, ts_code=code, adj_factor=1),
                    StockTradeStatusDaily(
                        trade_date=d3,
                        ts_code=code,
                        is_active=True,
                        is_suspended=False,
                        st_status_unknown=False,
                        tradable=True,
                        strategy_eligible=True,
                        calc_version=TRADE_STATUS_CALC_VERSION,
                        config_hash=analysis_strategy_hash(get_settings().strategy),
                        calculated_at=datetime.now(UTC),
                    ),
                ]
            )
            db.flush()
            gateway = PortfolioAccountingAccountGateway(db, repository=repository)
            first = gateway.account_state(run.id, d1)
            assert first.cash == Decimal("1000000")
            assert first.positions == ()
            with pytest.raises(AccountingSourceError) as exc:
                gateway.account_state(run.id, d3)
            assert exc.value.reason_code == ACCOUNTING_SOURCE_INCOMPLETE
            assert "exact previous NAV" in str(exc.value)

            db.add(_nav(run.id, d2, "222"))
            db.flush()
            account = gateway.account_state(run.id, d3)
            assert account.cash == Decimal("222")
            assert account.positions[0].quantity == 250
            assert account.positions[0].available_quantity == 250
        transaction.rollback()
    engine.dispose()


@pytest.mark.parametrize(
    ("active", "current_factor", "reason"),
    [
        (True, 2, UNSUPPORTED_CORPORATE_ACTION),
        (False, 1, UNSUPPORTED_INACTIVE_HELD_POSITION),
    ],
)
def test_execution_start_gate_failure_writes_no_attempt_or_fill(
    active, current_factor, reason
) -> None:
    d1, d2 = date(1897, 2, 1), date(1897, 2, 2)
    code = "M1331X.SZ"
    engine = sa.create_engine(get_settings().database_url)
    run_id: uuid.UUID | None = None
    try:
        with Session(engine) as db:
            repository = PortfolioRepository(db)
            run = repository.create_run(_run(d1, d2))
            run_id = run.id
            db.add_all(
                [
                    TradeCalendar(cal_date=d1, is_open=True, exchange="SSE"),
                    TradeCalendar(
                        cal_date=d2, is_open=True, pretrade_date=d1, exchange="SSE"
                    ),
                    _nav(run.id, d1, "997500"),
                    PortfolioPositionDaily(
                        run_id=run.id,
                        trade_date=d1,
                        ts_code=code,
                        quantity=250,
                        available_quantity=0,
                        avg_cost=Decimal("10"),
                        close_price=Decimal("10"),
                        market_value=Decimal("2500"),
                        weight=Decimal("0.0025"),
                        unrealized_pnl=Decimal("0"),
                        realized_pnl=Decimal("0"),
                        valuation_source="RAW_CLOSE",
                        adj_factor=Decimal("1"),
                    ),
                    StockAdjFactor(trade_date=d1, ts_code=code, adj_factor=1),
                    StockAdjFactor(
                        trade_date=d2, ts_code=code, adj_factor=current_factor
                    ),
                    StockTradeStatusDaily(
                        trade_date=d2,
                        ts_code=code,
                        is_active=active,
                        is_suspended=False,
                        st_status_unknown=False,
                        tradable=True,
                        strategy_eligible=True,
                        calc_version=TRADE_STATUS_CALC_VERSION,
                        config_hash=analysis_strategy_hash(get_settings().strategy),
                        calculated_at=datetime.now(UTC),
                    ),
                ]
            )
            repository.insert_orders(
                run.id,
                [
                    PortfolioOrder(
                        run_id=run.id,
                        signal_trade_date=d1,
                        scheduled_trade_date=d2,
                        ts_code=code,
                        side="SELL",
                        order_type="NEXT_OPEN",
                        target_quantity=200,
                        status="PENDING",
                    )
                ],
            )
            db.commit()

        with Session(engine) as db:
            with pytest.raises(AccountingSourceError) as exc:
                ExecutionApplicationService(db).execute_open_batch(run_id, d2)
            assert exc.value.reason_code == reason

        with Session(engine) as db:
            repository = PortfolioRepository(db)
            order = repository.list_orders(run_id)[0]
            assert order.status == "PENDING"
            assert order.attempt_count == 0
            assert repository.list_order_attempts(run_id) == []
            assert repository.list_fills(run_id) == []
    finally:
        with engine.begin() as connection:
            if run_id is not None:
                connection.execute(
                    sa.delete(PortfolioBacktestRun).where(
                        PortfolioBacktestRun.id == run_id
                    )
                )
            connection.execute(
                sa.delete(StockTradeStatusDaily).where(
                    StockTradeStatusDaily.ts_code == code,
                    StockTradeStatusDaily.trade_date.in_([d1, d2]),
                )
            )
            connection.execute(
                sa.delete(StockAdjFactor).where(
                    StockAdjFactor.ts_code == code,
                    StockAdjFactor.trade_date.in_([d1, d2]),
                )
            )
            connection.execute(
                sa.delete(TradeCalendar).where(TradeCalendar.cal_date.in_([d1, d2]))
            )
        engine.dispose()


def test_rebalance_same_hash_is_idempotent_and_changed_hash_conflicts() -> None:
    day, scheduled = date(1896, 3, 1), date(1896, 3, 2)
    code = "M1331R.SZ"

    class Provider:
        def load(self, trade_date, ts_codes):
            assert trade_date == day
            return {
                code: Decimal("10")
            }, {
                code: InstrumentExecutionProfile(
                    code, "SZSE", "main", 100, 100, 1_000_000, 100, 100, 1_000_000
                )
            }

    engine = sa.create_engine(get_settings().database_url)
    run_id: uuid.UUID | None = None
    try:
        with Session(engine, expire_on_commit=False) as db:
            repository = PortfolioRepository(db)
            run = repository.create_run(_run(day, scheduled))
            run_id = run.id
            db.commit()
            service = RebalanceApplicationService(db, provider=Provider())
            target = PortfolioTarget(
                day,
                (TargetPosition(code, Decimal("0.1"), Decimal("90")),),
                Decimal("0.9"),
                True,
            )
            account = DailyPortfolioSnapshot(
                day, Decimal("1000000"), Decimal("1000000"), Decimal("1"), ()
            )
            first = service.plan_and_persist(
                run.id, target=target, account=account, scheduled_trade_date=scheduled
            )
            second = service.plan_and_persist(
                run.id, target=target, account=account, scheduled_trade_date=scheduled
            )
            assert first.id == second.id
            assert first.input_hash is not None

            changed = DailyPortfolioSnapshot(
                day, Decimal("900000"), Decimal("900000"), Decimal("0.9"), ()
            )
            with pytest.raises(RebalancePlanConflictError):
                service.plan_and_persist(
                    run.id,
                    target=target,
                    account=changed,
                    scheduled_trade_date=scheduled,
                )
            assert len(repository.list_orders(run.id)) == 1
            assert repository.get_rebalance_plan(run.id, day).input_hash == first.input_hash
    finally:
        with engine.begin() as connection:
            if run_id is not None:
                connection.execute(
                    sa.delete(PortfolioBacktestRun).where(
                        PortfolioBacktestRun.id == run_id
                    )
                )
        engine.dispose()


def test_0034_requires_input_hash_only_for_portfolio_v3() -> None:
    day = date(1895, 4, 1)
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            run = PortfolioRepository(db).create_run(_run(day, day))
            db.add(
                PortfolioRebalancePlan(
                    run_id=run.id,
                    signal_trade_date=day,
                    scheduled_trade_date=date(1895, 4, 2),
                    total_assets=Decimal("1"),
                    portfolio_version="portfolio_v2",
                    input_hash=None,
                    target_snapshot={},
                    account_snapshot={},
                    plan_snapshot={},
                )
            )
            db.flush()
            with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
                db.add(
                    PortfolioRebalancePlan(
                        run_id=run.id,
                        signal_trade_date=date(1895, 4, 2),
                        scheduled_trade_date=date(1895, 4, 3),
                        total_assets=Decimal("1"),
                        portfolio_version="portfolio_v3",
                        input_hash=None,
                        target_snapshot={},
                        account_snapshot={},
                        plan_snapshot={},
                    )
                )
                db.flush()
        transaction.rollback()
    engine.dispose()


def test_run_for_update_serializes_two_real_sessions() -> None:
    day = date(1894, 5, 1)
    engine = sa.create_engine(get_settings().database_url)
    with Session(engine) as setup:
        run = PortfolioRepository(setup).create_run(_run(day, day))
        run_id = run.id
        setup.commit()

    first_locked = threading.Event()
    release_first = threading.Event()
    outcome: list[str] = []

    def hold_first_lock() -> None:
        with Session(engine) as session:
            PortfolioRepository(session).get_run_for_update(run_id)
            first_locked.set()
            release_first.wait(timeout=5)
            session.commit()

    thread = threading.Thread(target=hold_first_lock)
    thread.start()
    assert first_locked.wait(timeout=5)
    try:
        with Session(engine) as second:
            second.execute(sa.text("SET LOCAL lock_timeout = '200ms'"))
            with pytest.raises(sa.exc.OperationalError):
                PortfolioRepository(second).get_run_for_update(run_id)
            second.rollback()
            outcome.append("timed_out")
        release_first.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        with Session(engine) as retry:
            assert PortfolioRepository(retry).get_run_for_update(run_id) is not None
            retry.rollback()
            outcome.append("retried")
        assert outcome == ["timed_out", "retried"]
    finally:
        release_first.set()
        thread.join(timeout=5)
        with engine.begin() as connection:
            connection.execute(
                sa.delete(PortfolioBacktestRun).where(PortfolioBacktestRun.id == run_id)
            )
        engine.dispose()
