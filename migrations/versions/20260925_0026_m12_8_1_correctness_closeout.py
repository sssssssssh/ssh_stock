"""Add delayed-exit observation-window maturity.

Revision ID: 0026_m12_8_1_closeout
Revises: 0025_m12_7_research_correctness
"""

import sqlalchemy as sa
from alembic import op

revision = "0026_m12_8_1_closeout"
down_revision = "0025_m12_7_research_correctness"
branch_labels = None
depends_on = None

HORIZONS = (5, 10, 20, 60)
TABLES = ("opportunity_forward_eval", "theme_forward_eval")


def upgrade() -> None:
    for table in TABLES:
        for horizon in HORIZONS:
            op.add_column(
                table,
                sa.Column(
                    f"delayed_exit_window_mature{horizon}",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                ),
            )


def downgrade() -> None:
    for table in TABLES:
        for horizon in reversed(HORIZONS):
            op.drop_column(table, f"delayed_exit_window_mature{horizon}")
