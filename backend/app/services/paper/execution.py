from dataclasses import replace
from decimal import Decimal

from app.domain.decision.contracts import PaperError
from app.domain.execution import MarketExecutionSnapshot, OrderIntent
from app.services.execution.resolver import AshareExecutionResolver
from app.services.portfolio.accounting import AccountingFill, AccountingMarketSnapshot
from app.services.portfolio.ledger_precision import money

ZERO = Decimal("0")


def decimal_or_none(value):
    if value is None:
        return None
    result = Decimal(str(value))
    if not result.is_finite():
        raise PaperError("SOURCE_INVALID_NUMBER")
    return result


def accounting_market(facts, codes):
    result = {}
    for code in codes:
        raw = facts["stock_daily"].get(code, {})
        status = facts["stock_trade_status_daily"].get(code, {})
        current = facts["stock_adj_factor"].get(code, {}).get("adj_factor")
        result[code] = AccountingMarketSnapshot(
            ts_code=code,
            status_present=bool(status),
            is_active=status.get("is_active"),
            is_suspended=status.get("is_suspended"),
            close_price=decimal_or_none(raw.get("close")),
            previous_adj_factor=decimal_or_none(facts["previous_adj"].get(code)),
            current_adj_factor=decimal_or_none(current),
        )
    return result


def execution_block(order, facts):
    code = order.ts_code
    raw = facts["stock_daily"].get(code, {})
    status = facts["stock_trade_status_daily"].get(code, {})
    limits = facts["stock_limit_daily"].get(code, {})
    opening, volume = decimal_or_none(raw.get("open")), decimal_or_none(raw.get("vol"))
    up, down = decimal_or_none(limits.get("up_limit")), decimal_or_none(limits.get("down_limit"))
    if opening is None or opening <= 0:
        return "PRICE_UNAVAILABLE"
    if volume is None or volume <= 0:
        return "VOLUME_UNAVAILABLE"
    if not status or status.get("is_active") is not True:
        return "TRADING_STATUS_UNAVAILABLE"
    if status.get("is_suspended") is True:
        return "SUSPENDED"
    if status.get("is_st") is not False or status.get("st_status_unknown") is not False:
        return "ST_OR_QUALIFICATION_UNKNOWN"
    if status.get("tradable") is not True or status.get("strategy_eligible") is not True:
        return "TRADING_NOT_ELIGIBLE"
    if up is None or down is None or down <= 0 or up < down:
        return "PRICE_LIMIT_UNAVAILABLE"
    if opening > up or opening < down:
        return "PRICE_OUTSIDE_LIMIT"
    if order.side == "BUY" and opening >= up:
        return "LIMIT_UP_BUY_BLOCKED"
    if order.side == "SELL" and opening <= down:
        return "LIMIT_DOWN_SELL_BLOCKED"
    if order.quantity > volume * 100:
        return "VOLUME_INSUFFICIENT"
    return None


def resolve_order(order, facts, account, config):
    blocked = execution_block(order, facts)
    if blocked:
        return None, blocked
    code = order.ts_code
    raw, status = facts["stock_daily"][code], facts["stock_trade_status_daily"][code]
    profile, limits = facts["stock_basic"].get(code, {}), facts["stock_limit_daily"][code]
    snapshot = MarketExecutionSnapshot(
        trade_date=order.scheduled_date,
        ts_code=code,
        exchange=profile.get("exchange"),
        market=profile.get("market"),
        basic_present=bool(profile),
        raw_present=True,
        open_price=decimal_or_none(raw["open"]),
        close_price=decimal_or_none(raw.get("close")),
        status_present=True,
        is_active=status["is_active"],
        is_suspended=status["is_suspended"],
        tradable=status["tradable"],
        limit_present=True,
        up_limit=decimal_or_none(limits["up_limit"]),
        down_limit=decimal_or_none(limits["down_limit"]),
    )
    intent = OrderIntent(
        signal_trade_date=order.signal_date,
        scheduled_trade_date=order.scheduled_date,
        ts_code=code,
        side=order.side,
        order_type="NEXT_OPEN",
        target_weight=order.target_weight,
        target_quantity=order.quantity,
        order_id=order.id,
    )
    decision = AshareExecutionResolver().resolve([intent], [snapshot], account, config)[0]
    if not decision.executable:
        reasons = {
            "INSUFFICIENT_CASH": "CASH_INSUFFICIENT",
            "LIMIT_UP": "LIMIT_UP_BUY_BLOCKED",
            "LIMIT_DOWN": "LIMIT_DOWN_SELL_BLOCKED",
        }
        return None, reasons.get(decision.reason_code, decision.reason_code)
    return decision, None


def as_accounting_fill(decision, fill_id):
    return AccountingFill(
        fill_id=fill_id,
        order_id=decision.order_id,
        scheduled_trade_date=decision.intent.scheduled_trade_date,
        ts_code=decision.intent.ts_code,
        side=decision.intent.side,
        quantity=decision.fill_quantity,
        price=decision.fill_price,
        gross_amount=decision.gross_amount,
        cash_fee_total=decision.cash_fee_total,
        total_cost=decision.total_cost,
    )


def actual_risk(
    *, decision, before, after, contexts, facts, risk, opening_assets, turnover, new_codes
):
    if opening_assets <= 0:
        return "PAPER_ASSETS_INVALID"
    if (turnover + decision.gross_amount) / opening_assets > risk.max_daily_turnover:
        return "DAILY_TURNOVER_LIMIT"
    if decision.intent.side == "SELL":
        return None
    values = {}
    for position in after.positions:
        opening = decimal_or_none(facts["stock_daily"].get(position.ts_code, {}).get("open"))
        if opening is None or opening <= 0:
            return "RISK_PRICE_UNAVAILABLE"
        values[position.ts_code] = money(opening * position.quantity)
    assets = after.cash + sum(values.values(), ZERO)
    if assets <= 0 or after.cash < assets * risk.min_cash_ratio:
        return "CASH_BUFFER_LIMIT"
    if len(values) > risk.max_positions:
        return "MAX_POSITIONS_LIMIT"
    new = set(new_codes)
    if decision.intent.ts_code not in {p.ts_code for p in before.positions}:
        new.add(decision.intent.ts_code)
    if len(new) > risk.max_new_positions_per_day:
        return "MAX_NEW_POSITIONS_LIMIT"
    if max(values.values(), default=ZERO) > assets * risk.max_single_position_weight:
        return "SINGLE_WEIGHT_LIMIT"
    if sum(values.values(), ZERO) > assets * (1 - risk.min_cash_ratio):
        return "GROSS_WEIGHT_LIMIT"
    sectors, themes = {}, {}
    for code, value in values.items():
        context = contexts.get(code, {})
        sector, theme = context.get("industry_sector_id"), context.get("primary_theme_code")
        if sector is None:
            return "RISK_CONTEXT_UNAVAILABLE"
        sectors[sector] = sectors.get(sector, ZERO) + value
        if theme:
            themes[theme] = themes.get(theme, ZERO) + value
    if max(sectors.values(), default=ZERO) > assets * risk.max_sector_weight:
        return "SECTOR_WEIGHT_LIMIT"
    if max(themes.values(), default=ZERO) > assets * risk.max_theme_weight:
        return "THEME_WEIGHT_LIMIT"
    return None


def opening_valuation(account, facts):
    value = ZERO
    for position in account.positions:
        price = decimal_or_none(facts["stock_daily"].get(position.ts_code, {}).get("open"))
        if price is None or price <= 0:
            raise PaperError("RISK_PRICE_UNAVAILABLE")
        value += money(price * position.quantity)
    return account.cash + value


def price_at_close(account, market):
    # No implicit carry-forward valuation for missing PAPER closing evidence.
    for position in account.positions:
        row = market.get(position.ts_code)
        if row is None or row.close_price is None or row.close_price <= 0:
            raise PaperError("PRICE_UNAVAILABLE")
    return replace(account, positions=tuple(account.positions))
