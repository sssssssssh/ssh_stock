from decimal import Decimal

from app.domain.experiment_evaluation.contracts import (
    ConstraintResult,
    EvaluationMetricSnapshot,
    EvaluationPolicy,
)

_RULES = (
    ("min_trade_days", "trade_days", "MIN_TRADE_DAYS", "MIN"),
    ("min_annualized_return", "annualized_return", "MIN_ANNUALIZED_RETURN", "MIN"),
    ("max_drawdown_abs", "max_drawdown_abs", "MAX_DRAWDOWN_ABS", "MAX"),
    ("min_sharpe_ratio", "sharpe_ratio", "MIN_SHARPE_RATIO", "MIN"),
    ("min_calmar_ratio", "calmar_ratio", "MIN_CALMAR_RATIO", "MIN"),
    (
        "max_annualized_turnover",
        "annualized_turnover",
        "MAX_ANNUALIZED_TURNOVER",
        "MAX",
    ),
    (
        "max_total_cost_to_initial_capital",
        "total_cost_to_initial_capital",
        "MAX_TOTAL_COST_TO_INITIAL_CAPITAL",
        "MAX",
    ),
    (
        "min_closed_episode_count",
        "closed_episode_count",
        "MIN_CLOSED_EPISODE_COUNT",
        "MIN",
    ),
    ("min_win_rate", "win_rate", "MIN_WIN_RATE", "MIN"),
    ("min_profit_factor", "profit_factor", "MIN_PROFIT_FACTOR", "MIN"),
)


def evaluate_constraints(
    metrics: EvaluationMetricSnapshot, policy: EvaluationPolicy
) -> ConstraintResult:
    violations: list[str] = []
    for constraint, metric, code, comparison in _RULES:
        threshold = policy.constraints.get(constraint)
        if threshold is None:
            continue
        value = metrics.value(metric)
        if value is None:
            violations.append(f"MISSING_METRIC:{metric}")
            continue
        limit = Decimal(threshold)
        if (comparison == "MIN" and value < limit) or (
            comparison == "MAX" and value > limit
        ):
            violations.append(code)
    primary = metrics.value(policy.primary_objective)
    if primary is None:
        violations.append("MISSING_PRIMARY_OBJECTIVE")
    for metric in policy.pareto_metrics:
        if metrics.value(metric) is None:
            violations.append(f"MISSING_METRIC:{metric}")
    stable = tuple(sorted(set(violations)))
    return ConstraintResult(feasible=not stable, violations=stable)
