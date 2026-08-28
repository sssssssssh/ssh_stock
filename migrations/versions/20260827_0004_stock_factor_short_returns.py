"""add short return columns to stock factors

Revision ID: 0004_stock_factor_short_returns
Revises: 0003_market_sector
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_stock_factor_short_returns"
down_revision: str | None = "0003_market_sector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("stock_factor_daily", sa.Column("return1", sa.Float(), nullable=True))
    op.add_column("stock_factor_daily", sa.Column("return3", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("stock_factor_daily", "return3")
    op.drop_column("stock_factor_daily", "return1")
