"""add point in time stock trade status

Revision ID: 0011_stock_trade_status_daily
Revises: 0010_trade_status_raw
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_stock_trade_status_daily"
down_revision: str | None = "0010_trade_status_raw"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stock_trade_status_daily",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_suspended", sa.Boolean(), nullable=False),
        sa.Column("is_st", sa.Boolean(), nullable=True),
        sa.Column("st_status_unknown", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("up_limit", sa.Float(), nullable=True),
        sa.Column("down_limit", sa.Float(), nullable=True),
        sa.Column("is_limit_up_close", sa.Boolean(), nullable=True),
        sa.Column("is_limit_down_close", sa.Boolean(), nullable=True),
        sa.Column("tradable", sa.Boolean(), nullable=False),
        sa.Column("strategy_eligible", sa.Boolean(), nullable=False),
        sa.Column("status_reason", sa.String(length=256), nullable=True),
        sa.Column("calc_version", sa.String(length=32), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("calc_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "trade_date", "ts_code", name=op.f("pk_stock_trade_status_daily")
        ),
    )
    op.create_index(
        "idx_trade_status_date_tradable",
        "stock_trade_status_daily",
        ["trade_date", "tradable"],
    )
    op.create_index(
        "idx_trade_status_date_eligible",
        "stock_trade_status_daily",
        ["trade_date", "strategy_eligible"],
    )


def downgrade() -> None:
    op.drop_index("idx_trade_status_date_eligible", table_name="stock_trade_status_daily")
    op.drop_index("idx_trade_status_date_tradable", table_name="stock_trade_status_daily")
    op.drop_table("stock_trade_status_daily")
