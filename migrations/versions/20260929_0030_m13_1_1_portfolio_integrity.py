"""Close M13.1 portfolio time-source-ledger integrity gaps.

Revision ID: 0030_m13_1_1_portfolio_integrity
Revises: 0029_m13_1_portfolio_foundation
"""

import sqlalchemy as sa
from alembic import op

revision = "0030_m13_1_1_portfolio_integrity"
down_revision = "0029_m13_1_portfolio_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    mismatch_count = connection.scalar(
        sa.text(
            """
            SELECT count(*)
            FROM portfolio_fill AS fill
            JOIN portfolio_order AS orders ON orders.id = fill.order_id
            WHERE fill.run_id <> orders.run_id
            """
        )
    )
    if mismatch_count:
        raise RuntimeError(
            "cannot add portfolio fill/order composite foreign key: "
            f"found {mismatch_count} historical cross-run fill(s)"
        )

    op.create_unique_constraint(
        op.f("uq_portfolio_order_id_run_id"),
        "portfolio_order",
        ["id", "run_id"],
    )
    op.drop_constraint(
        op.f("fk_portfolio_fill_order_id_portfolio_order"),
        "portfolio_fill",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_portfolio_fill_order_run_portfolio_order"),
        "portfolio_fill",
        "portfolio_order",
        ["order_id", "run_id"],
        ["id", "run_id"],
        ondelete="CASCADE",
    )

    op.drop_constraint(
        op.f("ck_portfolio_order_target_weight"),
        "portfolio_order",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_order_target_weight"),
        "portfolio_order",
        "target_weight IS NULL OR (target_weight >= 0 AND target_weight <= 1)",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_position_available_lte_quantity"),
        "portfolio_position_daily",
        "available_quantity <= quantity",
    )
    op.drop_constraint(
        op.f("ck_portfolio_position_weight"),
        "portfolio_position_daily",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_position_weight"),
        "portfolio_position_daily",
        "weight >= 0 AND weight <= 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_portfolio_position_weight"),
        "portfolio_position_daily",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_position_weight"),
        "portfolio_position_daily",
        "weight >= 0",
    )
    op.drop_constraint(
        op.f("ck_portfolio_position_available_lte_quantity"),
        "portfolio_position_daily",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_portfolio_order_target_weight"),
        "portfolio_order",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_order_target_weight"),
        "portfolio_order",
        "target_weight IS NULL OR target_weight >= 0",
    )

    op.drop_constraint(
        op.f("fk_portfolio_fill_order_run_portfolio_order"),
        "portfolio_fill",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_portfolio_fill_order_id_portfolio_order"),
        "portfolio_fill",
        "portfolio_order",
        ["order_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        op.f("uq_portfolio_order_id_run_id"),
        "portfolio_order",
        type_="unique",
    )
