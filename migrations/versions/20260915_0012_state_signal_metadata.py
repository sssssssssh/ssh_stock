"""add state and signal calculation metadata

Revision ID: 0012_state_signal_metadata
Revises: 0011_stock_trade_status_daily
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_state_signal_metadata"
down_revision: str | None = "0011_stock_trade_status_daily"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in ("stock_state_daily", "strategy_signal"):
        op.add_column(table_name, sa.Column("calc_version", sa.String(length=32)))
        op.add_column(table_name, sa.Column("config_hash", sa.String(length=64)))
        op.add_column(
            table_name,
            sa.Column("calc_run_id", postgresql.UUID(as_uuid=True)),
        )
        op.add_column(table_name, sa.Column("calculated_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    for table_name in ("strategy_signal", "stock_state_daily"):
        op.drop_column(table_name, "calculated_at")
        op.drop_column(table_name, "calc_run_id")
        op.drop_column(table_name, "config_hash")
        op.drop_column(table_name, "calc_version")
