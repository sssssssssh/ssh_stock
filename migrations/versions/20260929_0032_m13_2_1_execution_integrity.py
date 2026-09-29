"""Close M13.2 execution quantity and attempt integrity gaps.

Revision ID: 0032_m13_2_1_execution_integrity
Revises: 0031_m13_2_execution_audit
"""

import sqlalchemy as sa
from alembic import op

revision = "0032_m13_2_1_execution_integrity"
down_revision = "0031_m13_2_execution_audit"
branch_labels = None
depends_on = None

_ATTEMPT_CONSISTENCY_PREDICATE = """
    requested_quantity >= 0
    AND (
        requested_quantity > 0
        OR (
            requested_quantity = 0
            AND outcome = 'REJECTED'
            AND reason_code = 'INVALID_QUANTITY'
        )
    )
    AND (
        (outcome = 'EXECUTED' AND reason_code IS NULL)
        OR (outcome <> 'EXECUTED' AND reason_code IS NOT NULL)
    )
    AND (
        outcome <> 'EXECUTED'
        OR (
            fill_quantity = requested_quantity
            AND requested_quantity > 0
            AND reference_price IS NOT NULL
            AND fill_price IS NOT NULL
            AND gross_amount > 0
        )
    )
    AND (
        outcome = 'EXECUTED'
        OR (
            fill_quantity = 0
            AND fill_price IS NULL
            AND gross_amount = 0
            AND commission = 0
            AND stamp_tax = 0
            AND transfer_fee = 0
            AND cash_fee_total = 0
            AND slippage_cost = 0
            AND total_cost = 0
        )
    )
    AND cash_fee_total = commission + stamp_tax + transfer_fee
    AND total_cost = cash_fee_total + slippage_cost
"""


def _count(connection, query: str) -> int:
    return int(connection.scalar(sa.text(query)) or 0)


def upgrade() -> None:
    connection = op.get_bind()
    zero_order_count = _count(
        connection,
        "SELECT count(*) FROM portfolio_order WHERE target_quantity = 0",
    )
    if zero_order_count:
        raise RuntimeError(
            "cannot enforce positive portfolio order target quantity: "
            f"found {zero_order_count} order(s) with target_quantity = 0"
        )

    invalid_attempt_count = _count(
        connection,
        "SELECT count(*) FROM portfolio_order_attempt "
        f"WHERE ({_ATTEMPT_CONSISTENCY_PREDICATE}) IS NOT TRUE",
    )
    if invalid_attempt_count:
        raise RuntimeError(
            "cannot enforce portfolio order attempt consistency: "
            f"found {invalid_attempt_count} violating historical attempt(s)"
        )

    op.drop_constraint(
        op.f("ck_portfolio_order_target_quantity"),
        "portfolio_order",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_order_target_quantity"),
        "portfolio_order",
        "target_quantity IS NULL OR target_quantity > 0",
    )

    op.drop_constraint(
        op.f("ck_portfolio_order_attempt_requested_quantity"),
        "portfolio_order_attempt",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_order_attempt_requested_quantity"),
        "portfolio_order_attempt",
        "requested_quantity >= 0",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_order_attempt_quantity_validity"),
        "portfolio_order_attempt",
        "requested_quantity > 0 OR "
        "(requested_quantity = 0 AND outcome = 'REJECTED' "
        "AND reason_code = 'INVALID_QUANTITY')",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_order_attempt_outcome_reason"),
        "portfolio_order_attempt",
        "(outcome = 'EXECUTED' AND reason_code IS NULL) OR "
        "(outcome <> 'EXECUTED' AND reason_code IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_order_attempt_executed_consistency"),
        "portfolio_order_attempt",
        "outcome <> 'EXECUTED' OR "
        "(fill_quantity = requested_quantity AND requested_quantity > 0 "
        "AND reference_price IS NOT NULL AND fill_price IS NOT NULL "
        "AND gross_amount > 0)",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_order_attempt_non_executed_consistency"),
        "portfolio_order_attempt",
        "outcome = 'EXECUTED' OR "
        "(fill_quantity = 0 AND fill_price IS NULL AND gross_amount = 0 "
        "AND commission = 0 AND stamp_tax = 0 AND transfer_fee = 0 "
        "AND cash_fee_total = 0 AND slippage_cost = 0 AND total_cost = 0)",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_order_attempt_cash_fee_components"),
        "portfolio_order_attempt",
        "cash_fee_total = commission + stamp_tax + transfer_fee",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_order_attempt_total_cost_components"),
        "portfolio_order_attempt",
        "total_cost = cash_fee_total + slippage_cost",
    )


def downgrade() -> None:
    connection = op.get_bind()
    zero_attempt_count = _count(
        connection,
        "SELECT count(*) FROM portfolio_order_attempt WHERE requested_quantity = 0",
    )
    if zero_attempt_count:
        raise RuntimeError(
            "cannot downgrade execution integrity migration: "
            f"found {zero_attempt_count} attempt(s) with requested_quantity = 0"
        )

    for constraint_name in (
        "ck_portfolio_order_attempt_total_cost_components",
        "ck_portfolio_order_attempt_cash_fee_components",
        "ck_portfolio_order_attempt_non_executed_consistency",
        "ck_portfolio_order_attempt_executed_consistency",
        "ck_portfolio_order_attempt_outcome_reason",
        "ck_portfolio_order_attempt_quantity_validity",
    ):
        op.drop_constraint(
            op.f(constraint_name),
            "portfolio_order_attempt",
            type_="check",
        )

    op.drop_constraint(
        op.f("ck_portfolio_order_attempt_requested_quantity"),
        "portfolio_order_attempt",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_order_attempt_requested_quantity"),
        "portfolio_order_attempt",
        "requested_quantity > 0",
    )

    op.drop_constraint(
        op.f("ck_portfolio_order_target_quantity"),
        "portfolio_order",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_order_target_quantity"),
        "portfolio_order",
        "target_quantity IS NULL OR target_quantity >= 0",
    )
