import uuid
from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.domain.execution import (
    ExecutionBatchResult,
    ExecutionMarketBatch,
    InstrumentExecutionProfile,
)
from app.domain.portfolio import (
    AccountState,
    DailyPortfolioSnapshot,
    PortfolioTarget,
    RebalancePlanResult,
    TargetPosition,
)
from app.models.market_data import (
    StockAdjFactor,
    StockBasic,
    StockDaily,
    StockLimitDaily,
    StockTradeStatusDaily,
    TradeCalendar,
)
from app.models.portfolio import (
    PortfolioBacktestRun,
    PortfolioFill,
    PortfolioNavDaily,
    PortfolioOrder,
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
from app.services.execution.application import (
    BacktestPhaseClosedError,
    ExecutionApplicationService,
)
from app.services.execution.instrument_rules import AshareInstrumentRuleResolver
from app.services.execution.resolver import AshareExecutionResolver
from app.services.portfolio.account_gateway import canonical_account_snapshot
from app.services.portfolio.accounting import (
    ACCOUNTING_SOURCE_INCOMPLETE,
    AccountingSourceError,
)
from app.services.portfolio.accounting_application import (
    AccountingApplicationService,
    CloseSnapshotSealedError,
)
from app.services.portfolio.rebalance_application import (
    RebalanceApplicationService,
    RebalanceCloseSnapshotMismatchError,
)
from app.services.portfolio.run_guard import RunConfigIntegrityError
from sqlalchemy.orm import Session


def _run(day: date) -> PortfolioBacktestRun:
    settings = get_settings()
    portfolio = settings.portfolio_config.model_dump(mode="json")
    execution = settings.execution_config.model_dump(mode="json")
    accounting = settings.accounting_config.model_dump(mode="json")
    return PortfolioBacktestRun(
        account_mode="BACKTEST",
        status="RUNNING",
        start_date=day,
        end_date=day,
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
            "strategy": deepcopy(settings.strategy),
            "opportunity": deepcopy(settings.opportunity_config),
            "portfolio": portfolio,
            "execution": execution,
            "accounting": accounting,
        },
    )


def _nav(
    run_id: uuid.UUID,
    day: date,
    *,
    cash: str = "1000000",
    market_value: str = "0",
    position_count: int = 0,
) -> PortfolioNavDaily:
    cash_value = Decimal(cash)
    market = Decimal(market_value)
    total = cash_value + market
    return PortfolioNavDaily(
        run_id=run_id,
        trade_date=day,
        cash=cash_value,
        market_value=market,
        total_assets=total,
        nav=total / Decimal("1000000"),
        gross_exposure=market / total if total else Decimal("0"),
        net_exposure=market / total if total else Decimal("0"),
        position_count=position_count,
        trading_cost=Decimal("0"),
    )


def _empty_snapshot(day: date, cash: str = "1000000") -> DailyPortfolioSnapshot:
    amount = Decimal(cash)
    return DailyPortfolioSnapshot(
        trade_date=day,
        cash=amount,
        total_assets=amount,
        nav=amount / Decimal("1000000"),
        positions=(),
    )


def _cleanup(engine, run_ids, days=(), codes=()) -> None:
    with engine.begin() as connection:
        if run_ids:
            connection.execute(
                sa.delete(PortfolioBacktestRun).where(
                    PortfolioBacktestRun.id.in_(run_ids)
                )
            )
        if codes:
            connection.execute(
                sa.delete(StockLimitDaily).where(StockLimitDaily.ts_code.in_(codes))
            )
            connection.execute(
                sa.delete(StockTradeStatusDaily).where(
                    StockTradeStatusDaily.ts_code.in_(codes)
                )
            )
            connection.execute(
                sa.delete(StockAdjFactor).where(StockAdjFactor.ts_code.in_(codes))
            )
            connection.execute(
                sa.delete(StockDaily).where(StockDaily.ts_code.in_(codes))
            )
            connection.execute(
                sa.delete(StockBasic).where(StockBasic.ts_code.in_(codes))
            )
        if days:
            connection.execute(
                sa.delete(TradeCalendar).where(TradeCalendar.cal_date.in_(days))
            )


def test_missing_pretrade_position_rows_fail_before_open_writes() -> None:
    previous, current = date(1893, 1, 3), date(1893, 1, 4)
    engine = sa.create_engine(get_settings().database_url)
    run_id = None
    try:
        with Session(engine) as db:
            repository = PortfolioRepository(db)
            run = _run(previous)
            run.end_date = current
            run_id = repository.create_run(run).id
            db.add_all(
                [
                    TradeCalendar(cal_date=previous, is_open=True, exchange="SSE"),
                    TradeCalendar(
                        cal_date=current,
                        is_open=True,
                        pretrade_date=previous,
                        exchange="SSE",
                    ),
                    _nav(
                        run_id,
                        previous,
                        cash="900000",
                        market_value="100000",
                        position_count=1,
                    ),
                ]
            )
            repository.insert_orders(
                run_id,
                [
                    PortfolioOrder(
                        run_id=run_id,
                        signal_trade_date=previous,
                        scheduled_trade_date=current,
                        ts_code="M1332M.SZ",
                        side="BUY",
                        order_type="NEXT_OPEN",
                        target_quantity=100,
                        status="PENDING",
                    )
                ],
            )
            db.commit()

        with Session(engine) as db:
            with pytest.raises(AccountingSourceError) as exc:
                ExecutionApplicationService(db).execute_open_batch(run_id, current)
            assert exc.value.reason_code == ACCOUNTING_SOURCE_INCOMPLETE
            assert "position_count mismatch" in str(exc.value)

        with Session(engine) as db:
            repository = PortfolioRepository(db)
            repository.upsert_nav(
                run_id,
                _nav(run_id, current, cash="777000"),
            )
            db.commit()
            with pytest.raises(AccountingSourceError):
                AccountingApplicationService(db).rebuild_close_snapshot(
                    run_id, current
                )

        with Session(engine) as db:
            persisted_nav = PortfolioRepository(db).get_nav(run_id, current)
            assert persisted_nav.cash == Decimal("777000.0000")
            assert persisted_nav.total_assets == Decimal("777000.0000")

        with Session(engine) as db:
            repository = PortfolioRepository(db)
            assert repository.list_order_attempts(run_id) == []
            assert repository.list_fills(run_id) == []
            assert repository.list_orders(run_id)[0].status == "PENDING"
    finally:
        _cleanup(engine, [run_id] if run_id else [], [previous, current])
        engine.dispose()


def test_corrupt_frozen_hash_blocks_all_write_services() -> None:
    day = date(1893, 2, 1)
    engine = sa.create_engine(get_settings().database_url)
    run_id = None
    try:
        with Session(engine) as db:
            run = _run(day)
            run.execution_config_hash = "0" * 64
            run_id = PortfolioRepository(db).create_run(run).id
            db.commit()

        account = _empty_snapshot(day)
        target = PortfolioTarget(day, (), Decimal("1"), True)
        calls = (
            lambda db: ExecutionApplicationService(db).execute_open_batch(run_id, day),
            lambda db: AccountingApplicationService(db).rebuild_close_snapshot(
                run_id, day
            ),
            lambda db: RebalanceApplicationService(db).plan_and_persist(
                run_id,
                target=target,
                account=account,
                scheduled_trade_date=date(1893, 2, 2),
            ),
        )
        for call in calls:
            with Session(engine) as db:
                with pytest.raises(RunConfigIntegrityError, match="hash mismatch"):
                    call(db)

        with Session(engine) as db:
            repository = PortfolioRepository(db)
            assert repository.list_order_attempts(run_id) == []
            assert repository.list_fills(run_id) == []
            assert repository.get_rebalance_plan(run_id, day) is None
            assert repository.get_nav(run_id, day) is None
    finally:
        _cleanup(engine, [run_id] if run_id else [])
        engine.dispose()


@pytest.mark.parametrize("seal", ["NAV", "PLAN"])
def test_closed_day_rejects_late_open_without_mutations(seal) -> None:
    day = date(1893, 3, 1 if seal == "NAV" else 2)
    engine = sa.create_engine(get_settings().database_url)
    run_id = None
    try:
        with Session(engine) as db:
            repository = PortfolioRepository(db)
            run = repository.create_run(_run(day))
            run_id = run.id
            order = PortfolioOrder(
                run_id=run.id,
                signal_trade_date=date(1893, 2, 28),
                scheduled_trade_date=day,
                ts_code="M1332P.SZ",
                side="BUY",
                order_type="NEXT_OPEN",
                target_quantity=100,
                status="PENDING",
            )
            repository.insert_orders(run.id, [order])
            if seal == "NAV":
                repository.upsert_nav(run.id, _nav(run.id, day))
            else:
                repository.insert_rebalance_plan(
                    run.id,
                    PortfolioRebalancePlan(
                        run_id=run.id,
                        signal_trade_date=day,
                        scheduled_trade_date=date(1893, 3, 3),
                        total_assets=Decimal("1000000"),
                        portfolio_version=PORTFOLIO_VERSION,
                        input_hash="a" * 64,
                        target_snapshot={},
                        account_snapshot=canonical_account_snapshot(
                            _empty_snapshot(day)
                        ),
                        plan_snapshot={},
                    ),
                )
            db.commit()

        with Session(engine) as db:
            message = "NAV" if seal == "NAV" else "rebalance plan"
            with pytest.raises(BacktestPhaseClosedError, match=message):
                ExecutionApplicationService(db).execute_open_batch(run_id, day)
        with Session(engine) as db:
            repository = PortfolioRepository(db)
            order = repository.list_orders(run_id)[0]
            assert (order.status, order.attempt_count) == ("PENDING", 0)
            assert repository.list_order_attempts(run_id) == []
            assert repository.list_fills(run_id) == []
    finally:
        _cleanup(engine, [run_id] if run_id else [])
        engine.dispose()


def test_rebalance_requires_authoritative_close_and_detects_tampering() -> None:
    day = date(1893, 4, 1)
    scheduled = date(1893, 4, 2)

    class Provider:
        def load(self, trade_date, ts_codes):
            return {}, {}

    engine = sa.create_engine(get_settings().database_url)
    run_id = None
    try:
        with Session(engine, expire_on_commit=False) as db:
            repository = PortfolioRepository(db)
            run = repository.create_run(_run(day))
            run_id = run.id
            db.commit()
            service = RebalanceApplicationService(db, provider=Provider())
            target = PortfolioTarget(day, (), Decimal("1"), True)
            account = _empty_snapshot(day)

            with pytest.raises(RebalanceCloseSnapshotMismatchError):
                service.plan_and_persist(
                    run.id,
                    target=target,
                    account=account,
                    scheduled_trade_date=scheduled,
                )
            assert repository.get_rebalance_plan(run.id, day) is None

            repository.upsert_nav(run.id, _nav(run.id, day))
            db.commit()
            with pytest.raises(RebalanceCloseSnapshotMismatchError):
                service.plan_and_persist(
                    run.id,
                    target=target,
                    account=_empty_snapshot(day, "900000"),
                    scheduled_trade_date=scheduled,
                )
            assert repository.get_rebalance_plan(run.id, day) is None

            first = service.plan_and_persist(
                run.id,
                target=target,
                account=account,
                scheduled_trade_date=scheduled,
            )
            second = service.plan_and_persist(
                run.id,
                target=target,
                account=account,
                scheduled_trade_date=scheduled,
            )
            assert first.id == second.id

            nav = repository.get_nav(run.id, day)
            nav.cash = nav.total_assets = Decimal("900000")
            nav.nav = Decimal("0.9")
            db.commit()
            with pytest.raises(RebalanceCloseSnapshotMismatchError, match="existing plan"):
                service.plan_and_persist(
                    run.id,
                    target=target,
                    account=_empty_snapshot(day, "900000"),
                    scheduled_trade_date=scheduled,
                )
            assert repository.get_rebalance_plan(run.id, day).id == first.id
    finally:
        _cleanup(engine, [run_id] if run_id else [])
        engine.dispose()


def test_sealed_close_is_idempotent_and_rejects_late_fill() -> None:
    day = date(1893, 5, 1)
    code = "M1332F.SZ"
    engine = sa.create_engine(get_settings().database_url)
    run_id = None

    class RebalanceProvider:
        def load(self, trade_date, ts_codes):
            return {code: Decimal("10")}, {
                code: InstrumentExecutionProfile(
                    code,
                    "SZSE",
                    "main",
                    100,
                    100,
                    1_000_000,
                    100,
                    100,
                    1_000_000,
                )
            }

    try:
        with Session(engine, expire_on_commit=False) as db:
            repository = PortfolioRepository(db)
            run = repository.create_run(_run(day))
            run_id = run.id
            db.add_all(
                [
                    TradeCalendar(cal_date=day, is_open=True, exchange="SSE"),
                    StockBasic(ts_code=code, exchange="SZSE", market="main"),
                    StockDaily(trade_date=day, ts_code=code, open=10, close=10),
                    StockAdjFactor(trade_date=day, ts_code=code, adj_factor=1),
                    StockTradeStatusDaily(
                        trade_date=day,
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
            first_order = PortfolioOrder(
                run_id=run.id,
                signal_trade_date=date(1893, 4, 30),
                scheduled_trade_date=day,
                ts_code=code,
                side="BUY",
                order_type="NEXT_OPEN",
                target_quantity=100,
                status="EXECUTED",
            )
            repository.insert_orders(run.id, [first_order])
            repository.insert_fills(
                run.id,
                [
                    PortfolioFill(
                        order_id=first_order.id,
                        attempt_id=None,
                        run_id=run.id,
                        trade_date=day,
                        ts_code=code,
                        side="BUY",
                        quantity=100,
                        price=Decimal("10"),
                        reference_price=Decimal("10"),
                        gross_amount=Decimal("1000"),
                        commission=Decimal("0"),
                        stamp_tax=Decimal("0"),
                        transfer_fee=Decimal("0"),
                        cash_fee_total=Decimal("0"),
                        slippage_cost=Decimal("0"),
                        total_cost=Decimal("0"),
                    )
                ],
            )
            db.commit()

            accounting = AccountingApplicationService(db)
            close = accounting.rebuild_close_snapshot(run.id, day)
            target = PortfolioTarget(day, (), Decimal("1"), True)
            RebalanceApplicationService(db, provider=RebalanceProvider()).plan_and_persist(
                run.id,
                target=target,
                account=close,
                scheduled_trade_date=date(1893, 5, 2),
            )
            repeated = accounting.rebuild_close_snapshot(run.id, day)
            assert canonical_account_snapshot(repeated) == canonical_account_snapshot(close)

            late_order = PortfolioOrder(
                run_id=run.id,
                signal_trade_date=date(1893, 4, 30),
                scheduled_trade_date=day,
                ts_code=code,
                side="BUY",
                order_type="NEXT_OPEN",
                target_quantity=100,
                status="EXECUTED",
            )
            repository.insert_orders(run.id, [late_order])
            repository.insert_fills(
                run.id,
                [
                    PortfolioFill(
                        order_id=late_order.id,
                        attempt_id=None,
                        run_id=run.id,
                        trade_date=day,
                        ts_code=code,
                        side="BUY",
                        quantity=100,
                        price=Decimal("10"),
                        reference_price=Decimal("10"),
                        gross_amount=Decimal("1000"),
                        commission=Decimal("0"),
                        stamp_tax=Decimal("0"),
                        transfer_fee=Decimal("0"),
                        cash_fee_total=Decimal("0"),
                        slippage_cost=Decimal("0"),
                        total_cost=Decimal("0"),
                    )
                ],
            )
            db.commit()
            with pytest.raises(CloseSnapshotSealedError):
                accounting.rebuild_close_snapshot(run.id, day)
            persisted = repository.get_nav(run.id, day)
            assert persisted.position_count == 1
            assert repository.list_position_snapshot(run.id, day)[0].quantity == 100
    finally:
        _cleanup(engine, [run_id] if run_id else [], [day], [code])
        engine.dispose()


def test_close_rebalance_and_sealed_retry_share_persisted_precision() -> None:
    day = date(1893, 5, 5)
    code = "M1333P.SZ"
    engine = sa.create_engine(get_settings().database_url)
    run_id = None

    class RebalanceProvider:
        def load(self, trade_date, ts_codes):
            return {code: Decimal("10.1234")}, {
                code: InstrumentExecutionProfile(
                    code,
                    "SZSE",
                    "main",
                    100,
                    100,
                    1_000_000,
                    100,
                    100,
                    1_000_000,
                )
            }

    try:
        with Session(engine, expire_on_commit=False) as db:
            repository = PortfolioRepository(db)
            run = repository.create_run(_run(day))
            run_id = run.id
            db.add_all(
                [
                    TradeCalendar(cal_date=day, is_open=True, exchange="SSE"),
                    StockBasic(ts_code=code, exchange="SZSE", market="main"),
                    StockDaily(
                        trade_date=day,
                        ts_code=code,
                        open=Decimal("10"),
                        close=Decimal("10.1234"),
                    ),
                    StockAdjFactor(trade_date=day, ts_code=code, adj_factor=1),
                    StockTradeStatusDaily(
                        trade_date=day,
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
            order = PortfolioOrder(
                run_id=run.id,
                signal_trade_date=date(1893, 5, 4),
                scheduled_trade_date=day,
                ts_code=code,
                side="BUY",
                order_type="NEXT_OPEN",
                target_quantity=300,
                status="EXECUTED",
            )
            repository.insert_orders(run.id, [order])
            repository.insert_fills(
                run.id,
                [
                    PortfolioFill(
                        order_id=order.id,
                        attempt_id=None,
                        run_id=run.id,
                        trade_date=day,
                        ts_code=code,
                        side="BUY",
                        quantity=300,
                        price=Decimal("10"),
                        reference_price=Decimal("10"),
                        gross_amount=Decimal("3000"),
                        commission=Decimal("5"),
                        stamp_tax=Decimal("0"),
                        transfer_fee=Decimal("0"),
                        cash_fee_total=Decimal("5"),
                        slippage_cost=Decimal("0"),
                        total_cost=Decimal("5"),
                    )
                ],
            )
            db.commit()

            accounting = AccountingApplicationService(db)
            close = accounting.rebuild_close_snapshot(run.id, day)
            persisted_position = repository.list_position_snapshot(run.id, day)[0]
            assert close.positions[0].avg_cost == Decimal("10.01666667")
            assert close.positions[0].avg_cost == persisted_position.avg_cost

            RebalanceApplicationService(
                db, provider=RebalanceProvider()
            ).plan_and_persist(
                run.id,
                target=PortfolioTarget(day, (), Decimal("1"), True),
                account=close,
                scheduled_trade_date=date(1893, 5, 6),
            )
            repeated = accounting.rebuild_close_snapshot(run.id, day)
            assert canonical_account_snapshot(repeated) == canonical_account_snapshot(
                close
            )
    finally:
        _cleanup(engine, [run_id] if run_id else [], [day], [code])
        engine.dispose()


def test_two_day_target_to_nav_flow_uses_real_postgresql_ledger() -> None:
    first_day, second_day = date(2098, 5, 8), date(2098, 5, 9)
    code = "M1333E.SZ"
    profile = InstrumentExecutionProfile(
        code,
        "SZSE",
        "main",
        100,
        100,
        1_000_000,
        100,
        100,
        1_000_000,
    )
    engine = sa.create_engine(get_settings().database_url)
    run_id = None

    class RebalanceProvider:
        def load(self, trade_date, ts_codes):
            return {code: Decimal("10")}, {code: profile}

    class MainRules(AshareInstrumentRuleResolver):
        def resolve(self, *, ts_code, exchange, market):
            return profile

    try:
        with Session(engine, expire_on_commit=False) as db:
            repository = PortfolioRepository(db)
            run = _run(first_day)
            run.end_date = second_day
            run = repository.create_run(run)
            run_id = run.id
            db.add_all(
                [
                    TradeCalendar(
                        cal_date=first_day, is_open=True, exchange="SSE"
                    ),
                    TradeCalendar(
                        cal_date=second_day,
                        is_open=True,
                        pretrade_date=first_day,
                        exchange="SSE",
                    ),
                    StockBasic(ts_code=code, exchange="SZSE", market="main"),
                    StockDaily(
                        trade_date=first_day,
                        ts_code=code,
                        open=Decimal("10"),
                        close=Decimal("10"),
                    ),
                    StockDaily(
                        trade_date=second_day,
                        ts_code=code,
                        open=Decimal("10"),
                        close=Decimal("10.1234"),
                    ),
                    StockLimitDaily(
                        trade_date=second_day,
                        ts_code=code,
                        up_limit=Decimal("11"),
                        down_limit=Decimal("9"),
                    ),
                    StockAdjFactor(
                        trade_date=second_day, ts_code=code, adj_factor=1
                    ),
                    StockTradeStatusDaily(
                        trade_date=second_day,
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
            db.commit()

            first_close = AccountingApplicationService(db).rebuild_close_snapshot(
                run.id, first_day
            )
            target = PortfolioTarget(
                signal_trade_date=first_day,
                targets=(
                    TargetPosition(
                        ts_code=code,
                        target_weight=Decimal("0.003"),
                        source_score=Decimal("90"),
                    ),
                ),
                target_cash_ratio=Decimal("0.997"),
                source_available=True,
            )
            plan = RebalanceApplicationService(
                db, provider=RebalanceProvider()
            ).plan_and_persist(
                run.id,
                target=target,
                account=first_close,
                scheduled_trade_date=second_day,
            )
            orders = repository.list_orders(run.id)
            assert plan.signal_trade_date == first_day
            assert [(order.side, order.target_quantity) for order in orders] == [
                ("BUY", 300)
            ]

            execution = ExecutionApplicationService(
                db,
                resolver=AshareExecutionResolver(instrument_rules=MainRules()),
            ).execute_open_batch(run.id, second_day)
            assert execution.decisions[0].outcome == "EXECUTED"
            fills = repository.list_fills(run.id)
            assert len(fills) == 1
            assert fills[0].quantity == 300

            second_close = AccountingApplicationService(db).rebuild_close_snapshot(
                run.id, second_day
            )
            persisted_nav = repository.get_nav(run.id, second_day)
            positions = repository.list_position_snapshot(run.id, second_day)
            assert persisted_nav is not None
            assert persisted_nav.total_assets == second_close.total_assets
            assert persisted_nav.position_count == 1
            assert len(positions) == 1
            assert positions[0].quantity == 300
            assert positions[0].avg_cost == second_close.positions[0].avg_cost
    finally:
        _cleanup(
            engine,
            [run_id] if run_id else [],
            [first_day, second_day],
            [code],
        )
        engine.dispose()


def test_execution_uses_frozen_config_not_runtime_yaml() -> None:
    day = date(1893, 6, 1)
    engine = sa.create_engine(get_settings().database_url)
    run_id = None
    captured = []
    frozen_execution = None

    class Gateway:
        def account_state(self, run_id, trade_date):
            return AccountState(trade_date, Decimal("1000000"))

    class Provider:
        def load(self, trade_date, intents):
            return ExecutionMarketBatch(trade_date, "READY", None, ())

    class Resolver:
        def resolve_batch(self, intents, market, account, config):
            captured.append(config)
            return ExecutionBatchResult(
                trade_date=day,
                starting_cash=account.cash,
                ending_cash_preview=account.cash,
                decisions=(),
            )

    try:
        with Session(engine) as db:
            run = _run(day)
            run_id = PortfolioRepository(db).create_run(run).id
            frozen_execution = deepcopy(run.config_snapshot["execution"])
            db.commit()
        runtime = get_settings().model_copy(deep=True)
        changed_cost = runtime.execution_config.trading_cost.model_copy(
            update={"slippage_bps": Decimal("999")}
        )
        runtime.execution_config = runtime.execution_config.model_copy(
            update={"trading_cost": changed_cost}
        )
        with Session(engine) as db:
            ExecutionApplicationService(
                db,
                settings=runtime,
                account_gateway=Gateway(),
                market_provider=Provider(),
                resolver=Resolver(),
            ).execute_open_batch(run_id, day)
        assert captured[0].trading_cost.slippage_bps != Decimal("999")
        assert captured[0].model_dump(mode="json") == frozen_execution
    finally:
        _cleanup(engine, [run_id] if run_id else [])
        engine.dispose()


def test_runtime_source_identity_drift_blocks_database_writes() -> None:
    day = date(1893, 6, 4)
    engine = sa.create_engine(get_settings().database_url)
    run_id = None
    try:
        with Session(engine) as db:
            run_id = PortfolioRepository(db).create_run(_run(day)).id
            db.commit()

        runtime = get_settings().model_copy(deep=True)
        strategy = deepcopy(runtime.strategy)
        strategy["factor"] = {**strategy["factor"], "m1332_probe": 1}
        runtime.strategy = strategy
        with Session(engine) as db:
            with pytest.raises(
                RunConfigIntegrityError, match="runtime source identity"
            ):
                ExecutionApplicationService(db, settings=runtime).execute_open_batch(
                    run_id, day
                )

        with Session(engine) as db:
            repository = PortfolioRepository(db)
            assert repository.list_order_attempts(run_id) == []
            assert repository.list_fills(run_id) == []
            assert repository.get_nav(run_id, day) is None
            assert repository.get_rebalance_plan(run_id, day) is None
    finally:
        _cleanup(engine, [run_id] if run_id else [])
        engine.dispose()


def test_rebalance_uses_frozen_portfolio_config_not_runtime_yaml() -> None:
    day = date(1893, 6, 2)
    scheduled = date(1893, 6, 3)
    engine = sa.create_engine(get_settings().database_url)
    run_id = None
    captured = []

    class Provider:
        def load(self, trade_date, ts_codes):
            return {}, {}

    class Planner:
        def plan(
            self,
            *,
            target,
            account,
            pending_orders,
            close_prices,
            instrument_profiles,
            scheduled_trade_date,
            config,
        ):
            captured.append(config)
            return RebalancePlanResult(
                signal_trade_date=target.signal_trade_date,
                scheduled_trade_date=scheduled_trade_date,
                total_assets=account.total_assets,
                targets=(),
                pending_actions=(),
                new_orders=(),
                skipped_targets=(),
            )

    try:
        with Session(engine) as db:
            repository = PortfolioRepository(db)
            run = repository.create_run(_run(day))
            run_id = run.id
            frozen_portfolio = deepcopy(run.config_snapshot["portfolio"])
            repository.upsert_nav(run.id, _nav(run.id, day))
            db.commit()
        runtime = get_settings().model_copy(deep=True)
        changed_construction = runtime.portfolio_config.construction.model_copy(
            update={"max_new_positions_per_day": 99}
        )
        runtime.portfolio_config = runtime.portfolio_config.model_copy(
            update={"construction": changed_construction}
        )
        with Session(engine) as db:
            RebalanceApplicationService(
                db,
                settings=runtime,
                provider=Provider(),
                planner=Planner(),
            ).plan_and_persist(
                run_id,
                target=PortfolioTarget(day, (), Decimal("1"), True),
                account=_empty_snapshot(day),
                scheduled_trade_date=scheduled,
            )
        assert captured[0].construction.max_new_positions_per_day != 99
        assert captured[0].model_dump(mode="json") == frozen_portfolio
    finally:
        _cleanup(engine, [run_id] if run_id else [])
        engine.dispose()
