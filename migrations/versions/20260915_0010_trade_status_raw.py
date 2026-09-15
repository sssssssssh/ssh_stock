"""add trade status raw tables

Revision ID: 0010_trade_status_raw
Revises: 0009_derived_result_integrity
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_trade_status_raw"
down_revision: str | None = "0009_derived_result_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stock_st_daily",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=True),
        sa.Column("st_type", sa.String(length=32), nullable=True),
        sa.Column("st_type_name", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("trade_date", "ts_code", name=op.f("pk_stock_st_daily")),
    )
    op.create_table(
        "stock_suspend_daily",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("suspend_type", sa.String(length=8), nullable=False),
        sa.Column("suspend_timing", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint(
            "trade_date",
            "ts_code",
            "suspend_type",
            name=op.f("pk_stock_suspend_daily"),
        ),
    )
    op.create_table(
        "stock_limit_daily",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("pre_close", sa.Float(), nullable=True),
        sa.Column("up_limit", sa.Float(), nullable=True),
        sa.Column("down_limit", sa.Float(), nullable=True),
        sa.Column("asset_type", sa.String(length=16), nullable=True),
        sa.Column("exchange", sa.String(length=8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("trade_date", "ts_code", name=op.f("pk_stock_limit_daily")),
    )


def downgrade() -> None:
    op.drop_table("stock_limit_daily")
    op.drop_table("stock_suspend_daily")
    op.drop_table("stock_st_daily")
