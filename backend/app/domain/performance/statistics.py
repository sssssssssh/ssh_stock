from decimal import Decimal, localcontext

ZERO = Decimal("0")


def mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("mean requires at least one observation")
    with localcontext() as context:
        context.prec = 60
        return sum(values, ZERO) / Decimal(len(values))


def sample_variance(values: tuple[Decimal, ...]) -> Decimal:
    if len(values) < 2:
        raise ValueError("sample variance requires at least two observations")
    with localcontext() as context:
        context.prec = 60
        average = mean(values)
        return sum(((value - average) ** 2 for value in values), ZERO) / Decimal(
            len(values) - 1
        )


def sample_stddev(values: tuple[Decimal, ...]) -> Decimal:
    with localcontext() as context:
        context.prec = 60
        return sample_variance(values).sqrt()


def sample_covariance(
    left: tuple[Decimal, ...], right: tuple[Decimal, ...]
) -> Decimal:
    if len(left) != len(right):
        raise ValueError("sample covariance requires equally sized samples")
    if len(left) < 2:
        raise ValueError("sample covariance requires at least two observations")
    with localcontext() as context:
        context.prec = 60
        left_mean = mean(left)
        right_mean = mean(right)
        return sum(
            (
                (left_value - left_mean) * (right_value - right_mean)
                for left_value, right_value in zip(left, right, strict=True)
            ),
            ZERO,
        ) / Decimal(len(left) - 1)
