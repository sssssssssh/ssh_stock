"""initial raw warehouse

Revision ID: 0001_initial_raw_warehouse
Revises:
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_raw_warehouse"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stock_basic",
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(length=8), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=True),
        sa.Column("market", sa.String(length=32), nullable=True),
        sa.Column("exchange", sa.String(length=8), nullable=True),
        sa.Column("industry", sa.String(length=64), nullable=True),
        sa.Column("list_status", sa.String(length=4), nullable=True),
        sa.Column("list_date", sa.Date(), nullable=True),
        sa.Column("delist_date", sa.Date(), nullable=True),
        sa.Column("is_hs", sa.String(length=4), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("ts_code", name=op.f("pk_stock_basic")),
    )
    op.create_table(
        "trade_calendar",
        sa.Column("cal_date", sa.Date(), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False),
        sa.Column("pretrade_date", sa.Date(), nullable=True),
        sa.Column("exchange", sa.String(length=8), nullable=False),
        sa.PrimaryKeyConstraint("cal_date", name=op.f("pk_trade_calendar")),
    )
    op.create_table(
        "stock_daily",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("open", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("close", sa.Float(), nullable=True),
        sa.Column("pre_close", sa.Float(), nullable=True),
        sa.Column("change", sa.Float(), nullable=True),
        sa.Column("pct_chg", sa.Float(), nullable=True),
        sa.Column("vol", sa.Float(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column(
            "source_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("trade_date", "ts_code", name=op.f("pk_stock_daily")),
    )
    op.create_index("idx_stock_daily_code_date", "stock_daily", ["ts_code", "trade_date"])
    op.create_table(
        "stock_adj_factor",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("adj_factor", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("trade_date", "ts_code", name=op.f("pk_stock_adj_factor")),
    )
    op.create_index("idx_stock_adj_factor_code_date", "stock_adj_factor", ["ts_code", "trade_date"])
    op.create_table(
        "stock_daily_basic",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("close", sa.Float(), nullable=True),
        sa.Column("turnover_rate", sa.Float(), nullable=True),
        sa.Column("turnover_rate_f", sa.Float(), nullable=True),
        sa.Column("volume_ratio", sa.Float(), nullable=True),
        sa.Column("pe", sa.Float(), nullable=True),
        sa.Column("pe_ttm", sa.Float(), nullable=True),
        sa.Column("pb", sa.Float(), nullable=True),
        sa.Column("ps", sa.Float(), nullable=True),
        sa.Column("ps_ttm", sa.Float(), nullable=True),
        sa.Column("total_share", sa.Float(), nullable=True),
        sa.Column("float_share", sa.Float(), nullable=True),
        sa.Column("free_share", sa.Float(), nullable=True),
        sa.Column("total_mv", sa.Float(), nullable=True),
        sa.Column("circ_mv", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("trade_date", "ts_code", name=op.f("pk_stock_daily_basic")),
    )
    op.create_index(
        "idx_stock_daily_basic_code_date", "stock_daily_basic", ["ts_code", "trade_date"]
    )
    op.create_table(
        "index_daily",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("open", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("close", sa.Float(), nullable=True),
        sa.Column("pre_close", sa.Float(), nullable=True),
        sa.Column("pct_chg", sa.Float(), nullable=True),
        sa.Column("vol", sa.Float(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("trade_date", "ts_code", name=op.f("pk_index_daily")),
    )
    op.create_index("idx_index_daily_code_date", "index_daily", ["ts_code", "trade_date"])
    op.create_table(
        "job_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("target_trade_date", sa.Date(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("step", sa.String(length=64), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.String(length=2048), nullable=True),
        sa.Column("job_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_run")),
    )
    op.create_index(
        "idx_job_run_type_date_status", "job_run", ["job_type", "target_trade_date", "status"]
    )
    op.create_table(
        "provider_api_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("api_name", sa.String(length=64), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_type", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_api_log")),
    )
    op.create_index(
        "idx_provider_api_log_date_name", "provider_api_log", ["trade_date", "api_name"]
    )


def downgrade() -> None:
    op.drop_index("idx_provider_api_log_date_name", table_name="provider_api_log")
    op.drop_table("provider_api_log")
    op.drop_index("idx_job_run_type_date_status", table_name="job_run")
    op.drop_table("job_run")
    op.drop_index("idx_index_daily_code_date", table_name="index_daily")
    op.drop_table("index_daily")
    op.drop_index("idx_stock_daily_basic_code_date", table_name="stock_daily_basic")
    op.drop_table("stock_daily_basic")
    op.drop_index("idx_stock_adj_factor_code_date", table_name="stock_adj_factor")
    op.drop_table("stock_adj_factor")
    op.drop_index("idx_stock_daily_code_date", table_name="stock_daily")
    op.drop_table("stock_daily")
    op.drop_table("trade_calendar")
    op.drop_table("stock_basic")
