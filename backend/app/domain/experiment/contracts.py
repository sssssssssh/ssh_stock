from dataclasses import dataclass
from typing import Any

EXPERIMENT_PARAMETER_ORDER = (
    "candidate.min_score",
    "candidate.top_n",
    "construction.max_positions",
    "construction.max_single_position_weight",
    "construction.min_cash_ratio",
    "construction.max_new_positions_per_day",
)


class ExperimentGridError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ExperimentTrialDefinition:
    trial_no: int
    parameter_values: dict[str, Any]
    parameter_hash: str
    portfolio_config_snapshot: dict[str, Any]
    portfolio_config_hash: str


@dataclass(frozen=True)
class ExpandedExperimentGrid:
    parameter_space: dict[str, list[Any]]
    parameter_space_hash: str
    trials: tuple[ExperimentTrialDefinition, ...]
