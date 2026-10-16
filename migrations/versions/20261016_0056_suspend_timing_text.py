"""Store suspension descriptions without truncation.

Revision ID: 0056_suspend_timing_text
Revises: 0055_retention_frozen_refs
"""

import sqlalchemy as sa
from alembic import op

revision = "0056_suspend_timing_text"
down_revision = "0055_retention_frozen_refs"
branch_labels = None
depends_on = None


def _lock_table():
    bind = op.get_bind()
    bind.execute(sa.text("SET LOCAL lock_timeout = '2s'"))
    bind.execute(sa.text("SET LOCAL statement_timeout = '30s'"))
    # Hold the same lock during the downgrade guard and ALTER, excluding new long values.
    bind.execute(sa.text("LOCK TABLE stock_suspend_daily IN ACCESS EXCLUSIVE MODE"))
    return bind


def upgrade():
    _lock_table()
    op.alter_column(
        "stock_suspend_daily", "suspend_timing",
        existing_type=sa.String(length=32), type_=sa.Text(), existing_nullable=True,
    )


def downgrade():
    bind = _lock_table()
    if bind.scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM stock_suspend_daily WHERE length(suspend_timing) > 32)"
    )):
        raise RuntimeError("SUSPEND_TIMING_DOWNGRADE_WOULD_TRUNCATE")
    op.alter_column(
        "stock_suspend_daily", "suspend_timing",
        existing_type=sa.Text(), type_=sa.String(length=32), existing_nullable=True,
    )
