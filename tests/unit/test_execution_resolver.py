import copy
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from app.core.config import get_settings
from app.core.execution_config import ExecutionConfig
from app.domain.execution import (
    ExecutionMarketBatch,
    MarketExecutionSnapshot,
    OrderIntent,
)
from app.domain.portfolio import AccountState, PositionState
from app.models.market_data import (
    StockBasic,
    StockDaily,
    StockLimitDaily,
    StockTradeStatusDaily,
)
from app.services.analysis_identity import (
    TRADE_STATUS_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.execution.contracts import ExecutionSourceNotReadyError
from app.services.execution.cost import (
    ExecutionCostCalculator,
    UnsupportedCostDateError,
)
from app.services.execution.instrument_rules import AshareInstrumentRuleResolver
from app.services.execution.market_data import ExecutionMarketDataProvider
from app.services.execution.resolver import AshareExecutionResolver
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

DAY = date(2026, 9, 1)


def _config() -> ExecutionConfig:
    return get_settings().execution_config


def _intent(
    code: str = "600000.SH",
    *,
    side: str = "BUY",
    quantity: int = 100,
    attempt_count: int = 0,
    order_no: int = 1,
) -> OrderIntent:
    return OrderIntent(
        order_id=uuid.UUID(int=order_no),
        signal_trade_date=date(2026, 8, 31),
        scheduled_trade_date=DAY,
        ts_code=code,
        side=side,
        order_type="NEXT_OPEN",
        target_quantity=quantity,
        attempt_count=attempt_count,
    )


def _snapshot(
    code: str = "600000.SH",
    *,
    exchange: str = "SSE",
    market: str = "主板",
    open_price: str = "10",
    up_limit: str | None = "11",
    down_limit: str | None = "9",
    active: bool = True,
    suspended: bool = False,
) -> MarketExecutionSnapshot:
    return MarketExecutionSnapshot(
        trade_date=DAY,
        ts_code=code,
        exchange=exchange,
        market=market,
        basic_present=True,
        raw_present=True,
        open_price=Decimal(open_price),
        close_price=Decimal(open_price),
        status_present=True,
        is_active=active,
        is_suspended=suspended,
        tradable=active and not suspended,
        limit_present=True,
        up_limit=Decimal(up_limit) if up_limit else None,
        down_limit=Decimal(down_limit) if down_limit else None,
    )


def _batch(*snapshots: MarketExecutionSnapshot) -> ExecutionMarketBatch:
    return ExecutionMarketBatch(DAY, "READY", None, tuple(snapshots))


def _position(
    code: str,
    quantity: int,
    available: int,
) -> PositionState:
    return PositionState(
        ts_code=code,
        quantity=quantity,
        available_quantity=available,
        avg_cost=Decimal("10"),
        market_value=Decimal(quantity * 10),
    )


def test_execution_v2_config_and_schedule_validation() -> None:
    config = _config()
    assert config.version == "execution_v2"
    assert config.ruleset_version == "cn_a_share_2026_v1"
    assert config.price_tick_cny == Decimal("0.01")
    assert config.fill_model.partial_fill is False
    assert config.trading_cost.commission_rate == Decimal("0.0003")

    duplicate_stamp = copy.deepcopy(config.model_dump(mode="python"))
    duplicate_stamp["trading_cost"]["stamp_tax_sell_schedule"] = [
        *duplicate_stamp["trading_cost"]["stamp_tax_sell_schedule"],
        {"effective_from": date(2023, 8, 28), "rate": Decimal("0.2")}
    ]
    with pytest.raises(ValidationError, match="stamp tax schedule"):
        ExecutionConfig.model_validate(duplicate_stamp)

    overlapping_transfer = copy.deepcopy(config.model_dump(mode="python"))
    overlapping_transfer["trading_cost"]["transfer_fee"]["schedules"] = [
        *overlapping_transfer["trading_cost"]["transfer_fee"]["schedules"],
        {
            "effective_from": date(2022, 1, 1),
            "effective_to": date(2022, 12, 31),
            "exchanges": ["SSE"],
            "rate": Decimal("0.1"),
        },
    ]
    with pytest.raises(ValidationError, match="overlap"):
        ExecutionConfig.model_validate(overlapping_transfer)


def test_market_provider_uses_four_fixed_queries_and_current_trade_status() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for model in (StockBasic, StockDaily, StockLimitDaily, StockTradeStatusDaily):
        model.__table__.create(engine)
    settings = get_settings()
    query_count = 0

    @event.listens_for(engine, "before_cursor_execute")
    def count_queries(*_args):
        nonlocal query_count
        query_count += 1

    with Session(engine) as db:
        db.add_all(
            [
                StockBasic(ts_code="600000.SH", exchange="SSE", market="主板"),
                StockDaily(trade_date=DAY, ts_code="600000.SH", open=10, close=10.2),
                StockLimitDaily(
                    trade_date=DAY,
                    ts_code="600000.SH",
                    up_limit=None,
                    down_limit=None,
                ),
                StockTradeStatusDaily(
                    trade_date=DAY,
                    ts_code="600000.SH",
                    is_active=True,
                    is_suspended=False,
                    st_status_unknown=False,
                    tradable=True,
                    strategy_eligible=True,
                    calc_version="old-trade-status",
                    config_hash="old-strategy",
                    calculated_at=datetime.now(UTC),
                ),
            ]
        )
        db.commit()
        query_count = 0
        provider = ExecutionMarketDataProvider(db, settings)
        old = provider.load(DAY, [_intent()])
        assert query_count == 4
        assert old.source_status == "INCOMPLETE"
        assert old.missing_by_layer == {"trade_status": ("600000.SH",)}

        status = db.get(StockTradeStatusDaily, (DAY, "600000.SH"))
        status.calc_version = TRADE_STATUS_CALC_VERSION
        status.config_hash = analysis_strategy_hash(settings.strategy)
        db.commit()
        query_count = 0
        current = provider.load(DAY, [_intent()])
        assert query_count == 4
        assert current.source_ready
        assert current.snapshots[0].open_price == Decimal("10.0")
        assert current.snapshots[0].up_limit is None
        assert current.snapshots[0].down_limit is None


def test_market_provider_reports_every_missing_source_layer() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for model in (StockBasic, StockDaily, StockLimitDaily, StockTradeStatusDaily):
        model.__table__.create(engine)
    with Session(engine) as db:
        result = ExecutionMarketDataProvider(db, get_settings()).load(DAY, [_intent()])
    assert result.source_status == "INCOMPLETE"
    assert set(result.missing_by_layer) == {
        "stock_daily",
        "trade_status",
        "stock_limit",
        "stock_basic",
    }


def test_market_provider_treats_nonpositive_raw_open_as_source_gap() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for model in (StockBasic, StockDaily, StockLimitDaily, StockTradeStatusDaily):
        model.__table__.create(engine)
    settings = get_settings()
    with Session(engine) as db:
        db.add_all(
            [
                StockBasic(ts_code="600000.SH", exchange="SSE", market="主板"),
                StockDaily(trade_date=DAY, ts_code="600000.SH", open=0, close=10),
                StockLimitDaily(trade_date=DAY, ts_code="600000.SH"),
                StockTradeStatusDaily(
                    trade_date=DAY,
                    ts_code="600000.SH",
                    is_active=True,
                    is_suspended=False,
                    st_status_unknown=False,
                    tradable=True,
                    strategy_eligible=True,
                    calc_version=TRADE_STATUS_CALC_VERSION,
                    config_hash=analysis_strategy_hash(settings.strategy),
                    calculated_at=datetime.now(UTC),
                ),
            ]
        )
        db.commit()
        result = ExecutionMarketDataProvider(db, settings).load(DAY, [_intent()])
    assert result.source_status == "INCOMPLETE"
    assert result.missing_by_layer == {"stock_daily": ("600000.SH",)}


@pytest.mark.parametrize(
    ("exchange", "market", "side", "quantity", "total", "valid"),
    [
        ("SSE", "主板", "BUY", 99, 0, False),
        ("SSE", "主板", "BUY", 100, 0, True),
        ("SSE", "主板", "BUY", 200, 0, True),
        ("SZSE", "创业板", "BUY", 100, 0, True),
        ("SZSE", "创业板", "BUY", 101, 0, False),
        ("SSE", "科创板", "BUY", 199, 0, False),
        ("SSE", "科创板", "BUY", 200, 0, True),
        ("SSE", "科创板", "BUY", 201, 0, True),
        ("BSE", "北交所", "BUY", 99, 0, False),
        ("BSE", "北交所", "BUY", 100, 0, True),
        ("BSE", "北交所", "BUY", 101, 0, True),
        ("SSE", "主板", "SELL", 100, 299, True),
        ("SSE", "主板", "SELL", 199, 299, False),
        ("SSE", "主板", "SELL", 299, 299, True),
    ],
)
def test_a_share_instrument_quantity_rules(
    exchange, market, side, quantity, total, valid
) -> None:
    rules = AshareInstrumentRuleResolver()
    profile = rules.resolve(ts_code="TEST", exchange=exchange, market=market)
    assert profile is not None
    actual = (
        rules.valid_buy(profile, quantity)
        if side == "BUY"
        else rules.valid_sell(profile, quantity, total)
    )
    assert actual is valid


def test_resolver_reason_precedence_and_limit_retries() -> None:
    resolver = AshareExecutionResolver()
    account = AccountState(DAY, Decimal("100000"))
    suspended = resolver.resolve_batch(
        [_intent()],
        _batch(_snapshot(open_price="11", suspended=True)),
        account,
        _config(),
    ).decisions[0]
    assert suspended.outcome == "RETRY"
    assert suspended.reason_code == "SUSPENDED"

    inactive = resolver.resolve_batch(
        [_intent()],
        _batch(_snapshot(open_price="11", active=False, suspended=True)),
        account,
        _config(),
    ).decisions[0]
    assert inactive.outcome == "REJECTED"
    assert inactive.reason_code == "NOT_ACTIVE"

    limit_up = resolver.resolve_batch(
        [_intent()], _batch(_snapshot(open_price="11")), account, _config()
    ).decisions[0]
    assert limit_up.reason_code == "LIMIT_UP"

    sell_account = AccountState(
        DAY, Decimal("0"), (_position("600000.SH", 100, 100),)
    )
    limit_down = resolver.resolve_batch(
        [_intent(side="SELL")],
        _batch(_snapshot(open_price="9")),
        sell_account,
        _config(),
    ).decisions[0]
    assert limit_down.reason_code == "LIMIT_DOWN"


def test_resolver_t_plus_one_and_position_precedence() -> None:
    resolver = AshareExecutionResolver()
    too_many = resolver.resolve_batch(
        [_intent(side="SELL", quantity=300)],
        _batch(_snapshot()),
        AccountState(DAY, Decimal("0"), (_position("600000.SH", 200, 100),)),
        _config(),
    ).decisions[0]
    assert too_many.reason_code == "INSUFFICIENT_POSITION"

    unavailable = resolver.resolve_batch(
        [_intent(side="SELL", quantity=200)],
        _batch(_snapshot()),
        AccountState(DAY, Decimal("0"), (_position("600000.SH", 200, 100),)),
        _config(),
    ).decisions[0]
    assert unavailable.outcome == "RETRY"
    assert unavailable.reason_code == "T_PLUS_ONE"


def test_adverse_slippage_costs_and_no_double_cash_deduction() -> None:
    decision = AshareExecutionResolver().resolve_batch(
        [_intent()],
        _batch(_snapshot()),
        AccountState(DAY, Decimal("2000")),
        _config(),
    ).decisions[0]
    assert decision.fill_price == Decimal("10.01")
    assert decision.gross_amount == Decimal("1001.0000")
    assert decision.commission == Decimal("5.0000")
    assert decision.transfer_fee == Decimal("0.0100")
    assert decision.cash_fee_total == Decimal("5.0100")
    assert decision.slippage_cost == Decimal("1.0000")
    assert decision.total_cost == Decimal("6.0100")
    assert decision.cash_delta == Decimal("-1006.0100")

    sell = AshareExecutionResolver().resolve_batch(
        [_intent(side="SELL")],
        _batch(_snapshot()),
        AccountState(DAY, Decimal("0"), (_position("600000.SH", 100, 100),)),
        _config(),
    ).decisions[0]
    assert sell.fill_price == Decimal("9.99")
    assert sell.cash_delta == sell.gross_amount - sell.cash_fee_total


def test_cost_schedule_switches_and_unsupported_dates() -> None:
    calculator = ExecutionCostCalculator()
    config = _config().trading_cost
    before = calculator.calculate(
        side="SELL",
        trade_date=date(2023, 8, 27),
        exchange="SSE",
        gross_amount=Decimal("10000"),
        config=config,
    )
    after = calculator.calculate(
        side="SELL",
        trade_date=date(2023, 8, 28),
        exchange="SSE",
        gross_amount=Decimal("10000"),
        config=config,
    )
    assert before.stamp_tax == Decimal("10.0000")
    assert after.stamp_tax == Decimal("5.0000")
    assert before.transfer_fee == Decimal("0.1000")

    large_buy = calculator.calculate(
        side="BUY",
        trade_date=date(2026, 9, 1),
        exchange="SSE",
        gross_amount=Decimal("100000"),
        config=config,
    )
    assert large_buy.commission == Decimal("30.0000")
    assert large_buy.stamp_tax == Decimal("0")

    old_transfer = calculator.calculate(
        side="BUY",
        trade_date=date(2022, 4, 28),
        exchange="SSE",
        gross_amount=Decimal("10000"),
        config=config,
    )
    new_transfer = calculator.calculate(
        side="BUY",
        trade_date=date(2022, 4, 29),
        exchange="SSE",
        gross_amount=Decimal("10000"),
        config=config,
    )
    assert old_transfer.transfer_fee == Decimal("0.2000")
    assert new_transfer.transfer_fee == Decimal("0.1000")
    with pytest.raises(UnsupportedCostDateError):
        calculator.calculate(
            side="BUY",
            trade_date=date(2010, 1, 1),
            exchange="SSE",
            gross_amount=Decimal("10000"),
            config=config,
        )


def test_batch_sells_before_buys_and_prevents_multi_buy_overspend() -> None:
    resolver = AshareExecutionResolver()
    sell = _intent("600001.SH", side="SELL", order_no=9)
    buy = _intent("600000.SH", side="BUY", order_no=1)
    result = resolver.resolve_batch(
        [buy, sell],
        _batch(
            _snapshot("600000.SH"),
            _snapshot("600001.SH", open_price="20", up_limit="22", down_limit="18"),
        ),
        AccountState(
            DAY, Decimal("100"), (_position("600001.SH", 100, 100),)
        ),
        _config(),
    )
    assert [item.intent.side for item in result.decisions] == ["SELL", "BUY"]
    assert all(item.outcome == "EXECUTED" for item in result.decisions)

    first = _intent("600000.SH", order_no=1)
    second = _intent("600002.SH", order_no=2)
    limited = resolver.resolve_batch(
        [second, first],
        _batch(_snapshot("600000.SH"), _snapshot("600002.SH")),
        AccountState(DAY, Decimal("1500")),
        _config(),
    )
    assert [item.outcome for item in limited.decisions] == ["EXECUTED", "REJECTED"]
    assert limited.decisions[1].reason_code == "INSUFFICIENT_CASH"
    assert limited.decisions[1].fill_quantity == 0


def test_slippage_is_clamped_to_valid_limit_and_invalid_orders_do_not_fill() -> None:
    resolver = AshareExecutionResolver()
    clamped = resolver.resolve_batch(
        [_intent()],
        _batch(_snapshot(open_price="10.99", up_limit="11")),
        AccountState(DAY, Decimal("100000")),
        _config(),
    ).decisions[0]
    assert clamped.outcome == "EXECUTED"
    assert clamped.fill_price == Decimal("11")

    invalid_lot = resolver.resolve_batch(
        [_intent(quantity=101)],
        _batch(_snapshot()),
        AccountState(DAY, Decimal("100000")),
        _config(),
    ).decisions[0]
    assert invalid_lot.reason_code == "INVALID_LOT"
    assert invalid_lot.fill_quantity == 0

    unsupported = resolver.resolve_batch(
        [_intent()],
        _batch(_snapshot(market="未知板块")),
        AccountState(DAY, Decimal("100000")),
        _config(),
    ).decisions[0]
    assert unsupported.reason_code == "UNSUPPORTED_INSTRUMENT"


def test_temporary_block_expires_exactly_on_fifth_attempt() -> None:
    resolver = AshareExecutionResolver()
    account = AccountState(DAY, Decimal("100000"))
    fourth = resolver.resolve_batch(
        [_intent(attempt_count=3)],
        _batch(_snapshot(suspended=True)),
        account,
        _config(),
    ).decisions[0]
    fifth = resolver.resolve_batch(
        [_intent(attempt_count=4)],
        _batch(_snapshot(suspended=True)),
        account,
        _config(),
    ).decisions[0]
    assert (fourth.outcome, fourth.status_after, fourth.retryable) == (
        "RETRY",
        "PENDING",
        True,
    )
    assert (fifth.outcome, fifth.status_after, fifth.reason_code) == (
        "EXPIRED",
        "CANCELLED",
        "SUSPENDED",
    )


def test_source_incomplete_fails_before_any_order_decision() -> None:
    batch = ExecutionMarketBatch(
        DAY,
        "INCOMPLETE",
        "EXECUTION_SOURCE_INCOMPLETE",
        (),
        {"stock_limit": ("600000.SH",)},
    )
    with pytest.raises(ExecutionSourceNotReadyError):
        AshareExecutionResolver().resolve_batch(
            [_intent()], batch, AccountState(DAY, Decimal("10000")), _config()
        )


def test_execution_domain_and_resolver_have_no_sqlalchemy_dependency() -> None:
    import app.domain.execution as domain_module
    import app.services.execution.resolver as resolver_module

    assert "sqlalchemy" not in domain_module.__dict__
    assert "sqlalchemy" not in resolver_module.__dict__
