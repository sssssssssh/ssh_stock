"""add signal forward evaluation table

Revision ID: 0006_signal_forward_eval
Revises: 0005_trend_state_signal
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_signal_forward_eval"
down_revision: str | None = "0005_trend_state_signal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signal_forward_eval",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("signal_id", sa.BigInteger(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("signal_type", sa.String(length=32), nullable=False),
        sa.Column("algo_version", sa.String(length=32), nullable=False),
        sa.Column("ret5", sa.Float(), nullable=True),
        sa.Column("ret10", sa.Float(), nullable=True),
        sa.Column("ret20", sa.Float(), nullable=True),
        sa.Column("ret60", sa.Float(), nullable=True),
        sa.Column("mfe20", sa.Float(), nullable=True),
        sa.Column("mae20", sa.Float(), nullable=True),
        sa.Column("evaluated_until_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["signal_id"], ["strategy_signal.id"], name=op.f("fk_signal_forward_eval_signal_id")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signal_forward_eval")),
        sa.UniqueConstraint("signal_id", name="uq_signal_forward_eval_signal"),
    )
    op.create_index(
        "idx_signal_forward_eval_type_version",
        "signal_forward_eval",
        ["signal_type", "algo_version"],
    )


def downgrade() -> None:
    op.drop_index("idx_signal_forward_eval_type_version", table_name="signal_forward_eval")
    op.drop_table("signal_forward_eval")
