from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.domain.experiment.contracts import EXPERIMENT_PARAMETER_ORDER


@dataclass(frozen=True)
class ParameterStabilityRow:
    parameter_name: str
    parameter_value: str
    selected_window_count: int
    selected_rate: Decimal


@dataclass(frozen=True)
class ParameterStabilityResult:
    unique_selected_parameter_hash_count: int
    dominant_parameter_hash: str
    dominant_parameter_hash_count: int
    dominant_parameter_hash_rate: Decimal
    rows: tuple[ParameterStabilityRow, ...]


def _canonical_parameter_value(value: Any) -> str:
    if isinstance(value, Decimal):
        return "0" if value == 0 else format(value.normalize(), "f")
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def calculate_parameter_stability(
    selections: tuple[tuple[str, dict[str, Any]], ...],
) -> ParameterStabilityResult:
    if not selections:
        raise ValueError("parameter stability requires at least one selection")
    hashes = Counter(parameter_hash for parameter_hash, _ in selections)
    dominant_count = max(hashes.values())
    dominant_hash = min(
        value for value, count in hashes.items() if count == dominant_count
    )
    counts: dict[str, Counter[str]] = {
        name: Counter() for name in EXPERIMENT_PARAMETER_ORDER
    }
    for _, values in selections:
        if set(values) != set(EXPERIMENT_PARAMETER_ORDER):
            raise ValueError("selected parameter set is incomplete")
        for name in EXPERIMENT_PARAMETER_ORDER:
            counts[name][_canonical_parameter_value(values[name])] += 1
    total = Decimal(len(selections))
    rows: list[ParameterStabilityRow] = []
    for name in EXPERIMENT_PARAMETER_ORDER:
        selected = sorted(counts[name].items())
        assigned = Decimal(0)
        for index, (value, count) in enumerate(selected):
            rate = (
                Decimal(1) - assigned
                if index == len(selected) - 1
                else Decimal(count) / total
            )
            rows.append(
                ParameterStabilityRow(
                    parameter_name=name,
                    parameter_value=value,
                    selected_window_count=count,
                    selected_rate=rate,
                )
            )
            assigned += rate
    return ParameterStabilityResult(
        unique_selected_parameter_hash_count=len(hashes),
        dominant_parameter_hash=dominant_hash,
        dominant_parameter_hash_count=dominant_count,
        dominant_parameter_hash_rate=Decimal(dominant_count) / total,
        rows=tuple(rows),
    )
