"""Add deterministic rebalance plans and portfolio accounting identity.

Revision ID: 0033_m13_3_rebalance_accounting
Revises: 0032_m13_2_1_execution_integrity
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0033_m13_3_rebalance_accounting"
down_revision = "0032_m13_2_1_execution_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    legacy_order_count = int(
        connection.scalar(
            sa.text(
                "SELECT count(*) FROM portfolio_order "
                "WHERE order_type = 'MARKET_ON_OPEN'"
            )
        )
        or 0
    )
    if legacy_order_count:
        raise RuntimeError(
            "cannot enforce NEXT_OPEN-only portfolio orders: "
            f"found {legacy_order_count} MARKET_ON_OPEN order(s)"
        )

    op.add_column(
        "portfolio_backtest_run",
        sa.Column(
            "accounting_version",
            sa.String(length=32),
            server_default="accounting_v0_unimplemented",
            nullable=False,
        ),
    )
    op.add_column(
        "portfolio_backtest_run",
        sa.Column(
            "accounting_config_hash",
            sa.String(length=64),
            server_default="UNAVAILABLE",
            nullable=False,
        ),
    )

    op.create_table(
        "portfolio_rebalance_plan",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_trade_date", sa.Date(), nullable=False),
        sa.Column("scheduled_trade_date", sa.Date(), nullable=False),
        sa.Column("total_assets", sa.Numeric(20, 4), nullable=False),
        sa.Column("portfolio_version", sa.String(length=32), nullable=False),
        sa.Column(
            "target_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "account_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "plan_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["portfolio_backtest_run.id"],
            name=op.f("fk_portfolio_rebalance_plan_run_id_portfolio_backtest_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_rebalance_plan")),
        sa.UniqueConstraint(
            "run_id",
            "signal_trade_date",
            name=op.f("uq_portfolio_rebalance_plan_run_signal_date"),
        ),
        sa.UniqueConstraint(
            "id",
            "run_id",
            name=op.f("uq_portfolio_rebalance_plan_id_run_id"),
        ),
    )

    op.add_column(
        "portfolio_order",
        sa.Column("rebalance_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "portfolio_order", sa.Column("child_index", sa.Integer(), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_portfolio_order_child_index"),
        "portfolio_order",
        "child_index IS NULL OR child_index > 0",
    )
    op.create_check_constraint(
        op.f("ck_portfolio_order_plan_child_pair"),
        "portfolio_order",
        "(rebalance_plan_id IS NULL AND child_index IS NULL) OR "
        "(rebalance_plan_id IS NOT NULL AND child_index IS NOT NULL)",
    )
    op.create_foreign_key(
        op.f("fk_portfolio_order_plan_run_portfolio_rebalance_plan"),
        "portfolio_order",
        "portfolio_rebalance_plan",
        ["rebalance_plan_id", "run_id"],
        ["id", "run_id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        op.f("uq_portfolio_order_plan_code_side_child"),
        "portfolio_order",
        ["rebalance_plan_id", "ts_code", "side", "child_index"],
    )
    op.drop_constraint(
        op.f("ck_portfolio_order_type"), "portfolio_order", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_portfolio_order_type"),
        "portfolio_order",
        "order_type = 'NEXT_OPEN'",
    )

    op.alter_column(
        "portfolio_position_daily",
        "avg_cost",
        existing_type=sa.Numeric(18, 4),
        type_=sa.Numeric(20, 8),
        existing_nullable=False,
    )
    op.add_column(
        "portfolio_position_daily",
        sa.Column("valuation_source", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "portfolio_position_daily",
        sa.Column("adj_factor", sa.Numeric(24, 10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("portfolio_position_daily", "adj_factor")
    op.drop_column("portfolio_position_daily", "valuation_source")
    op.alter_column(
        "portfolio_position_daily",
        "avg_cost",
        existing_type=sa.Numeric(20, 8),
        type_=sa.Numeric(18, 4),
        existing_nullable=False,
    )

    op.drop_constraint(
        op.f("ck_portfolio_order_type"), "portfolio_order", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_portfolio_order_type"),
        "portfolio_order",
        "order_type IN ('NEXT_OPEN', 'MARKET_ON_OPEN')",
    )
    op.drop_constraint(
        op.f("uq_portfolio_order_plan_code_side_child"),
        "portfolio_order",
        type_="unique",
    )
    op.drop_constraint(
        op.f("fk_portfolio_order_plan_run_portfolio_rebalance_plan"),
        "portfolio_order",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("ck_portfolio_order_child_index"),
        "portfolio_order",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_portfolio_order_plan_child_pair"),
        "portfolio_order",
        type_="check",
    )
    op.drop_column("portfolio_order", "child_index")
    op.drop_column("portfolio_order", "rebalance_plan_id")
    op.drop_table("portfolio_rebalance_plan")
    op.drop_column("portfolio_backtest_run", "accounting_config_hash")
    op.drop_column("portfolio_backtest_run", "accounting_version")
