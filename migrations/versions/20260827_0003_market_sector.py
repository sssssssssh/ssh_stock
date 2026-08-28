"""add market and sector tables

Revision ID: 0003_market_sector
Revises: 0002_stock_factor_daily
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_market_sector"
down_revision: str | None = "0002_stock_factor_daily"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_daily",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("market_score", sa.Float(), nullable=True),
        sa.Column("regime", sa.String(length=16), nullable=True),
        sa.Column("breadth20", sa.Float(), nullable=True),
        sa.Column("breadth60", sa.Float(), nullable=True),
        sa.Column("up_count", sa.Integer(), nullable=True),
        sa.Column("down_count", sa.Integer(), nullable=True),
        sa.Column("flat_count", sa.Integer(), nullable=True),
        sa.Column("up_rate", sa.Float(), nullable=True),
        sa.Column("new_high20_count", sa.Integer(), nullable=True),
        sa.Column("new_low20_count", sa.Integer(), nullable=True),
        sa.Column("new_high60_count", sa.Integer(), nullable=True),
        sa.Column("new_low60_count", sa.Integer(), nullable=True),
        sa.Column("total_amount", sa.Float(), nullable=True),
        sa.Column("amount_ratio20", sa.Float(), nullable=True),
        sa.Column("index_trend_score", sa.Float(), nullable=True),
        sa.Column("breadth_score", sa.Float(), nullable=True),
        sa.Column("ad_score", sa.Float(), nullable=True),
        sa.Column("new_high_low_score", sa.Float(), nullable=True),
        sa.Column("liquidity_score", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("trade_date", name=op.f("pk_market_daily")),
    )
    op.create_table(
        "sector",
        sa.Column("sector_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("source_code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=True),
        sa.Column("parent_code", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("sector_id", name=op.f("pk_sector")),
        sa.UniqueConstraint("source", "source_code", name="uq_sector_source_code"),
    )
    op.create_table(
        "sector_member",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sector_id", sa.Integer(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_latest", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["sector_id"], ["sector.sector_id"], name=op.f("fk_sector_member_sector_id_sector")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sector_member")),
        sa.UniqueConstraint("sector_id", "ts_code", "valid_from", name="uq_sector_member_from"),
    )
    op.create_index("idx_sector_member_stock", "sector_member", ["ts_code", "is_latest"])
    op.create_table(
        "sector_factor_daily",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("sector_id", sa.Integer(), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=True),
        sa.Column("eligible_member_count", sa.Integer(), nullable=True),
        sa.Column("return1", sa.Float(), nullable=True),
        sa.Column("return3", sa.Float(), nullable=True),
        sa.Column("return5", sa.Float(), nullable=True),
        sa.Column("return20", sa.Float(), nullable=True),
        sa.Column("excess_return5", sa.Float(), nullable=True),
        sa.Column("excess_return20", sa.Float(), nullable=True),
        sa.Column("breadth20", sa.Float(), nullable=True),
        sa.Column("breadth60", sa.Float(), nullable=True),
        sa.Column("up_rate", sa.Float(), nullable=True),
        sa.Column("new_high20_rate", sa.Float(), nullable=True),
        sa.Column("rps60_median", sa.Float(), nullable=True),
        sa.Column("rps60_top20_rate", sa.Float(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("amount_ratio20", sa.Float(), nullable=True),
        sa.Column("limit_up_density", sa.Float(), nullable=True),
        sa.Column("moneyflow_score", sa.Float(), nullable=True),
        sa.Column("heat_score", sa.Float(), nullable=True),
        sa.Column("heat_momentum1", sa.Float(), nullable=True),
        sa.Column("heat_momentum3", sa.Float(), nullable=True),
        sa.Column("heat_rank", sa.Integer(), nullable=True),
        sa.Column("rank_change", sa.Integer(), nullable=True),
        sa.Column("lifecycle", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(
            ["sector_id"],
            ["sector.sector_id"],
            name=op.f("fk_sector_factor_daily_sector_id_sector"),
        ),
        sa.PrimaryKeyConstraint("trade_date", "sector_id", name=op.f("pk_sector_factor_daily")),
    )
    op.create_index(
        "idx_sector_factor_date_rank", "sector_factor_daily", ["trade_date", "heat_rank"]
    )


def downgrade() -> None:
    op.drop_index("idx_sector_factor_date_rank", table_name="sector_factor_daily")
    op.drop_table("sector_factor_daily")
    op.drop_index("idx_sector_member_stock", table_name="sector_member")
    op.drop_table("sector_member")
    op.drop_table("sector")
    op.drop_table("market_daily")
