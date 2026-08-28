"""add stock factor daily

Revision ID: 0002_stock_factor_daily
Revises: 0001_initial_raw_warehouse
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_stock_factor_daily"
down_revision: str | None = "0001_initial_raw_warehouse"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stock_factor_daily",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("adj_open", sa.Float(), nullable=True),
        sa.Column("adj_high", sa.Float(), nullable=True),
        sa.Column("adj_low", sa.Float(), nullable=True),
        sa.Column("adj_close", sa.Float(), nullable=True),
        sa.Column("ma5", sa.Float(), nullable=True),
        sa.Column("ma10", sa.Float(), nullable=True),
        sa.Column("ma20", sa.Float(), nullable=True),
        sa.Column("ma60", sa.Float(), nullable=True),
        sa.Column("ma120", sa.Float(), nullable=True),
        sa.Column("ma250", sa.Float(), nullable=True),
        sa.Column("return5", sa.Float(), nullable=True),
        sa.Column("return20", sa.Float(), nullable=True),
        sa.Column("return60", sa.Float(), nullable=True),
        sa.Column("return120", sa.Float(), nullable=True),
        sa.Column("return250", sa.Float(), nullable=True),
        sa.Column("ma20_slope5", sa.Float(), nullable=True),
        sa.Column("ma60_slope10", sa.Float(), nullable=True),
        sa.Column("atr20", sa.Float(), nullable=True),
        sa.Column("atr20_pct", sa.Float(), nullable=True),
        sa.Column("amount_ma20", sa.Float(), nullable=True),
        sa.Column("amount_ratio20", sa.Float(), nullable=True),
        sa.Column("prev_high20", sa.Float(), nullable=True),
        sa.Column("prev_high60", sa.Float(), nullable=True),
        sa.Column("prev_high120", sa.Float(), nullable=True),
        sa.Column("low20", sa.Float(), nullable=True),
        sa.Column("low60", sa.Float(), nullable=True),
        sa.Column("breakout20", sa.Boolean(), nullable=True),
        sa.Column("breakout60", sa.Boolean(), nullable=True),
        sa.Column("cross_above_ma20", sa.Boolean(), nullable=True),
        sa.Column("cross_above_ma60", sa.Boolean(), nullable=True),
        sa.Column("higher_low", sa.Boolean(), nullable=True),
        sa.Column("higher_low_pct", sa.Float(), nullable=True),
        sa.Column("drawdown_high60", sa.Float(), nullable=True),
        sa.Column("drawdown_high120", sa.Float(), nullable=True),
        sa.Column("max_drawdown60", sa.Float(), nullable=True),
        sa.Column("trend_efficiency20", sa.Float(), nullable=True),
        sa.Column("rps20", sa.Float(), nullable=True),
        sa.Column("rps60", sa.Float(), nullable=True),
        sa.Column("rps120", sa.Float(), nullable=True),
        sa.Column("rps250", sa.Float(), nullable=True),
        sa.Column("rps20_delta5", sa.Float(), nullable=True),
        sa.Column("rps60_delta5", sa.Float(), nullable=True),
        sa.Column("relative_return20", sa.Float(), nullable=True),
        sa.Column("relative_return60", sa.Float(), nullable=True),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("exclusion_reason", sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint("trade_date", "ts_code", name=op.f("pk_stock_factor_daily")),
    )
    op.create_index(
        "idx_factor_date_eligible", "stock_factor_daily", ["trade_date", "eligible"]
    )
    op.create_index("idx_factor_code_date", "stock_factor_daily", ["ts_code", "trade_date"])


def downgrade() -> None:
    op.drop_index("idx_factor_code_date", table_name="stock_factor_daily")
    op.drop_index("idx_factor_date_eligible", table_name="stock_factor_daily")
    op.drop_table("stock_factor_daily")

