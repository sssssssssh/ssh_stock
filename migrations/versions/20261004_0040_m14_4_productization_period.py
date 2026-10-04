"""Add M14.4 period analytics artifacts.

Revision ID: 0040_m14_4_period_analytics
Revises: 0039_m14_3_trade_analytics
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0040_m14_4_period_analytics"
down_revision = "0039_m14_3_trade_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_performance_period_report",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("performance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_version", sa.String(32), nullable=False),
        sa.Column("period_config_hash", sa.String(64), nullable=False),
        sa.Column("period_source_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="SUCCESS", nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("trade_days", sa.Integer(), nullable=False),
        sa.Column("month_count", sa.Integer(), nullable=False),
        sa.Column("year_count", sa.Integer(), nullable=False),
        sa.Column(
            "warnings", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            "result_summary",
            postgresql.JSONB(),
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
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status = 'SUCCESS'", name=op.f("ck_perf_period_report_status")),
        sa.CheckConstraint("trade_days > 0", name=op.f("ck_perf_period_report_days")),
        sa.CheckConstraint("month_count > 0", name=op.f("ck_perf_period_report_months")),
        sa.CheckConstraint("year_count > 0", name=op.f("ck_perf_period_report_years")),
        sa.ForeignKeyConstraint(
            ["performance_id", "run_id"],
            ["portfolio_performance_report.id", "portfolio_performance_report.run_id"],
            name=op.f("fk_perf_period_report_performance"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["risk_id", "performance_id", "run_id"],
            [
                "portfolio_performance_risk_report.id",
                "portfolio_performance_risk_report.performance_id",
                "portfolio_performance_risk_report.run_id",
            ],
            name=op.f("fk_perf_period_report_risk"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trade_id", "performance_id", "run_id"],
            [
                "portfolio_performance_trade_report.id",
                "portfolio_performance_trade_report.performance_id",
                "portfolio_performance_trade_report.run_id",
            ],
            name=op.f("fk_perf_period_report_trade"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_performance_period_report")),
        sa.UniqueConstraint(
            "performance_id",
            "risk_id",
            "trade_id",
            "period_version",
            "period_config_hash",
            "period_source_hash",
            name=op.f("uq_perf_period_report_identity"),
        ),
        sa.UniqueConstraint(
            "id",
            "performance_id",
            "risk_id",
            "trade_id",
            "run_id",
            name=op.f("uq_perf_period_report_owner"),
        ),
    )
    op.create_index(
        "idx_perf_period_report_bundle",
        "portfolio_performance_period_report",
        ["performance_id", "risk_id", "trade_id"],
    )
    op.create_index(
        "idx_perf_period_report_run_calculated",
        "portfolio_performance_period_report",
        ["run_id", "calculated_at"],
    )

    op.create_table(
        "portfolio_performance_period",
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("performance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_type", sa.String(8), nullable=False),
        sa.Column("period_key", sa.String(7), nullable=False),
        sa.Column("period_start_date", sa.Date(), nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        sa.Column("trade_days", sa.Integer(), nullable=False),
        sa.Column("strategy_return", sa.Numeric(60, 18), nullable=False),
        sa.Column("benchmark_return", sa.Numeric(60, 18), nullable=False),
        sa.Column("relative_return", sa.Numeric(60, 18), nullable=False),
        sa.Column("return_spread", sa.Numeric(60, 18), nullable=False),
        sa.Column("period_turnover", sa.Numeric(60, 18), nullable=False),
        sa.Column("traded_gross_amount", sa.Numeric(60, 18), nullable=False),
        sa.Column("commission", sa.Numeric(60, 18), nullable=False),
        sa.Column("stamp_tax", sa.Numeric(60, 18), nullable=False),
        sa.Column("transfer_fee", sa.Numeric(60, 18), nullable=False),
        sa.Column("cash_fee_total", sa.Numeric(60, 18), nullable=False),
        sa.Column("slippage_cost", sa.Numeric(60, 18), nullable=False),
        sa.Column("total_execution_cost", sa.Numeric(60, 18), nullable=False),
        sa.Column("closed_episode_count", sa.Integer(), nullable=False),
        sa.Column("win_count", sa.Integer(), nullable=False),
        sa.Column("loss_count", sa.Integer(), nullable=False),
        sa.Column("breakeven_count", sa.Integer(), nullable=False),
        sa.Column("win_rate", sa.Numeric(60, 18)),
        sa.Column("closed_realized_pnl", sa.Numeric(60, 18), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("period_type IN ('MONTH','YEAR')", name=op.f("ck_perf_period_type")),
        sa.CheckConstraint("trade_days > 0", name=op.f("ck_perf_period_days")),
        sa.CheckConstraint("closed_episode_count >= 0", name=op.f("ck_perf_period_closed")),
        sa.CheckConstraint(
            "win_count >= 0 AND loss_count >= 0 AND breakeven_count >= 0",
            name=op.f("ck_perf_period_class_counts"),
        ),
        sa.CheckConstraint(
            "win_count + loss_count + breakeven_count = closed_episode_count",
            name=op.f("ck_perf_period_class_total"),
        ),
        sa.CheckConstraint(
            "win_rate IS NULL OR (win_rate >= 0 AND win_rate <= 1)",
            name=op.f("ck_perf_period_win_rate"),
        ),
        sa.ForeignKeyConstraint(
            ["period_id", "performance_id", "risk_id", "trade_id", "run_id"],
            [
                "portfolio_performance_period_report.id",
                "portfolio_performance_period_report.performance_id",
                "portfolio_performance_period_report.risk_id",
                "portfolio_performance_period_report.trade_id",
                "portfolio_performance_period_report.run_id",
            ],
            name=op.f("fk_perf_period_row_report_owner"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "period_id", "period_type", "period_key", name=op.f("pk_portfolio_performance_period")
        ),
    )
    op.create_index(
        "idx_perf_period_row_run_type_key",
        "portfolio_performance_period",
        ["run_id", "period_type", "period_key"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    artifact_count = int(
        connection.scalar(
            sa.text(
                "SELECT (SELECT count(*) FROM portfolio_performance_period_report) + "
                "(SELECT count(*) FROM portfolio_performance_period)"
            )
        )
        or 0
    )
    if artifact_count:
        raise RuntimeError(
            "cannot downgrade M14.4 while period artifacts exist; export and explicitly "
            f"remove {artifact_count} report/period row(s) first"
        )
    op.drop_index(
        "idx_perf_period_row_run_type_key", table_name="portfolio_performance_period"
    )
    op.drop_table("portfolio_performance_period")
    op.drop_index(
        "idx_perf_period_report_run_calculated",
        table_name="portfolio_performance_period_report",
    )
    op.drop_index(
        "idx_perf_period_report_bundle", table_name="portfolio_performance_period_report"
    )
    op.drop_table("portfolio_performance_period_report")
