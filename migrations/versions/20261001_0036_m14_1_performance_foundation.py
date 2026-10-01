"""Add the M14.1 performance report and daily artifacts.

Revision ID: 0036_m14_1_performance
Revises: 0035_m13_4_backtest_runner
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0036_m14_1_performance"
down_revision = "0035_m13_4_backtest_runner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_performance_report",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("performance_version", sa.String(length=32), nullable=False),
        sa.Column("performance_config_hash", sa.String(length=64), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="SUCCESS", nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("trade_days", sa.Integer(), nullable=False),
        sa.Column("initial_nav", sa.Numeric(20, 8), nullable=False),
        sa.Column("final_nav", sa.Numeric(20, 8), nullable=False),
        sa.Column("cumulative_return", sa.Numeric(20, 10), nullable=False),
        sa.Column("annualized_return", sa.Numeric(20, 10), nullable=False),
        sa.Column("max_drawdown", sa.Numeric(20, 10), nullable=False),
        sa.Column("max_drawdown_peak_date", sa.Date(), nullable=True),
        sa.Column("max_drawdown_trough_date", sa.Date(), nullable=True),
        sa.Column("max_drawdown_recovery_date", sa.Date(), nullable=True),
        sa.Column("max_drawdown_duration_days", sa.Integer(), nullable=False),
        sa.Column("positive_days", sa.Integer(), nullable=False),
        sa.Column("negative_days", sa.Integer(), nullable=False),
        sa.Column("flat_days", sa.Integer(), nullable=False),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "result_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
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
            "status IN ('SUCCESS', 'FAILED')",
            name=op.f("ck_portfolio_performance_report_status"),
        ),
        sa.CheckConstraint(
            "trade_days > 0", name=op.f("ck_portfolio_performance_trade_days")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["portfolio_backtest_run.id"],
            name=op.f("fk_portfolio_performance_report_run_id_portfolio_backtest_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_performance_report")),
        sa.UniqueConstraint(
            "run_id",
            "performance_version",
            "performance_config_hash",
            "source_hash",
            name=op.f("uq_portfolio_performance_report_identity"),
        ),
    )
    op.create_index(
        "idx_portfolio_performance_report_run_calculated",
        "portfolio_performance_report",
        ["run_id", "calculated_at"],
        unique=False,
    )
    op.create_table(
        "portfolio_performance_daily",
        sa.Column("performance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("nav", sa.Numeric(20, 8), nullable=False),
        sa.Column("daily_return", sa.Numeric(20, 10), nullable=False),
        sa.Column("cumulative_return", sa.Numeric(20, 10), nullable=False),
        sa.Column("running_peak_nav", sa.Numeric(20, 8), nullable=False),
        sa.Column("drawdown", sa.Numeric(20, 10), nullable=False),
        sa.Column("drawdown_duration_days", sa.Integer(), nullable=False),
        sa.Column("cash_ratio", sa.Numeric(20, 10), nullable=False),
        sa.Column("gross_exposure", sa.Numeric(20, 10), nullable=False),
        sa.Column("net_exposure", sa.Numeric(20, 10), nullable=False),
        sa.Column("position_count", sa.Integer(), nullable=False),
        sa.Column("trading_cost", sa.Numeric(20, 4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["performance_id"],
            ["portfolio_performance_report.id"],
            name=op.f(
                "fk_portfolio_performance_daily_performance_id_portfolio_performance_report"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["portfolio_backtest_run.id"],
            name=op.f("fk_portfolio_performance_daily_run_id_portfolio_backtest_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "performance_id",
            "trade_date",
            name=op.f("pk_portfolio_performance_daily"),
        ),
    )
    op.create_index(
        "idx_portfolio_performance_daily_run_date",
        "portfolio_performance_daily",
        ["run_id", "trade_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_portfolio_performance_daily_run_date",
        table_name="portfolio_performance_daily",
    )
    op.drop_table("portfolio_performance_daily")
    op.drop_index(
        "idx_portfolio_performance_report_run_calculated",
        table_name="portfolio_performance_report",
    )
    op.drop_table("portfolio_performance_report")
