"""add versioned executable signal evaluation

Revision ID: 0014_signal_eval_v2
Revises: 0013_worker_reliability
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_signal_eval_v2"
down_revision: str | None = "0013_worker_reliability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_signal_forward_eval_signal",
        "signal_forward_eval",
        type_="unique",
    )
    op.add_column(
        "signal_forward_eval",
        sa.Column("eval_version", sa.String(length=16), nullable=False, server_default="eval_v1"),
    )
    op.add_column(
        "signal_forward_eval",
        sa.Column(
            "entry_basis",
            sa.String(length=16),
            nullable=False,
            server_default="SIGNAL_CLOSE",
        ),
    )
    op.add_column(
        "signal_forward_eval",
        sa.Column(
            "horizon_basis",
            sa.String(length=32),
            nullable=False,
            server_default="STOCK_ROW",
        ),
    )
    op.add_column("signal_forward_eval", sa.Column("entry_trade_date", sa.Date()))
    op.add_column("signal_forward_eval", sa.Column("entry_price", sa.Float()))
    op.add_column("signal_forward_eval", sa.Column("entry_executable", sa.Boolean()))
    op.add_column("signal_forward_eval", sa.Column("exit_executable", sa.Boolean()))
    op.add_column(
        "signal_forward_eval",
        sa.Column("non_executable_reason", sa.String(length=128)),
    )
    op.create_unique_constraint(
        "uq_signal_forward_eval_version_basis",
        "signal_forward_eval",
        ["signal_id", "eval_version", "entry_basis"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_signal_forward_eval_version_basis",
        "signal_forward_eval",
        type_="unique",
    )
    for column in (
        "non_executable_reason",
        "exit_executable",
        "entry_executable",
        "entry_price",
        "entry_trade_date",
        "horizon_basis",
        "entry_basis",
        "eval_version",
    ):
        op.drop_column("signal_forward_eval", column)
    op.create_unique_constraint(
        "uq_signal_forward_eval_signal",
        "signal_forward_eval",
        ["signal_id"],
    )
