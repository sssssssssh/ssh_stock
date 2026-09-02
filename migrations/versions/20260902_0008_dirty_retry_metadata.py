"""add dirty retry metadata

Revision ID: 0008_dirty_retry_metadata
Revises: 0007_data_reliability
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_dirty_retry_metadata"
down_revision: str | None = "0007_data_reliability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "data_dirty_range",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("data_dirty_range", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column(
        "data_dirty_range",
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("data_dirty_range", "last_failed_at")
    op.drop_column("data_dirty_range", "last_error")
    op.drop_column("data_dirty_range", "retry_count")
