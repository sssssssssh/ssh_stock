"""Add M13.2 execution attempts and fill audit fields.

Revision ID: 0031_m13_2_execution_audit
Revises: 0030_m13_1_1_portfolio_integrity
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031_m13_2_execution_audit"
down_revision = "0030_m13_1_1_portfolio_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_order_attempt",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_trade_date", sa.Date(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("requested_quantity", sa.BigInteger(), nullable=False),
        sa.Column(
            "fill_quantity", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column("reference_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("fill_price", sa.Numeric(18, 4), nullable=True),
        sa.Column(
            "gross_amount", sa.Numeric(20, 4), server_default="0", nullable=False
        ),
        sa.Column(
            "commission", sa.Numeric(20, 4), server_default="0", nullable=False
        ),
        sa.Column("stamp_tax", sa.Numeric(20, 4), server_default="0", nullable=False),
        sa.Column(
            "transfer_fee", sa.Numeric(20, 4), server_default="0", nullable=False
        ),
        sa.Column(
            "cash_fee_total", sa.Numeric(20, 4), server_default="0", nullable=False
        ),
        sa.Column(
            "slippage_cost", sa.Numeric(20, 4), server_default="0", nullable=False
        ),
        sa.Column("total_cost", sa.Numeric(20, 4), server_default="0", nullable=False),
        sa.Column(
            "market_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "account_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_no > 0", name=op.f("ck_portfolio_order_attempt_attempt_no")
        ),
        sa.CheckConstraint(
            "outcome IN ('RETRY', 'EXECUTED', 'REJECTED', 'EXPIRED')",
            name=op.f("ck_portfolio_order_attempt_outcome"),
        ),
        sa.CheckConstraint(
            "requested_quantity > 0",
            name=op.f("ck_portfolio_order_attempt_requested_quantity"),
        ),
        sa.CheckConstraint(
            "fill_quantity >= 0",
            name=op.f("ck_portfolio_order_attempt_fill_quantity"),
        ),
        sa.CheckConstraint(
            "fill_quantity <= requested_quantity",
            name=op.f("ck_portfolio_order_attempt_fill_lte_requested"),
        ),
        sa.CheckConstraint(
            "reference_price IS NULL OR reference_price > 0",
            name=op.f("ck_portfolio_order_attempt_reference_price"),
        ),
        sa.CheckConstraint(
            "fill_price IS NULL OR fill_price > 0",
            name=op.f("ck_portfolio_order_attempt_fill_price"),
        ),
        sa.CheckConstraint(
            "gross_amount >= 0",
            name=op.f("ck_portfolio_order_attempt_gross_amount"),
        ),
        sa.CheckConstraint(
            "commission >= 0", name=op.f("ck_portfolio_order_attempt_commission")
        ),
        sa.CheckConstraint(
            "stamp_tax >= 0", name=op.f("ck_portfolio_order_attempt_stamp_tax")
        ),
        sa.CheckConstraint(
            "transfer_fee >= 0",
            name=op.f("ck_portfolio_order_attempt_transfer_fee"),
        ),
        sa.CheckConstraint(
            "cash_fee_total >= 0",
            name=op.f("ck_portfolio_order_attempt_cash_fee_total"),
        ),
        sa.CheckConstraint(
            "slippage_cost >= 0",
            name=op.f("ck_portfolio_order_attempt_slippage_cost"),
        ),
        sa.CheckConstraint(
            "total_cost >= 0", name=op.f("ck_portfolio_order_attempt_total_cost")
        ),
        sa.ForeignKeyConstraint(
            ["order_id", "run_id"],
            ["portfolio_order.id", "portfolio_order.run_id"],
            name=op.f("fk_portfolio_order_attempt_order_run_portfolio_order"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_order_attempt")),
        sa.UniqueConstraint(
            "id", "run_id", name=op.f("uq_portfolio_order_attempt_id_run_id")
        ),
        sa.UniqueConstraint(
            "order_id",
            "attempt_no",
            name=op.f("uq_portfolio_order_attempt_order_no"),
        ),
        sa.UniqueConstraint(
            "order_id",
            "attempt_trade_date",
            name=op.f("uq_portfolio_order_attempt_order_date"),
        ),
    )
    op.create_index(
        "idx_portfolio_order_attempt_run_date",
        "portfolio_order_attempt",
        ["run_id", "attempt_trade_date"],
        unique=False,
    )

    op.add_column(
        "portfolio_fill",
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "portfolio_fill",
        sa.Column("reference_price", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "portfolio_fill",
        sa.Column("transfer_fee", sa.Numeric(20, 4), server_default="0", nullable=False),
    )
    op.add_column(
        "portfolio_fill",
        sa.Column(
            "cash_fee_total", sa.Numeric(20, 4), server_default="0", nullable=False
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE portfolio_fill
            SET reference_price = price,
                transfer_fee = 0,
                cash_fee_total = commission + stamp_tax,
                total_cost = commission + stamp_tax + slippage_cost
            """
        )
    )
    op.alter_column("portfolio_fill", "reference_price", nullable=False)
    op.create_check_constraint(
        op.f("ck_portfolio_fill_transfer_fee"),
        "portfolio_fill",
        "transfer_fee >= 0",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_fill_cash_fee_total"),
        "portfolio_fill",
        "cash_fee_total >= 0",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_fill_cash_fee_components"),
        "portfolio_fill",
        "cash_fee_total = commission + stamp_tax + transfer_fee",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_fill_total_cost_components"),
        "portfolio_fill",
        "total_cost = cash_fee_total + slippage_cost",
    )
    op.create_foreign_key(
        op.f("fk_portfolio_fill_attempt_run_portfolio_order_attempt"),
        "portfolio_fill",
        "portfolio_order_attempt",
        ["attempt_id", "run_id"],
        ["id", "run_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_portfolio_fill_attempt_run_portfolio_order_attempt"),
        "portfolio_fill",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("ck_portfolio_fill_total_cost_components"),
        "portfolio_fill",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_portfolio_fill_cash_fee_components"),
        "portfolio_fill",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_portfolio_fill_cash_fee_total"),
        "portfolio_fill",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_portfolio_fill_transfer_fee"),
        "portfolio_fill",
        type_="check",
    )
    op.drop_column("portfolio_fill", "cash_fee_total")
    op.drop_column("portfolio_fill", "transfer_fee")
    op.drop_column("portfolio_fill", "reference_price")
    op.drop_column("portfolio_fill", "attempt_id")
    op.drop_index(
        "idx_portfolio_order_attempt_run_date",
        table_name="portfolio_order_attempt",
    )
    op.drop_table("portfolio_order_attempt")
