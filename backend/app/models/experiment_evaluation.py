import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.naming import conv

from app.models.base import Base


class PortfolioExperimentEvaluationReport(Base):
    __tablename__ = "portfolio_experiment_evaluation_report"
    __table_args__ = (
        UniqueConstraint(
            "experiment_id",
            "evaluation_version",
            "evaluation_config_hash",
            "policy_hash",
            "source_hash",
            name=conv("uq_experiment_evaluation_identity"),
        ),
        UniqueConstraint(
            "id", "experiment_id", name=conv("uq_experiment_evaluation_owner")
        ),
        CheckConstraint("trial_count > 0", name=conv("ck_experiment_eval_trials")),
        CheckConstraint(
            "success_trial_count > 0", name=conv("ck_experiment_eval_success")
        ),
        CheckConstraint(
            "evaluated_trial_count = success_trial_count",
            name=conv("ck_experiment_eval_evaluated"),
        ),
        CheckConstraint(
            "excluded_trial_count + evaluated_trial_count = trial_count",
            name=conv("ck_experiment_eval_total"),
        ),
        CheckConstraint(
            "feasible_count + infeasible_count = evaluated_trial_count",
            name=conv("ck_experiment_eval_feasibility"),
        ),
        CheckConstraint(
            "pareto_front1_count <= feasible_count",
            name=conv("ck_experiment_eval_pareto"),
        ),
        CheckConstraint(
            "shortlist_count <= feasible_count",
            name=conv("ck_experiment_eval_shortlist"),
        ),
        CheckConstraint("status = 'SUCCESS'", name=conv("ck_experiment_eval_status")),
        Index("idx_experiment_eval_history", "experiment_id", "calculated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_experiment.id", ondelete="CASCADE"),
        nullable=False,
    )
    evaluation_version: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluation_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    trial_count: Mapped[int] = mapped_column(Integer, nullable=False)
    success_trial_count: Mapped[int] = mapped_column(Integer, nullable=False)
    excluded_trial_count: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_trial_count: Mapped[int] = mapped_column(Integer, nullable=False)
    feasible_count: Mapped[int] = mapped_column(Integer, nullable=False)
    infeasible_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pareto_front1_count: Mapped[int] = mapped_column(Integer, nullable=False)
    shortlist_count: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_trial_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    selected_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SUCCESS", server_default=text("'SUCCESS'")
    )
    warnings: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    result_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PortfolioExperimentTrialEvaluation(Base):
    __tablename__ = "portfolio_experiment_trial_evaluation"
    __table_args__ = (
        PrimaryKeyConstraint("evaluation_id", "trial_id"),
        ForeignKeyConstraint(
            ("evaluation_id", "experiment_id"),
            (
                "portfolio_experiment_evaluation_report.id",
                "portfolio_experiment_evaluation_report.experiment_id",
            ),
            name=conv("fk_experiment_trial_eval_report_owner"),
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("trial_id", "experiment_id"),
            ("portfolio_experiment_trial.id", "portfolio_experiment_trial.experiment_id"),
            name=conv("fk_experiment_trial_eval_trial_owner"),
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('EVALUATED','EXCLUDED')",
            name=conv("ck_experiment_trial_eval_status"),
        ),
        CheckConstraint("trial_no > 0", name=conv("ck_experiment_trial_eval_number")),
        CheckConstraint(
            "pareto_front IS NULL OR pareto_front > 0",
            name=conv("ck_experiment_trial_eval_front"),
        ),
        CheckConstraint(
            "selection_rank IS NULL OR selection_rank > 0",
            name=conv("ck_experiment_trial_eval_rank"),
        ),
        CheckConstraint(
            "status <> 'EXCLUDED' OR "
            "(feasible = false AND shortlisted = false AND selection_rank IS NULL "
            "AND pareto_front IS NULL)",
            name=conv("ck_experiment_trial_eval_excluded"),
        ),
        CheckConstraint(
            "shortlisted = false OR (feasible = true AND selection_rank IS NOT NULL)",
            name=conv("ck_experiment_trial_eval_shortlisted"),
        ),
        Index("idx_experiment_trial_eval_page", "evaluation_id", "selection_rank"),
    )

    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    experiment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trial_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trial_no: Mapped[int] = mapped_column(Integer, nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(64))
    parameter_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parameter_values: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    performance_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    risk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    trade_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    period_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cumulative_return: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    annualized_return: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    max_drawdown_abs: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    strategy_annualized_volatility: Mapped[Decimal | None] = mapped_column(
        Numeric(60, 18)
    )
    excess_cumulative_return: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    sortino_ratio: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    calmar_ratio: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    information_ratio: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    alpha_annualized: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    annualized_turnover: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    total_cost_to_initial_capital: Mapped[Decimal | None] = mapped_column(
        Numeric(60, 18)
    )
    closed_episode_count: Mapped[int | None] = mapped_column(Integer)
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    profit_factor: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    payoff_ratio: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    closed_realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    positive_month_rate: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    worst_month_return: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    monthly_return_volatility: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    primary_objective_value: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    feasible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    constraint_violations: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    pareto_front: Mapped[int | None] = mapped_column(Integer)
    selection_rank: Mapped[int | None] = mapped_column(Integer)
    shortlisted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    warnings: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PortfolioExperimentParameterSensitivity(Base):
    __tablename__ = "portfolio_experiment_parameter_sensitivity"
    __table_args__ = (
        PrimaryKeyConstraint("evaluation_id", "parameter_name", "parameter_value"),
        ForeignKeyConstraint(
            ("evaluation_id", "experiment_id"),
            (
                "portfolio_experiment_evaluation_report.id",
                "portfolio_experiment_evaluation_report.experiment_id",
            ),
            name=conv("fk_experiment_sensitivity_report_owner"),
            ondelete="CASCADE",
        ),
        CheckConstraint("trial_count > 0", name=conv("ck_experiment_sensitivity_trials")),
        CheckConstraint(
            "evaluated_count >= 0 AND evaluated_count <= trial_count",
            name=conv("ck_experiment_sensitivity_evaluated"),
        ),
        CheckConstraint(
            "feasible_count >= 0 AND feasible_count <= evaluated_count",
            name=conv("ck_experiment_sensitivity_feasible"),
        ),
    )

    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    experiment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    parameter_name: Mapped[str] = mapped_column(String(96), nullable=False)
    parameter_value: Mapped[str] = mapped_column(String(64), nullable=False)
    trial_count: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_count: Mapped[int] = mapped_column(Integer, nullable=False)
    feasible_count: Mapped[int] = mapped_column(Integer, nullable=False)
    feasible_rate: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    pareto_front1_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pareto_front1_rate: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    primary_objective_sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mean_primary_objective: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    median_primary_objective: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    best_primary_objective: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    worst_primary_objective: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    mean_annualized_return: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    mean_max_drawdown_abs: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    mean_annualized_turnover: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
