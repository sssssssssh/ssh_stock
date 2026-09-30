import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import app.services.portfolio.source_integrity as source_integrity_module
import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from app.core.config import get_settings
from app.core.db import get_db
from app.domain.execution import InstrumentExecutionProfile
from app.domain.portfolio import (
    AccountState,
    DailyPortfolioSnapshot,
    PortfolioTarget,
    TargetPosition,
)
from app.main import app
from app.models.market_data import (
    StockAdjFactor,
    StockBasic,
    StockDaily,
    StockFactorDaily,
    StockLimitDaily,
    StockOpportunityDaily,
    StockStateDaily,
    StockSuspendDaily,
    StockTradeStatusDaily,
    TradeCalendar,
)
from app.models.portfolio import (
    PortfolioBacktestRun,
    PortfolioFill,
    PortfolioNavDaily,
    PortfolioOrder,
    PortfolioOrderAttempt,
    PortfolioPositionDaily,
    PortfolioRebalancePlan,
)
from app.repositories.portfolio import PortfolioRepository
from app.services.analysis_identity import (
    ACCOUNTING_VERSION,
    BACKTEST_ENGINE_VERSION,
    EXECUTION_VERSION,
    FACTOR_CALC_VERSION,
    OPPORTUNITY_CALC_VERSION,
    PORTFOLIO_VERSION,
    TRADE_STATUS_CALC_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.execution.application import ExecutionApplicationService
from app.services.execution.contracts import (
    ExecutionSourceNotReadyError,
)
from app.services.portfolio.accounting_application import AccountingApplicationService
from app.services.portfolio.application import PortfolioApplicationService
from app.services.portfolio.contracts import SourceReadinessStatus
from app.services.portfolio.rebalance_application import RebalanceApplicationService
from app.services.portfolio.rebalance_market_data import RebalanceMarketDataProvider
from app.services.portfolio.run_guard import BacktestContractMismatchError
from app.services.portfolio.source_integrity import check_portfolio_source_integrity
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _run() -> PortfolioBacktestRun:
    settings = get_settings()
    portfolio = settings.portfolio_config.model_dump(mode="json")
    execution = settings.execution_config.model_dump(mode="json")
    accounting = settings.accounting_config.model_dump(mode="json")
    return PortfolioBacktestRun(
        account_mode="BACKTEST",
        status="RUNNING",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 2),
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
            "strategy": settings.strategy,
            "opportunity": settings.opportunity_config,
            "portfolio": portfolio,
            "execution": execution,
            "accounting": accounting,
        },
    )


def test_five_portfolio_tables_round_trip_and_cascade() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            repository = PortfolioRepository(db)
            run = repository.create_run(_run())
            order = PortfolioOrder(
                run_id=run.id,
                signal_trade_date=date(2026, 9, 1),
                scheduled_trade_date=date(2026, 9, 2),
                ts_code="000001.SZ",
                side="BUY",
                order_type="NEXT_OPEN",
                target_weight=Decimal("0.1"),
                status="EXECUTED",
            )
            repository.insert_orders(run.id, [order])
            attempt = PortfolioOrderAttempt(
                order_id=order.id,
                run_id=run.id,
                attempt_trade_date=date(2026, 9, 2),
                attempt_no=1,
                outcome="EXECUTED",
                requested_quantity=100,
                fill_quantity=100,
                reference_price=Decimal("9.995"),
                fill_price=Decimal("10"),
                gross_amount=Decimal("1000"),
                commission=Decimal("5"),
                stamp_tax=Decimal("0"),
                transfer_fee=Decimal("0"),
                cash_fee_total=Decimal("5"),
                slippage_cost=Decimal("0.5"),
                total_cost=Decimal("5.5"),
            )
            repository.insert_order_attempts(run.id, [attempt])
            repository.insert_fills(
                run.id,
                [
                    PortfolioFill(
                        order_id=order.id,
                        attempt_id=attempt.id,
                        run_id=run.id,
                        trade_date=date(2026, 9, 2),
                        ts_code="000001.SZ",
                        side="BUY",
                        quantity=100,
                        price=Decimal("10"),
                        reference_price=Decimal("9.995"),
                        gross_amount=Decimal("1000"),
                        commission=Decimal("5"),
                        stamp_tax=Decimal("0"),
                        transfer_fee=Decimal("0"),
                        cash_fee_total=Decimal("5"),
                        slippage_cost=Decimal("0.5"),
                        total_cost=Decimal("5.5"),
                    )
                ],
            )
            repository.replace_position_snapshot(
                run.id,
                date(2026, 9, 2),
                [
                    PortfolioPositionDaily(
                        run_id=run.id,
                        trade_date=date(2026, 9, 2),
                        ts_code="000001.SZ",
                        quantity=100,
                        available_quantity=0,
                        avg_cost=Decimal("10.055"),
                        close_price=Decimal("10.2"),
                        market_value=Decimal("1020"),
                        weight=Decimal("0.00102"),
                        unrealized_pnl=Decimal("14.5"),
                        realized_pnl=Decimal("0"),
                    )
                ],
            )
            repository.upsert_nav(
                run.id,
                PortfolioNavDaily(
                    run_id=run.id,
                    trade_date=date(2026, 9, 2),
                    cash=Decimal("998994.5"),
                    market_value=Decimal("1020"),
                    total_assets=Decimal("1000014.5"),
                    nav=Decimal("1.0000145"),
                    gross_exposure=Decimal("0.00102"),
                    net_exposure=Decimal("0.00102"),
                    position_count=1,
                    trading_cost=Decimal("5.5"),
                ),
            )
            assert len(repository.list_orders(run.id)) == 1
            assert len(repository.list_order_attempts(run.id)) == 1
            fills = repository.list_fills(run.id)
            assert len(fills) == 1
            assert fills[0].price == Decimal("10.0000")
            assert fills[0].total_cost == Decimal("5.5000")
            assert len(repository.list_positions(run.id)) == 1
            nav = repository.list_nav(run.id)
            assert len(nav) == 1
            assert nav[0].cash == Decimal("998994.5000")

            db.delete(run)
            db.flush()
            for table in (
                PortfolioOrder,
                PortfolioOrderAttempt,
                PortfolioFill,
                PortfolioPositionDaily,
                PortfolioNavDaily,
            ):
                count = db.scalar(
                    sa.select(sa.func.count()).select_from(table).where(table.run_id == run.id)
                )
                assert count == 0
        transaction.rollback()
    engine.dispose()


def test_create_backtest_definition_freezes_all_config_identities() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, expire_on_commit=False) as db:
            # Keep the service transaction inside the outer test transaction.
            service = PortfolioApplicationService(db)
            historical = _run()
            historical.backtest_engine_version = "backtest_v2"
            PortfolioRepository(db).create_run(historical)
            run = service.create_backtest_definition(
                name="identity-test",
                start_date=date(2026, 9, 1),
                end_date=date(2026, 9, 30),
            )
            assert run.status == "CREATED"
            assert run.backtest_engine_version == "backtest_v6"
            assert service.get_backtest(historical.id).backtest_engine_version == (
                "backtest_v2"
            )
            assert set(run.config_snapshot) == {
                "strategy",
                "opportunity",
                "portfolio",
                "execution",
                "accounting",
            }
            assert run.portfolio_config_hash == config_hash(run.config_snapshot["portfolio"])
            assert run.execution_config_hash == config_hash(run.config_snapshot["execution"])
            assert run.accounting_config_hash == config_hash(
                run.config_snapshot["accounting"]
            )
            assert service.get_backtest(run.id).id == run.id
            duplicate = service.create_backtest_definition(
                name="identity-test-copy",
                start_date=date(2026, 9, 1),
                end_date=date(2026, 9, 30),
            )
            assert duplicate.id != run.id
            app.dependency_overrides[get_db] = lambda: db
            try:
                response = TestClient(app).get(f"/api/v1/portfolio/backtests/{run.id}")
            finally:
                app.dependency_overrides.pop(get_db, None)
            assert response.status_code == 200
            assert response.json()["data"]["source_strategy_config_hash"] == (
                run.source_strategy_config_hash
            )
            assert response.json()["data"]["config_snapshot"] == run.config_snapshot
        transaction.rollback()
    engine.dispose()


def test_portfolio_source_integrity_real_db_exact_sets_and_current_identity(
    monkeypatch,
) -> None:
    settings = get_settings()
    target = date(1900, 1, 15)
    code_a, code_b, suspended_code = "M1312A.SZ", "M1312B.SZ", "M1312S.SZ"
    strategy_hash = analysis_strategy_hash(settings.strategy)
    opportunity_hash = config_hash(settings.opportunity_config)
    calculated_at = datetime.now(UTC)
    monkeypatch.setattr(
        source_integrity_module,
        "is_core_analysis_complete",
        lambda *a, **k: True,
    )

    def factor(code: str, *, current: bool) -> StockFactorDaily:
        return StockFactorDaily(
            trade_date=target,
            ts_code=code,
            eligible=True,
            calc_version=FACTOR_CALC_VERSION if current else "old-factor",
            config_hash=strategy_hash if current else "old-strategy",
            calculated_at=calculated_at,
        )

    def state(code: str, *, current: bool) -> StockStateDaily:
        return StockStateDaily(
            trade_date=target,
            ts_code=code,
            algo_version=settings.algo_version if current else "old-algo",
            state="S4",
            is_new_state=False,
            fast_transition=False,
            calc_version=TREND_CALC_VERSION if current else "old-trend",
            config_hash=strategy_hash if current else "old-strategy",
            calculated_at=calculated_at,
        )

    def opportunity(code: str, *, current: bool) -> StockOpportunityDaily:
        return StockOpportunityDaily(
            trade_date=target,
            ts_code=code,
            algo_version=settings.algo_version if current else "old-algo",
            state="S4",
            left_reversal_new=False,
            opportunity_stage="TREND",
            opportunity_score=90,
            reason_codes=["TREND"],
            calc_version=(
                OPPORTUNITY_CALC_VERSION if current else "old-opportunity"
            ),
            config_hash=opportunity_hash if current else "old-opportunity-config",
            source_strategy_config_hash=(
                strategy_hash if current else "old-strategy"
            ),
            calculated_at=calculated_at,
        )

    engine = sa.create_engine(settings.database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            db.add_all(
                [
                    StockBasic(
                        ts_code=code_a,
                        list_status="L",
                        list_date=date(1899, 1, 1),
                    ),
                    StockBasic(
                        ts_code=code_b,
                        list_status="L",
                        list_date=date(1899, 1, 1),
                    ),
                    StockBasic(
                        ts_code=suspended_code,
                        list_status="L",
                        list_date=date(1899, 1, 1),
                    ),
                    StockSuspendDaily(
                        trade_date=target,
                        ts_code=suspended_code,
                        suspend_type="S",
                    ),
                    StockDaily(trade_date=target, ts_code=code_b),
                    factor(code_b, current=True),
                    state(code_b, current=True),
                    opportunity(code_b, current=True),
                ]
            )
            db.flush()

            same_missing = check_portfolio_source_integrity(
                db, target, settings=settings
            )
            assert same_missing.status == SourceReadinessStatus.INCOMPLETE
            assert same_missing.reason == "RAW_UNIVERSE_SET_MISMATCH"
            assert same_missing.missing_code_samples["stock_daily"] == (code_a,)

            old_factor = factor(code_a, current=False)
            db.add_all(
                [
                    StockDaily(trade_date=target, ts_code=code_a),
                    old_factor,
                    state(code_a, current=False),
                    opportunity(code_a, current=False),
                ]
            )
            db.flush()
            raw_only = check_portfolio_source_integrity(db, target, settings=settings)
            assert raw_only.reason == "RAW_FACTOR_SET_MISMATCH"
            assert raw_only.factor_count == 1

            old_factor.calc_version = FACTOR_CALC_VERSION
            old_factor.config_hash = strategy_hash
            db.flush()
            factor_only = check_portfolio_source_integrity(
                db, target, settings=settings
            )
            assert factor_only.reason == "FACTOR_STATE_SET_MISMATCH"
            assert factor_only.state_count == 1

            db.add(state(code_a, current=True))
            db.flush()
            state_only = check_portfolio_source_integrity(
                db, target, settings=settings
            )
            assert state_only.reason == "STATE_OPPORTUNITY_SET_MISMATCH"
            assert state_only.opportunity_count == 1

            db.add(opportunity(code_a, current=True))
            db.flush()
            ready = check_portfolio_source_integrity(db, target, settings=settings)
            assert ready.status == SourceReadinessStatus.READY
            assert ready.reason is None
            assert ready.expected_count == ready.stock_daily_count == 2
            assert ready.factor_count == ready.state_count == ready.opportunity_count == 2
        transaction.rollback()
    engine.dispose()


def test_m13_3_accounting_rebuild_is_idempotent_and_precise() -> None:
    settings = get_settings()
    trade_date = date(1900, 2, 1)
    code = "M133A.SZ"
    strategy_hash = analysis_strategy_hash(settings.strategy)
    engine = sa.create_engine(settings.database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, expire_on_commit=False) as db:
            repository = PortfolioRepository(db)
            definition = _run()
            definition.start_date = trade_date
            definition.end_date = trade_date
            run = repository.create_run(definition)
            order = PortfolioOrder(
                run_id=run.id,
                signal_trade_date=date(1900, 1, 31),
                scheduled_trade_date=trade_date,
                ts_code=code,
                side="BUY",
                order_type="NEXT_OPEN",
                target_quantity=100,
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
                        trade_date=trade_date,
                        ts_code=code,
                        side="BUY",
                        quantity=100,
                        price=Decimal("10"),
                        reference_price=Decimal("10"),
                        gross_amount=Decimal("1000"),
                        commission=Decimal("5"),
                        stamp_tax=Decimal("0"),
                        transfer_fee=Decimal("0"),
                        cash_fee_total=Decimal("5"),
                        slippage_cost=Decimal("1"),
                        total_cost=Decimal("6"),
                    )
                ],
            )
            db.add_all(
                [
                    StockDaily(
                        trade_date=trade_date, ts_code=code, open=10, close=12
                    ),
                    StockAdjFactor(
                        trade_date=trade_date, ts_code=code, adj_factor=1
                    ),
                    StockTradeStatusDaily(
                        trade_date=trade_date,
                        ts_code=code,
                        is_active=True,
                        is_suspended=False,
                        st_status_unknown=False,
                        tradable=True,
                        strategy_eligible=True,
                        calc_version=TRADE_STATUS_CALC_VERSION,
                        config_hash=strategy_hash,
                        calculated_at=datetime.now(UTC),
                    ),
                    TradeCalendar(
                        cal_date=trade_date,
                        is_open=True,
                        pretrade_date=date(1900, 1, 31),
                        exchange="SSE",
                    ),
                ]
            )
            db.flush()
            monkey_commit = db.commit
            db.commit = db.flush
            try:
                service = AccountingApplicationService(db)
                first = service.rebuild_close_snapshot(run.id, trade_date)
                second = service.rebuild_close_snapshot(run.id, trade_date)
            finally:
                db.commit = monkey_commit
            assert first == second
            assert first.cash == Decimal("998995")
            assert first.total_assets == Decimal("1000195")
            position = repository.list_position_snapshot(run.id, trade_date)[0]
            assert position.avg_cost == Decimal("10.05000000")
            assert position.available_quantity == 0
            assert position.valuation_source == "RAW_CLOSE"
            assert position.adj_factor == Decimal("1.0000000000")
            assert len(repository.list_nav(run.id)) == 1
        transaction.rollback()
    engine.dispose()


def test_m13_3_rebalance_application_is_idempotent() -> None:
    signal_date = date(1900, 2, 3)
    next_date = date(1900, 2, 4)
    code = "M133R.SZ"

    class Provider:
        def load(self, trade_date, ts_codes):
            assert trade_date == signal_date
            assert tuple(ts_codes) == (code,)
            return (
                {code: Decimal("10")},
                {
                    code: InstrumentExecutionProfile(
                        ts_code=code,
                        exchange="SZSE",
                        market="main",
                        min_buy_quantity=100,
                        buy_step=100,
                        max_buy_quantity=1_000_000,
                        min_sell_quantity=100,
                        sell_step=100,
                        max_sell_quantity=1_000_000,
                    )
                },
            )

    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, expire_on_commit=False) as db:
            repository = PortfolioRepository(db)
            run = repository.create_run(_run())
            target = PortfolioTarget(
                signal_trade_date=signal_date,
                targets=(
                    TargetPosition(code, Decimal("0.1"), Decimal("90")),
                ),
                target_cash_ratio=Decimal("0.9"),
                source_available=True,
            )
            account = DailyPortfolioSnapshot(
                trade_date=signal_date,
                cash=Decimal("1000000"),
                total_assets=Decimal("1000000"),
                nav=Decimal("1"),
                positions=(),
            )
            repository.upsert_nav(
                run.id,
                PortfolioNavDaily(
                    run_id=run.id,
                    trade_date=signal_date,
                    cash=Decimal("1000000"),
                    market_value=Decimal("0"),
                    total_assets=Decimal("1000000"),
                    nav=Decimal("1"),
                    gross_exposure=Decimal("0"),
                    net_exposure=Decimal("0"),
                    position_count=0,
                    trading_cost=Decimal("0"),
                ),
            )
            original_commit = db.commit
            db.commit = db.flush
            try:
                service = RebalanceApplicationService(
                    db, repository=repository, provider=Provider()
                )
                first = service.plan_and_persist(
                    run.id,
                    target=target,
                    account=account,
                    scheduled_trade_date=next_date,
                )
                second = service.plan_and_persist(
                    run.id,
                    target=target,
                    account=account,
                    scheduled_trade_date=next_date,
                )
            finally:
                db.commit = original_commit
            assert first.id == second.id
            orders = repository.list_orders(run.id)
            assert len(orders) == 1
            assert orders[0].rebalance_plan_id == first.id
            assert orders[0].child_index == 1
            assert orders[0].target_quantity == 10000
            assert orders[0].order_type == "NEXT_OPEN"
        transaction.rollback()
    engine.dispose()


def test_m13_3_rebalance_market_provider_batches_close_and_profile() -> None:
    trade_date = date(1900, 2, 5)
    code = "M133P.SZ"
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            db.add_all(
                [
                    StockBasic(
                        ts_code=code,
                        exchange="SZSE",
                        market="主板",
                    ),
                    StockDaily(
                        trade_date=trade_date,
                        ts_code=code,
                        open=Decimal("9.8"),
                        close=Decimal("10.2"),
                    ),
                ]
            )
            db.flush()
            closes, profiles = RebalanceMarketDataProvider(db).load(
                trade_date, [code]
            )
            assert closes == {code: Decimal("10.2")}
            assert profiles[code].buy_step == 100
        transaction.rollback()
    engine.dispose()


def test_m13_3_run_guard_rejects_created_accounting_write() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            run = _run()
            run.status = "CREATED"
            PortfolioRepository(db).create_run(run)
            with pytest.raises(BacktestContractMismatchError, match="RUNNING"):
                AccountingApplicationService(db).rebuild_close_snapshot(
                    run.id, date(1900, 2, 1)
                )
        if transaction.is_active:
            transaction.rollback()
    engine.dispose()


def test_m13_3_plan_order_same_run_fk_and_unique_date() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            repository = PortfolioRepository(db)
            run_a = repository.create_run(_run())
            run_b = repository.create_run(_run())
            plan = PortfolioRebalancePlan(
                run_id=run_a.id,
                signal_trade_date=date(1900, 2, 1),
                scheduled_trade_date=date(1900, 2, 2),
                total_assets=Decimal("1000000"),
                portfolio_version=PORTFOLIO_VERSION,
                input_hash="a" * 64,
                target_snapshot={},
                account_snapshot={},
                plan_snapshot={},
            )
            repository.insert_rebalance_plan(run_a.id, plan)
            with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
                db.add(
                    PortfolioOrder(
                        run_id=run_a.id,
                        rebalance_plan_id=plan.id,
                        child_index=None,
                        signal_trade_date=plan.signal_trade_date,
                        scheduled_trade_date=plan.scheduled_trade_date,
                        ts_code="M133C.SZ",
                        side="BUY",
                        order_type="NEXT_OPEN",
                        target_quantity=100,
                        status="PENDING",
                    )
                )
                db.flush()
            with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
                db.add(
                    PortfolioRebalancePlan(
                        run_id=run_a.id,
                        signal_trade_date=plan.signal_trade_date,
                        scheduled_trade_date=plan.scheduled_trade_date,
                        total_assets=Decimal("1000000"),
                        portfolio_version=PORTFOLIO_VERSION,
                        input_hash="b" * 64,
                        target_snapshot={},
                        account_snapshot={},
                        plan_snapshot={},
                    )
                )
                db.flush()
            with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
                db.add(
                    PortfolioOrder(
                        run_id=run_b.id,
                        rebalance_plan_id=plan.id,
                        child_index=1,
                        signal_trade_date=plan.signal_trade_date,
                        scheduled_trade_date=plan.scheduled_trade_date,
                        ts_code="M133B.SZ",
                        side="BUY",
                        order_type="NEXT_OPEN",
                        target_quantity=100,
                        status="PENDING",
                    )
                )
                db.flush()
        transaction.rollback()
    engine.dispose()


def test_portfolio_database_check_constraints() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            for field, value in (("account_mode", "INVALID"), ("status", "UNKNOWN")):
                invalid_run = _run()
                setattr(invalid_run, field, value)
                with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
                    db.add(invalid_run)
                    db.flush()
            repository = PortfolioRepository(db)
            run = repository.create_run(_run())
            invalid_rows = [
                PortfolioOrder(
                    run_id=run.id,
                    signal_trade_date=date(2026, 9, 1),
                    scheduled_trade_date=date(2026, 9, 2),
                    ts_code="000001.SZ",
                    side="HOLD",
                    order_type="NEXT_OPEN",
                    status="PENDING",
                ),
                PortfolioOrder(
                    run_id=run.id,
                    signal_trade_date=date(2026, 9, 1),
                    scheduled_trade_date=date(2026, 9, 2),
                    ts_code="000002.SZ",
                    side="BUY",
                    order_type="NEXT_OPEN",
                    status="UNKNOWN",
                ),
                PortfolioOrder(
                    run_id=run.id,
                    signal_trade_date=date(2026, 9, 1),
                    scheduled_trade_date=date(2026, 9, 2),
                    ts_code="000003.SZ",
                    side="BUY",
                    order_type="NEXT_OPEN",
                    target_weight=Decimal("1.01"),
                    status="PENDING",
                ),
            ]
            for invalid in invalid_rows:
                with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
                    db.add(invalid)
                    db.flush()

            invalid_positions = [
                PortfolioPositionDaily(
                    run_id=run.id,
                    trade_date=date(2026, 9, 2),
                    ts_code="000004.SZ",
                    quantity=100,
                    available_quantity=101,
                    avg_cost=Decimal("10"),
                    close_price=Decimal("10"),
                    market_value=Decimal("1000"),
                    weight=Decimal("0.1"),
                    unrealized_pnl=Decimal("0"),
                    realized_pnl=Decimal("0"),
                ),
                PortfolioPositionDaily(
                    run_id=run.id,
                    trade_date=date(2026, 9, 2),
                    ts_code="000005.SZ",
                    quantity=100,
                    available_quantity=100,
                    avg_cost=Decimal("10"),
                    close_price=Decimal("10"),
                    market_value=Decimal("1000"),
                    weight=Decimal("1.01"),
                    unrealized_pnl=Decimal("0"),
                    realized_pnl=Decimal("0"),
                ),
            ]
            for invalid in invalid_positions:
                with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
                    db.add(invalid)
                    db.flush()
        transaction.rollback()
    engine.dispose()


def test_fill_order_run_identity_is_enforced_by_database() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            repository = PortfolioRepository(db)
            run_a = repository.create_run(_run())
            run_b = repository.create_run(_run())
            order = PortfolioOrder(
                run_id=run_a.id,
                signal_trade_date=date(2026, 9, 1),
                scheduled_trade_date=date(2026, 9, 2),
                ts_code="000001.SZ",
                side="BUY",
                order_type="NEXT_OPEN",
                target_weight=Decimal("0.1"),
                status="EXECUTED",
            )
            repository.insert_orders(run_a.id, [order])

            def fill(run_id):
                return PortfolioFill(
                    order_id=order.id,
                    run_id=run_id,
                    trade_date=date(2026, 9, 2),
                    ts_code="000001.SZ",
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

            with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
                db.add(fill(run_b.id))
                db.flush()
            db.add(fill(run_a.id))
            db.flush()
            assert len(repository.list_fills(run_a.id)) == 1
        transaction.rollback()
    engine.dispose()


def test_m13_check_constraint_names_match_orm_metadata() -> None:
    engine = sa.create_engine(get_settings().database_url)
    inspector = sa.inspect(engine)
    for model in (
        PortfolioBacktestRun,
        PortfolioOrder,
        PortfolioOrderAttempt,
        PortfolioFill,
        PortfolioPositionDaily,
        PortfolioNavDaily,
    ):
        database_names = {
            item["name"] for item in inspector.get_check_constraints(model.__tablename__)
        }
        metadata_names = {
            constraint.name
            for constraint in model.__table__.constraints
            if isinstance(constraint, sa.CheckConstraint)
        }
        assert database_names == metadata_names

    order_uniques = {
        item["name"]: tuple(item["column_names"])
        for item in inspector.get_unique_constraints("portfolio_order")
    }
    assert order_uniques["uq_portfolio_order_id_run_id"] == ("id", "run_id")

    fill_foreign_keys = {
        item["name"]: (
            tuple(item["constrained_columns"]),
            tuple(item["referred_columns"]),
        )
        for item in inspector.get_foreign_keys("portfolio_fill")
    }
    assert fill_foreign_keys["fk_portfolio_fill_order_run_portfolio_order"] == (
        ("order_id", "run_id"),
        ("id", "run_id"),
    )
    assert "fk_portfolio_fill_order_id_portfolio_order" not in fill_foreign_keys
    assert fill_foreign_keys[
        "fk_portfolio_fill_attempt_run_portfolio_order_attempt"
    ] == (
        ("attempt_id", "run_id"),
        ("id", "run_id"),
    )
    engine.dispose()


def test_execution_application_persists_attempt_and_fill_and_fails_closed(
    monkeypatch,
) -> None:
    settings = get_settings()
    strategy_hash = analysis_strategy_hash(settings.strategy)
    trade_date = date(2026, 7, 1)
    code = "M132A.SH"

    class AccountGateway:
        def account_state(self, run_id, requested_date):
            return AccountState(requested_date, Decimal("100000"))

    engine = sa.create_engine(settings.database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, expire_on_commit=False) as db:
            repository = PortfolioRepository(db)
            run = repository.create_run(_run())
            order = PortfolioOrder(
                run_id=run.id,
                signal_trade_date=date(2026, 6, 30),
                scheduled_trade_date=trade_date,
                ts_code=code,
                side="BUY",
                order_type="NEXT_OPEN",
                target_quantity=100,
                status="PENDING",
            )
            repository.insert_orders(run.id, [order])
            db.add_all(
                [
                    StockBasic(ts_code=code, exchange="SSE", market="主板"),
                    StockDaily(trade_date=trade_date, ts_code=code, open=10, close=10),
                    StockLimitDaily(
                        trade_date=trade_date,
                        ts_code=code,
                        up_limit=11,
                        down_limit=9,
                    ),
                    StockTradeStatusDaily(
                        trade_date=trade_date,
                        ts_code=code,
                        is_active=True,
                        is_suspended=False,
                        st_status_unknown=False,
                        tradable=True,
                        strategy_eligible=True,
                        calc_version=TRADE_STATUS_CALC_VERSION,
                        config_hash=strategy_hash,
                        calculated_at=datetime.now(UTC),
                    ),
                ]
            )
            db.flush()
            monkeypatch.setattr(db, "commit", db.flush)
            service = ExecutionApplicationService(
                db, account_gateway=AccountGateway(), settings=settings
            )
            result = service.execute_open_batch(run.id, trade_date)
            attempts = repository.list_order_attempts(run.id)
            fills = repository.list_fills(run.id)
            assert result.decisions[0].outcome == "EXECUTED"
            assert (order.status, order.attempt_count) == ("EXECUTED", 1)
            assert len(attempts) == len(fills) == 1
            assert fills[0].attempt_id == attempts[0].id
            assert fills[0].reference_price == Decimal("10.0000")
            assert fills[0].total_cost == (
                fills[0].cash_fee_total + fills[0].slippage_cost
            )

            missing_code = "M132B.SH"
            missing_order = PortfolioOrder(
                run_id=run.id,
                signal_trade_date=date(2026, 6, 30),
                scheduled_trade_date=trade_date,
                ts_code=missing_code,
                side="BUY",
                order_type="NEXT_OPEN",
                target_quantity=100,
                status="PENDING",
            )
            repository.insert_orders(run.id, [missing_order])
            with pytest.raises(ExecutionSourceNotReadyError):
                service.execute_open_batch(run.id, trade_date)
            assert missing_order.status == "PENDING"
            assert missing_order.attempt_count == 0
            assert repository.list_order_attempts(run.id, missing_order.id) == []

            old_run = _run()
            old_run.execution_version = "execution_v2"
            repository.create_run(old_run)
            with pytest.raises(BacktestContractMismatchError):
                service.execute_open_batch(old_run.id, trade_date)
        if transaction.is_active:
            transaction.rollback()
    engine.dispose()


def test_execution_application_preserves_three_day_attempt_history(monkeypatch) -> None:
    settings = get_settings()
    strategy_hash = analysis_strategy_hash(settings.strategy)
    days = [date(2026, 7, day) for day in (6, 7, 8)]
    code = "M132C.SH"

    class AccountGateway:
        def account_state(self, run_id, requested_date):
            return AccountState(requested_date, Decimal("100000"))

    engine = sa.create_engine(settings.database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, expire_on_commit=False) as db:
            repository = PortfolioRepository(db)
            run = repository.create_run(_run())
            order = PortfolioOrder(
                run_id=run.id,
                signal_trade_date=date(2026, 7, 3),
                scheduled_trade_date=days[0],
                ts_code=code,
                side="BUY",
                order_type="NEXT_OPEN",
                target_quantity=100,
                status="PENDING",
            )
            repository.insert_orders(run.id, [order])
            db.add(StockBasic(ts_code=code, exchange="SSE", market="主板"))
            for index, current in enumerate(days):
                db.add_all(
                    [
                        StockDaily(
                            trade_date=current,
                            ts_code=code,
                            open=11 if index < 2 else 10,
                            close=10,
                        ),
                        StockLimitDaily(
                            trade_date=current,
                            ts_code=code,
                            up_limit=11,
                            down_limit=9,
                        ),
                        StockTradeStatusDaily(
                            trade_date=current,
                            ts_code=code,
                            is_active=True,
                            is_suspended=False,
                            st_status_unknown=False,
                            tradable=True,
                            strategy_eligible=True,
                            calc_version=TRADE_STATUS_CALC_VERSION,
                            config_hash=strategy_hash,
                            calculated_at=datetime.now(UTC),
                        ),
                    ]
                )
            db.flush()
            monkeypatch.setattr(db, "commit", db.flush)
            service = ExecutionApplicationService(
                db, account_gateway=AccountGateway(), settings=settings
            )
            assert service.execute_open_batch(run.id, days[0]).decisions[0].outcome == (
                "RETRY"
            )
            assert service.execute_open_batch(run.id, days[1]).decisions[0].outcome == (
                "RETRY"
            )
            assert service.execute_open_batch(run.id, days[2]).decisions[0].outcome == (
                "EXECUTED"
            )
            attempts = repository.list_order_attempts(run.id, order.id)
            assert [item.outcome for item in attempts] == [
                "RETRY",
                "RETRY",
                "EXECUTED",
            ]
            assert [item.attempt_no for item in attempts] == [1, 2, 3]
            assert order.status == "EXECUTED"
            assert order.attempt_count == 3
            assert len(repository.list_fills(run.id)) == 1

            expiry_code = "M132E.SH"
            expiry_days = [date(2026, 7, day) for day in range(13, 18)]
            expiry_order = PortfolioOrder(
                run_id=run.id,
                signal_trade_date=date(2026, 7, 10),
                scheduled_trade_date=expiry_days[0],
                ts_code=expiry_code,
                side="BUY",
                order_type="NEXT_OPEN",
                target_quantity=100,
                status="PENDING",
            )
            repository.insert_orders(run.id, [expiry_order])
            db.add(StockBasic(ts_code=expiry_code, exchange="SSE", market="主板"))
            for current in expiry_days:
                db.add_all(
                    [
                        StockDaily(
                            trade_date=current,
                            ts_code=expiry_code,
                            open=10,
                            close=10,
                        ),
                        StockLimitDaily(
                            trade_date=current,
                            ts_code=expiry_code,
                            up_limit=11,
                            down_limit=9,
                        ),
                        StockTradeStatusDaily(
                            trade_date=current,
                            ts_code=expiry_code,
                            is_active=True,
                            is_suspended=True,
                            st_status_unknown=False,
                            tradable=False,
                            strategy_eligible=False,
                            calc_version=TRADE_STATUS_CALC_VERSION,
                            config_hash=strategy_hash,
                            calculated_at=datetime.now(UTC),
                        ),
                    ]
                )
            db.flush()
            expiry_outcomes = [
                service.execute_open_batch(run.id, current).decisions[0].outcome
                for current in expiry_days
            ]
            assert expiry_outcomes == ["RETRY", "RETRY", "RETRY", "RETRY", "EXPIRED"]
            assert expiry_order.status == "CANCELLED"
            assert expiry_order.reason_code == "EXPIRED"
            expiry_attempts = repository.list_order_attempts(run.id, expiry_order.id)
            assert len(expiry_attempts) == 5
            assert expiry_attempts[-1].outcome == "EXPIRED"
            assert expiry_attempts[-1].reason_code == "SUSPENDED"
        transaction.rollback()
    engine.dispose()


def test_attempt_and_fill_same_run_foreign_keys_reject_cross_run_rows() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            repository = PortfolioRepository(db)
            run_a = repository.create_run(_run())
            run_b = repository.create_run(_run())
            order_a = PortfolioOrder(
                run_id=run_a.id,
                signal_trade_date=date(2026, 9, 1),
                scheduled_trade_date=date(2026, 9, 2),
                ts_code="M132FK.SH",
                side="BUY",
                order_type="NEXT_OPEN",
                target_quantity=100,
                status="EXECUTED",
            )
            order_b = PortfolioOrder(
                run_id=run_b.id,
                signal_trade_date=date(2026, 9, 1),
                scheduled_trade_date=date(2026, 9, 2),
                ts_code="M132FB.SH",
                side="BUY",
                order_type="NEXT_OPEN",
                target_quantity=100,
                status="EXECUTED",
            )
            repository.insert_orders(run_a.id, [order_a])
            repository.insert_orders(run_b.id, [order_b])

            def attempt(run_id):
                return PortfolioOrderAttempt(
                    order_id=order_a.id,
                    run_id=run_id,
                    attempt_trade_date=date(2026, 9, 2),
                    attempt_no=1,
                    outcome="EXECUTED",
                    requested_quantity=100,
                    fill_quantity=100,
                    reference_price=Decimal("10"),
                    fill_price=Decimal("10"),
                    gross_amount=Decimal("1000"),
                )

            with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
                db.add(attempt(run_b.id))
                db.flush()
            valid_attempt = attempt(run_a.id)
            db.add(valid_attempt)
            other_attempt = PortfolioOrderAttempt(
                order_id=order_b.id,
                run_id=run_b.id,
                attempt_trade_date=date(2026, 9, 2),
                attempt_no=1,
                outcome="EXECUTED",
                requested_quantity=100,
                fill_quantity=100,
                reference_price=Decimal("10"),
                fill_price=Decimal("10"),
                gross_amount=Decimal("1000"),
            )
            db.add(other_attempt)
            db.flush()
            cross_fill = PortfolioFill(
                order_id=order_a.id,
                attempt_id=other_attempt.id,
                run_id=run_a.id,
                trade_date=date(2026, 9, 2),
                ts_code="M132FK.SH",
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
            with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
                db.add(cross_fill)
                db.flush()
        transaction.rollback()
    engine.dispose()


def test_0031_migration_backfills_historical_fill(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("path_separator", "os")
    migration = ScriptDirectory.from_config(config).get_revision(
        "0031_m13_2_execution_audit"
    ).module
    schema = f"m13_2_fill_{uuid.uuid4().hex}"
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            metadata = sa.MetaData()
            order_table = sa.Table(
                "portfolio_order",
                metadata,
                sa.Column("id", sa.UUID(), primary_key=True),
                sa.Column("run_id", sa.UUID(), nullable=False),
                sa.UniqueConstraint("id", "run_id"),
            )
            fill_table = sa.Table(
                "portfolio_fill",
                metadata,
                sa.Column("id", sa.UUID(), primary_key=True),
                sa.Column("order_id", sa.UUID(), nullable=False),
                sa.Column("run_id", sa.UUID(), nullable=False),
                sa.Column("price", sa.Numeric(18, 4), nullable=False),
                sa.Column("commission", sa.Numeric(20, 4), nullable=False),
                sa.Column("stamp_tax", sa.Numeric(20, 4), nullable=False),
                sa.Column("slippage_cost", sa.Numeric(20, 4), nullable=False),
                sa.Column("total_cost", sa.Numeric(20, 4), nullable=False),
            )
            metadata.create_all(connection)
            run_id, order_id, fill_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            connection.execute(
                order_table.insert().values(id=order_id, run_id=run_id)
            )
            connection.execute(
                fill_table.insert().values(
                    id=fill_id,
                    order_id=order_id,
                    run_id=run_id,
                    price=Decimal("10.25"),
                    commission=Decimal("5"),
                    stamp_tax=Decimal("0.5"),
                    slippage_cost=Decimal("1"),
                    total_cost=Decimal("6.5"),
                )
            )
            monkeypatch.setattr(
                migration, "op", Operations(MigrationContext.configure(connection))
            )
            migration.upgrade()
            row = connection.execute(
                sa.text(
                    """
                    SELECT attempt_id, reference_price, transfer_fee,
                           cash_fee_total, total_cost
                    FROM portfolio_fill WHERE id = :fill_id
                    """
                ),
                {"fill_id": fill_id},
            ).mappings().one()
            assert row["attempt_id"] is None
            assert row["reference_price"] == Decimal("10.2500")
            assert row["transfer_fee"] == Decimal("0.0000")
            assert row["cash_fee_total"] == Decimal("5.5000")
            assert row["total_cost"] == Decimal("6.5000")
            migration.downgrade()
            columns = {
                item["name"]
                for item in sa.inspect(connection).get_columns(
                    "portfolio_fill", schema=schema
                )
            }
            assert "reference_price" not in columns
        finally:
            transaction.rollback()
    engine.dispose()


def test_invalid_quantity_order_does_not_rollback_valid_order(monkeypatch) -> None:
    settings = get_settings()
    strategy_hash = analysis_strategy_hash(settings.strategy)
    trade_date = date(2026, 9, 3)
    invalid_code = "M132N.SH"
    valid_code = "M132V.SH"

    class AccountGateway:
        def account_state(self, run_id, requested_date):
            return AccountState(requested_date, Decimal("100000"))

    engine = sa.create_engine(settings.database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, expire_on_commit=False) as db:
            repository = PortfolioRepository(db)
            run = repository.create_run(_run())
            invalid_order = PortfolioOrder(
                run_id=run.id,
                signal_trade_date=date(2026, 9, 2),
                scheduled_trade_date=trade_date,
                ts_code=invalid_code,
                side="BUY",
                order_type="NEXT_OPEN",
                target_quantity=None,
                status="PENDING",
            )
            valid_order = PortfolioOrder(
                run_id=run.id,
                signal_trade_date=date(2026, 9, 2),
                scheduled_trade_date=trade_date,
                ts_code=valid_code,
                side="BUY",
                order_type="NEXT_OPEN",
                target_quantity=100,
                status="PENDING",
            )
            repository.insert_orders(run.id, [invalid_order, valid_order])
            for code in (invalid_code, valid_code):
                db.add_all(
                    [
                        StockBasic(ts_code=code, exchange="SSE", market="主板"),
                        StockDaily(
                            trade_date=trade_date,
                            ts_code=code,
                            open=10,
                            close=10,
                        ),
                        StockLimitDaily(
                            trade_date=trade_date,
                            ts_code=code,
                            up_limit=11,
                            down_limit=9,
                        ),
                        StockTradeStatusDaily(
                            trade_date=trade_date,
                            ts_code=code,
                            is_active=True,
                            is_suspended=False,
                            st_status_unknown=False,
                            tradable=True,
                            strategy_eligible=True,
                            calc_version=TRADE_STATUS_CALC_VERSION,
                            config_hash=strategy_hash,
                            calculated_at=datetime.now(UTC),
                        ),
                    ]
                )
            db.flush()
            monkeypatch.setattr(db, "commit", db.flush)

            result = ExecutionApplicationService(
                db,
                account_gateway=AccountGateway(),
                settings=settings,
            ).execute_open_batch(run.id, trade_date)

            decisions = {item.intent.ts_code: item for item in result.decisions}
            assert decisions[invalid_code].reason_code == "INVALID_QUANTITY"
            assert decisions[valid_code].outcome == "EXECUTED"
            assert (invalid_order.status, invalid_order.reason_code) == (
                "REJECTED",
                "INVALID_QUANTITY",
            )
            assert valid_order.status == "EXECUTED"
            invalid_attempt = repository.list_order_attempts(
                run.id, invalid_order.id
            )[0]
            assert (invalid_attempt.outcome, invalid_attempt.requested_quantity) == (
                "REJECTED",
                0,
            )
            assert repository.list_order_attempts(run.id, valid_order.id)[0].outcome == (
                "EXECUTED"
            )
            fills = repository.list_fills(run.id)
            assert len(fills) == 1
            assert fills[0].order_id == valid_order.id
        transaction.rollback()
    engine.dispose()


def test_execution_integrity_database_checks_reject_invalid_rows() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            repository = PortfolioRepository(db)
            run = repository.create_run(_run())
            order = PortfolioOrder(
                run_id=run.id,
                signal_trade_date=date(2026, 9, 2),
                scheduled_trade_date=date(2026, 9, 3),
                ts_code="M132Q.SH",
                side="BUY",
                order_type="NEXT_OPEN",
                target_quantity=100,
                status="PENDING",
            )
            repository.insert_orders(run.id, [order])

            with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
                db.add(
                    PortfolioOrder(
                        run_id=run.id,
                        signal_trade_date=date(2026, 9, 2),
                        scheduled_trade_date=date(2026, 9, 3),
                        ts_code="M132Z.SH",
                        side="BUY",
                        order_type="NEXT_OPEN",
                        target_quantity=0,
                        status="PENDING",
                    )
                )
                db.flush()

            base = {
                "id": uuid.uuid4(),
                "order_id": order.id,
                "run_id": run.id,
                "attempt_trade_date": date(2026, 9, 3),
                "attempt_no": 1,
                "outcome": "EXECUTED",
                "reason_code": None,
                "requested_quantity": 100,
                "fill_quantity": 100,
                "reference_price": Decimal("10"),
                "fill_price": Decimal("10"),
                "gross_amount": Decimal("1000"),
                "commission": Decimal("5"),
                "stamp_tax": Decimal("0"),
                "transfer_fee": Decimal("0"),
                "cash_fee_total": Decimal("5"),
                "slippage_cost": Decimal("0"),
                "total_cost": Decimal("5"),
                "market_snapshot": {},
                "account_snapshot": {},
            }
            invalid_overrides = (
                {"reason_code": "UNEXPECTED"},
                {
                    "outcome": "REJECTED",
                    "reason_code": None,
                    "fill_quantity": 0,
                    "fill_price": None,
                    "gross_amount": Decimal("0"),
                    "commission": Decimal("0"),
                    "cash_fee_total": Decimal("0"),
                    "total_cost": Decimal("0"),
                },
                {
                    "outcome": "RETRY",
                    "reason_code": "LIMIT_UP",
                    "requested_quantity": 0,
                    "fill_quantity": 0,
                    "reference_price": Decimal("10"),
                    "fill_price": None,
                    "gross_amount": Decimal("0"),
                    "commission": Decimal("0"),
                    "cash_fee_total": Decimal("0"),
                    "total_cost": Decimal("0"),
                },
                {
                    "requested_quantity": 0,
                    "fill_quantity": 0,
                    "gross_amount": Decimal("0"),
                },
                {"fill_quantity": 99},
                {"fill_price": None},
                {
                    "outcome": "RETRY",
                    "reason_code": "LIMIT_UP",
                    "fill_quantity": 1,
                    "fill_price": None,
                    "gross_amount": Decimal("0"),
                    "commission": Decimal("0"),
                    "cash_fee_total": Decimal("0"),
                    "total_cost": Decimal("0"),
                },
                {
                    "outcome": "REJECTED",
                    "reason_code": "INVALID_LOT",
                    "fill_quantity": 0,
                    "fill_price": None,
                    "gross_amount": Decimal("0"),
                    "commission": Decimal("1"),
                    "cash_fee_total": Decimal("1"),
                    "total_cost": Decimal("1"),
                },
                {"cash_fee_total": Decimal("6"), "total_cost": Decimal("6")},
                {"total_cost": Decimal("6")},
            )
            for overrides in invalid_overrides:
                values = {**base, **overrides, "id": uuid.uuid4()}
                with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
                    db.execute(sa.insert(PortfolioOrderAttempt).values(**values))

            invalid_quantity = {
                **base,
                "id": uuid.uuid4(),
                "outcome": "REJECTED",
                "reason_code": "INVALID_QUANTITY",
                "requested_quantity": 0,
                "fill_quantity": 0,
                "reference_price": None,
                "fill_price": None,
                "gross_amount": Decimal("0"),
                "commission": Decimal("0"),
                "cash_fee_total": Decimal("0"),
                "total_cost": Decimal("0"),
            }
            db.execute(sa.insert(PortfolioOrderAttempt).values(**invalid_quantity))
            db.flush()
        transaction.rollback()
    engine.dispose()


def test_0032_migration_preflights_and_fail_safe_downgrade(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("path_separator", "os")
    migration = ScriptDirectory.from_config(config).get_revision(
        "0032_m13_2_1_execution_integrity"
    ).module
    schema = f"m13_2_1_integrity_{uuid.uuid4().hex}"
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            metadata = sa.MetaData()
            order_table = sa.Table(
                "portfolio_order",
                metadata,
                sa.Column("id", sa.UUID(), primary_key=True),
                sa.Column("target_quantity", sa.BigInteger()),
                sa.CheckConstraint(
                    "target_quantity IS NULL OR target_quantity >= 0",
                    name="ck_portfolio_order_target_quantity",
                ),
            )
            attempt_table = sa.Table(
                "portfolio_order_attempt",
                metadata,
                sa.Column("id", sa.UUID(), primary_key=True),
                sa.Column("outcome", sa.String(16), nullable=False),
                sa.Column("reason_code", sa.String(64)),
                sa.Column("requested_quantity", sa.BigInteger(), nullable=False),
                sa.Column("fill_quantity", sa.BigInteger(), nullable=False),
                sa.Column("reference_price", sa.Numeric(18, 4)),
                sa.Column("fill_price", sa.Numeric(18, 4)),
                sa.Column("gross_amount", sa.Numeric(20, 4), nullable=False),
                sa.Column("commission", sa.Numeric(20, 4), nullable=False),
                sa.Column("stamp_tax", sa.Numeric(20, 4), nullable=False),
                sa.Column("transfer_fee", sa.Numeric(20, 4), nullable=False),
                sa.Column("cash_fee_total", sa.Numeric(20, 4), nullable=False),
                sa.Column("slippage_cost", sa.Numeric(20, 4), nullable=False),
                sa.Column("total_cost", sa.Numeric(20, 4), nullable=False),
                sa.CheckConstraint(
                    "requested_quantity > 0",
                    name="ck_portfolio_order_attempt_requested_quantity",
                ),
            )
            metadata.create_all(connection)
            monkeypatch.setattr(
                migration, "op", Operations(MigrationContext.configure(connection))
            )

            zero_order_id = uuid.uuid4()
            connection.execute(
                order_table.insert().values(id=zero_order_id, target_quantity=0)
            )
            with pytest.raises(RuntimeError, match="1 order.*target_quantity = 0"):
                migration.upgrade()
            connection.execute(
                order_table.delete().where(order_table.c.id == zero_order_id)
            )

            dirty_attempt_id = uuid.uuid4()
            connection.execute(
                attempt_table.insert().values(
                    id=dirty_attempt_id,
                    outcome="EXECUTED",
                    reason_code=None,
                    requested_quantity=100,
                    fill_quantity=99,
                    reference_price=Decimal("10"),
                    fill_price=Decimal("10"),
                    gross_amount=Decimal("1000"),
                    commission=Decimal("5"),
                    stamp_tax=Decimal("0"),
                    transfer_fee=Decimal("0"),
                    cash_fee_total=Decimal("5"),
                    slippage_cost=Decimal("0"),
                    total_cost=Decimal("5"),
                )
            )
            with pytest.raises(RuntimeError, match="1 violating historical attempt"):
                migration.upgrade()
            connection.execute(
                attempt_table.delete().where(attempt_table.c.id == dirty_attempt_id)
            )

            migration.upgrade()
            zero_attempt_id = uuid.uuid4()
            connection.execute(
                attempt_table.insert().values(
                    id=zero_attempt_id,
                    outcome="REJECTED",
                    reason_code="INVALID_QUANTITY",
                    requested_quantity=0,
                    fill_quantity=0,
                    reference_price=None,
                    fill_price=None,
                    gross_amount=Decimal("0"),
                    commission=Decimal("0"),
                    stamp_tax=Decimal("0"),
                    transfer_fee=Decimal("0"),
                    cash_fee_total=Decimal("0"),
                    slippage_cost=Decimal("0"),
                    total_cost=Decimal("0"),
                )
            )
            with pytest.raises(RuntimeError, match="1 attempt.*requested_quantity = 0"):
                migration.downgrade()
            assert connection.scalar(
                sa.select(sa.func.count()).select_from(attempt_table)
            ) == 1
            connection.execute(
                attempt_table.delete().where(attempt_table.c.id == zero_attempt_id)
            )
            migration.downgrade()
            migration.upgrade()
        finally:
            transaction.rollback()
    engine.dispose()
