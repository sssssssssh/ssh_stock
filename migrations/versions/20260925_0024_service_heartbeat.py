"""Add service heartbeat registry.

Revision ID: 0024_service_heartbeat
Revises: 0023_m12_research_returns
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_service_heartbeat"
down_revision: str | None = "0023_m12_research_returns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_heartbeat",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_name", sa.String(length=32), nullable=False),
        sa.Column("instance_id", sa.String(length=160), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("service_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "service_name", "instance_id", name="uq_service_heartbeat_instance"
        ),
    )
    op.create_index(
        "idx_service_heartbeat_name_time",
        "service_heartbeat",
        ["service_name", "heartbeat_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_service_heartbeat_name_time", table_name="service_heartbeat")
    op.drop_table("service_heartbeat")
