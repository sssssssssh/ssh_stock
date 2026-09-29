from datetime import UTC, date, datetime
from decimal import Decimal

import app.services.portfolio.source_integrity as source_integrity_module
import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.core.db import get_db
from app.main import app
from app.models.market_data import (
    StockBasic,
    StockDaily,
    StockFactorDaily,
    StockOpportunityDaily,
    StockStateDaily,
    StockSuspendDaily,
)
from app.models.portfolio import (
    PortfolioBacktestRun,
    PortfolioFill,
    PortfolioNavDaily,
    PortfolioOrder,
    PortfolioPositionDaily,
)
from app.repositories.portfolio import PortfolioRepository
from app.services.analysis_identity import (
    BACKTEST_ENGINE_VERSION,
    EXECUTION_VERSION,
    FACTOR_CALC_VERSION,
    OPPORTUNITY_CALC_VERSION,
    PORTFOLIO_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.portfolio.application import PortfolioApplicationService
from app.services.portfolio.contracts import SourceReadinessStatus
from app.services.portfolio.source_integrity import check_portfolio_source_integrity
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _run() -> PortfolioBacktestRun:
    settings = get_settings()
    portfolio = settings.portfolio_config.model_dump(mode="json")
    execution = settings.execution_config.model_dump(mode="json")
    return PortfolioBacktestRun(
        account_mode="BACKTEST",
        status="CREATED",
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
        backtest_engine_version=BACKTEST_ENGINE_VERSION,
        config_snapshot={
            "strategy": settings.strategy,
            "opportunity": settings.opportunity_config,
            "portfolio": portfolio,
            "execution": execution,
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
            repository.insert_fills(
                run.id,
                [
                    PortfolioFill(
                        order_id=order.id,
                        run_id=run.id,
                        trade_date=date(2026, 9, 2),
                        ts_code="000001.SZ",
                        side="BUY",
                        quantity=100,
                        price=Decimal("10"),
                        gross_amount=Decimal("1000"),
                        commission=Decimal("5"),
                        stamp_tax=Decimal("0"),
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
            assert run.backtest_engine_version == "backtest_v3"
            assert service.get_backtest(historical.id).backtest_engine_version == (
                "backtest_v2"
            )
            assert set(run.config_snapshot) == {
                "strategy",
                "opportunity",
                "portfolio",
                "execution",
            }
            assert run.portfolio_config_hash == config_hash(run.config_snapshot["portfolio"])
            assert run.execution_config_hash == config_hash(run.config_snapshot["execution"])
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
                    gross_amount=Decimal("1000"),
                    commission=Decimal("0"),
                    stamp_tax=Decimal("0"),
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
    engine.dispose()
