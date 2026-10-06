from dataclasses import replace
from decimal import Decimal

from app.domain.experiment_evaluation.contracts import EvaluatedTrial, EvaluationPolicy
from app.domain.experiment_evaluation.metrics import METRIC_CATALOG, MetricDirection


def rank_trials(
    trials: tuple[EvaluatedTrial, ...], policy: EvaluationPolicy
) -> tuple[EvaluatedTrial, ...]:
    feasible = sorted((row for row in trials if row.feasible), key=lambda row: _key(row, policy))
    ranks = {row.source.trial_id: index for index, row in enumerate(feasible, start=1)}
    return tuple(
        replace(
            row,
            selection_rank=ranks.get(row.source.trial_id),
            shortlisted=(
                row.source.trial_id in ranks
                and ranks[row.source.trial_id] <= policy.shortlist_size
            ),
        )
        for row in trials
    )


def _key(row: EvaluatedTrial, policy: EvaluationPolicy) -> tuple[object, ...]:
    assert row.source.metrics is not None and row.pareto_front is not None
    metrics = (policy.primary_objective, *policy.tie_breakers)
    return (
        row.pareto_front,
        *(_metric_key(row.source.metrics.value(metric), metric) for metric in metrics),
        row.source.trial_no,
    )


def _metric_key(value: Decimal | None, metric: str) -> tuple[bool, Decimal]:
    if value is None:
        return True, Decimal(0)
    if METRIC_CATALOG[metric] == MetricDirection.MAX:
        return False, -value
    return False, value
