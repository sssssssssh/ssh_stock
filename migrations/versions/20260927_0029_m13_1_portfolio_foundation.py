"""Establish the M13.1 portfolio and backtest persistence foundation.

Revision ID: 0029_m13_1_portfolio_foundation
Revises: 0028_m12_8_3_exit_checks
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029_m13_1_portfolio_foundation"
down_revision = "0028_m12_8_3_exit_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_backtest_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("account_mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="CREATED", nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("initial_cash", sa.Numeric(20, 4), nullable=False),
        sa.Column("benchmark_code", sa.String(length=16), nullable=False),
        sa.Column("algo_version", sa.String(length=32), nullable=False),
        sa.Column("source_strategy_config_hash", sa.String(length=64), nullable=False),
        sa.Column("opportunity_calc_version", sa.String(length=32), nullable=False),
        sa.Column("opportunity_config_hash", sa.String(length=64), nullable=False),
        sa.Column("portfolio_version", sa.String(length=32), nullable=False),
        sa.Column("portfolio_config_hash", sa.String(length=64), nullable=False),
        sa.Column("execution_version", sa.String(length=32), nullable=False),
        sa.Column("execution_config_hash", sa.String(length=64), nullable=False),
        sa.Column("backtest_engine_version", sa.String(length=32), nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "result_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error_message", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "account_mode IN ('BACKTEST', 'PAPER', 'LIVE')",
            name=op.f("ck_portfolio_backtest_run_account_mode"),
        ),
        sa.CheckConstraint(
            "status IN ('CREATED', 'RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED')",
            name=op.f("ck_portfolio_backtest_run_status"),
        ),
        sa.CheckConstraint(
            "end_date >= start_date", name=op.f("ck_portfolio_backtest_run_dates")
        ),
        sa.CheckConstraint(
            "initial_cash > 0", name=op.f("ck_portfolio_backtest_run_initial_cash")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["job_run.id"],
            name=op.f("fk_portfolio_backtest_run_job_id_job_run"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_backtest_run")),
    )
    op.create_index(
        "idx_portfolio_backtest_status_created",
        "portfolio_backtest_run",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "portfolio_order",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_trade_date", sa.Date(), nullable=False),
        sa.Column("scheduled_trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=24), nullable=False),
        sa.Column("target_weight", sa.Numeric(12, 8), nullable=True),
        sa.Column("target_quantity", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="PENDING", nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
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
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name=op.f("ck_portfolio_order_side")),
        sa.CheckConstraint(
            "order_type IN ('NEXT_OPEN', 'MARKET_ON_OPEN')",
            name=op.f("ck_portfolio_order_type"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PARTIAL', 'EXECUTED', 'REJECTED', 'CANCELLED')",
            name=op.f("ck_portfolio_order_status"),
        ),
        sa.CheckConstraint(
            "target_weight IS NULL OR target_weight >= 0",
            name=op.f("ck_portfolio_order_target_weight"),
        ),
        sa.CheckConstraint(
            "target_quantity IS NULL OR target_quantity >= 0",
            name=op.f("ck_portfolio_order_target_quantity"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name=op.f("ck_portfolio_order_attempt_count")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["portfolio_backtest_run.id"],
            name=op.f("fk_portfolio_order_run_id_portfolio_backtest_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_order")),
    )
    op.create_index(
        "idx_portfolio_order_run_schedule_status",
        "portfolio_order",
        ["run_id", "scheduled_trade_date", "status"],
        unique=False,
    )

    op.create_table(
        "portfolio_fill",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("price", sa.Numeric(18, 4), nullable=False),
        sa.Column("gross_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("commission", sa.Numeric(20, 4), server_default="0", nullable=False),
        sa.Column("stamp_tax", sa.Numeric(20, 4), server_default="0", nullable=False),
        sa.Column("slippage_cost", sa.Numeric(20, 4), server_default="0", nullable=False),
        sa.Column("total_cost", sa.Numeric(20, 4), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name=op.f("ck_portfolio_fill_side")),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_portfolio_fill_quantity")),
        sa.CheckConstraint("price > 0", name=op.f("ck_portfolio_fill_price")),
        sa.CheckConstraint("gross_amount >= 0", name=op.f("ck_portfolio_fill_gross_amount")),
        sa.CheckConstraint("commission >= 0", name=op.f("ck_portfolio_fill_commission")),
        sa.CheckConstraint("stamp_tax >= 0", name=op.f("ck_portfolio_fill_stamp_tax")),
        sa.CheckConstraint("slippage_cost >= 0", name=op.f("ck_portfolio_fill_slippage_cost")),
        sa.CheckConstraint("total_cost >= 0", name=op.f("ck_portfolio_fill_total_cost")),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["portfolio_order.id"],
            name=op.f("fk_portfolio_fill_order_id_portfolio_order"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["portfolio_backtest_run.id"],
            name=op.f("fk_portfolio_fill_run_id_portfolio_backtest_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_fill")),
    )
    op.create_index(
        "idx_portfolio_fill_run_date", "portfolio_fill", ["run_id", "trade_date"], unique=False
    )

    op.create_table(
        "portfolio_position_daily",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("available_quantity", sa.BigInteger(), nullable=False),
        sa.Column("avg_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("close_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("market_value", sa.Numeric(20, 4), nullable=False),
        sa.Column("weight", sa.Numeric(12, 8), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(20, 4), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(20, 4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("quantity >= 0", name=op.f("ck_portfolio_position_quantity")),
        sa.CheckConstraint(
            "available_quantity >= 0", name=op.f("ck_portfolio_position_available_quantity")
        ),
        sa.CheckConstraint("avg_cost >= 0", name=op.f("ck_portfolio_position_avg_cost")),
        sa.CheckConstraint(
            "close_price IS NULL OR close_price >= 0",
            name=op.f("ck_portfolio_position_close_price"),
        ),
        sa.CheckConstraint(
            "market_value >= 0", name=op.f("ck_portfolio_position_market_value")
        ),
        sa.CheckConstraint("weight >= 0", name=op.f("ck_portfolio_position_weight")),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["portfolio_backtest_run.id"],
            name=op.f("fk_portfolio_position_daily_run_id_portfolio_backtest_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "run_id", "trade_date", "ts_code", name=op.f("pk_portfolio_position_daily")
        ),
    )
    op.create_index(
        "idx_portfolio_position_run_date",
        "portfolio_position_daily",
        ["run_id", "trade_date"],
        unique=False,
    )

    op.create_table(
        "portfolio_nav_daily",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("cash", sa.Numeric(20, 4), nullable=False),
        sa.Column("market_value", sa.Numeric(20, 4), nullable=False),
        sa.Column("total_assets", sa.Numeric(20, 4), nullable=False),
        sa.Column("nav", sa.Numeric(20, 8), nullable=False),
        sa.Column("daily_return", sa.Numeric(16, 8), nullable=True),
        sa.Column("benchmark_nav", sa.Numeric(20, 8), nullable=True),
        sa.Column("benchmark_daily_return", sa.Numeric(16, 8), nullable=True),
        sa.Column("gross_exposure", sa.Numeric(12, 8), nullable=False),
        sa.Column("net_exposure", sa.Numeric(12, 8), nullable=False),
        sa.Column("position_count", sa.Integer(), nullable=False),
        sa.Column("turnover", sa.Numeric(16, 8), nullable=True),
        sa.Column("trading_cost", sa.Numeric(20, 4), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("cash >= 0", name=op.f("ck_portfolio_nav_cash")),
        sa.CheckConstraint("market_value >= 0", name=op.f("ck_portfolio_nav_market_value")),
        sa.CheckConstraint("total_assets >= 0", name=op.f("ck_portfolio_nav_total_assets")),
        sa.CheckConstraint("nav >= 0", name=op.f("ck_portfolio_nav_nav")),
        sa.CheckConstraint(
            "gross_exposure >= 0", name=op.f("ck_portfolio_nav_gross_exposure")
        ),
        sa.CheckConstraint("net_exposure >= 0", name=op.f("ck_portfolio_nav_net_exposure")),
        sa.CheckConstraint(
            "position_count >= 0", name=op.f("ck_portfolio_nav_position_count")
        ),
        sa.CheckConstraint("trading_cost >= 0", name=op.f("ck_portfolio_nav_trading_cost")),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["portfolio_backtest_run.id"],
            name=op.f("fk_portfolio_nav_daily_run_id_portfolio_backtest_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id", "trade_date", name=op.f("pk_portfolio_nav_daily")),
    )
    op.create_index(
        "idx_portfolio_nav_run_date",
        "portfolio_nav_daily",
        ["run_id", "trade_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_portfolio_nav_run_date", table_name="portfolio_nav_daily")
    op.drop_table("portfolio_nav_daily")
    op.drop_index("idx_portfolio_position_run_date", table_name="portfolio_position_daily")
    op.drop_table("portfolio_position_daily")
    op.drop_index("idx_portfolio_fill_run_date", table_name="portfolio_fill")
    op.drop_table("portfolio_fill")
    op.drop_index("idx_portfolio_order_run_schedule_status", table_name="portfolio_order")
    op.drop_table("portfolio_order")
    op.drop_index("idx_portfolio_backtest_status_created", table_name="portfolio_backtest_run")
    op.drop_table("portfolio_backtest_run")
