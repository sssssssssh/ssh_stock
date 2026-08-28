"""add trend state and signal tables

Revision ID: 0005_trend_state_signal
Revises: 0004_stock_factor_short_returns
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_trend_state_signal"
down_revision: str | None = "0004_stock_factor_short_returns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stock_state_daily",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("algo_version", sa.String(length=32), nullable=False),
        sa.Column("previous_state", sa.String(length=16), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("state_day_count", sa.Integer(), nullable=True),
        sa.Column("is_new_state", sa.Boolean(), nullable=False),
        sa.Column("right_side_score", sa.Float(), nullable=True),
        sa.Column("trend_score", sa.Float(), nullable=True),
        sa.Column("opportunity_score", sa.Float(), nullable=True),
        sa.Column("primary_sector_id", sa.Integer(), nullable=True),
        sa.Column("sector_heat", sa.Float(), nullable=True),
        sa.Column("market_score", sa.Float(), nullable=True),
        sa.Column("fast_transition", sa.Boolean(), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint(
            "trade_date", "ts_code", "algo_version", name=op.f("pk_stock_state_daily")
        ),
    )
    op.create_index("idx_stock_state_date_state", "stock_state_daily", ["trade_date", "state"])
    op.create_index(
        "idx_stock_state_date_score", "stock_state_daily", ["trade_date", "opportunity_score"]
    )

    op.create_table(
        "strategy_signal",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("signal_type", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("opportunity_score", sa.Float(), nullable=True),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("algo_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategy_signal")),
        sa.UniqueConstraint(
            "trade_date",
            "ts_code",
            "signal_type",
            "algo_version",
            name="uq_strategy_signal_natural",
        ),
    )
    op.create_index(
        "idx_strategy_signal_date_type", "strategy_signal", ["trade_date", "signal_type"]
    )


def downgrade() -> None:
    op.drop_index("idx_strategy_signal_date_type", table_name="strategy_signal")
    op.drop_table("strategy_signal")
    op.drop_index("idx_stock_state_date_score", table_name="stock_state_daily")
    op.drop_index("idx_stock_state_date_state", table_name="stock_state_daily")
    op.drop_table("stock_state_daily")
