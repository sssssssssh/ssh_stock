"""Add M15.3 walk-forward out-of-sample validation artifacts.

Revision ID: 0043_m15_3_walk_forward_validation
Revises: 0042_m15_2_experiment_evaluation
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0043_m15_3_walk_forward_validation"
down_revision = "0042_m15_2_experiment_evaluation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The frozen M15.3 revision identifier is longer than Alembic's historical
    # 32-character default. Widen the version column before Alembic records it.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(32),
        type_=sa.String(64),
        existing_nullable=False,
    )
    op.alter_column(
        "job_run",
        "job_type",
        existing_type=sa.String(32),
        type_=sa.String(64),
        existing_nullable=False,
    )
    op.create_table(
        "portfolio_walk_forward_study",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(128)),
        sa.Column("walk_forward_version", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("exchange", sa.String(8), nullable=False),
        sa.Column("requested_start_date", sa.Date(), nullable=False),
        sa.Column("requested_end_date", sa.Date(), nullable=False),
        sa.Column("train_trade_days", sa.Integer(), nullable=False),
        sa.Column("test_trade_days", sa.Integer(), nullable=False),
        sa.Column("step_trade_days", sa.Integer(), nullable=False),
        sa.Column("window_count", sa.Integer(), nullable=False),
        sa.Column("unused_tail_trade_days", sa.Integer(), nullable=False),
        sa.Column("calendar_hash", sa.String(64), nullable=False),
        sa.Column("initial_cash", sa.Numeric(20, 4), nullable=False),
        sa.Column("benchmark_code", sa.String(16), nullable=False),
        sa.Column("parameter_space", postgresql.JSONB(), nullable=False),
        sa.Column("parameter_space_hash", sa.String(64), nullable=False),
        sa.Column("train_policy_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("train_policy_hash", sa.String(64), nullable=False),
        sa.Column("base_algo_version", sa.String(32), nullable=False),
        sa.Column("base_source_strategy_config_hash", sa.String(64), nullable=False),
        sa.Column("base_opportunity_calc_version", sa.String(32), nullable=False),
        sa.Column("base_opportunity_config_hash", sa.String(64), nullable=False),
        sa.Column("base_portfolio_version", sa.String(32), nullable=False),
        sa.Column("base_portfolio_config_hash", sa.String(64), nullable=False),
        sa.Column("base_execution_version", sa.String(32), nullable=False),
        sa.Column("base_execution_config_hash", sa.String(64), nullable=False),
        sa.Column("base_accounting_version", sa.String(32), nullable=False),
        sa.Column("base_accounting_config_hash", sa.String(64), nullable=False),
        sa.Column("base_backtest_engine_version", sa.String(32), nullable=False),
        sa.Column("base_config_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("definition_hash", sa.String(64), nullable=False),
        sa.Column(
            "cancel_requested", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "walk_forward_version = 'walk_forward_v1'",
            name=op.f("ck_walk_forward_study_version"),
        ),
        sa.CheckConstraint(
            "mode IN ('ROLLING','EXPANDING')", name=op.f("ck_walk_forward_study_mode")
        ),
        sa.CheckConstraint(
            "requested_end_date >= requested_start_date",
            name=op.f("ck_walk_forward_study_dates"),
        ),
        sa.CheckConstraint(
            "train_trade_days > 0 AND test_trade_days > 0",
            name=op.f("ck_walk_forward_study_trade_days"),
        ),
        sa.CheckConstraint(
            "step_trade_days = test_trade_days",
            name=op.f("ck_walk_forward_study_step"),
        ),
        sa.CheckConstraint(
            "window_count > 0 AND unused_tail_trade_days >= 0",
            name=op.f("ck_walk_forward_study_window_counts"),
        ),
        sa.CheckConstraint(
            "initial_cash > 0", name=op.f("ck_walk_forward_study_initial_cash")
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_walk_forward_study_definition",
        "portfolio_walk_forward_study",
        ["definition_hash"],
    )
    op.create_index(
        "idx_walk_forward_study_created",
        "portfolio_walk_forward_study",
        ["created_at"],
    )

    op.create_table(
        "portfolio_walk_forward_window",
        sa.Column("study_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("window_no", sa.Integer(), nullable=False),
        sa.Column("train_start_date", sa.Date(), nullable=False),
        sa.Column("train_end_date", sa.Date(), nullable=False),
        sa.Column("test_start_date", sa.Date(), nullable=False),
        sa.Column("test_end_date", sa.Date(), nullable=False),
        sa.Column("train_trade_days", sa.Integer(), nullable=False),
        sa.Column("test_trade_days", sa.Integer(), nullable=False),
        sa.Column("train_trade_dates", postgresql.JSONB(), nullable=False),
        sa.Column("test_trade_dates", postgresql.JSONB(), nullable=False),
        sa.Column("train_date_hash", sa.String(64), nullable=False),
        sa.Column("test_date_hash", sa.String(64), nullable=False),
        sa.Column("train_experiment_id", postgresql.UUID(as_uuid=True)),
        sa.Column("train_evaluation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("selected_trial_id", postgresql.UUID(as_uuid=True)),
        sa.Column("selected_parameter_hash", sa.String(64)),
        sa.Column("selected_parameter_values", postgresql.JSONB()),
        sa.Column("selected_portfolio_config_hash", sa.String(64)),
        sa.Column("selected_portfolio_config_snapshot", postgresql.JSONB()),
        sa.Column("selected_at", sa.DateTime(timezone=True)),
        sa.Column("oos_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("oos_performance_id", postgresql.UUID(as_uuid=True)),
        sa.Column("oos_risk_id", postgresql.UUID(as_uuid=True)),
        sa.Column("oos_trade_id", postgresql.UUID(as_uuid=True)),
        sa.Column("oos_period_id", postgresql.UUID(as_uuid=True)),
        sa.Column("oos_bound_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("window_no > 0", name=op.f("ck_walk_forward_window_number")),
        sa.CheckConstraint(
            "train_end_date < test_start_date",
            name=op.f("ck_walk_forward_window_date_order"),
        ),
        sa.CheckConstraint(
            "train_trade_days > 0 AND test_trade_days > 0",
            name=op.f("ck_walk_forward_window_trade_days"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(train_evaluation_id, selected_trial_id, "
            "selected_parameter_hash, selected_parameter_values, "
            "selected_portfolio_config_hash, selected_portfolio_config_snapshot, "
            "selected_at) IN (0, 7)",
            name=op.f("ck_walk_forward_window_selection_all_or_none"),
        ),
        sa.CheckConstraint(
            "train_evaluation_id IS NULL OR train_experiment_id IS NOT NULL",
            name=op.f("ck_walk_forward_window_selection_has_train"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(oos_performance_id, oos_risk_id, oos_trade_id, "
            "oos_period_id, oos_bound_at) IN (0, 5)",
            name=op.f("ck_walk_forward_window_oos_bundle_all_or_none"),
        ),
        sa.CheckConstraint(
            "oos_performance_id IS NULL OR oos_run_id IS NOT NULL",
            name=op.f("ck_walk_forward_window_bundle_has_run"),
        ),
        sa.CheckConstraint(
            "oos_run_id IS NULL OR selected_trial_id IS NOT NULL",
            name=op.f("ck_walk_forward_window_oos_after_selection"),
        ),
        sa.ForeignKeyConstraint(
            ["study_id"], ["portfolio_walk_forward_study.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["train_experiment_id"], ["portfolio_experiment.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["train_evaluation_id", "train_experiment_id"],
            [
                "portfolio_experiment_evaluation_report.id",
                "portfolio_experiment_evaluation_report.experiment_id",
            ],
            name=op.f("fk_walk_forward_window_train_evaluation"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["selected_trial_id", "train_experiment_id"],
            ["portfolio_experiment_trial.id", "portfolio_experiment_trial.experiment_id"],
            name=op.f("fk_walk_forward_window_selected_trial"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["oos_run_id"], ["portfolio_backtest_run.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["oos_performance_id", "oos_run_id"],
            ["portfolio_performance_report.id", "portfolio_performance_report.run_id"],
            name=op.f("fk_walk_forward_window_oos_performance"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["oos_risk_id", "oos_performance_id", "oos_run_id"],
            [
                "portfolio_performance_risk_report.id",
                "portfolio_performance_risk_report.performance_id",
                "portfolio_performance_risk_report.run_id",
            ],
            name=op.f("fk_walk_forward_window_oos_risk"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["oos_trade_id", "oos_performance_id", "oos_run_id"],
            [
                "portfolio_performance_trade_report.id",
                "portfolio_performance_trade_report.performance_id",
                "portfolio_performance_trade_report.run_id",
            ],
            name=op.f("fk_walk_forward_window_oos_trade"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "oos_period_id",
                "oos_performance_id",
                "oos_risk_id",
                "oos_trade_id",
                "oos_run_id",
            ],
            [
                "portfolio_performance_period_report.id",
                "portfolio_performance_period_report.performance_id",
                "portfolio_performance_period_report.risk_id",
                "portfolio_performance_period_report.trade_id",
                "portfolio_performance_period_report.run_id",
            ],
            name=op.f("fk_walk_forward_window_oos_period"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("study_id", "window_no"),
        sa.UniqueConstraint(
            "train_experiment_id", name=op.f("uq_walk_forward_window_train_experiment")
        ),
        sa.UniqueConstraint(
            "train_evaluation_id", name=op.f("uq_walk_forward_window_train_evaluation")
        ),
        sa.UniqueConstraint("oos_run_id", name=op.f("uq_walk_forward_window_oos_run")),
    )
    op.create_index(
        "idx_walk_forward_window_train",
        "portfolio_walk_forward_window",
        ["train_experiment_id"],
    )
    op.create_index(
        "idx_walk_forward_window_oos",
        "portfolio_walk_forward_window",
        ["oos_run_id"],
    )

    op.create_table(
        "portfolio_walk_forward_validation_report",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("study_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("walk_forward_version", sa.String(32), nullable=False),
        sa.Column("walk_forward_config_hash", sa.String(64), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="SUCCESS", nullable=False),
        sa.Column("window_count", sa.Integer(), nullable=False),
        sa.Column("total_oos_trade_days", sa.Integer(), nullable=False),
        sa.Column("stitched_oos_final_nav", sa.Numeric(60, 18), nullable=False),
        sa.Column("stitched_oos_cumulative_return", sa.Numeric(60, 18), nullable=False),
        sa.Column("stitched_oos_annualized_return", sa.Numeric(60, 18), nullable=False),
        sa.Column("stitched_oos_max_drawdown", sa.Numeric(60, 18), nullable=False),
        sa.Column("stitched_oos_annualized_volatility", sa.Numeric(60, 18)),
        sa.Column("stitched_oos_sharpe_ratio", sa.Numeric(60, 18)),
        sa.Column("stitched_benchmark_final_nav", sa.Numeric(60, 18), nullable=False),
        sa.Column(
            "stitched_benchmark_cumulative_return", sa.Numeric(60, 18), nullable=False
        ),
        sa.Column("stitched_excess_cumulative_return", sa.Numeric(60, 18), nullable=False),
        sa.Column("positive_oos_window_count", sa.Integer(), nullable=False),
        sa.Column("positive_oos_window_rate", sa.Numeric(60, 18), nullable=False),
        sa.Column("mean_oos_annualized_return", sa.Numeric(60, 18), nullable=False),
        sa.Column("median_oos_annualized_return", sa.Numeric(60, 18), nullable=False),
        sa.Column("mean_return_degradation", sa.Numeric(60, 18), nullable=False),
        sa.Column("median_return_degradation", sa.Numeric(60, 18), nullable=False),
        sa.Column("mean_drawdown_worsening", sa.Numeric(60, 18), nullable=False),
        sa.Column("median_drawdown_worsening", sa.Numeric(60, 18), nullable=False),
        sa.Column("unique_selected_parameter_hash_count", sa.Integer(), nullable=False),
        sa.Column("dominant_parameter_hash", sa.String(64)),
        sa.Column("dominant_parameter_hash_count", sa.Integer(), nullable=False),
        sa.Column("dominant_parameter_hash_rate", sa.Numeric(60, 18), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("result_summary", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status = 'SUCCESS'", name=op.f("ck_walk_forward_validation_status")),
        sa.CheckConstraint(
            "window_count > 0 AND total_oos_trade_days > 0",
            name=op.f("ck_walk_forward_validation_counts"),
        ),
        sa.CheckConstraint(
            "positive_oos_window_count >= 0 AND positive_oos_window_count <= window_count",
            name=op.f("ck_walk_forward_validation_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["study_id"], ["portfolio_walk_forward_study.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "study_id",
            "walk_forward_version",
            "walk_forward_config_hash",
            "source_hash",
            name=op.f("uq_walk_forward_validation_identity"),
        ),
        sa.UniqueConstraint(
            "id", "study_id", name=op.f("uq_walk_forward_validation_owner")
        ),
    )
    op.create_index(
        "idx_walk_forward_validation_history",
        "portfolio_walk_forward_validation_report",
        ["study_id", "calculated_at"],
    )

    metric_columns = [
        "train_annualized_return",
        "train_max_drawdown_abs",
        "train_sharpe_ratio",
        "train_annualized_turnover",
        "oos_cumulative_return",
        "oos_annualized_return",
        "oos_max_drawdown_abs",
        "oos_sharpe_ratio",
        "oos_annualized_turnover",
        "oos_total_cost_to_initial_capital",
        "oos_win_rate",
        "oos_profit_factor",
        "return_degradation",
        "sharpe_degradation",
        "drawdown_worsening",
        "turnover_change",
    ]
    required_metrics = {
        "train_annualized_return",
        "train_max_drawdown_abs",
        "train_annualized_turnover",
        "oos_cumulative_return",
        "oos_annualized_return",
        "oos_max_drawdown_abs",
        "oos_annualized_turnover",
        "oos_total_cost_to_initial_capital",
        "return_degradation",
        "drawdown_worsening",
        "turnover_change",
    }
    op.create_table(
        "portfolio_walk_forward_window_validation",
        sa.Column("validation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("study_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("window_no", sa.Integer(), nullable=False),
        sa.Column("train_experiment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("train_evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("selected_trial_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("selected_parameter_hash", sa.String(64), nullable=False),
        sa.Column("selected_parameter_values", postgresql.JSONB(), nullable=False),
        sa.Column("oos_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("oos_performance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("oos_risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("oos_trade_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("oos_period_id", postgresql.UUID(as_uuid=True), nullable=False),
        *[
            sa.Column(name, sa.Numeric(60, 18), nullable=name not in required_metrics)
            for name in metric_columns
        ],
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("window_no > 0", name=op.f("ck_walk_forward_window_validation_no")),
        sa.ForeignKeyConstraint(
            ["validation_id", "study_id"],
            [
                "portfolio_walk_forward_validation_report.id",
                "portfolio_walk_forward_validation_report.study_id",
            ],
            name=op.f("fk_walk_forward_window_validation_report"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["study_id", "window_no"],
            ["portfolio_walk_forward_window.study_id", "portfolio_walk_forward_window.window_no"],
            name=op.f("fk_walk_forward_window_validation_window"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("validation_id", "window_no"),
    )

    op.create_table(
        "portfolio_walk_forward_parameter_stability",
        sa.Column("validation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("study_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parameter_name", sa.String(96), nullable=False),
        sa.Column("parameter_value", sa.String(64), nullable=False),
        sa.Column("selected_window_count", sa.Integer(), nullable=False),
        sa.Column("selected_rate", sa.Numeric(60, 18), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "parameter_name IN ('candidate.min_score','candidate.top_n',"
            "'construction.max_positions','construction.max_single_position_weight',"
            "'construction.min_cash_ratio','construction.max_new_positions_per_day')",
            name=op.f("ck_walk_forward_parameter_stability_name"),
        ),
        sa.CheckConstraint(
            "selected_window_count > 0",
            name=op.f("ck_walk_forward_parameter_stability_count"),
        ),
        sa.CheckConstraint(
            "selected_rate > 0 AND selected_rate <= 1",
            name=op.f("ck_walk_forward_parameter_stability_rate"),
        ),
        sa.ForeignKeyConstraint(
            ["validation_id", "study_id"],
            [
                "portfolio_walk_forward_validation_report.id",
                "portfolio_walk_forward_validation_report.study_id",
            ],
            name=op.f("fk_walk_forward_parameter_stability_report"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("validation_id", "parameter_name", "parameter_value"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    artifact_count = int(
        connection.scalar(
            sa.text(
                "SELECT (SELECT count(*) FROM portfolio_walk_forward_study) + "
                "(SELECT count(*) FROM portfolio_walk_forward_window) + "
                "(SELECT count(*) FROM portfolio_walk_forward_validation_report) + "
                "(SELECT count(*) FROM portfolio_walk_forward_window_validation) + "
                "(SELECT count(*) FROM portfolio_walk_forward_parameter_stability)"
            )
        )
        or 0
    )
    if artifact_count:
        raise RuntimeError("cannot downgrade M15.3 while walk-forward artifacts exist")
    op.drop_table("portfolio_walk_forward_parameter_stability")
    op.drop_table("portfolio_walk_forward_window_validation")
    op.drop_index(
        "idx_walk_forward_validation_history",
        table_name="portfolio_walk_forward_validation_report",
    )
    op.drop_table("portfolio_walk_forward_validation_report")
    op.drop_index("idx_walk_forward_window_oos", table_name="portfolio_walk_forward_window")
    op.drop_index("idx_walk_forward_window_train", table_name="portfolio_walk_forward_window")
    op.drop_table("portfolio_walk_forward_window")
    op.drop_index("idx_walk_forward_study_created", table_name="portfolio_walk_forward_study")
    op.drop_index(
        "idx_walk_forward_study_definition", table_name="portfolio_walk_forward_study"
    )
    op.drop_table("portfolio_walk_forward_study")
