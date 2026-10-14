import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.core.config import get_settings
from app.domain.decision.account_requests import CreatePaperAccount
from app.domain.portfolio import AccountState
from app.services.paper.execution import execution_block, resolve_order
from pydantic import ValidationError


def case():
    order = SimpleNamespace(
        id=uuid.uuid4(),
        ts_code="000001.SZ",
        side="BUY",
        quantity=100,
        signal_date=date(2026, 10, 14),
        scheduled_date=date(2026, 10, 15),
        target_weight=Decimal("0.08"),
    )
    facts = {
        "stock_daily": {order.ts_code: {"open": "10", "close": "10", "vol": "1000"}},
        "stock_basic": {order.ts_code: {"exchange": "SZSE", "market": "主板"}},
        "stock_limit_daily": {order.ts_code: {"up_limit": "11", "down_limit": "9"}},
        "stock_trade_status_daily": {
            order.ts_code: {
                "is_active": True,
                "is_suspended": False,
                "is_st": False,
                "st_status_unknown": False,
                "tradable": True,
                "strategy_eligible": True,
            }
        },
    }
    return order, facts


@pytest.mark.parametrize(
    "layer,field,value,reason",
    [
        ("stock_daily", "open", None, "PRICE_UNAVAILABLE"),
        ("stock_daily", "open", 0, "PRICE_UNAVAILABLE"),
        ("stock_daily", "vol", 0, "VOLUME_UNAVAILABLE"),
        ("stock_daily", "vol", None, "VOLUME_UNAVAILABLE"),
        ("stock_trade_status_daily", "is_suspended", True, "SUSPENDED"),
        ("stock_trade_status_daily", "is_st", None, "ST_OR_QUALIFICATION_UNKNOWN"),
        ("stock_trade_status_daily", "is_st", True, "ST_OR_QUALIFICATION_UNKNOWN"),
        ("stock_trade_status_daily", "st_status_unknown", True, "ST_OR_QUALIFICATION_UNKNOWN"),
        ("stock_trade_status_daily", "tradable", False, "TRADING_NOT_ELIGIBLE"),
        ("stock_limit_daily", "up_limit", None, "PRICE_LIMIT_UNAVAILABLE"),
        ("stock_daily", "open", 11, "LIMIT_UP_BUY_BLOCKED"),
        ("stock_daily", "open", 12, "PRICE_OUTSIDE_LIMIT"),
        ("stock_daily", "vol", "0.1", "VOLUME_INSUFFICIENT"),
    ],
)
def test_conservative_market_blocks(layer, field, value, reason):
    order, facts = case()
    facts[layer][order.ts_code][field] = value
    assert execution_block(order, facts) == reason


def test_decimal_fees_and_no_partial_fill():
    order, facts = case()
    account = AccountState(trade_date=order.scheduled_date, cash=Decimal("10000"))
    decision, reason = resolve_order(order, facts, account, get_settings().execution_config)
    assert reason is None and decision.executable
    assert isinstance(decision.cash_delta, Decimal)
    assert decision.cash_delta == -decision.gross_amount - decision.cash_fee_total
    assert decision.total_cost == decision.cash_fee_total + decision.slippage_cost
    assert decision.stamp_tax == 0
    assert decision.fill_quantity == 100


def test_sell_limit_and_t_plus_one():
    from app.domain.portfolio import PositionState

    order, facts = case()
    order.side = "SELL"
    facts["stock_daily"][order.ts_code]["open"] = "9"
    assert execution_block(order, facts) == "LIMIT_DOWN_SELL_BLOCKED"
    facts["stock_daily"][order.ts_code]["open"] = "10"
    account = AccountState(
        trade_date=order.scheduled_date,
        cash=Decimal("0"),
        positions=(
            PositionState(
                ts_code=order.ts_code,
                quantity=100,
                available_quantity=0,
                avg_cost=Decimal("10"),
                market_value=Decimal("1000"),
            ),
        ),
    )
    decision, reason = resolve_order(order, facts, account, get_settings().execution_config)
    assert decision is None and reason == "T_PLUS_ONE"


@pytest.mark.parametrize(
    "patch",
    [
        {"mode": "LIVE"},
        {"owner_user_id": str(uuid.uuid4())},
        {"initial_cash": 1.5},
        {"initial_cash": True},
        {"initial_cash": "NaN"},
        {"name": " "},
        {"broker_url": "https://example.invalid"},
    ],
)
def test_account_input_has_no_live_or_fact_overrides(patch):
    with pytest.raises(ValidationError):
        CreatePaperAccount.model_validate(
            {"name": "test", "request_id": "create", "initial_cash": "1000000", **patch}
        )
