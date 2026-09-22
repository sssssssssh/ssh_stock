"""Add row-level research validation results.

Revision ID: 0017_milestone11_research
Revises: 0016_theme_closeout
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_milestone11_research"
down_revision: str | None = "0016_theme_closeout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _forward_columns() -> list[sa.Column]:
    columns = [
        sa.Column("entry_trade_date", sa.Date()),
        sa.Column("entry_price", sa.Float()),
        sa.Column("entry_executable", sa.Boolean()),
        sa.Column("entry_reason", sa.String(32)),
        sa.Column("evaluated_until_date", sa.Date()),
    ]
    for horizon in (5, 10, 20, 60):
        columns.extend(
            [
                sa.Column(f"mature{horizon}", sa.Boolean(), nullable=False),
                sa.Column(f"exit_trade_date{horizon}", sa.Date()),
                sa.Column(f"exit_executable{horizon}", sa.Boolean()),
                sa.Column(f"exit_reason{horizon}", sa.String(32)),
                sa.Column(f"ret{horizon}", sa.Float()),
                sa.Column(f"benchmark_ret{horizon}", sa.Float()),
                sa.Column(f"excess_ret{horizon}", sa.Float()),
            ]
        )
    columns.extend(
        [
            sa.Column("mfe20", sa.Float()),
            sa.Column("mae20", sa.Float()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        ]
    )
    return columns


def upgrade() -> None:
    op.create_table(
        "opportunity_forward_eval",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(16), nullable=False),
        sa.Column("algo_version", sa.String(32), nullable=False),
        sa.Column("opportunity_calc_version", sa.String(32), nullable=False),
        sa.Column("opportunity_config_hash", sa.String(64), nullable=False),
        sa.Column("research_version", sa.String(32), nullable=False),
        sa.Column("research_config_hash", sa.String(64), nullable=False),
        sa.Column("eval_version", sa.String(32), nullable=False),
        sa.Column("entry_basis", sa.String(16), nullable=False),
        sa.Column("benchmark_code", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("previous_state", sa.String(16)),
        sa.Column("state_day_count", sa.Integer()),
        sa.Column("opportunity_stage", sa.String(32), nullable=False),
        sa.Column("left_reversal_score", sa.Float()),
        sa.Column("left_reversal_new", sa.Boolean()),
        sa.Column("right_side_score", sa.Float()),
        sa.Column("trend_score", sa.Float()),
        sa.Column("trend_rank_score", sa.Float()),
        sa.Column("position_score", sa.Float()),
        sa.Column("extension_risk", sa.String(16)),
        sa.Column("opportunity_score", sa.Float()),
        sa.Column("context_score", sa.Float()),
        sa.Column("market_score", sa.Float()),
        sa.Column("market_regime", sa.String(32)),
        sa.Column("industry_sector_id", sa.Integer()),
        sa.Column("industry_heat", sa.Float()),
        sa.Column("industry_lifecycle", sa.String(32)),
        sa.Column("primary_theme_code", sa.String(32)),
        sa.Column("primary_theme_heat", sa.Float()),
        sa.Column("primary_theme_lifecycle", sa.String(32)),
        sa.Column("hot_theme_count", sa.Integer()),
        *_forward_columns(),
        sa.UniqueConstraint(
            "trade_date",
            "ts_code",
            "algo_version",
            "opportunity_config_hash",
            "research_version",
            "research_config_hash",
            "eval_version",
            "entry_basis",
            name="uq_opportunity_forward_eval_identity",
        ),
    )
    op.create_index(
        "idx_opp_eval_date_stage", "opportunity_forward_eval", ["trade_date", "opportunity_stage"]
    )
    op.create_index(
        "idx_opp_eval_stage_rank",
        "opportunity_forward_eval",
        ["opportunity_stage", "trend_rank_score"],
    )
    op.create_index(
        "idx_opp_eval_risk_date", "opportunity_forward_eval", ["extension_risk", "trade_date"]
    )
    op.create_index(
        "idx_opp_eval_regime_date", "opportunity_forward_eval", ["market_regime", "trade_date"]
    )

    op.create_table(
        "theme_forward_eval",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("theme_code", sa.String(32), nullable=False),
        sa.Column("theme_calc_version", sa.String(32), nullable=False),
        sa.Column("opportunity_config_hash", sa.String(64), nullable=False),
        sa.Column("research_version", sa.String(32), nullable=False),
        sa.Column("research_config_hash", sa.String(64), nullable=False),
        sa.Column("eval_version", sa.String(32), nullable=False),
        sa.Column("entry_basis", sa.String(16), nullable=False),
        sa.Column("benchmark_code", sa.String(16), nullable=False),
        sa.Column("heat_score", sa.Float()),
        sa.Column("heat_rank", sa.Integer()),
        sa.Column("heat_momentum1", sa.Float()),
        sa.Column("heat_momentum3", sa.Float()),
        sa.Column("rank_change", sa.Integer()),
        sa.Column("lifecycle", sa.String(32)),
        sa.Column("return1", sa.Float()),
        sa.Column("return5", sa.Float()),
        sa.Column("return20", sa.Float()),
        sa.Column("moneyflow_score", sa.Float()),
        sa.Column("net_amount", sa.Float()),
        sa.Column("net_amount_3d", sa.Float()),
        sa.Column("limit_strength_score", sa.Float()),
        sa.Column("limit_up_count", sa.Integer()),
        sa.Column("continuous_limit_count", sa.Integer()),
        sa.Column("breadth20", sa.Float()),
        sa.Column("breadth60", sa.Float()),
        sa.Column("rps60_median", sa.Float()),
        sa.Column("source_coverage", sa.Float()),
        sa.Column("data_coverage", sa.Float()),
        *_forward_columns(),
        sa.UniqueConstraint(
            "trade_date",
            "theme_code",
            "opportunity_config_hash",
            "research_version",
            "research_config_hash",
            "eval_version",
            "entry_basis",
            name="uq_theme_forward_eval_identity",
        ),
    )
    op.create_index("idx_theme_eval_date_rank", "theme_forward_eval", ["trade_date", "heat_rank"])
    op.create_index(
        "idx_theme_eval_lifecycle_date", "theme_forward_eval", ["lifecycle", "trade_date"]
    )

    transition_columns = [
        sa.Column("mature5", sa.Boolean(), nullable=False),
        sa.Column("mature10", sa.Boolean(), nullable=False),
        sa.Column("mature20", sa.Boolean(), nullable=False),
        sa.Column("state5", sa.String(16)),
        sa.Column("state10", sa.String(16)),
        sa.Column("state20", sa.String(16)),
        sa.Column("days_to_s3", sa.Integer()),
        sa.Column("days_to_s4plus", sa.Integer()),
        sa.Column("days_to_s5", sa.Integer()),
    ]
    for target in ("s3", "s4plus", "s5"):
        for horizon in (5, 10, 20):
            transition_columns.append(sa.Column(f"reached_{target}_{horizon}", sa.Boolean()))
    transition_columns.extend(
        [
            sa.Column("hit_s0_20", sa.Boolean()),
            sa.Column("hit_s6_20", sa.Boolean()),
            sa.Column("fell_below_s3_20", sa.Boolean()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        ]
    )
    op.create_table(
        "research_transition_eval",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_trade_date", sa.Date(), nullable=False),
        sa.Column("ts_code", sa.String(16), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("event_key", sa.String(32), nullable=False),
        sa.Column("threshold_value", sa.Float()),
        sa.Column("source_state", sa.String(16), nullable=False),
        sa.Column("source_score", sa.Float()),
        sa.Column("algo_version", sa.String(32), nullable=False),
        sa.Column("trend_calc_version", sa.String(32), nullable=False),
        sa.Column("strategy_config_hash", sa.String(64), nullable=False),
        sa.Column("opportunity_config_hash", sa.String(64), nullable=False),
        sa.Column("research_version", sa.String(32), nullable=False),
        sa.Column("research_config_hash", sa.String(64), nullable=False),
        *transition_columns,
        sa.UniqueConstraint(
            "event_trade_date",
            "ts_code",
            "event_key",
            "algo_version",
            "strategy_config_hash",
            "opportunity_config_hash",
            "research_version",
            "research_config_hash",
            name="uq_research_transition_identity",
        ),
    )
    op.create_index(
        "idx_transition_key_date", "research_transition_eval", ["event_key", "event_trade_date"]
    )
    op.create_index(
        "idx_transition_type_threshold",
        "research_transition_eval",
        ["event_type", "threshold_value"],
    )


def downgrade() -> None:
    op.drop_table("research_transition_eval")
    op.drop_table("theme_forward_eval")
    op.drop_table("opportunity_forward_eval")
