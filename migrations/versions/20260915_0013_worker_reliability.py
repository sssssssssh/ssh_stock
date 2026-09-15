"""add worker heartbeat and dirty processing timestamps

Revision ID: 0013_worker_reliability
Revises: 0012_state_signal_metadata
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_worker_reliability"
down_revision: str | None = "0012_state_signal_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job_run", sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
    op.add_column("job_run", sa.Column("worker_id", sa.String(length=128)))
    op.add_column(
        "data_dirty_range",
        sa.Column("processing_started_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "idx_job_run_status_started",
        "job_run",
        ["status", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_job_run_status_started", table_name="job_run")
    op.drop_column("data_dirty_range", "processing_started_at")
    op.drop_column("job_run", "worker_id")
    op.drop_column("job_run", "heartbeat_at")
