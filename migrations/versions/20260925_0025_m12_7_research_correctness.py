"""Add auditable mark-to-market dates for Research V3.

Revision ID: 0025_m12_7_research_correctness
Revises: 0024_service_heartbeat
"""

import sqlalchemy as sa
from alembic import op

revision = "0025_m12_7_research_correctness"
down_revision = "0024_service_heartbeat"
branch_labels = None
depends_on = None

HORIZONS = (5, 10, 20, 60)
TABLES = ("opportunity_forward_eval", "theme_forward_eval")


def upgrade() -> None:
    for table in TABLES:
        for horizon in HORIZONS:
            op.add_column(
                table,
                sa.Column(f"mark_trade_date{horizon}", sa.Date(), nullable=True),
            )


def downgrade() -> None:
    for table in TABLES:
        for horizon in reversed(HORIZONS):
            op.drop_column(table, f"mark_trade_date{horizon}")
