"""add data reliability metadata

Revision ID: 0007_data_reliability
Revises: 0006_signal_forward_eval
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_data_reliability"
down_revision: str | None = "0006_signal_forward_eval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_quality_daily",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("dataset", sa.String(length=64), nullable=False),
        sa.Column("expected_rows", sa.Integer(), nullable=True),
        sa.Column("actual_rows", sa.Integer(), nullable=True),
        sa.Column("coverage_rate", sa.Float(), nullable=True),
        sa.Column("missing_count", sa.Integer(), nullable=True),
        sa.Column("duplicate_count", sa.Integer(), nullable=True),
        sa.Column("null_count", sa.Integer(), nullable=True),
        sa.Column("warning_count", sa.Integer(), nullable=True),
        sa.Column("error_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("issue_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_quality_daily")),
        sa.UniqueConstraint("trade_date", "dataset", name="uq_data_quality_daily_dataset_date"),
    )
    op.create_index(
        "idx_data_quality_daily_date_status",
        "data_quality_daily",
        ["trade_date", "status"],
    )

    op.create_table(
        "data_dirty_range",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dataset", sa.String(length=64), nullable=False),
        sa.Column("dirty_start_date", sa.Date(), nullable=False),
        sa.Column("dirty_end_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=256), nullable=True),
        sa.Column("source_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_dirty_range")),
    )
    op.create_index(
        "idx_data_dirty_range_status_start",
        "data_dirty_range",
        ["status", "dirty_start_date"],
    )

    for table_name in ("stock_factor_daily", "market_daily", "sector_factor_daily"):
        op.add_column(table_name, sa.Column("calc_version", sa.String(length=32), nullable=True))
        op.add_column(table_name, sa.Column("config_hash", sa.String(length=64), nullable=True))
        op.add_column(
            table_name,
            sa.Column("calc_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    for table_name in ("sector_factor_daily", "market_daily", "stock_factor_daily"):
        op.drop_column(table_name, "calculated_at")
        op.drop_column(table_name, "calc_run_id")
        op.drop_column(table_name, "config_hash")
        op.drop_column(table_name, "calc_version")

    op.drop_index("idx_data_dirty_range_status_start", table_name="data_dirty_range")
    op.drop_table("data_dirty_range")
    op.drop_index("idx_data_quality_daily_date_status", table_name="data_quality_daily")
    op.drop_table("data_quality_daily")
