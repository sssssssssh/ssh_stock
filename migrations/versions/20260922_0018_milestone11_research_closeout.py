"""Preserve research results across production strategy versions.

Revision ID: 0018_research_closeout
Revises: 0017_milestone11_research
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_research_closeout"
down_revision: str | None = "0017_milestone11_research"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_IDENTITIES = {
    "opportunity_forward_eval": (
        "trade_date", "ts_code", "algo_version", "strategy_config_hash",
        "opportunity_calc_version", "opportunity_config_hash", "research_version",
        "research_config_hash", "eval_version", "entry_basis",
    ),
    "theme_forward_eval": (
        "trade_date", "theme_code", "strategy_config_hash", "theme_calc_version",
        "opportunity_config_hash", "research_version", "research_config_hash",
        "eval_version", "entry_basis",
    ),
}


def upgrade() -> None:
    for table, columns in _IDENTITIES.items():
        op.add_column(table, sa.Column("strategy_config_hash", sa.String(64)))
        # The prior schema did not record the source strategy. Never attribute old rows
        # to the currently deployed strategy without evidence; reruns create verified rows.
        table_ref = sa.table(table, sa.column("strategy_config_hash", sa.String(64)))
        op.execute(table_ref.update().values(strategy_config_hash="legacy-unverified"))
        op.alter_column(table, "strategy_config_hash", nullable=False)
        constraint = f"uq_{table}_identity"
        op.drop_constraint(constraint, table, type_="unique")
        op.create_unique_constraint(constraint, table, list(columns))


def downgrade() -> None:
    for table, columns in _IDENTITIES.items():
        constraint = f"uq_{table}_identity"
        old = tuple(column for column in columns if column not in {
            "strategy_config_hash", "opportunity_calc_version", "theme_calc_version"
        })
        op.drop_constraint(constraint, table, type_="unique")
        op.create_unique_constraint(constraint, table, list(old))
        op.drop_column(table, "strategy_config_hash")
