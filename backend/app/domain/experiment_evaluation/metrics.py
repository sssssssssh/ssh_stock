from decimal import Decimal, localcontext
from enum import StrEnum


class MetricDirection(StrEnum):
    MAX = "MAX"
    MIN = "MIN"


METRIC_CATALOG: dict[str, MetricDirection] = {
    "cumulative_return": MetricDirection.MAX,
    "annualized_return": MetricDirection.MAX,
    "max_drawdown_abs": MetricDirection.MIN,
    "strategy_annualized_volatility": MetricDirection.MIN,
    "excess_cumulative_return": MetricDirection.MAX,
    "sharpe_ratio": MetricDirection.MAX,
    "sortino_ratio": MetricDirection.MAX,
    "calmar_ratio": MetricDirection.MAX,
    "information_ratio": MetricDirection.MAX,
    "alpha_annualized": MetricDirection.MAX,
    "annualized_turnover": MetricDirection.MIN,
    "total_cost_to_initial_capital": MetricDirection.MIN,
    "closed_episode_count": MetricDirection.MAX,
    "win_rate": MetricDirection.MAX,
    "profit_factor": MetricDirection.MAX,
    "payoff_ratio": MetricDirection.MAX,
    "closed_realized_pnl": MetricDirection.MAX,
    "positive_month_rate": MetricDirection.MAX,
    "worst_month_return": MetricDirection.MAX,
    "monthly_return_volatility": MetricDirection.MIN,
}

RANKABLE_METRICS = frozenset(METRIC_CATALOG) - {"closed_episode_count"}


def validate_policy_metrics(
    primary_objective: str,
    pareto_metrics: tuple[str, ...],
    tie_breakers: tuple[str, ...],
) -> None:
    unknown = (
        {primary_objective, *pareto_metrics, *tie_breakers} - RANKABLE_METRICS
    )
    if unknown:
        raise ValueError(f"unsupported evaluation metrics: {sorted(unknown)}")


def monthly_robustness(
    monthly_returns: tuple[Decimal, ...], *, minimum_observations: int
) -> tuple[Decimal | None, Decimal | None, Decimal | None, tuple[str, ...]]:
    if not monthly_returns:
        return None, None, None, ("INSUFFICIENT_MONTH_OBSERVATIONS",)
    with localcontext() as context:
        context.prec = 60
        count = Decimal(len(monthly_returns))
        positive_rate = Decimal(sum(value > 0 for value in monthly_returns)) / count
        worst = min(monthly_returns)
        if len(monthly_returns) < minimum_observations:
            return (
                positive_rate,
                worst,
                None,
                ("INSUFFICIENT_MONTH_OBSERVATIONS",),
            )
        mean = sum(monthly_returns, Decimal(0)) / count
        variance = sum(
            ((value - mean) ** 2 for value in monthly_returns), Decimal(0)
        ) / Decimal(len(monthly_returns) - 1)
        return positive_rate, worst, variance.sqrt(), ()
