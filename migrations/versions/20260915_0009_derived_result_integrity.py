"""add derived result integrity cascade

Revision ID: 0009_derived_result_integrity
Revises: 0008_dirty_retry_metadata
Create Date: 2026-09-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009_derived_result_integrity"
down_revision: str | None = "0008_dirty_retry_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("fk_signal_forward_eval_signal_id"),
        "signal_forward_eval",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_signal_forward_eval_signal_id"),
        "signal_forward_eval",
        "strategy_signal",
        ["signal_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_signal_forward_eval_signal_id"),
        "signal_forward_eval",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_signal_forward_eval_signal_id"),
        "signal_forward_eval",
        "strategy_signal",
        ["signal_id"],
        ["id"],
    )
