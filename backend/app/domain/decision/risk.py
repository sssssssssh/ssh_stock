from decimal import Decimal

from app.domain.decision.contracts import PaperError
from app.services.execution.cost import ExecutionCostCalculator
from app.services.execution.instrument_rules import AshareInstrumentRuleResolver
from app.services.execution.price import adverse_fill_price
from app.services.portfolio.ledger_precision import money


def plan_order(*, candidate, action, weight, snapshot, contexts, pending, scheduled, config):
    if action == "WATCH":
        raise PaperError("WATCH_NOT_EXECUTABLE", status_code=422)
    risk = config.policy.risk
    code = candidate["ts_code"]
    if any(row["ts_code"] == code for row in pending):
        raise PaperError("REJECT_CONFLICTING_PENDING")
    positions = {row.ts_code: row for row in snapshot.positions}
    position = positions.get(code)
    current_quantity = position.quantity if position else 0
    close = Decimal(candidate["close"])
    if not close.is_finite() or close <= 0 or snapshot.total_assets <= 0:
        raise PaperError("SOURCE_PRICE_UNAVAILABLE")
    if weight > risk.max_single_position_weight:
        raise PaperError("SINGLE_WEIGHT_LIMIT")
    if action == "PROPOSE_EXIT" and weight != 0:
        raise PaperError("EXIT_REQUIRES_ZERO_WEIGHT", status_code=422)
    rules = AshareInstrumentRuleResolver()
    profile = rules.resolve(
        ts_code=code, exchange=candidate["exchange"], market=candidate["market"]
    )
    if profile is None:
        raise PaperError("UNSUPPORTED_INSTRUMENT")
    side = "BUY" if action == "PROPOSE_BUY" else "SELL"
    estimated_price = adverse_fill_price(
        side=side,
        reference_price=close,
        slippage_bps=config.execution.trading_cost.slippage_bps,
        price_tick=config.execution.price_tick_cny,
        up_limit=None,
        down_limit=None,
    )
    target = int(weight * snapshot.total_assets / (estimated_price if side == "BUY" else close))
    if action == "PROPOSE_BUY":
        if candidate["risk_codes"]:
            raise PaperError("DECISION_RISK_BLOCKED")
        delta = target - current_quantity
        quantity = (
            profile.min_buy_quantity
            + (delta - profile.min_buy_quantity) // profile.buy_step * profile.buy_step
            if delta >= profile.min_buy_quantity
            else 0
        )
        validation = rules.validate_buy(profile, quantity)
        side = "BUY"
    else:
        quantity = current_quantity if action == "PROPOSE_EXIT" else current_quantity - target
        if quantity <= 0 or quantity > current_quantity:
            raise PaperError("INSUFFICIENT_POSITION_OR_NON_REDUCING_TARGET")
        validation = rules.validate_sell(profile, quantity, current_quantity)
        side = "SELL"
    if not validation.valid:
        raise PaperError(validation.reason or "LOT_SIZE_INVALID")
    gross = money(estimated_price * quantity)
    costs = ExecutionCostCalculator().calculate(
        side=side,
        trade_date=scheduled,
        exchange=profile.exchange,
        gross_amount=gross,
        config=config.execution.trading_cost,
    )
    projected = {p.ts_code: p.market_value / snapshot.total_assets for p in snapshot.positions}
    all_contexts = dict(contexts)
    reserved, turnover = Decimal("0"), Decimal("0")
    new_codes = set()
    for order in pending:
        data = order["data"]
        turnover += Decimal(data["estimated_gross"])
        if order["side"] == "BUY":
            projected[order["ts_code"]] = order["target_weight"]
            reserved += Decimal(data["estimated_cash_required"])
            all_contexts[order["ts_code"]] = data["candidate"]
            if order["ts_code"] not in positions:
                new_codes.add(order["ts_code"])
    if side == "BUY":
        projected[code] = weight
        all_contexts[code] = candidate
        if code not in positions:
            new_codes.add(code)
        if len(projected) > risk.max_positions:
            raise PaperError("MAX_POSITIONS_LIMIT")
        if len(new_codes) > risk.max_new_positions_per_day:
            raise PaperError("MAX_NEW_POSITIONS_LIMIT")
        if sum(projected.values()) > 1 - risk.min_cash_ratio:
            raise PaperError("GROSS_WEIGHT_LIMIT")
        if (
            snapshot.cash - reserved - gross - costs.cash_fee_total
            < risk.min_cash_ratio * snapshot.total_assets
        ):
            raise PaperError("CASH_BUFFER_LIMIT")
        sectors, themes = {}, {}
        for symbol, exposure in projected.items():
            context = all_contexts.get(symbol)
            if not context or context.get("industry_sector_id") is None:
                raise PaperError("RISK_CONTEXT_UNAVAILABLE")
            sector, theme = context["industry_sector_id"], context.get("primary_theme_code")
            sectors[sector] = sectors.get(sector, Decimal("0")) + exposure
            if theme:
                themes[theme] = themes.get(theme, Decimal("0")) + exposure
        if max(sectors.values(), default=Decimal("0")) > risk.max_sector_weight:
            raise PaperError("SECTOR_WEIGHT_LIMIT")
        if max(themes.values(), default=Decimal("0")) > risk.max_theme_weight:
            raise PaperError("THEME_WEIGHT_LIMIT")
    if (turnover + gross) / snapshot.total_assets > risk.max_daily_turnover:
        raise PaperError("DAILY_TURNOVER_LIMIT")
    return {
        "side": side,
        "quantity": quantity,
        "estimated_gross": gross,
        "estimated_cash_required": gross + costs.cash_fee_total if side == "BUY" else Decimal("0"),
        "candidate": candidate,
        "target_weight": weight,
        "sizing_basis": "SIGNAL_CLOSE_TOTAL_ASSETS",
    }
