import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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


class PortfolioWalkForwardStudy(Base):
    __tablename__ = "portfolio_walk_forward_study"
    __table_args__ = (
        CheckConstraint(
            "walk_forward_version = 'walk_forward_v1'",
            name=conv("ck_walk_forward_study_version"),
        ),
        CheckConstraint(
            "mode IN ('ROLLING','EXPANDING')",
            name=conv("ck_walk_forward_study_mode"),
        ),
        CheckConstraint(
            "requested_end_date >= requested_start_date",
            name=conv("ck_walk_forward_study_dates"),
        ),
        CheckConstraint(
            "train_trade_days > 0 AND test_trade_days > 0",
            name=conv("ck_walk_forward_study_trade_days"),
        ),
        CheckConstraint(
            "step_trade_days = test_trade_days",
            name=conv("ck_walk_forward_study_step"),
        ),
        CheckConstraint(
            "window_count > 0 AND unused_tail_trade_days >= 0",
            name=conv("ck_walk_forward_study_window_counts"),
        ),
        CheckConstraint(
            "initial_cash > 0", name=conv("ck_walk_forward_study_initial_cash")
        ),
        Index("idx_walk_forward_study_definition", "definition_hash"),
        Index("idx_walk_forward_study_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str | None] = mapped_column(String(128))
    walk_forward_version: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)
    requested_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    requested_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    train_trade_days: Mapped[int] = mapped_column(Integer, nullable=False)
    test_trade_days: Mapped[int] = mapped_column(Integer, nullable=False)
    step_trade_days: Mapped[int] = mapped_column(Integer, nullable=False)
    window_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unused_tail_trade_days: Mapped[int] = mapped_column(Integer, nullable=False)
    calendar_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    benchmark_code: Mapped[str] = mapped_column(String(16), nullable=False)
    parameter_space: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    parameter_space_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    train_policy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    train_policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    base_algo_version: Mapped[str] = mapped_column(String(32), nullable=False)
    base_source_strategy_config_hash: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    base_opportunity_calc_version: Mapped[str] = mapped_column(
        String(32), nullable=False
    )
    base_opportunity_config_hash: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    base_portfolio_version: Mapped[str] = mapped_column(String(32), nullable=False)
    base_portfolio_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    base_execution_version: Mapped[str] = mapped_column(String(32), nullable=False)
    base_execution_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    base_accounting_version: Mapped[str] = mapped_column(String(32), nullable=False)
    base_accounting_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    base_backtest_engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    base_config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PortfolioWalkForwardWindow(Base):
    __tablename__ = "portfolio_walk_forward_window"
    __table_args__ = (
        PrimaryKeyConstraint("study_id", "window_no"),
        ForeignKeyConstraint(
            ("train_evaluation_id", "train_experiment_id"),
            (
                "portfolio_experiment_evaluation_report.id",
                "portfolio_experiment_evaluation_report.experiment_id",
            ),
            name=conv("fk_walk_forward_window_train_evaluation"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("selected_trial_id", "train_experiment_id"),
            ("portfolio_experiment_trial.id", "portfolio_experiment_trial.experiment_id"),
            name=conv("fk_walk_forward_window_selected_trial"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("oos_performance_id", "oos_run_id"),
            ("portfolio_performance_report.id", "portfolio_performance_report.run_id"),
            name=conv("fk_walk_forward_window_oos_performance"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("oos_risk_id", "oos_performance_id", "oos_run_id"),
            (
                "portfolio_performance_risk_report.id",
                "portfolio_performance_risk_report.performance_id",
                "portfolio_performance_risk_report.run_id",
            ),
            name=conv("fk_walk_forward_window_oos_risk"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("oos_trade_id", "oos_performance_id", "oos_run_id"),
            (
                "portfolio_performance_trade_report.id",
                "portfolio_performance_trade_report.performance_id",
                "portfolio_performance_trade_report.run_id",
            ),
            name=conv("fk_walk_forward_window_oos_trade"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            (
                "oos_period_id",
                "oos_performance_id",
                "oos_risk_id",
                "oos_trade_id",
                "oos_run_id",
            ),
            (
                "portfolio_performance_period_report.id",
                "portfolio_performance_period_report.performance_id",
                "portfolio_performance_period_report.risk_id",
                "portfolio_performance_period_report.trade_id",
                "portfolio_performance_period_report.run_id",
            ),
            name=conv("fk_walk_forward_window_oos_period"),
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "train_experiment_id", name=conv("uq_walk_forward_window_train_experiment")
        ),
        UniqueConstraint(
            "train_evaluation_id", name=conv("uq_walk_forward_window_train_evaluation")
        ),
        UniqueConstraint("oos_run_id", name=conv("uq_walk_forward_window_oos_run")),
        CheckConstraint("window_no > 0", name=conv("ck_walk_forward_window_number")),
        CheckConstraint(
            "train_end_date < test_start_date",
            name=conv("ck_walk_forward_window_date_order"),
        ),
        CheckConstraint(
            "train_trade_days > 0 AND test_trade_days > 0",
            name=conv("ck_walk_forward_window_trade_days"),
        ),
        CheckConstraint(
            "num_nonnulls(train_evaluation_id, selected_trial_id, "
            "selected_parameter_hash, selected_parameter_values, "
            "selected_portfolio_config_hash, selected_portfolio_config_snapshot, "
            "selected_at) IN (0, 7)",
            name=conv("ck_walk_forward_window_selection_all_or_none"),
        ),
        CheckConstraint(
            "train_evaluation_id IS NULL OR train_experiment_id IS NOT NULL",
            name=conv("ck_walk_forward_window_selection_has_train"),
        ),
        CheckConstraint(
            "num_nonnulls(oos_performance_id, oos_risk_id, oos_trade_id, "
            "oos_period_id, oos_bound_at) IN (0, 5)",
            name=conv("ck_walk_forward_window_oos_bundle_all_or_none"),
        ),
        CheckConstraint(
            "oos_performance_id IS NULL OR oos_run_id IS NOT NULL",
            name=conv("ck_walk_forward_window_bundle_has_run"),
        ),
        CheckConstraint(
            "oos_run_id IS NULL OR selected_trial_id IS NOT NULL",
            name=conv("ck_walk_forward_window_oos_after_selection"),
        ),
        Index("idx_walk_forward_window_train", "train_experiment_id"),
        Index("idx_walk_forward_window_oos", "oos_run_id"),
    )

    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_walk_forward_study.id", ondelete="CASCADE"),
        nullable=False,
    )
    window_no: Mapped[int] = mapped_column(Integer, nullable=False)
    train_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    train_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    test_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    test_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    train_trade_days: Mapped[int] = mapped_column(Integer, nullable=False)
    test_trade_days: Mapped[int] = mapped_column(Integer, nullable=False)
    train_trade_dates: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    test_trade_dates: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    train_date_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    test_date_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    train_experiment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_experiment.id", ondelete="RESTRICT"),
    )
    train_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    selected_trial_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    selected_parameter_hash: Mapped[str | None] = mapped_column(String(64))
    selected_parameter_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    selected_portfolio_config_hash: Mapped[str | None] = mapped_column(String(64))
    selected_portfolio_config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB
    )
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    oos_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_backtest_run.id", ondelete="RESTRICT"),
    )
    oos_performance_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    oos_risk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    oos_trade_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    oos_period_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    oos_bound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PortfolioWalkForwardValidationReport(Base):
    __tablename__ = "portfolio_walk_forward_validation_report"
    __table_args__ = (
        UniqueConstraint(
            "study_id",
            "walk_forward_version",
            "policy_identity_version",
            "validation_policy_hash",
            "source_hash",
            name=conv("uq_walk_forward_validation_identity"),
        ),
        UniqueConstraint(
            "id", "study_id", name=conv("uq_walk_forward_validation_owner")
        ),
        CheckConstraint("status = 'SUCCESS'", name=conv("ck_walk_forward_validation_status")),
        CheckConstraint(
            "window_count > 0 AND total_oos_trade_days > 0",
            name=conv("ck_walk_forward_validation_counts"),
        ),
        CheckConstraint(
            "positive_oos_window_count >= 0 AND "
            "positive_oos_window_count <= window_count",
            name=conv("ck_walk_forward_validation_positive"),
        ),
        CheckConstraint(
            "(policy_identity_version = 'legacy_v0' AND "
            "validation_policy_hash = walk_forward_config_hash) OR "
            "(policy_identity_version = 'policy_v1' AND "
            "validation_policy_snapshot->>'version' = "
            "'walk_forward_validation_policy_v1')",
            name=conv("ck_walk_forward_validation_policy_identity"),
        ),
        CheckConstraint(
            "transition_count = GREATEST(window_count - 1, 0) AND "
            "switch_count >= 0 AND switch_count <= transition_count AND "
            "((transition_count = 0 AND switch_rate IS NULL) OR "
            "(transition_count > 0 AND switch_rate >= 0 AND switch_rate <= 1))",
            name=conv("ck_walk_forward_validation_switches"),
        ),
        Index("idx_walk_forward_validation_history", "study_id", "calculated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_walk_forward_study.id", ondelete="CASCADE"),
        nullable=False,
    )
    walk_forward_version: Mapped[str] = mapped_column(String(32), nullable=False)
    walk_forward_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_identity_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="policy_v1", server_default=text("'policy_v1'")
    )
    validation_policy_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False
    )
    validation_policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SUCCESS", server_default=text("'SUCCESS'")
    )
    window_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_oos_trade_days: Mapped[int] = mapped_column(Integer, nullable=False)
    stitched_oos_final_nav: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    stitched_oos_cumulative_return: Mapped[Decimal] = mapped_column(
        Numeric(60, 18), nullable=False
    )
    stitched_oos_annualized_return: Mapped[Decimal] = mapped_column(
        Numeric(60, 18), nullable=False
    )
    stitched_oos_max_drawdown: Mapped[Decimal] = mapped_column(
        Numeric(60, 18), nullable=False
    )
    stitched_oos_annualized_volatility: Mapped[Decimal | None] = mapped_column(
        Numeric(60, 18)
    )
    stitched_oos_sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    stitched_benchmark_final_nav: Mapped[Decimal] = mapped_column(
        Numeric(60, 18), nullable=False
    )
    stitched_benchmark_cumulative_return: Mapped[Decimal] = mapped_column(
        Numeric(60, 18), nullable=False
    )
    stitched_excess_cumulative_return: Mapped[Decimal] = mapped_column(
        Numeric(60, 18), nullable=False
    )
    positive_oos_window_count: Mapped[int] = mapped_column(Integer, nullable=False)
    positive_oos_window_rate: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    mean_oos_annualized_return: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    median_oos_annualized_return: Mapped[Decimal] = mapped_column(
        Numeric(60, 18), nullable=False
    )
    mean_return_degradation: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    median_return_degradation: Mapped[Decimal] = mapped_column(
        Numeric(60, 18), nullable=False
    )
    mean_drawdown_worsening: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    median_drawdown_worsening: Mapped[Decimal] = mapped_column(
        Numeric(60, 18), nullable=False
    )
    unique_selected_parameter_hash_count: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    dominant_parameter_hash: Mapped[str | None] = mapped_column(String(64))
    dominant_parameter_hash_count: Mapped[int] = mapped_column(Integer, nullable=False)
    dominant_parameter_hash_rate: Mapped[Decimal] = mapped_column(
        Numeric(60, 18), nullable=False
    )
    transition_count: Mapped[int] = mapped_column(Integer, nullable=False)
    switch_count: Mapped[int] = mapped_column(Integer, nullable=False)
    switch_rate: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
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
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PortfolioWalkForwardWindowValidation(Base):
    __tablename__ = "portfolio_walk_forward_window_validation"
    __table_args__ = (
        PrimaryKeyConstraint("validation_id", "window_no"),
        ForeignKeyConstraint(
            ("validation_id", "study_id"),
            (
                "portfolio_walk_forward_validation_report.id",
                "portfolio_walk_forward_validation_report.study_id",
            ),
            name=conv("fk_walk_forward_window_validation_report"),
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("study_id", "window_no"),
            ("portfolio_walk_forward_window.study_id", "portfolio_walk_forward_window.window_no"),
            name=conv("fk_walk_forward_window_validation_window"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("train_evaluation_id", "train_experiment_id"),
            (
                "portfolio_experiment_evaluation_report.id",
                "portfolio_experiment_evaluation_report.experiment_id",
            ),
            name=conv("fk_walk_forward_window_result_train_evaluation"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("selected_trial_id", "train_experiment_id"),
            (
                "portfolio_experiment_trial.id",
                "portfolio_experiment_trial.experiment_id",
            ),
            name=conv("fk_walk_forward_window_result_selected_trial"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("train_evaluation_id", "selected_trial_id"),
            (
                "portfolio_experiment_trial_evaluation.evaluation_id",
                "portfolio_experiment_trial_evaluation.trial_id",
            ),
            name=conv("fk_walk_forward_window_result_trial_evaluation"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("selected_trial_id", "selected_train_run_id"),
            ("portfolio_experiment_trial.id", "portfolio_experiment_trial.run_id"),
            name=conv("fk_walk_forward_window_result_train_run"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("train_performance_id", "selected_train_run_id"),
            ("portfolio_performance_report.id", "portfolio_performance_report.run_id"),
            name=conv("fk_walk_forward_window_result_train_performance"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("train_risk_id", "train_performance_id", "selected_train_run_id"),
            (
                "portfolio_performance_risk_report.id",
                "portfolio_performance_risk_report.performance_id",
                "portfolio_performance_risk_report.run_id",
            ),
            name=conv("fk_walk_forward_window_result_train_risk"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("train_trade_id", "train_performance_id", "selected_train_run_id"),
            (
                "portfolio_performance_trade_report.id",
                "portfolio_performance_trade_report.performance_id",
                "portfolio_performance_trade_report.run_id",
            ),
            name=conv("fk_walk_forward_window_result_train_trade"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            (
                "train_period_id",
                "train_performance_id",
                "train_risk_id",
                "train_trade_id",
                "selected_train_run_id",
            ),
            (
                "portfolio_performance_period_report.id",
                "portfolio_performance_period_report.performance_id",
                "portfolio_performance_period_report.risk_id",
                "portfolio_performance_period_report.trade_id",
                "portfolio_performance_period_report.run_id",
            ),
            name=conv("fk_walk_forward_window_result_train_period"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("oos_performance_id", "oos_run_id"),
            ("portfolio_performance_report.id", "portfolio_performance_report.run_id"),
            name=conv("fk_walk_forward_window_result_oos_performance"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("oos_risk_id", "oos_performance_id", "oos_run_id"),
            (
                "portfolio_performance_risk_report.id",
                "portfolio_performance_risk_report.performance_id",
                "portfolio_performance_risk_report.run_id",
            ),
            name=conv("fk_walk_forward_window_result_oos_risk"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("oos_trade_id", "oos_performance_id", "oos_run_id"),
            (
                "portfolio_performance_trade_report.id",
                "portfolio_performance_trade_report.performance_id",
                "portfolio_performance_trade_report.run_id",
            ),
            name=conv("fk_walk_forward_window_result_oos_trade"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            (
                "oos_period_id",
                "oos_performance_id",
                "oos_risk_id",
                "oos_trade_id",
                "oos_run_id",
            ),
            (
                "portfolio_performance_period_report.id",
                "portfolio_performance_period_report.performance_id",
                "portfolio_performance_period_report.risk_id",
                "portfolio_performance_period_report.trade_id",
                "portfolio_performance_period_report.run_id",
            ),
            name=conv("fk_walk_forward_window_result_oos_period"),
            ondelete="RESTRICT",
        ),
        CheckConstraint("window_no > 0", name=conv("ck_walk_forward_window_validation_no")),
        CheckConstraint(
            "jsonb_typeof(identity_snapshot) = 'object' AND "
            "identity_snapshot->>'schema_version' = "
            "'walk_forward_window_validation_identity_v1' AND "
            "jsonb_typeof(identity_snapshot->'train') = 'object' AND "
            "jsonb_typeof(identity_snapshot->'oos') = 'object'",
            name=conv("ck_walk_forward_window_validation_identity_schema"),
        ),
    )

    validation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    study_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    window_no: Mapped[int] = mapped_column(Integer, nullable=False)
    train_experiment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    train_evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    selected_trial_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    selected_train_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    train_performance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    train_risk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    train_trade_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    train_period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    selected_parameter_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_parameter_values: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    train_date_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    test_date_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    oos_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    oos_performance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    oos_risk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    oos_trade_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    oos_period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    train_annualized_return: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    train_max_drawdown_abs: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    train_sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    train_annualized_turnover: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    oos_cumulative_return: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    oos_annualized_return: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    oos_max_drawdown_abs: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    oos_sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    oos_annualized_turnover: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    oos_total_cost_to_initial_capital: Mapped[Decimal] = mapped_column(
        Numeric(60, 18), nullable=False
    )
    oos_win_rate: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    oos_profit_factor: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    return_degradation: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    sharpe_degradation: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    drawdown_worsening: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    turnover_change: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PortfolioWalkForwardParameterStability(Base):
    __tablename__ = "portfolio_walk_forward_parameter_stability"
    __table_args__ = (
        PrimaryKeyConstraint("validation_id", "parameter_name", "parameter_value"),
        ForeignKeyConstraint(
            ("validation_id", "study_id"),
            (
                "portfolio_walk_forward_validation_report.id",
                "portfolio_walk_forward_validation_report.study_id",
            ),
            name=conv("fk_walk_forward_parameter_stability_report"),
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "parameter_name IN ('candidate.min_score','candidate.top_n',"
            "'construction.max_positions','construction.max_single_position_weight',"
            "'construction.min_cash_ratio','construction.max_new_positions_per_day')",
            name=conv("ck_walk_forward_parameter_stability_name"),
        ),
        CheckConstraint(
            "selected_window_count > 0",
            name=conv("ck_walk_forward_parameter_stability_count"),
        ),
        CheckConstraint(
            "selected_rate > 0 AND selected_rate <= 1",
            name=conv("ck_walk_forward_parameter_stability_rate"),
        ),
        CheckConstraint(
            "transition_count >= 0 AND adjacent_value_switch_count >= 0 AND "
            "adjacent_value_switch_count <= transition_count AND "
            "((transition_count = 0 AND adjacent_value_switch_rate IS NULL) OR "
            "(transition_count > 0 AND adjacent_value_switch_rate >= 0 AND "
            "adjacent_value_switch_rate <= 1))",
            name=conv("ck_walk_forward_parameter_stability_switches"),
        ),
    )

    validation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    study_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    parameter_name: Mapped[str] = mapped_column(String(96), nullable=False)
    parameter_value: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_window_count: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_rate: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    transition_count: Mapped[int] = mapped_column(Integer, nullable=False)
    adjacent_value_switch_count: Mapped[int] = mapped_column(Integer, nullable=False)
    adjacent_value_switch_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(60, 18)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
