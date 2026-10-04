"""Add the M14.3 trade cost and episode analytics artifacts.

Revision ID: 0039_m14_3_trade_analytics
Revises: 0038_m14_2_benchmark_risk
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0039_m14_3_trade_analytics"
down_revision = "0038_m14_2_benchmark_risk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_performance_trade_report",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("performance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_version", sa.String(32), nullable=False),
        sa.Column("trade_config_hash", sa.String(64), nullable=False),
        sa.Column("trade_source_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="SUCCESS", nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("trade_days", sa.Integer(), nullable=False),
        sa.Column("order_count", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("fill_count", sa.Integer(), nullable=False),
        sa.Column("buy_fill_count", sa.Integer(), nullable=False),
        sa.Column("sell_fill_count", sa.Integer(), nullable=False),
        sa.Column("buy_gross_amount", sa.Numeric(60, 18), nullable=False),
        sa.Column("sell_gross_amount", sa.Numeric(60, 18), nullable=False),
        sa.Column("traded_gross_amount", sa.Numeric(60, 18), nullable=False),
        sa.Column("commission_total", sa.Numeric(60, 18), nullable=False),
        sa.Column("stamp_tax_total", sa.Numeric(60, 18), nullable=False),
        sa.Column("transfer_fee_total", sa.Numeric(60, 18), nullable=False),
        sa.Column("cash_fee_total", sa.Numeric(60, 18), nullable=False),
        sa.Column("slippage_cost_total", sa.Numeric(60, 18), nullable=False),
        sa.Column("total_execution_cost", sa.Numeric(60, 18), nullable=False),
        sa.Column("cash_fee_to_initial_capital", sa.Numeric(60, 18), nullable=False),
        sa.Column("total_cost_to_initial_capital", sa.Numeric(60, 18), nullable=False),
        sa.Column("total_cost_to_traded_amount", sa.Numeric(60, 18)),
        sa.Column("total_turnover", sa.Numeric(60, 18), nullable=False),
        sa.Column("average_daily_turnover", sa.Numeric(60, 18), nullable=False),
        sa.Column("annualized_turnover", sa.Numeric(60, 18), nullable=False),
        sa.Column("closed_episode_count", sa.Integer(), nullable=False),
        sa.Column("open_episode_count", sa.Integer(), nullable=False),
        sa.Column("win_count", sa.Integer(), nullable=False),
        sa.Column("loss_count", sa.Integer(), nullable=False),
        sa.Column("breakeven_count", sa.Integer(), nullable=False),
        sa.Column("win_rate", sa.Numeric(60, 18)),
        sa.Column("gross_profit", sa.Numeric(60, 18), nullable=False),
        sa.Column("gross_loss_abs", sa.Numeric(60, 18), nullable=False),
        sa.Column("profit_factor", sa.Numeric(60, 18)),
        sa.Column("average_win", sa.Numeric(60, 18)),
        sa.Column("average_loss_abs", sa.Numeric(60, 18)),
        sa.Column("payoff_ratio", sa.Numeric(60, 18)),
        sa.Column("best_episode_pnl", sa.Numeric(60, 18)),
        sa.Column("worst_episode_pnl", sa.Numeric(60, 18)),
        sa.Column("average_holding_trade_days", sa.Numeric(20, 8)),
        sa.Column("median_holding_trade_days", sa.Numeric(20, 8)),
        sa.Column("closed_realized_pnl", sa.Numeric(60, 18), nullable=False),
        sa.Column("open_realized_pnl_end", sa.Numeric(60, 18), nullable=False),
        sa.Column("open_unrealized_pnl_end", sa.Numeric(60, 18), nullable=False),
        sa.Column("open_mark_to_market_pnl_end", sa.Numeric(60, 18), nullable=False),
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
        sa.CheckConstraint("status = 'SUCCESS'", name=op.f("ck_perf_trade_report_status")),
        sa.CheckConstraint("trade_days > 0", name=op.f("ck_perf_trade_report_days")),
        sa.ForeignKeyConstraint(
            ["performance_id", "run_id"],
            ["portfolio_performance_report.id", "portfolio_performance_report.run_id"],
            name=op.f("fk_perf_trade_report_performance_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_performance_trade_report")),
        sa.UniqueConstraint(
            "performance_id",
            "trade_version",
            "trade_config_hash",
            "trade_source_hash",
            name=op.f("uq_perf_trade_report_identity"),
        ),
        sa.UniqueConstraint(
            "id", "performance_id", "run_id", name=op.f("uq_perf_trade_report_owner")
        ),
    )
    op.create_index(
        "idx_perf_trade_report_performance_calculated",
        "portfolio_performance_trade_report",
        ["performance_id", "calculated_at"],
    )
    op.create_index(
        "idx_perf_trade_report_run_calculated",
        "portfolio_performance_trade_report",
        ["run_id", "calculated_at"],
    )

    op.create_table(
        "portfolio_performance_trade_daily",
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("performance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("buy_fill_count", sa.Integer(), nullable=False),
        sa.Column("sell_fill_count", sa.Integer(), nullable=False),
        sa.Column("fill_count", sa.Integer(), nullable=False),
        sa.Column("buy_gross_amount", sa.Numeric(60, 18), nullable=False),
        sa.Column("sell_gross_amount", sa.Numeric(60, 18), nullable=False),
        sa.Column("traded_gross_amount", sa.Numeric(60, 18), nullable=False),
        sa.Column("commission", sa.Numeric(60, 18), nullable=False),
        sa.Column("stamp_tax", sa.Numeric(60, 18), nullable=False),
        sa.Column("transfer_fee", sa.Numeric(60, 18), nullable=False),
        sa.Column("cash_fee_total", sa.Numeric(60, 18), nullable=False),
        sa.Column("slippage_cost", sa.Numeric(60, 18), nullable=False),
        sa.Column("total_execution_cost", sa.Numeric(60, 18), nullable=False),
        sa.Column("turnover_denominator", sa.Numeric(60, 18), nullable=False),
        sa.Column("daily_turnover", sa.Numeric(60, 18), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["trade_id", "performance_id", "run_id"],
            [
                "portfolio_performance_trade_report.id",
                "portfolio_performance_trade_report.performance_id",
                "portfolio_performance_trade_report.run_id",
            ],
            name=op.f("fk_perf_trade_daily_report_owner"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["performance_id", "trade_date"],
            [
                "portfolio_performance_daily.performance_id",
                "portfolio_performance_daily.trade_date",
            ],
            name=op.f("fk_perf_trade_daily_base_date"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "trade_date"],
            ["portfolio_nav_daily.run_id", "portfolio_nav_daily.trade_date"],
            name=op.f("fk_perf_trade_daily_nav_date"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "trade_id", "trade_date", name=op.f("pk_portfolio_performance_trade_daily")
        ),
    )
    op.create_index(
        "idx_perf_trade_daily_run_date",
        "portfolio_performance_trade_daily",
        ["run_id", "trade_date"],
    )
    op.create_index(
        "idx_perf_trade_daily_performance_date",
        "portfolio_performance_trade_daily",
        ["performance_id", "trade_date"],
    )

    op.create_table(
        "portfolio_performance_trade_episode",
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("performance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ts_code", sa.String(16), nullable=False),
        sa.Column("episode_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("classification", sa.String(16)),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("exit_date", sa.Date()),
        sa.Column("holding_trade_days", sa.Integer(), nullable=False),
        sa.Column("buy_fill_count", sa.Integer(), nullable=False),
        sa.Column("sell_fill_count", sa.Integer(), nullable=False),
        sa.Column("fill_count", sa.Integer(), nullable=False),
        sa.Column("total_buy_quantity", sa.BigInteger(), nullable=False),
        sa.Column("total_sell_quantity", sa.BigInteger(), nullable=False),
        sa.Column("ending_quantity", sa.BigInteger(), nullable=False),
        sa.Column("buy_gross_amount", sa.Numeric(60, 18), nullable=False),
        sa.Column("sell_gross_amount", sa.Numeric(60, 18), nullable=False),
        sa.Column("buy_cash_fee_total", sa.Numeric(60, 18), nullable=False),
        sa.Column("sell_cash_fee_total", sa.Numeric(60, 18), nullable=False),
        sa.Column("commission", sa.Numeric(60, 18), nullable=False),
        sa.Column("stamp_tax", sa.Numeric(60, 18), nullable=False),
        sa.Column("transfer_fee", sa.Numeric(60, 18), nullable=False),
        sa.Column("cash_fee_total", sa.Numeric(60, 18), nullable=False),
        sa.Column("slippage_cost", sa.Numeric(60, 18), nullable=False),
        sa.Column("total_execution_cost", sa.Numeric(60, 18), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(60, 18), nullable=False),
        sa.Column("unrealized_pnl_end", sa.Numeric(60, 18), nullable=False),
        sa.Column("mark_to_market_pnl_end", sa.Numeric(60, 18), nullable=False),
        sa.Column("total_buy_cash_cost", sa.Numeric(60, 18), nullable=False),
        sa.Column("sell_net_proceeds", sa.Numeric(60, 18), nullable=False),
        sa.Column("episode_return", sa.Numeric(60, 18)),
        sa.Column("first_fill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_fill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("episode_no > 0", name=op.f("ck_perf_trade_episode_no")),
        sa.CheckConstraint("holding_trade_days > 0", name=op.f("ck_perf_trade_episode_days")),
        sa.CheckConstraint(
            "(status = 'CLOSED' AND exit_date IS NOT NULL AND ending_quantity = 0 "
            "AND classification IN ('WIN','LOSS','BREAKEVEN')) OR "
            "(status = 'OPEN' AND exit_date IS NULL AND ending_quantity > 0 "
            "AND classification IS NULL)",
            name=op.f("ck_perf_trade_episode_state"),
        ),
        sa.ForeignKeyConstraint(
            ["trade_id", "performance_id", "run_id"],
            [
                "portfolio_performance_trade_report.id",
                "portfolio_performance_trade_report.performance_id",
                "portfolio_performance_trade_report.run_id",
            ],
            name=op.f("fk_perf_trade_episode_report_owner"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "trade_id", "ts_code", "episode_no", name=op.f("pk_portfolio_performance_trade_episode")
        ),
    )
    op.create_index(
        "idx_perf_trade_episode_run_code",
        "portfolio_performance_trade_episode",
        ["run_id", "ts_code"],
    )
    op.create_index(
        "idx_perf_trade_episode_performance_status",
        "portfolio_performance_trade_episode",
        ["performance_id", "status"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    artifact_count = int(
        connection.scalar(
            sa.text(
                "SELECT (SELECT count(*) FROM portfolio_performance_trade_report) + "
                "(SELECT count(*) FROM portfolio_performance_trade_daily) + "
                "(SELECT count(*) FROM portfolio_performance_trade_episode)"
            )
        )
        or 0
    )
    if artifact_count:
        raise RuntimeError(
            "cannot downgrade M14.3 while trade artifacts exist; export and explicitly "
            f"remove {artifact_count} report/daily/episode row(s) first"
        )
    op.drop_index(
        "idx_perf_trade_episode_performance_status",
        table_name="portfolio_performance_trade_episode",
    )
    op.drop_index(
        "idx_perf_trade_episode_run_code", table_name="portfolio_performance_trade_episode"
    )
    op.drop_table("portfolio_performance_trade_episode")
    op.drop_index(
        "idx_perf_trade_daily_performance_date", table_name="portfolio_performance_trade_daily"
    )
    op.drop_index("idx_perf_trade_daily_run_date", table_name="portfolio_performance_trade_daily")
    op.drop_table("portfolio_performance_trade_daily")
    op.drop_index(
        "idx_perf_trade_report_run_calculated", table_name="portfolio_performance_trade_report"
    )
    op.drop_index(
        "idx_perf_trade_report_performance_calculated",
        table_name="portfolio_performance_trade_report",
    )
    op.drop_table("portfolio_performance_trade_report")
