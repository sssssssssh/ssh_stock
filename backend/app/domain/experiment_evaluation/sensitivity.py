from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Any

from app.domain.experiment.contracts import EXPERIMENT_PARAMETER_ORDER
from app.domain.experiment_evaluation.contracts import (
    EvaluatedTrial,
    EvaluationPolicy,
    SensitivityRow,
)
from app.domain.experiment_evaluation.metrics import METRIC_CATALOG, MetricDirection


def canonical_parameter_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    number = Decimal(str(value))
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def calculate_sensitivity(
    trials: tuple[EvaluatedTrial, ...], policy: EvaluationPolicy
) -> tuple[SensitivityRow, ...]:
    grouped: dict[tuple[str, str], list[EvaluatedTrial]] = defaultdict(list)
    for trial in trials:
        for name in EXPERIMENT_PARAMETER_ORDER:
            grouped[(name, canonical_parameter_value(trial.source.parameter_values[name]))].append(
                trial
            )
    rows: list[SensitivityRow] = []
    for name in EXPERIMENT_PARAMETER_ORDER:
        values = sorted(
            (value for parameter, value in grouped if parameter == name), key=Decimal
        )
        for value in values:
            members = grouped[(name, value)]
            evaluated = [row for row in members if row.status == "EVALUATED"]
            feasible = [row for row in evaluated if row.feasible]
            front1 = [row for row in feasible if row.pareto_front == 1]
            primary = [
                row.primary_objective_value
                for row in evaluated
                if row.primary_objective_value is not None
            ]
            annualized = _metric_values(evaluated, "annualized_return")
            drawdown = _metric_values(evaluated, "max_drawdown_abs")
            turnover = _metric_values(evaluated, "annualized_turnover")
            direction = METRIC_CATALOG[policy.primary_objective]
            rows.append(
                SensitivityRow(
                    parameter_name=name,
                    parameter_value=value,
                    trial_count=len(members),
                    evaluated_count=len(evaluated),
                    feasible_count=len(feasible),
                    feasible_rate=_rate(len(feasible), len(evaluated)),
                    pareto_front1_count=len(front1),
                    pareto_front1_rate=(
                        _rate(len(front1), len(feasible)) if feasible else None
                    ),
                    primary_objective_sample_count=len(primary),
                    mean_primary_objective=_mean(primary),
                    median_primary_objective=_median(primary),
                    best_primary_objective=(
                        (max(primary) if direction == MetricDirection.MAX else min(primary))
                        if primary
                        else None
                    ),
                    worst_primary_objective=(
                        (min(primary) if direction == MetricDirection.MAX else max(primary))
                        if primary
                        else None
                    ),
                    mean_annualized_return=_mean(annualized),
                    mean_max_drawdown_abs=_mean(drawdown),
                    mean_annualized_turnover=_mean(turnover),
                )
            )
    return tuple(rows)


def _metric_values(rows: list[EvaluatedTrial], metric: str) -> list[Decimal]:
    values: list[Decimal] = []
    for row in rows:
        assert row.source.metrics is not None
        value = row.source.metrics.value(metric)
        if value is not None:
            values.append(value)
    return values


def _rate(numerator: int, denominator: int) -> Decimal:
    return Decimal(numerator) / Decimal(denominator) if denominator else Decimal(0)


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    with localcontext() as context:
        context.prec = 60
        return sum(values, Decimal(0)) / Decimal(len(values))


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    with localcontext() as context:
        context.prec = 60
        return (ordered[middle - 1] + ordered[middle]) / Decimal(2)
