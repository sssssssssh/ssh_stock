import importlib.util
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.core.accounting_config import AccountingConfig
from app.core.config import get_settings
from app.domain.execution import InstrumentExecutionProfile
from app.domain.portfolio import (
    AccountState,
    DailyPortfolioSnapshot,
    PendingOrderState,
    PortfolioTarget,
    PositionState,
    TargetPosition,
)
from app.services.analysis_identity import (
    ACCOUNTING_VERSION,
    BACKTEST_ENGINE_VERSION,
    PORTFOLIO_VERSION,
)
from app.services.portfolio.accounting import (
    ACCOUNTING_SOURCE_INCOMPLETE,
    UNSUPPORTED_CORPORATE_ACTION,
    UNSUPPORTED_INACTIVE_HELD_POSITION,
    AccountingEngine,
    AccountingFill,
    AccountingMarketSnapshot,
    AccountingSourceError,
)
from app.services.portfolio.accounting_application import AccountingApplicationService
from app.services.portfolio.rebalance import (
    DELTA_BELOW_MIN_ORDER,
    NEW_POSITION_DAILY_CAP,
    SUPERSEDED_BY_REBALANCE,
    RebalancePlanner,
)
from app.services.portfolio.run_guard import BacktestContractMismatchError
from pydantic import ValidationError

DAY = date(2026, 9, 1)
NEXT_DAY = date(2026, 9, 2)


def _profile(
    code: str,
    *,
    minimum: int = 100,
    step: int = 100,
    maximum: int = 1_000_000,
) -> InstrumentExecutionProfile:
    return InstrumentExecutionProfile(
        ts_code=code,
        exchange="SSE",
        market="main",
        min_buy_quantity=minimum,
        buy_step=step,
        max_buy_quantity=maximum,
        min_sell_quantity=minimum,
        sell_step=step,
        max_sell_quantity=maximum,
    )


def _position(
    code: str = "A.SZ",
    *,
    quantity: int = 100,
    available: int = 0,
    avg: str = "10",
    close: str | None = "11",
) -> PositionState:
    close_value = Decimal(close) if close is not None else None
    return PositionState(
        ts_code=code,
        quantity=quantity,
        available_quantity=available,
        avg_cost=Decimal(avg),
        market_value=(close_value or Decimal("0")) * quantity,
        close_price=close_value,
    )


def _snapshot(*positions: PositionState, total: str = "1000000") -> DailyPortfolioSnapshot:
    return DailyPortfolioSnapshot(
        trade_date=DAY,
        cash=Decimal(total) - sum((p.market_value for p in positions), Decimal("0")),
        total_assets=Decimal(total),
        nav=Decimal("1"),
        positions=tuple(positions),
        market_value=sum((p.market_value for p in positions), Decimal("0")),
    )


def _target(*items: tuple[str, str, str]) -> PortfolioTarget:
    return PortfolioTarget(
        signal_trade_date=DAY,
        targets=tuple(
            TargetPosition(
                ts_code=code,
                target_weight=Decimal(weight),
                source_score=Decimal(score),
            )
            for code, weight, score in items
        ),
        target_cash_ratio=Decimal("0"),
        source_available=True,
    )


def _market(
    code: str = "A.SZ",
    *,
    active: bool = True,
    suspended: bool = False,
    close: str | None = "11",
    previous_factor: str | None = "1",
    current_factor: str | None = "1",
) -> AccountingMarketSnapshot:
    return AccountingMarketSnapshot(
        ts_code=code,
        status_present=True,
        is_active=active,
        is_suspended=suspended,
        close_price=Decimal(close) if close is not None else None,
        previous_adj_factor=(
            Decimal(previous_factor) if previous_factor is not None else None
        ),
        current_adj_factor=(
            Decimal(current_factor) if current_factor is not None else None
        ),
    )


def test_m13_3_versions_and_strict_accounting_config() -> None:
    settings = get_settings()
    assert PORTFOLIO_VERSION == settings.portfolio_config.version == "portfolio_v3"
    assert ACCOUNTING_VERSION == settings.accounting_config.version == "accounting_v2"
    assert BACKTEST_ENGINE_VERSION == "backtest_v5"
    raw = settings.accounting_config.model_dump(mode="python")
    raw["unknown"] = True
    with pytest.raises(ValidationError):
        AccountingConfig.model_validate(raw)


def test_accounting_application_rejects_historical_identity() -> None:
    class Database:
        def __init__(self):
            self.rolled_back = False

        def rollback(self):
            self.rolled_back = True

    class Repository:
        def get_run_for_update(self, _run_id):
            return SimpleNamespace(
                account_mode="BACKTEST",
                status="RUNNING",
                portfolio_version="portfolio_v3",
                execution_version="execution_v3",
                accounting_version="accounting_v0_unimplemented",
                backtest_engine_version="backtest_v5",
            )

    database = Database()
    service = AccountingApplicationService(database, repository=Repository())
    with pytest.raises(BacktestContractMismatchError, match="accounting_v0"):
        service.rebuild_close_snapshot(uuid.uuid4(), DAY)
    assert database.rolled_back is True


def test_open_state_first_day_and_t_plus_one_unlock() -> None:
    engine = AccountingEngine()
    first = engine.open_state(
        trade_date=DAY, initial_cash=Decimal("1000"), previous_snapshot=None
    )
    assert first == AccountState(DAY, Decimal("1000"))
    prior = _snapshot(_position(quantity=300, available=0), total="4000")
    rolled = engine.open_state(
        trade_date=NEXT_DAY,
        initial_cash=Decimal("1000"),
        previous_snapshot=prior,
    )
    assert rolled.positions[0].available_quantity == 300


def test_buy_capitalizes_cash_fee_without_double_deducting_slippage() -> None:
    engine = AccountingEngine()
    account = AccountState(DAY, Decimal("2000"))
    fill = AccountingFill(
        fill_id=uuid.uuid4(),
        order_id=uuid.uuid4(),
        scheduled_trade_date=DAY,
        ts_code="A.SZ",
        side="BUY",
        quantity=100,
        price=Decimal("10"),
        gross_amount=Decimal("1000"),
        cash_fee_total=Decimal("5"),
        total_cost=Decimal("7"),
    )
    result, cost = engine.apply_fills(account, [fill])
    assert result.cash == Decimal("995")
    assert result.positions[0].avg_cost == Decimal("10.05")
    assert result.positions[0].available_quantity == 0
    assert cost == Decimal("7")


def test_sell_then_buy_replay_and_realized_pnl() -> None:
    engine = AccountingEngine()
    account = AccountState(DAY, Decimal("1000"), (_position(available=100),))
    buy = AccountingFill(
        uuid.UUID(int=1), uuid.UUID(int=2), DAY, "A.SZ", "BUY", 100,
        Decimal("8"), Decimal("800"), Decimal("2"), Decimal("2"),
    )
    sell = AccountingFill(
        uuid.UUID(int=3), uuid.UUID(int=4), DAY, "A.SZ", "SELL", 50,
        Decimal("12"), Decimal("600"), Decimal("1"), Decimal("1"),
    )
    result, _ = engine.apply_fills(account, [buy, sell])
    position = result.positions[0]
    assert result.cash == Decimal("797")
    assert position.quantity == 150
    assert position.available_quantity == 50
    assert position.realized_pnl == Decimal("99")
    assert position.avg_cost == Decimal("8.68")


def test_mark_to_market_raw_and_suspended_carry() -> None:
    engine = AccountingEngine()
    account = AccountState(DAY, Decimal("100"), (_position(available=100),))
    raw = engine.mark_to_market(
        account=account,
        market={"A.SZ": _market(close="12")},
        initial_cash=Decimal("1000"),
        trading_cost=Decimal("2"),
    )
    assert raw.positions[0].valuation_source == "RAW_CLOSE"
    assert raw.total_assets == Decimal("1300")
    carried = engine.mark_to_market(
        account=account,
        market={"A.SZ": _market(close=None, suspended=True)},
        initial_cash=Decimal("1000"),
        trading_cost=Decimal("0"),
    )
    assert carried.positions[0].close_price == Decimal("11")
    assert carried.positions[0].valuation_source == "CARRY_FORWARD"


@pytest.mark.parametrize(
    ("market", "reason"),
    [
        (_market(close=None), ACCOUNTING_SOURCE_INCOMPLETE),
        (_market(active=False), UNSUPPORTED_INACTIVE_HELD_POSITION),
    ],
)
def test_mark_to_market_fail_closed(market, reason) -> None:
    with pytest.raises(AccountingSourceError) as exc:
        AccountingEngine().mark_to_market(
            account=AccountState(DAY, Decimal("100"), (_position(),)),
            market={"A.SZ": market},
            initial_cash=Decimal("1000"),
            trading_cost=Decimal("0"),
        )
    assert exc.value.reason_code == reason


@pytest.mark.parametrize(
    ("market", "reason"),
    [
        (_market(previous_factor=None), ACCOUNTING_SOURCE_INCOMPLETE),
        (_market(current_factor="2"), UNSUPPORTED_CORPORATE_ACTION),
    ],
)
def test_start_of_day_corporate_action_gate(market, reason) -> None:
    with pytest.raises(AccountingSourceError) as exc:
        AccountingEngine().validate_start_of_day(
            AccountState(DAY, Decimal("0"), (_position(),)), {"A.SZ": market}
        )
    assert exc.value.reason_code == reason


def test_rebalance_sizing_main_star_bse_and_small_delta() -> None:
    planner = RebalancePlanner()
    config = get_settings().portfolio_config
    target = _target(
        ("MAIN.SZ", "0.10", "90"),
        ("STAR.SH", "0.00199", "80"),
        ("BSE.BJ", "0.00099", "70"),
    )
    result = planner.plan(
        target=target,
        account=_snapshot(),
        pending_orders=(),
        close_prices={code: Decimal("10") for code in ("MAIN.SZ", "STAR.SH", "BSE.BJ")},
        instrument_profiles={
            "MAIN.SZ": _profile("MAIN.SZ"),
            "STAR.SH": _profile("STAR.SH", minimum=200, step=1, maximum=100_000),
            "BSE.BJ": _profile("BSE.BJ", minimum=100, step=1),
        },
        scheduled_trade_date=NEXT_DAY,
        config=config,
    )
    quantities = {item.ts_code: item.target_quantity for item in result.targets}
    assert quantities == {"BSE.BJ": 0, "MAIN.SZ": 10000, "STAR.SH": 0}
    assert {item.reason_code for item in result.skipped_targets} == set()


@pytest.mark.parametrize(
    ("code", "current", "target_quantity", "minimum", "step", "expected_order", "projected"),
    [
        ("STAR.SH", 250, 150, 200, 1, None, 250),
        ("STAR.SH", 250, 50, 200, 1, ("SELL", 200), 50),
        ("MAIN.SZ", 100, 150, 100, 100, None, 100),
        ("BSE.BJ", 150, 90, 100, 100, None, 150),
    ],
)
def test_existing_position_preserves_economic_target_and_skips_illegal_delta(
    code,
    current,
    target_quantity,
    minimum,
    step,
    expected_order,
    projected,
) -> None:
    total = Decimal("10000")
    price = Decimal("10")
    result = RebalancePlanner().plan(
        target=_target((code, str(Decimal(target_quantity) * price / total), "90")),
        account=_snapshot(
            _position(code, quantity=current, available=current, close="10"),
            total=str(total),
        ),
        pending_orders=(),
        close_prices={code: price},
        instrument_profiles={
            code: _profile(code, minimum=minimum, step=step, maximum=1_000_000)
        },
        scheduled_trade_date=NEXT_DAY,
        config=get_settings().portfolio_config,
    )
    planned = result.targets[0]
    assert planned.target_quantity == target_quantity
    assert planned.projected_quantity == projected
    orders = [(item.side, item.quantity) for item in result.new_orders]
    assert orders == ([] if expected_order is None else [expected_order])
    if expected_order is None:
        assert result.skipped_targets[0].reason_code == DELTA_BELOW_MIN_ORDER


def test_existing_position_full_liquidation_and_new_star_threshold() -> None:
    profile = _profile("STAR.SH", minimum=200, step=1, maximum=100_000)
    liquidation = RebalancePlanner().plan(
        target=_target(),
        account=_snapshot(
            _position("STAR.SH", quantity=250, available=250, close="10"),
            total="10000",
        ),
        pending_orders=(),
        close_prices={},
        instrument_profiles={"STAR.SH": profile},
        scheduled_trade_date=NEXT_DAY,
        config=get_settings().portfolio_config,
    )
    assert [(item.side, item.quantity) for item in liquidation.new_orders] == [
        ("SELL", 250)
    ]
    assert liquidation.targets[0].projected_quantity == 0

    for raw, expected in ((199, 0), (200, 200)):
        total = Decimal(raw * 10)
        opened = RebalancePlanner().plan(
            target=_target(("STAR.SH", "1", "90")),
            account=_snapshot(total=str(total)),
            pending_orders=(),
            close_prices={"STAR.SH": Decimal("10")},
            instrument_profiles={"STAR.SH": profile},
            scheduled_trade_date=NEXT_DAY,
            config=get_settings().portfolio_config,
        )
        assert opened.targets[0].target_quantity == expected
        assert opened.targets[0].projected_quantity == expected


def test_pending_reconcile_keep_cancel_and_topup() -> None:
    keep_id, cancel_id = uuid.uuid4(), uuid.uuid4()
    result = RebalancePlanner().plan(
        target=_target(("A.SZ", "0.10", "90")),
        account=_snapshot(),
        pending_orders=(
            PendingOrderState(keep_id, "A.SZ", "BUY", 6000, 2),
            PendingOrderState(cancel_id, "A.SZ", "SELL", 100, 1),
        ),
        close_prices={"A.SZ": Decimal("10")},
        instrument_profiles={"A.SZ": _profile("A.SZ")},
        scheduled_trade_date=NEXT_DAY,
        config=get_settings().portfolio_config,
    )
    actions = {item.order_id: (item.action, item.reason_code) for item in result.pending_actions}
    assert actions[keep_id] == ("KEEP", None)
    assert actions[cancel_id] == ("CANCEL", SUPERSEDED_BY_REBALANCE)
    assert [item.quantity for item in result.new_orders] == [4000]


def test_new_position_cap_is_score_then_code_deterministic() -> None:
    config = get_settings().portfolio_config.model_copy(
        update={
            "construction": get_settings().portfolio_config.construction.model_copy(
                update={"max_new_positions_per_day": 2}
            )
        }
    )
    items = (("B.SZ", "0.1", "90"), ("A.SZ", "0.1", "90"), ("C.SZ", "0.1", "80"))
    result = RebalancePlanner().plan(
        target=_target(*items),
        account=_snapshot(),
        pending_orders=(),
        close_prices={code: Decimal("10") for code, _, _ in items},
        instrument_profiles={code: _profile(code) for code, _, _ in items},
        scheduled_trade_date=NEXT_DAY,
        config=config,
    )
    assert {item.ts_code for item in result.new_orders} == {"A.SZ", "B.SZ"}
    assert result.skipped_targets == ((
        result.skipped_targets[0]
    ),)
    assert result.skipped_targets[0].reason_code == NEW_POSITION_DAILY_CAP


def test_deterministic_child_split_and_odd_lot_liquidation() -> None:
    split = RebalancePlanner._split_quantity(
        1_500_000,
        side="BUY",
        profile=_profile("A.SZ"),
        full_liquidation=False,
    )
    assert split == (1_000_000, 500_000)
    star = RebalancePlanner._split_quantity(
        100_050,
        side="BUY",
        profile=_profile("STAR.SH", minimum=200, step=1, maximum=100_000),
        full_liquidation=False,
    )
    assert star == (99_850, 200)
    odd = RebalancePlanner._split_quantity(
        50,
        side="SELL",
        profile=_profile("A.SZ"),
        full_liquidation=True,
    )
    assert odd == (50,)
    assert RebalancePlanner._split_quantity(
        50,
        side="BUY",
        profile=_profile("A.SZ"),
        full_liquidation=False,
    ) == ()
    assert DELTA_BELOW_MIN_ORDER == "DELTA_BELOW_MIN_ORDER"


def test_0033_migration_rejects_market_on_open_history(monkeypatch) -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "20260930_0033_m13_3_rebalance_accounting.py"
    )
    spec = importlib.util.spec_from_file_location("m13_3_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    class Connection:
        def scalar(self, _statement):
            return 3

    monkeypatch.setattr(migration.op, "get_bind", lambda: Connection())
    with pytest.raises(RuntimeError, match="3 MARKET_ON_OPEN"):
        migration.upgrade()
