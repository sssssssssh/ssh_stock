from decimal import Decimal


def mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("mean requires at least one observation")
    return sum(values, Decimal("0")) / Decimal(len(values))


def median(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("median requires at least one observation")
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")
