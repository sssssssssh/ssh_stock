from datetime import date
from decimal import Decimal

import app.services.portfolio.candidates as candidate_module
import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.core.db import get_db
from app.main import app
from app.models.market_data import StockOpportunityDaily, StockStateDaily
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
    OPPORTUNITY_CALC_VERSION,
    PORTFOLIO_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.portfolio.application import PortfolioApplicationService
from app.services.portfolio.candidates import OpportunityCandidateProvider
from app.services.portfolio.contracts import SourceReadinessStatus
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
            run = service.create_backtest_definition(
                name="identity-test",
                start_date=date(2026, 9, 1),
                end_date=date(2026, 9, 30),
            )
            assert run.status == "CREATED"
            assert run.backtest_engine_version == "backtest_v2"
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


def test_candidate_provider_real_db_current_identity_and_no_fallback(monkeypatch) -> None:
    settings = get_settings()
    target = date(2099, 1, 15)
    old_only = date(2099, 1, 16)
    common = {
        "state": "S4",
        "opportunity_stage": "TREND",
        "reason_codes": ["TREND"],
        "calc_version": OPPORTUNITY_CALC_VERSION,
        "config_hash": config_hash(settings.opportunity_config),
        "source_strategy_config_hash": analysis_strategy_hash(settings.strategy),
        "calculated_at": sa.func.now(),
    }
    engine = sa.create_engine(settings.database_url)
    monkeypatch.setattr(candidate_module, "is_core_analysis_complete", lambda *a, **k: True)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            db.add_all(
                [
                    StockStateDaily(
                        trade_date=target,
                        ts_code="990001.SZ",
                        algo_version=settings.algo_version,
                        state="S4",
                        is_new_state=False,
                        fast_transition=False,
                        calc_version=TREND_CALC_VERSION,
                        config_hash=analysis_strategy_hash(settings.strategy),
                    ),
                    StockStateDaily(
                        trade_date=target,
                        ts_code="990000.SZ",
                        algo_version=settings.algo_version,
                        state="S4",
                        is_new_state=False,
                        fast_transition=False,
                        calc_version=TREND_CALC_VERSION,
                        config_hash=analysis_strategy_hash(settings.strategy),
                    ),
                    StockOpportunityDaily(
                        trade_date=target,
                        ts_code="990001.SZ",
                        algo_version=settings.algo_version,
                        opportunity_score=90,
                        **common,
                    ),
                    StockOpportunityDaily(
                        trade_date=target,
                        ts_code="990000.SZ",
                        algo_version=settings.algo_version,
                        opportunity_score=90,
                        **common,
                    ),
                    StockOpportunityDaily(
                        trade_date=target,
                        ts_code="990099.SZ",
                        algo_version="old-algo",
                        opportunity_score=99,
                        **common,
                    ),
                    StockOpportunityDaily(
                        trade_date=target,
                        ts_code="990097.SZ",
                        algo_version=settings.algo_version,
                        opportunity_score=99,
                        **{**common, "calc_version": "old-opportunity"},
                    ),
                    StockOpportunityDaily(
                        trade_date=target,
                        ts_code="990096.SZ",
                        algo_version=settings.algo_version,
                        opportunity_score=99,
                        **{**common, "config_hash": "old-opportunity-config"},
                    ),
                    StockOpportunityDaily(
                        trade_date=target,
                        ts_code="990095.SZ",
                        algo_version=settings.algo_version,
                        opportunity_score=99,
                        **{**common, "source_strategy_config_hash": "old-strategy"},
                    ),
                    StockOpportunityDaily(
                        trade_date=old_only,
                        ts_code="990098.SZ",
                        algo_version="old-algo",
                        opportunity_score=99,
                        **common,
                    ),
                ]
            )
            db.flush()
            provider = OpportunityCandidateProvider(db, settings)
            current = provider.list_candidates(target, settings.portfolio_config)
            unavailable = provider.list_candidates(old_only, settings.portfolio_config)
            no_fallback = provider.list_candidates(date(2099, 1, 17), settings.portfolio_config)
            assert [item.ts_code for item in current.candidates] == [
                "990000.SZ",
                "990001.SZ",
            ]
            assert current.source_status == SourceReadinessStatus.READY
            assert current.state_count == current.opportunity_count == 2
            assert unavailable.source_status == SourceReadinessStatus.UNAVAILABLE
            assert no_fallback.source_status == SourceReadinessStatus.UNAVAILABLE
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
