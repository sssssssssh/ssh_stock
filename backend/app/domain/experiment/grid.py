import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from itertools import product
from math import prod
from typing import Any

from pydantic import ValidationError

from app.core.portfolio_config import PortfolioConfig
from app.domain.experiment.contracts import (
    EXPERIMENT_PARAMETER_ORDER,
    ExpandedExperimentGrid,
    ExperimentGridError,
    ExperimentTrialDefinition,
)

_DECIMAL_PARAMETERS = {
    "candidate.min_score",
    "construction.max_single_position_weight",
    "construction.min_cash_ratio",
}


def expand_grid(
    *,
    base_portfolio: PortfolioConfig,
    grid: Mapping[str, Sequence[Any]],
    max_trials: int,
    max_values_per_parameter: int,
) -> ExpandedExperimentGrid:
    """Expand the fixed M15.1 Portfolio GRID with deterministic ordering."""
    unknown = set(grid) - set(EXPERIMENT_PARAMETER_ORDER)
    if unknown:
        raise ExperimentGridError(
            "EXPERIMENT_GRID_INVALID",
            f"unsupported experiment parameters: {sorted(unknown)}",
        )

    base = base_portfolio.model_dump(mode="json")
    canonical_space: dict[str, list[Any]] = {}
    for path in EXPERIMENT_PARAMETER_ORDER:
        supplied = grid.get(path)
        if supplied is None:
            section, field = path.split(".", maxsplit=1)
            supplied = [base[section][field]]
        canonical_space[path] = _canonical_values(
            path,
            supplied,
            max_values=max_values_per_parameter,
        )

    trial_count = prod(len(canonical_space[path]) for path in EXPERIMENT_PARAMETER_ORDER)
    if trial_count < 1:
        raise ExperimentGridError(
            "EXPERIMENT_GRID_INVALID", "experiment grid must produce at least one trial"
        )
    if trial_count > max_trials:
        raise ExperimentGridError(
            "EXPERIMENT_TRIAL_LIMIT_EXCEEDED",
            f"experiment grid produces {trial_count} trials; maximum is {max_trials}",
        )

    trials: list[ExperimentTrialDefinition] = []
    ordered_values = [canonical_space[path] for path in EXPERIMENT_PARAMETER_ORDER]
    for trial_no, values in enumerate(product(*ordered_values), start=1):
        parameters = dict(zip(EXPERIMENT_PARAMETER_ORDER, values, strict=True))
        snapshot = deepcopy(base)
        for path, value in parameters.items():
            section, field = path.split(".", maxsplit=1)
            snapshot[section][field] = value
        try:
            portfolio = PortfolioConfig.model_validate(snapshot)
        except ValidationError as exc:
            raise ExperimentGridError(
                "EXPERIMENT_CONFIG_INVALID",
                f"trial {trial_no} has invalid portfolio configuration: {exc}",
            ) from exc
        if portfolio.candidate.top_n < portfolio.construction.max_positions:
            raise ExperimentGridError(
                "EXPERIMENT_CONFIG_INVALID",
                f"trial {trial_no}: candidate.top_n must be >= construction.max_positions",
            )
        if (
            portfolio.construction.max_new_positions_per_day
            > portfolio.construction.max_positions
        ):
            raise ExperimentGridError(
                "EXPERIMENT_CONFIG_INVALID",
                "trial "
                f"{trial_no}: construction.max_new_positions_per_day must be <= "
                "construction.max_positions",
            )
        frozen = portfolio.model_dump(mode="json")
        trials.append(
            ExperimentTrialDefinition(
                trial_no=trial_no,
                parameter_values=parameters,
                parameter_hash=_config_hash(parameters),
                portfolio_config_snapshot=frozen,
                portfolio_config_hash=_config_hash(frozen),
            )
        )

    return ExpandedExperimentGrid(
        parameter_space=canonical_space,
        parameter_space_hash=_config_hash(canonical_space),
        trials=tuple(trials),
    )


def _canonical_values(path: str, values: Sequence[Any], *, max_values: int) -> list[Any]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ExperimentGridError(
            "EXPERIMENT_GRID_INVALID", f"{path} must be a list"
        )
    if not values:
        raise ExperimentGridError(
            "EXPERIMENT_GRID_INVALID", f"{path} must not be empty"
        )
    if len(values) > max_values:
        raise ExperimentGridError(
            "EXPERIMENT_GRID_INVALID",
            f"{path} contains {len(values)} values; maximum is {max_values}",
        )
    canonical = [
        _canonical_decimal(path, value)
        if path in _DECIMAL_PARAMETERS
        else _canonical_integer(path, value)
        for value in values
    ]
    if len(set(canonical)) != len(canonical):
        raise ExperimentGridError(
            "EXPERIMENT_GRID_INVALID", f"{path} contains duplicate values"
        )
    return sorted(canonical, key=Decimal if path in _DECIMAL_PARAMETERS else None)


def _canonical_decimal(path: str, value: Any) -> str:
    if isinstance(value, bool):
        raise ExperimentGridError(
            "EXPERIMENT_GRID_INVALID", f"{path} values must be finite decimals"
        )
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ExperimentGridError(
            "EXPERIMENT_GRID_INVALID", f"{path} values must be finite decimals"
        ) from exc
    if not number.is_finite():
        raise ExperimentGridError(
            "EXPERIMENT_GRID_INVALID", f"{path} values must be finite decimals"
        )
    if path == "candidate.min_score" and number < 0:
        raise ExperimentGridError("EXPERIMENT_GRID_INVALID", f"{path} must be >= 0")
    if path == "construction.max_single_position_weight" and not 0 < number <= 1:
        raise ExperimentGridError("EXPERIMENT_GRID_INVALID", f"{path} must be in (0, 1]")
    if path == "construction.min_cash_ratio" and not 0 <= number < 1:
        raise ExperimentGridError("EXPERIMENT_GRID_INVALID", f"{path} must be in [0, 1)")
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def _canonical_integer(path: str, value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise ExperimentGridError(
            "EXPERIMENT_GRID_INVALID", f"{path} values must be positive integers"
        )
    return value


def _config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(
        config, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
