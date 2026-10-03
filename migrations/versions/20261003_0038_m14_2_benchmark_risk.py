"""Add the M14.2 benchmark and risk artifacts.

Revision ID: 0038_m14_2_benchmark_risk
Revises: 0037_m14_1_1_closeout
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0038_m14_2_benchmark_risk"
down_revision = "0037_m14_1_1_closeout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_performance_risk_report",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("performance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_version", sa.String(length=32), nullable=False),
        sa.Column("risk_config_hash", sa.String(length=64), nullable=False),
        sa.Column("benchmark_code", sa.String(length=16), nullable=False),
        sa.Column("benchmark_source_hash", sa.String(length=64), nullable=False),
        sa.Column("risk_source_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="SUCCESS", nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("trade_days", sa.Integer(), nullable=False),
        sa.Column("risk_free_rate_annual", sa.Numeric(20, 12), nullable=False),
        sa.Column("benchmark_initial_nav", sa.Numeric(30, 12), nullable=False),
        sa.Column("benchmark_final_nav", sa.Numeric(30, 12), nullable=False),
        sa.Column("benchmark_cumulative_return", sa.Numeric(60, 18), nullable=False),
        sa.Column("benchmark_annualized_return", sa.Numeric(60, 18), nullable=False),
        sa.Column("excess_cumulative_return", sa.Numeric(60, 18), nullable=False),
        sa.Column("relative_nav_final", sa.Numeric(30, 12), nullable=False),
        sa.Column("strategy_annualized_volatility", sa.Numeric(60, 18)),
        sa.Column("benchmark_annualized_volatility", sa.Numeric(60, 18)),
        sa.Column("downside_deviation_annualized", sa.Numeric(60, 18)),
        sa.Column("sharpe_ratio", sa.Numeric(60, 18)),
        sa.Column("sortino_ratio", sa.Numeric(60, 18)),
        sa.Column("calmar_ratio", sa.Numeric(60, 18)),
        sa.Column("tracking_error", sa.Numeric(60, 18)),
        sa.Column("information_ratio", sa.Numeric(60, 18)),
        sa.Column("alpha_daily", sa.Numeric(60, 18)),
        sa.Column("alpha_annualized", sa.Numeric(60, 18)),
        sa.Column("beta", sa.Numeric(60, 18)),
        sa.Column("correlation", sa.Numeric(60, 18)),
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
        sa.CheckConstraint("status = 'SUCCESS'", name=op.f("ck_perf_risk_report_status")),
        sa.CheckConstraint("trade_days > 0", name=op.f("ck_perf_risk_report_trade_days")),
        sa.ForeignKeyConstraint(
            ["performance_id", "run_id"],
            ["portfolio_performance_report.id", "portfolio_performance_report.run_id"],
            name=op.f("fk_perf_risk_report_performance_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_performance_risk_report")),
        sa.UniqueConstraint(
            "performance_id",
            "risk_version",
            "risk_config_hash",
            "benchmark_source_hash",
            name=op.f("uq_perf_risk_report_identity"),
        ),
        sa.UniqueConstraint(
            "id",
            "performance_id",
            "run_id",
            name=op.f("uq_perf_risk_report_owner"),
        ),
    )
    op.create_index(
        "idx_perf_risk_report_performance_calculated",
        "portfolio_performance_risk_report",
        ["performance_id", "calculated_at"],
        unique=False,
    )
    op.create_index(
        "idx_perf_risk_report_run_calculated",
        "portfolio_performance_risk_report",
        ["run_id", "calculated_at"],
        unique=False,
    )
    op.create_table(
        "portfolio_performance_risk_daily",
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("performance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("benchmark_reference_close", sa.Numeric(30, 12), nullable=False),
        sa.Column("benchmark_close", sa.Numeric(30, 12), nullable=False),
        sa.Column("benchmark_daily_return", sa.Numeric(60, 18), nullable=False),
        sa.Column("benchmark_nav", sa.Numeric(30, 12), nullable=False),
        sa.Column("active_return", sa.Numeric(60, 18), nullable=False),
        sa.Column("relative_nav", sa.Numeric(30, 12), nullable=False),
        sa.Column("excess_cumulative_return", sa.Numeric(60, 18), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["risk_id", "performance_id", "run_id"],
            [
                "portfolio_performance_risk_report.id",
                "portfolio_performance_risk_report.performance_id",
                "portfolio_performance_risk_report.run_id",
            ],
            name=op.f("fk_perf_risk_daily_report_owner"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["performance_id", "trade_date"],
            [
                "portfolio_performance_daily.performance_id",
                "portfolio_performance_daily.trade_date",
            ],
            name=op.f("fk_perf_risk_daily_base_date"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "risk_id", "trade_date", name=op.f("pk_portfolio_performance_risk_daily")
        ),
    )
    op.create_index(
        "idx_perf_risk_daily_run_date",
        "portfolio_performance_risk_daily",
        ["run_id", "trade_date"],
        unique=False,
    )
    op.create_index(
        "idx_perf_risk_daily_performance_date",
        "portfolio_performance_risk_daily",
        ["performance_id", "trade_date"],
        unique=False,
    )


def downgrade() -> None:
    connection = op.get_bind()
    artifact_count = int(
        connection.scalar(
            sa.text(
                "SELECT (SELECT count(*) FROM portfolio_performance_risk_report) + "
                "(SELECT count(*) FROM portfolio_performance_risk_daily)"
            )
        )
        or 0
    )
    if artifact_count:
        raise RuntimeError(
            "cannot downgrade M14.2 while risk artifacts exist; export and explicitly "
            f"remove {artifact_count} report/daily row(s) first"
        )
    op.drop_index(
        "idx_perf_risk_daily_performance_date",
        table_name="portfolio_performance_risk_daily",
    )
    op.drop_index(
        "idx_perf_risk_daily_run_date",
        table_name="portfolio_performance_risk_daily",
    )
    op.drop_table("portfolio_performance_risk_daily")
    op.drop_index(
        "idx_perf_risk_report_run_calculated",
        table_name="portfolio_performance_risk_report",
    )
    op.drop_index(
        "idx_perf_risk_report_performance_calculated",
        table_name="portfolio_performance_risk_report",
    )
    op.drop_table("portfolio_performance_risk_report")
