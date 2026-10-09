from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.experiment.contracts import EXPERIMENT_PARAMETER_ORDER


@dataclass(frozen=True)
class ParameterStabilityRow:
    parameter_name: str
    parameter_value: str
    selected_window_count: int
    selected_rate: Decimal
    transition_count: int
    adjacent_value_switch_count: int
    adjacent_value_switch_rate: Decimal | None


@dataclass(frozen=True)
class ParameterStabilityResult:
    unique_selected_parameter_hash_count: int
    dominant_parameter_hash: str
    dominant_parameter_hash_count: int
    dominant_parameter_hash_rate: Decimal
    transition_count: int
    switch_count: int
    switch_rate: Decimal | None
    warnings: tuple[str, ...]
    rows: tuple[ParameterStabilityRow, ...]


def _canonical_parameter_value(value: Any) -> str:
    if isinstance(value, Decimal):
        return "0" if value == 0 else format(value.normalize(), "f")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        try:
            decimal = Decimal(value)
        except (InvalidOperation, ValueError):
            return value
        return "0" if decimal == 0 else format(decimal.normalize(), "f")
    return str(value)


def calculate_parameter_stability(
    selections: tuple[tuple[str, dict[str, Any]], ...],
    *,
    frequent_switch_rate_threshold: Decimal = Decimal("0.5"),
    low_dominant_parameter_rate_threshold: Decimal = Decimal("0.5"),
) -> ParameterStabilityResult:
    if not selections:
        raise ValueError("parameter stability requires at least one selection")
    hashes = Counter(parameter_hash for parameter_hash, _ in selections)
    dominant_count = max(hashes.values())
    dominant_hash = min(
        value for value, count in hashes.items() if count == dominant_count
    )
    transition_count = max(len(selections) - 1, 0)
    switch_count = sum(
        current_hash != previous_hash
        for (previous_hash, _), (current_hash, _) in zip(
            selections, selections[1:], strict=False
        )
    )
    switch_rate = (
        Decimal(switch_count) / Decimal(transition_count)
        if transition_count
        else None
    )
    counts: dict[str, Counter[str]] = {
        name: Counter() for name in EXPERIMENT_PARAMETER_ORDER
    }
    for _, values in selections:
        if set(values) != set(EXPERIMENT_PARAMETER_ORDER):
            raise ValueError("selected parameter set is incomplete")
        for name in EXPERIMENT_PARAMETER_ORDER:
            counts[name][_canonical_parameter_value(values[name])] += 1
    parameter_switches: dict[str, int] = {}
    for name in EXPERIMENT_PARAMETER_ORDER:
        canonical_values = tuple(
            _canonical_parameter_value(values[name]) for _, values in selections
        )
        parameter_switches[name] = sum(
            current != previous
            for previous, current in zip(
                canonical_values, canonical_values[1:], strict=False
            )
        )
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
                    transition_count=transition_count,
                    adjacent_value_switch_count=parameter_switches[name],
                    adjacent_value_switch_rate=(
                        Decimal(parameter_switches[name])
                        / Decimal(transition_count)
                        if transition_count
                        else None
                    ),
                )
            )
            assigned += rate
    dominant_rate = Decimal(dominant_count) / total
    warnings: list[str] = []
    if len(selections) > 1 and len(hashes) == len(selections):
        warnings.append("ALL_WINDOWS_SELECT_DIFFERENT_PARAMETERS")
    if (
        switch_rate is not None
        and switch_rate >= frequent_switch_rate_threshold
        and switch_count > 0
    ):
        warnings.append("FREQUENT_PARAMETER_SWITCHING")
    if dominant_rate < low_dominant_parameter_rate_threshold:
        warnings.append("LOW_DOMINANT_PARAMETER_RATE")
    return ParameterStabilityResult(
        unique_selected_parameter_hash_count=len(hashes),
        dominant_parameter_hash=dominant_hash,
        dominant_parameter_hash_count=dominant_count,
        dominant_parameter_hash_rate=dominant_rate,
        transition_count=transition_count,
        switch_count=switch_count,
        switch_rate=switch_rate,
        warnings=tuple(warnings),
        rows=tuple(rows),
    )
