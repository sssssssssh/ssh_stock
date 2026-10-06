from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EXPERIMENT_EVALUATION_VERSION = "experiment_eval_v1"


class EvaluationConstraintsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_trade_days: int | None = Field(default=None, gt=0)
    min_annualized_return: Decimal | None = None
    max_drawdown_abs: Decimal | None = Field(default=None, ge=0)
    min_sharpe_ratio: Decimal | None = None
    min_calmar_ratio: Decimal | None = None
    max_annualized_turnover: Decimal | None = Field(default=None, ge=0)
    max_total_cost_to_initial_capital: Decimal | None = Field(default=None, ge=0)
    min_closed_episode_count: int | None = Field(default=None, ge=0)
    min_win_rate: Decimal | None = Field(default=None, ge=0, le=1)
    min_profit_factor: Decimal | None = Field(default=None, ge=0)


class EvaluationPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_objective: str
    shortlist_size: int = Field(gt=0)
    constraints: EvaluationConstraintsConfig = Field(
        default_factory=EvaluationConstraintsConfig
    )
    pareto_metrics: tuple[str, ...]
    tie_breakers: tuple[str, ...] = ()

    @field_validator("pareto_metrics", "tie_breakers")
    @classmethod
    def reject_duplicates(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("metric lists must not contain duplicates")
        return value

    @model_validator(mode="after")
    def reject_primary_tie_breaker(self) -> "EvaluationPolicyConfig":
        if self.primary_objective in self.tie_breakers:
            raise ValueError("primary_objective must not be repeated in tie_breakers")
        return self


class ExperimentEvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["experiment_eval_v1"]
    max_shortlist_size: int = Field(gt=0)
    max_pareto_metrics: int = Field(ge=2)
    minimum_month_observations: int = Field(ge=2)
    default_policy: EvaluationPolicyConfig

    @model_validator(mode="after")
    def validate_default_policy(self) -> "ExperimentEvaluationConfig":
        from app.domain.experiment_evaluation.metrics import validate_policy_metrics

        validate_policy_metrics(
            self.default_policy.primary_objective,
            self.default_policy.pareto_metrics,
            self.default_policy.tie_breakers,
        )
        if self.default_policy.shortlist_size > self.max_shortlist_size:
            raise ValueError("default shortlist_size exceeds max_shortlist_size")
        if not 2 <= len(self.default_policy.pareto_metrics) <= self.max_pareto_metrics:
            raise ValueError("default pareto metric count is outside configured bounds")
        return self
