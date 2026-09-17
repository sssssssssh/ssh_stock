"""add theme source coverage

Revision ID: 0016_theme_closeout
Revises: 0015_milestone10
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_theme_closeout"
down_revision: str | None = "0015_milestone10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("theme_factor_daily", sa.Column("source_coverage", sa.Float()))


def downgrade() -> None:
    op.drop_column("theme_factor_daily", "source_coverage")
