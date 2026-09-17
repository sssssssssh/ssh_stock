"""add milestone 10 theme and opportunity tables

Revision ID: 0015_milestone10
Revises: 0014_signal_eval_v2
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_milestone10"
down_revision: str | None = "0014_signal_eval_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.alter_column(
        "data_quality_daily",
        "status",
        existing_type=sa.String(16),
        type_=sa.String(32),
        existing_nullable=False,
    )
    op.create_table(
        "theme",
        sa.Column("theme_code", sa.String(32), primary_key=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("theme_type", sa.String(16), nullable=False),
        sa.Column("exchange", sa.String(16)),
        sa.Column("constituent_count", sa.Integer()),
        sa.Column("list_date", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("first_seen_date", sa.Date()),
        sa.Column("last_seen_date", sa.Date()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "theme_member_snapshot",
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("theme_code", sa.String(32), sa.ForeignKey("theme.theme_code"), nullable=False),
        sa.Column("ts_code", sa.String(16), nullable=False),
        sa.Column("stock_name", sa.String(64)),
        sa.Column("is_new", sa.Boolean()),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("snapshot_date", "theme_code", "ts_code"),
    )
    op.create_index(
        "idx_theme_member_stock_snapshot",
        "theme_member_snapshot",
        ["ts_code", "snapshot_date"],
    )
    daily_columns = [
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("theme_code", sa.String(32), sa.ForeignKey("theme.theme_code"), nullable=False),
    ]
    op.create_table(
        "theme_daily",
        *daily_columns,
        *[sa.Column(name, sa.Float()) for name in (
            "open", "high", "low", "close", "pre_close", "avg_price", "change",
            "pct_change", "vol", "turnover_rate", "total_mv",
        )],
        *_timestamps(),
        sa.PrimaryKeyConstraint("trade_date", "theme_code"),
    )
    op.create_index("idx_theme_daily_code_date", "theme_daily", ["theme_code", "trade_date"])
    op.create_table(
        "theme_moneyflow_daily",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("theme_code", sa.String(32), sa.ForeignKey("theme.theme_code"), nullable=False),
        sa.Column("name", sa.String(128)),
        sa.Column("lead_stock", sa.String(64)),
        *[sa.Column(name, sa.Float()) for name in (
            "close_price", "pct_change", "theme_index", "company_num",
            "lead_stock_pct_change", "net_buy_amount", "net_sell_amount", "net_amount",
        )],
        *_timestamps(),
        sa.PrimaryKeyConstraint("trade_date", "theme_code"),
    )
    op.create_table(
        "theme_limit_daily",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("theme_code", sa.String(32), sa.ForeignKey("theme.theme_code"), nullable=False),
        sa.Column("name", sa.String(128)),
        sa.Column("days", sa.Integer()),
        sa.Column("up_stat", sa.String(64)),
        sa.Column("cons_nums", sa.Integer()),
        sa.Column("up_nums", sa.Integer()),
        sa.Column("pct_chg", sa.Float()),
        sa.Column("hot_rank", sa.Integer()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("trade_date", "theme_code"),
    )
    op.create_table(
        "theme_factor_daily",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("theme_code", sa.String(32), sa.ForeignKey("theme.theme_code"), nullable=False),
        sa.Column("member_snapshot_date", sa.Date()),
        sa.Column("member_count", sa.Integer()),
        sa.Column("eligible_member_count", sa.Integer()),
        *[sa.Column(name, sa.Float()) for name in (
            "return1", "return3", "return5", "return20", "excess_return5",
            "excess_return20", "breadth20", "breadth60", "up_rate",
            "new_high20_rate", "rps60_median", "turnover_rate", "turnover_ratio20",
            "net_amount", "net_amount_3d", "net_amount_per_member", "moneyflow_score",
            "limit_up_density", "continuous_limit_density", "limit_strength_score",
            "heat_score", "heat_momentum1", "heat_momentum3", "data_coverage",
        )],
        sa.Column("limit_up_count", sa.Integer()),
        sa.Column("continuous_limit_count", sa.Integer()),
        sa.Column("hot_list_days", sa.Integer()),
        sa.Column("hot_rank", sa.Integer()),
        sa.Column("heat_rank", sa.Integer()),
        sa.Column("rank_change", sa.Integer()),
        sa.Column("lifecycle", sa.String(32)),
        sa.Column("calc_version", sa.String(32), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("calc_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("trade_date", "theme_code"),
    )
    op.create_index("idx_theme_factor_date_rank", "theme_factor_daily", ["trade_date", "heat_rank"])
    op.create_table(
        "stock_opportunity_daily",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(16), nullable=False),
        sa.Column("algo_version", sa.String(32), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("previous_state", sa.String(16)),
        sa.Column("state_day_count", sa.Integer()),
        *[sa.Column(name, sa.Float()) for name in (
            "left_reversal_score", "right_side_score", "trend_score", "trend_rank_score",
            "position_score", "market_score", "industry_heat", "primary_theme_heat",
            "context_score", "opportunity_score",
        )],
        sa.Column("left_reversal_new", sa.Boolean(), nullable=False),
        sa.Column("extension_risk", sa.String(16)),
        sa.Column("industry_sector_id", sa.Integer()),
        sa.Column("industry_lifecycle", sa.String(32)),
        sa.Column("primary_theme_code", sa.String(32)),
        sa.Column("primary_theme_name", sa.String(128)),
        sa.Column("primary_theme_lifecycle", sa.String(32)),
        sa.Column("hot_theme_count", sa.Integer()),
        sa.Column("opportunity_stage", sa.String(32), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB()),
        sa.Column("calc_version", sa.String(32), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("calc_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("trade_date", "ts_code", "algo_version"),
    )
    op.create_index(
        "idx_opportunity_date_stage_score",
        "stock_opportunity_daily",
        ["trade_date", "opportunity_stage", "opportunity_score"],
    )


def downgrade() -> None:
    op.drop_index("idx_opportunity_date_stage_score", table_name="stock_opportunity_daily")
    op.drop_table("stock_opportunity_daily")
    op.drop_index("idx_theme_factor_date_rank", table_name="theme_factor_daily")
    op.drop_table("theme_factor_daily")
    op.drop_table("theme_limit_daily")
    op.drop_table("theme_moneyflow_daily")
    op.drop_index("idx_theme_daily_code_date", table_name="theme_daily")
    op.drop_table("theme_daily")
    op.drop_index("idx_theme_member_stock_snapshot", table_name="theme_member_snapshot")
    op.drop_table("theme_member_snapshot")
    op.drop_table("theme")
    op.execute(
        sa.text(
            "DELETE FROM data_quality_daily WHERE dataset IN "
            "('ths_theme_catalog', 'ths_theme_member_snapshot', 'ths_theme_daily', "
            "'ths_theme_moneyflow', 'ths_theme_limit')"
        )
    )
    op.alter_column(
        "data_quality_daily",
        "status",
        existing_type=sa.String(32),
        type_=sa.String(16),
        existing_nullable=False,
    )
