import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class EvaluationMetricSnapshot:
    trade_days: Decimal | None = None
    cumulative_return: Decimal | None = None
    annualized_return: Decimal | None = None
    max_drawdown_abs: Decimal | None = None
    strategy_annualized_volatility: Decimal | None = None
    excess_cumulative_return: Decimal | None = None
    sharpe_ratio: Decimal | None = None
    sortino_ratio: Decimal | None = None
    calmar_ratio: Decimal | None = None
    information_ratio: Decimal | None = None
    alpha_annualized: Decimal | None = None
    annualized_turnover: Decimal | None = None
    total_cost_to_initial_capital: Decimal | None = None
    closed_episode_count: Decimal | None = None
    win_rate: Decimal | None = None
    profit_factor: Decimal | None = None
    payoff_ratio: Decimal | None = None
    closed_realized_pnl: Decimal | None = None
    positive_month_rate: Decimal | None = None
    worst_month_return: Decimal | None = None
    monthly_return_volatility: Decimal | None = None

    def value(self, metric: str) -> Decimal | None:
        value = getattr(self, metric, None)
        return value if isinstance(value, Decimal) or value is None else Decimal(value)


@dataclass(frozen=True)
class EvaluationTrialInput:
    trial_id: uuid.UUID
    trial_no: int
    parameter_hash: str
    parameter_values: dict[str, Any]
    run_id: uuid.UUID | None
    run_status: str
    metrics: EvaluationMetricSnapshot | None = None
    performance_id: uuid.UUID | None = None
    risk_id: uuid.UUID | None = None
    trade_id: uuid.UUID | None = None
    period_id: uuid.UUID | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationPolicy:
    primary_objective: str
    shortlist_size: int
    constraints: dict[str, Decimal | int | None]
    pareto_metrics: tuple[str, ...]
    tie_breakers: tuple[str, ...]


@dataclass(frozen=True)
class ConstraintResult:
    feasible: bool
    violations: tuple[str, ...]


@dataclass(frozen=True)
class EvaluatedTrial:
    source: EvaluationTrialInput
    status: str
    exclusion_reason: str | None
    feasible: bool
    constraint_violations: tuple[str, ...]
    primary_objective_value: Decimal | None
    pareto_front: int | None = None
    selection_rank: int | None = None
    shortlisted: bool = False


@dataclass(frozen=True)
class SensitivityRow:
    parameter_name: str
    parameter_value: str
    trial_count: int
    evaluated_count: int
    feasible_count: int
    feasible_rate: Decimal
    pareto_front1_count: int
    pareto_front1_rate: Decimal | None
    primary_objective_sample_count: int
    mean_primary_objective: Decimal | None
    median_primary_objective: Decimal | None
    best_primary_objective: Decimal | None
    worst_primary_objective: Decimal | None
    mean_annualized_return: Decimal | None
    mean_max_drawdown_abs: Decimal | None
    mean_annualized_turnover: Decimal | None


@dataclass(frozen=True)
class EvaluationResult:
    trials: tuple[EvaluatedTrial, ...]
    sensitivity: tuple[SensitivityRow, ...]
    warnings: tuple[str, ...]
