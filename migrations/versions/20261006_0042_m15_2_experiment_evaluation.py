"""Add M15.2 experiment evaluation and selection artifacts.

Revision ID: 0042_m15_2_experiment_evaluation
Revises: 0041_m15_1_experiment_foundation
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0042_m15_2_experiment_evaluation"
down_revision = "0041_m15_1_experiment_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        op.f("uq_portfolio_experiment_trial_owner"),
        "portfolio_experiment_trial",
        ["id", "experiment_id"],
    )
    op.create_table(
        "portfolio_experiment_evaluation_report",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_version", sa.String(32), nullable=False),
        sa.Column("evaluation_config_hash", sa.String(64), nullable=False),
        sa.Column("policy_hash", sa.String(64), nullable=False),
        sa.Column("policy_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("trial_count", sa.Integer(), nullable=False),
        sa.Column("success_trial_count", sa.Integer(), nullable=False),
        sa.Column("excluded_trial_count", sa.Integer(), nullable=False),
        sa.Column("evaluated_trial_count", sa.Integer(), nullable=False),
        sa.Column("feasible_count", sa.Integer(), nullable=False),
        sa.Column("infeasible_count", sa.Integer(), nullable=False),
        sa.Column("pareto_front1_count", sa.Integer(), nullable=False),
        sa.Column("shortlist_count", sa.Integer(), nullable=False),
        sa.Column("selected_trial_id", postgresql.UUID(as_uuid=True)),
        sa.Column("selected_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(16), server_default="SUCCESS", nullable=False),
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
        sa.CheckConstraint("trial_count > 0", name=op.f("ck_experiment_eval_trials")),
        sa.CheckConstraint(
            "success_trial_count > 0", name=op.f("ck_experiment_eval_success")
        ),
        sa.CheckConstraint(
            "evaluated_trial_count = success_trial_count",
            name=op.f("ck_experiment_eval_evaluated"),
        ),
        sa.CheckConstraint(
            "excluded_trial_count + evaluated_trial_count = trial_count",
            name=op.f("ck_experiment_eval_total"),
        ),
        sa.CheckConstraint(
            "feasible_count + infeasible_count = evaluated_trial_count",
            name=op.f("ck_experiment_eval_feasibility"),
        ),
        sa.CheckConstraint(
            "pareto_front1_count <= feasible_count", name=op.f("ck_experiment_eval_pareto")
        ),
        sa.CheckConstraint(
            "shortlist_count <= feasible_count", name=op.f("ck_experiment_eval_shortlist")
        ),
        sa.CheckConstraint("status = 'SUCCESS'", name=op.f("ck_experiment_eval_status")),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["portfolio_experiment.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "experiment_id",
            "evaluation_version",
            "evaluation_config_hash",
            "policy_hash",
            "source_hash",
            name=op.f("uq_experiment_evaluation_identity"),
        ),
        sa.UniqueConstraint(
            "id", "experiment_id", name=op.f("uq_experiment_evaluation_owner")
        ),
    )
    op.create_index(
        "idx_experiment_eval_history",
        "portfolio_experiment_evaluation_report",
        ["experiment_id", "calculated_at"],
    )
    op.create_table(
        "portfolio_experiment_trial_evaluation",
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trial_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trial_no", sa.Integer(), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("exclusion_reason", sa.String(64)),
        sa.Column("parameter_hash", sa.String(64), nullable=False),
        sa.Column("parameter_values", postgresql.JSONB(), nullable=False),
        sa.Column("performance_id", postgresql.UUID(as_uuid=True)),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True)),
        sa.Column("trade_id", postgresql.UUID(as_uuid=True)),
        sa.Column("period_id", postgresql.UUID(as_uuid=True)),
        sa.Column("cumulative_return", sa.Numeric(60, 18)),
        sa.Column("annualized_return", sa.Numeric(60, 18)),
        sa.Column("max_drawdown_abs", sa.Numeric(60, 18)),
        sa.Column("strategy_annualized_volatility", sa.Numeric(60, 18)),
        sa.Column("excess_cumulative_return", sa.Numeric(60, 18)),
        sa.Column("sharpe_ratio", sa.Numeric(60, 18)),
        sa.Column("sortino_ratio", sa.Numeric(60, 18)),
        sa.Column("calmar_ratio", sa.Numeric(60, 18)),
        sa.Column("information_ratio", sa.Numeric(60, 18)),
        sa.Column("alpha_annualized", sa.Numeric(60, 18)),
        sa.Column("annualized_turnover", sa.Numeric(60, 18)),
        sa.Column("total_cost_to_initial_capital", sa.Numeric(60, 18)),
        sa.Column("closed_episode_count", sa.Integer()),
        sa.Column("win_rate", sa.Numeric(60, 18)),
        sa.Column("profit_factor", sa.Numeric(60, 18)),
        sa.Column("payoff_ratio", sa.Numeric(60, 18)),
        sa.Column("closed_realized_pnl", sa.Numeric(60, 18)),
        sa.Column("positive_month_rate", sa.Numeric(60, 18)),
        sa.Column("worst_month_return", sa.Numeric(60, 18)),
        sa.Column("monthly_return_volatility", sa.Numeric(60, 18)),
        sa.Column("primary_objective_value", sa.Numeric(60, 18)),
        sa.Column("feasible", sa.Boolean(), nullable=False),
        sa.Column("constraint_violations", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("pareto_front", sa.Integer()),
        sa.Column("selection_rank", sa.Integer()),
        sa.Column("shortlisted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('EVALUATED','EXCLUDED')", name=op.f("ck_experiment_trial_eval_status")
        ),
        sa.CheckConstraint("trial_no > 0", name=op.f("ck_experiment_trial_eval_number")),
        sa.CheckConstraint(
            "pareto_front IS NULL OR pareto_front > 0",
            name=op.f("ck_experiment_trial_eval_front"),
        ),
        sa.CheckConstraint(
            "selection_rank IS NULL OR selection_rank > 0",
            name=op.f("ck_experiment_trial_eval_rank"),
        ),
        sa.CheckConstraint(
            "status <> 'EXCLUDED' OR (feasible = false AND shortlisted = false "
            "AND selection_rank IS NULL AND pareto_front IS NULL)",
            name=op.f("ck_experiment_trial_eval_excluded"),
        ),
        sa.CheckConstraint(
            "shortlisted = false OR (feasible = true AND selection_rank IS NOT NULL)",
            name=op.f("ck_experiment_trial_eval_shortlisted"),
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id", "experiment_id"],
            [
                "portfolio_experiment_evaluation_report.id",
                "portfolio_experiment_evaluation_report.experiment_id",
            ],
            name=op.f("fk_experiment_trial_eval_report_owner"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trial_id", "experiment_id"],
            ["portfolio_experiment_trial.id", "portfolio_experiment_trial.experiment_id"],
            name=op.f("fk_experiment_trial_eval_trial_owner"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("evaluation_id", "trial_id"),
    )
    op.create_index(
        "idx_experiment_trial_eval_page",
        "portfolio_experiment_trial_evaluation",
        ["evaluation_id", "selection_rank"],
    )
    op.create_table(
        "portfolio_experiment_parameter_sensitivity",
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parameter_name", sa.String(96), nullable=False),
        sa.Column("parameter_value", sa.String(64), nullable=False),
        sa.Column("trial_count", sa.Integer(), nullable=False),
        sa.Column("evaluated_count", sa.Integer(), nullable=False),
        sa.Column("feasible_count", sa.Integer(), nullable=False),
        sa.Column("feasible_rate", sa.Numeric(60, 18), nullable=False),
        sa.Column("pareto_front1_count", sa.Integer(), nullable=False),
        sa.Column("pareto_front1_rate", sa.Numeric(60, 18)),
        sa.Column("primary_objective_sample_count", sa.Integer(), nullable=False),
        sa.Column("mean_primary_objective", sa.Numeric(60, 18)),
        sa.Column("median_primary_objective", sa.Numeric(60, 18)),
        sa.Column("best_primary_objective", sa.Numeric(60, 18)),
        sa.Column("worst_primary_objective", sa.Numeric(60, 18)),
        sa.Column("mean_annualized_return", sa.Numeric(60, 18)),
        sa.Column("mean_max_drawdown_abs", sa.Numeric(60, 18)),
        sa.Column("mean_annualized_turnover", sa.Numeric(60, 18)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("trial_count > 0", name=op.f("ck_experiment_sensitivity_trials")),
        sa.CheckConstraint(
            "evaluated_count >= 0 AND evaluated_count <= trial_count",
            name=op.f("ck_experiment_sensitivity_evaluated"),
        ),
        sa.CheckConstraint(
            "feasible_count >= 0 AND feasible_count <= evaluated_count",
            name=op.f("ck_experiment_sensitivity_feasible"),
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id", "experiment_id"],
            [
                "portfolio_experiment_evaluation_report.id",
                "portfolio_experiment_evaluation_report.experiment_id",
            ],
            name=op.f("fk_experiment_sensitivity_report_owner"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("evaluation_id", "parameter_name", "parameter_value"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    artifact_count = int(
        connection.scalar(
            sa.text(
                "SELECT (SELECT count(*) FROM portfolio_experiment_evaluation_report) + "
                "(SELECT count(*) FROM portfolio_experiment_trial_evaluation) + "
                "(SELECT count(*) FROM portfolio_experiment_parameter_sensitivity)"
            )
        )
        or 0
    )
    if artifact_count:
        raise RuntimeError(
            "cannot downgrade M15.2 while experiment evaluation artifacts exist"
        )
    op.drop_table("portfolio_experiment_parameter_sensitivity")
    op.drop_index(
        "idx_experiment_trial_eval_page",
        table_name="portfolio_experiment_trial_evaluation",
    )
    op.drop_table("portfolio_experiment_trial_evaluation")
    op.drop_index(
        "idx_experiment_eval_history",
        table_name="portfolio_experiment_evaluation_report",
    )
    op.drop_table("portfolio_experiment_evaluation_report")
    op.drop_constraint(
        op.f("uq_portfolio_experiment_trial_owner"),
        "portfolio_experiment_trial",
        type_="unique",
    )
