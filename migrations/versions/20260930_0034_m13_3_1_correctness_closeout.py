"""Close M13.3.1 rebalance input identity correctness.

Revision ID: 0034_m13_3_1_closeout
Revises: 0033_m13_3_rebalance_accounting
"""

import sqlalchemy as sa
from alembic import op

revision = "0034_m13_3_1_closeout"
down_revision = "0033_m13_3_rebalance_accounting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "portfolio_rebalance_plan",
        sa.Column("input_hash", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_portfolio_rebalance_plan_v3_input_hash"),
        "portfolio_rebalance_plan",
        "portfolio_version <> 'portfolio_v3' OR input_hash IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_portfolio_rebalance_plan_v3_input_hash"),
        "portfolio_rebalance_plan",
        type_="check",
    )
    op.drop_column("portfolio_rebalance_plan", "input_hash")
