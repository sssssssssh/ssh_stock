"""Add historical theme membership intervals and research context metadata.

Revision ID: 0022_theme_member_interval
Revises: 0021_admin_auth
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_theme_member_interval"
down_revision: str | None = "0021_admin_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job_run",
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "theme_member_interval",
        sa.Column("theme_code", sa.String(32), sa.ForeignKey("theme.theme_code"), nullable=False),
        sa.Column("ts_code", sa.String(16), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date()),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("source_is_new", sa.Boolean()),
        sa.Column("quality_flag", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("theme_code", "ts_code", "valid_from"),
    )
    op.create_index(
        "idx_theme_member_interval_stock_dates",
        "theme_member_interval",
        ["ts_code", "valid_from", "valid_to"],
    )
    for table in ("opportunity_forward_eval", "theme_forward_eval"):
        op.add_column(
            table,
            sa.Column(
                "theme_context_available", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )
        op.add_column(table, sa.Column("theme_context_coverage", sa.Float()))


def downgrade() -> None:
    for table in ("theme_forward_eval", "opportunity_forward_eval"):
        op.drop_column(table, "theme_context_coverage")
        op.drop_column(table, "theme_context_available")
    op.drop_table("theme_member_interval")
    op.drop_column("job_run", "cancel_requested")
