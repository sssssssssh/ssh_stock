from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal


def to_decimal(value: object | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def is_positive_price(value: Decimal | None) -> bool:
    return value is not None and value > 0


def prices_match(left: Decimal | None, right: Decimal | None) -> bool:
    if not is_positive_price(left) or not is_positive_price(right):
        return False
    assert left is not None and right is not None
    tolerance = max(Decimal("0.001"), abs(right) * Decimal("0.000001"))
    return abs(left - right) <= tolerance


def adverse_fill_price(
    *,
    side: str,
    reference_price: Decimal,
    slippage_bps: Decimal,
    price_tick: Decimal,
    up_limit: Decimal | None,
    down_limit: Decimal | None,
) -> Decimal:
    slippage = slippage_bps / Decimal("10000")
    if side == "BUY":
        theoretical = reference_price * (Decimal("1") + slippage)
        fill_price = _round_to_tick(theoretical, price_tick, ROUND_CEILING)
    else:
        theoretical = reference_price * (Decimal("1") - slippage)
        fill_price = _round_to_tick(theoretical, price_tick, ROUND_FLOOR)
    if is_positive_price(up_limit):
        fill_price = min(fill_price, up_limit)
    if is_positive_price(down_limit):
        fill_price = max(fill_price, down_limit)
    return fill_price


def _round_to_tick(value: Decimal, tick: Decimal, rounding: str) -> Decimal:
    units = (value / tick).to_integral_value(rounding=rounding)
    return units * tick
