from decimal import Decimal, localcontext

ONE = Decimal("1")
ZERO = Decimal("0")


def daily_return(nav: Decimal, previous_nav: Decimal) -> Decimal:
    return nav / previous_nav - ONE


def cumulative_return(nav: Decimal) -> Decimal:
    return nav - ONE


def annualized_return(
    final_nav: Decimal, *, trade_days: int, annualization_trade_days: int
) -> Decimal:
    if final_nav <= ZERO or trade_days <= 0 or annualization_trade_days <= 0:
        raise ValueError("annualized return requires positive NAV and trade-day counts")
    with localcontext() as context:
        context.prec = 50
        exponent = Decimal(annualization_trade_days) / Decimal(trade_days)
        return (final_nav.ln() * exponent).exp() - ONE
