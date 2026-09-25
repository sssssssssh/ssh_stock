"""Add Milestone 12 research return semantics.

Revision ID: 0023_m12_research_returns
Revises: 0022_theme_member_interval
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_m12_research_returns"
down_revision: str | None = "0022_theme_member_interval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HORIZONS = (5, 10, 20, 60)
TABLES = ("opportunity_forward_eval", "theme_forward_eval")


def upgrade() -> None:
    for table in TABLES:
        for horizon in HORIZONS:
            op.add_column(table, sa.Column(f"mark_ret{horizon}", sa.Float(), nullable=True))
            op.add_column(
                table, sa.Column(f"delayed_exit_trade_date{horizon}", sa.Date(), nullable=True)
            )
            op.add_column(
                table, sa.Column(f"delayed_exit_price{horizon}", sa.Float(), nullable=True)
            )
            op.add_column(
                table, sa.Column(f"delayed_exit_delay_days{horizon}", sa.Integer(), nullable=True)
            )
            op.add_column(
                table, sa.Column(f"delayed_exit_ret{horizon}", sa.Float(), nullable=True)
            )
            op.add_column(table, sa.Column(f"net_ret{horizon}", sa.Float(), nullable=True))
            op.add_column(
                table, sa.Column(f"net_delayed_exit_ret{horizon}", sa.Float(), nullable=True)
            )


def downgrade() -> None:
    for table in TABLES:
        for horizon in reversed(HORIZONS):
            for prefix in (
                "net_delayed_exit_ret",
                "net_ret",
                "delayed_exit_ret",
                "delayed_exit_delay_days",
                "delayed_exit_price",
                "delayed_exit_trade_date",
                "mark_ret",
            ):
                op.drop_column(table, f"{prefix}{horizon}")
