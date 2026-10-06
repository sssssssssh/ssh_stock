from dataclasses import replace

from app.domain.experiment_evaluation.contracts import EvaluatedTrial, EvaluationPolicy
from app.domain.experiment_evaluation.metrics import METRIC_CATALOG, MetricDirection


def assign_pareto_fronts(
    trials: tuple[EvaluatedTrial, ...], policy: EvaluationPolicy
) -> tuple[EvaluatedTrial, ...]:
    remaining = {row.source.trial_id: row for row in trials if row.feasible}
    fronts: dict[object, int] = {}
    front = 1
    while remaining:
        current = [
            row
            for row in remaining.values()
            if not any(
                _dominates(other, row, policy.pareto_metrics)
                for other in remaining.values()
                if other.source.trial_id != row.source.trial_id
            )
        ]
        for row in current:
            fronts[row.source.trial_id] = front
            remaining.pop(row.source.trial_id)
        front += 1
    return tuple(
        replace(row, pareto_front=fronts.get(row.source.trial_id)) for row in trials
    )


def _dominates(
    left: EvaluatedTrial, right: EvaluatedTrial, metrics: tuple[str, ...]
) -> bool:
    assert left.source.metrics is not None and right.source.metrics is not None
    weakly_better = True
    strictly_better = False
    for metric in metrics:
        left_value = left.source.metrics.value(metric)
        right_value = right.source.metrics.value(metric)
        assert left_value is not None and right_value is not None
        if METRIC_CATALOG[metric] == MetricDirection.MAX:
            weakly_better = weakly_better and left_value >= right_value
            strictly_better = strictly_better or left_value > right_value
        else:
            weakly_better = weakly_better and left_value <= right_value
            strictly_better = strictly_better or left_value < right_value
    return weakly_better and strictly_better
