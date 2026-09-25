"""Persist auditable final-exit status semantics.

Revision ID: 0027_m12_8_2_final_exit
Revises: 0026_m12_8_1_closeout
"""

import sqlalchemy as sa
from alembic import op

revision = "0027_m12_8_2_final_exit"
down_revision = "0026_m12_8_1_closeout"
branch_labels = None
depends_on = None

HORIZONS = (5, 10, 20, 60)
TABLES = ("opportunity_forward_eval", "theme_forward_eval")


def upgrade() -> None:
    for table in TABLES:
        for horizon in HORIZONS:
            op.add_column(
                table,
                sa.Column(f"final_exit_status{horizon}", sa.String(24), nullable=True),
            )


def downgrade() -> None:
    for table in TABLES:
        for horizon in reversed(HORIZONS):
            op.drop_column(table, f"final_exit_status{horizon}")
