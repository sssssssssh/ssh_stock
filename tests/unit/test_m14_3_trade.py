import importlib.util
import inspect
import uuid
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, localcontext

import pytest
from app.core.performance_trade_config import PerformanceTradeConfig
from app.domain.performance import trade_engine, trade_statistics
from app.domain.performance.trade_contracts import (
    TradeSourceFill,
    TradeSourceNav,
    TradeSourcePosition,
    TradeSourceSnapshot,
)
from app.domain.performance.trade_engine import TradeCalculationError, TradeEngine
from app.services.performance.risk_identity import performance_risk_lock_key
from app.services.performance.trade_identity import (
    performance_trade_lock_key,
    trade_source_hash,
)
from pydantic import ValidationError


def _config(**overrides) -> PerformanceTradeConfig:
    values = {
        "version": "trade_v1",
        "pnl_zero_epsilon_cny": Decimal("0.0001"),
        "short_sample_warning_trade_days": 20,
    }
    values.update(overrides)
    return PerformanceTradeConfig.model_validate(values)


def _fill(
    number: int,
    trade_date: date,
    side: str,
    quantity: int,
    price: str,
    *,
    reference_price: str | None = None,
    commission: str = "1",
) -> TradeSourceFill:
    fill_price = Decimal(price)
    reference = Decimal(reference_price or price)
    cash_fee = Decimal(commission)
    slippage = abs(fill_price - reference) * quantity
    return TradeSourceFill(
        fill_id=uuid.UUID(int=number),
        order_id=uuid.UUID(int=100 + number),
        attempt_id=uuid.UUID(int=200 + number),
        scheduled_trade_date=trade_date,
        trade_date=trade_date,
        ts_code="000001.SZ",
        side=side,
        quantity=quantity,
        price=fill_price,
        reference_price=reference,
        gross_amount=fill_price * quantity,
        commission=cash_fee,
        stamp_tax=Decimal("0"),
        transfer_fee=Decimal("0"),
        cash_fee_total=cash_fee,
        slippage_cost=slippage,
        total_cost=cash_fee + slippage,
    )


def _source() -> TradeSourceSnapshot:
    first = date(2026, 1, 5)
    dates = tuple(first + timedelta(days=index) for index in range(3))
    fills = (
        _fill(1, dates[0], "BUY", 100, "10"),
        # Deliberately list BUY before SELL. The frozen replay order must sell first.
        _fill(3, dates[1], "BUY", 50, "11"),
        _fill(2, dates[1], "SELL", 100, "12", reference_price="11.9"),
    )
    positions = (
        TradeSourcePosition(
            dates[0], "000001.SZ", 100, Decimal("10.01000000"), Decimal("0"), Decimal("0")
        ),
        TradeSourcePosition(
            dates[1], "000001.SZ", 50, Decimal("11.02000000"), Decimal("0"), Decimal("0")
        ),
        TradeSourcePosition(
            dates[2], "000001.SZ", 50, Decimal("11.02000000"), Decimal("0"), Decimal("24")
        ),
    )
    return TradeSourceSnapshot(
        run_id=uuid.UUID(int=1000),
        performance_id=uuid.UUID(int=1001),
        performance_version="performance_v1",
        performance_config_hash="a" * 64,
        performance_source_hash="b" * 64,
        trade_version="trade_v1",
        trade_config_hash="c" * 64,
        trade_source_hash="",
        backtest_engine_version="backtest_v1",
        portfolio_version="portfolio_v1",
        execution_version="execution_v1",
        accounting_version="accounting_v1",
        start_date=dates[0],
        end_date=dates[-1],
        trade_days=len(dates),
        annualization_trade_days=252,
        initial_cash=Decimal("10000"),
        dates=dates,
        orders=(),
        attempts=(),
        fills=fills,
        nav=(
            TradeSourceNav(dates[0], Decimal("11000"), Decimal("1")),
            TradeSourceNav(dates[1], Decimal("12000"), Decimal("12")),
            TradeSourceNav(dates[2], Decimal("12500"), Decimal("0")),
        ),
        positions=positions,
    )


def test_trade_config_is_independent_strict_and_validated() -> None:
    assert _config().version == "trade_v1"
    with pytest.raises(ValidationError):
        PerformanceTradeConfig.model_validate(
            {**_config().model_dump(), "annualization_trade_days": 250}
        )
    with pytest.raises(ValidationError):
        _config(pnl_zero_epsilon_cny=Decimal("-0.1"))
    with pytest.raises(ValidationError):
        _config(short_sample_warning_trade_days=0)


def test_weighted_average_episode_replay_and_slippage_semantics() -> None:
    result = TradeEngine().calculate(_source(), _config())
    assert result.fill_count == 3
    assert result.closed_episode_count == 1
    assert result.open_episode_count == 1
    closed, opened = result.episodes
    assert closed.status == "CLOSED"
    assert closed.entry_date == _source().dates[0]
    assert closed.exit_date == _source().dates[1]
    assert closed.holding_trade_days == 2
    # 1200 gross - 1 cash fee - 100 * 10.01 basis. Slippage is not deducted twice.
    assert closed.realized_pnl == Decimal("198.00")
    assert closed.classification == "WIN"
    with localcontext() as context:
        context.prec = 60
        assert closed.episode_return == Decimal("198") / Decimal("1001")
    assert opened.status == "OPEN"
    assert opened.episode_no == 2
    assert opened.ending_quantity == 50
    assert opened.realized_pnl == Decimal("0")
    assert opened.unrealized_pnl_end == Decimal("24")
    assert opened.mark_to_market_pnl_end == Decimal("24")
    assert result.closed_realized_pnl == Decimal("198.00")
    assert result.open_unrealized_pnl_end == Decimal("24")
    assert "OPEN_EPISODES_EXCLUDED_FROM_CLOSED_STATS" in result.warnings


def test_daily_cost_and_double_sided_turnover_include_zero_fill_days() -> None:
    result = TradeEngine().calculate(_source(), _config())
    first, second, third = result.daily
    assert first.traded_gross_amount == Decimal("1000")
    assert first.turnover_denominator == Decimal("10000")
    assert first.daily_turnover == Decimal("0.1")
    assert second.traded_gross_amount == Decimal("1750")
    assert second.turnover_denominator == Decimal("11000")
    assert second.total_execution_cost == Decimal("12.0")
    assert third.fill_count == 0
    assert third.daily_turnover == 0
    assert result.traded_gross_amount == Decimal("2750")
    assert result.total_execution_cost == Decimal("13.0")
    with localcontext() as context:
        context.prec = 60
        assert result.total_turnover == (Decimal("0.1") + Decimal("1750") / Decimal("11000"))
        assert result.annualized_turnover == result.average_daily_turnover * 252


def test_position_replay_mismatch_fails_closed() -> None:
    source = _source()
    broken = replace(
        source,
        positions=(
            replace(source.positions[0], avg_cost=Decimal("10.02")),
            *source.positions[1:],
        ),
    )
    with pytest.raises(TradeCalculationError) as exc_info:
        TradeEngine().calculate(broken, _config())
    assert exc_info.value.code == "TRADE_POSITION_REPLAY_MISMATCH"


def test_empty_execution_creates_daily_rows_and_explicit_warnings() -> None:
    source = _source()
    empty = replace(
        source,
        fills=(),
        positions=(),
        nav=tuple(replace(row, trading_cost=Decimal("0")) for row in source.nav),
    )
    result = TradeEngine().calculate(empty, _config())
    assert len(result.daily) == empty.trade_days
    assert result.episodes == ()
    assert result.total_cost_to_traded_amount is None
    assert {
        "NO_FILLS",
        "NO_CLOSED_EPISODES",
        "ZERO_TRADED_GROSS_AMOUNT",
        "ZERO_GROSS_LOSS",
        "ZERO_WIN_COUNT",
        "ZERO_LOSS_COUNT",
    }.issubset(result.warnings)


def test_source_hash_is_order_independent_sensitive_and_lock_is_independent() -> None:
    source = _source()
    first = trade_source_hash(source)
    reordered = trade_source_hash(
        replace(
            source, fills=tuple(reversed(source.fills)), positions=tuple(reversed(source.positions))
        )
    )
    revised = trade_source_hash(
        replace(
            source, nav=(*source.nav[:-1], replace(source.nav[-1], total_assets=Decimal("13000")))
        )
    )
    assert len(first) == 64
    assert first == reordered
    assert first != revised
    assert performance_trade_lock_key(source.performance_id) != performance_risk_lock_key(
        source.performance_id
    )


def test_trade_statistics_and_domain_are_decimal_only_and_orm_free() -> None:
    values = (Decimal("1"), Decimal("4"), Decimal("2"), Decimal("3"))
    assert trade_statistics.mean(values) == Decimal("2.5")
    assert trade_statistics.median(values) == Decimal("2.5")
    source = inspect.getsource(trade_engine) + inspect.getsource(trade_statistics)
    for forbidden in ("sqlalchemy", "Session", "app.models", "numpy", "pandas", "float("):
        assert forbidden not in source


def test_migration_0039_downgrade_fails_closed_when_artifacts_exist(
    monkeypatch,
) -> None:
    path = (
        __import__("pathlib").Path(__file__).parents[2]
        / "migrations/versions/20261003_0039_m14_3_trade_cost_analytics.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0039", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Connection:
        @staticmethod
        def scalar(_statement):
            return 1

    monkeypatch.setattr(module.op, "get_bind", lambda: Connection())
    with pytest.raises(RuntimeError, match="cannot downgrade M14.3"):
        module.downgrade()
