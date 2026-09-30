"""Add M13.4 backtest ownership and phase checkpoints.

Revision ID: 0035_m13_4_backtest_runner
Revises: 0034_m13_3_1_closeout
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035_m13_4_backtest_runner"
down_revision = "0034_m13_3_1_closeout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "portfolio_backtest_run",
        sa.Column("owner_worker_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "portfolio_backtest_run",
        sa.Column(
            "ownership_version",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        op.f("uq_portfolio_backtest_run_job_id"),
        "portfolio_backtest_run",
        ["job_id"],
    )

    op.create_table(
        "portfolio_backtest_checkpoint",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("phase", sa.String(length=24), nullable=False),
        sa.Column("phase_status", sa.String(length=16), nullable=False),
        sa.Column(
            "input_identity",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "result_identity",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=2048), nullable=True),
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("worker_owner", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "phase IN ('START_OF_DAY', 'OPEN', 'CLOSE', 'AFTER_CLOSE', "
            "'DAY_COMPLETED')",
            name=op.f("ck_portfolio_backtest_checkpoint_phase"),
        ),
        sa.CheckConstraint(
            "phase_status IN ('STARTED', 'COMPLETED', 'FAILED')",
            name=op.f("ck_portfolio_backtest_checkpoint_status"),
        ),
        sa.CheckConstraint(
            "attempt > 0",
            name=op.f("ck_portfolio_backtest_checkpoint_attempt"),
        ),
        sa.CheckConstraint(
            "version > 0",
            name=op.f("ck_portfolio_backtest_checkpoint_version"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["portfolio_backtest_run.id"],
            name=op.f(
                "fk_portfolio_backtest_checkpoint_run_id_portfolio_backtest_run"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_portfolio_backtest_checkpoint")
        ),
        sa.UniqueConstraint(
            "run_id",
            "trade_date",
            "phase",
            name=op.f("uq_portfolio_backtest_checkpoint_run_date_phase"),
        ),
    )
    op.create_index(
        "idx_portfolio_backtest_checkpoint_run_status",
        "portfolio_backtest_checkpoint",
        ["run_id", "phase_status", "trade_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_portfolio_backtest_checkpoint_run_status",
        table_name="portfolio_backtest_checkpoint",
    )
    op.drop_table("portfolio_backtest_checkpoint")
    op.drop_constraint(
        op.f("uq_portfolio_backtest_run_job_id"),
        "portfolio_backtest_run",
        type_="unique",
    )
    op.drop_column("portfolio_backtest_run", "ownership_version")
    op.drop_column("portfolio_backtest_run", "owner_worker_id")
