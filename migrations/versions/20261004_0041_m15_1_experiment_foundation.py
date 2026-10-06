"""Add M15.1 strategy experiment foundation.

Revision ID: 0041_m15_1_experiment_foundation
Revises: 0040_m14_4_period_analytics
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0041_m15_1_experiment_foundation"
down_revision = "0040_m14_4_period_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_experiment",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(128)),
        sa.Column("experiment_version", sa.String(32), nullable=False),
        sa.Column("search_method", sa.String(16), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("initial_cash", sa.Numeric(20, 4), nullable=False),
        sa.Column("benchmark_code", sa.String(16), nullable=False),
        sa.Column("definition_hash", sa.String(64), nullable=False),
        sa.Column("parameter_space_hash", sa.String(64), nullable=False),
        sa.Column("parameter_space", postgresql.JSONB(), nullable=False),
        sa.Column("trial_count", sa.Integer(), nullable=False),
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
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "experiment_version = 'experiment_v1'",
            name=op.f("ck_portfolio_experiment_version"),
        ),
        sa.CheckConstraint(
            "search_method = 'GRID'",
            name=op.f("ck_portfolio_experiment_search_method"),
        ),
        sa.CheckConstraint(
            "end_date >= start_date", name=op.f("ck_portfolio_experiment_dates")
        ),
        sa.CheckConstraint(
            "initial_cash > 0", name=op.f("ck_portfolio_experiment_initial_cash")
        ),
        sa.CheckConstraint(
            "trial_count > 0", name=op.f("ck_portfolio_experiment_trial_count")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_experiment")),
    )
    op.create_index(
        "idx_portfolio_experiment_definition_hash",
        "portfolio_experiment",
        ["definition_hash"],
    )
    op.create_index(
        "idx_portfolio_experiment_created_at",
        "portfolio_experiment",
        ["created_at"],
    )

    op.create_table(
        "portfolio_experiment_trial",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trial_no", sa.Integer(), nullable=False),
        sa.Column("parameter_values", postgresql.JSONB(), nullable=False),
        sa.Column("parameter_hash", sa.String(64), nullable=False),
        sa.Column("portfolio_config_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("portfolio_config_hash", sa.String(64), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "trial_no > 0", name=op.f("ck_portfolio_experiment_trial_number")
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["portfolio_experiment.id"],
            name=op.f("fk_portfolio_experiment_trial_experiment_id_portfolio_experiment"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["portfolio_backtest_run.id"],
            name=op.f("fk_portfolio_experiment_trial_run_id_portfolio_backtest_run"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_experiment_trial")),
        sa.UniqueConstraint(
            "experiment_id",
            "trial_no",
            name=op.f("uq_portfolio_experiment_trial_number"),
        ),
        sa.UniqueConstraint(
            "experiment_id",
            "parameter_hash",
            name=op.f("uq_portfolio_experiment_trial_parameter"),
        ),
        sa.UniqueConstraint(
            "run_id", name=op.f("uq_portfolio_experiment_trial_run_id")
        ),
    )
    op.create_index(
        "idx_portfolio_experiment_trial_experiment",
        "portfolio_experiment_trial",
        ["experiment_id"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    artifact_count = int(
        connection.scalar(
            sa.text(
                "SELECT (SELECT count(*) FROM portfolio_experiment) + "
                "(SELECT count(*) FROM portfolio_experiment_trial)"
            )
        )
        or 0
    )
    if artifact_count:
        raise RuntimeError("cannot downgrade M15.1 while experiment artifacts exist")
    op.drop_index(
        "idx_portfolio_experiment_trial_experiment",
        table_name="portfolio_experiment_trial",
    )
    op.drop_table("portfolio_experiment_trial")
    op.drop_index(
        "idx_portfolio_experiment_created_at", table_name="portfolio_experiment"
    )
    op.drop_index(
        "idx_portfolio_experiment_definition_hash",
        table_name="portfolio_experiment",
    )
    op.drop_table("portfolio_experiment")
