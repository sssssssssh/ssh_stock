"""Keep Transition research rows separate across calculation versions.

Revision ID: 0020_transition_calc_lineage
Revises: 0019_research_source_lineage
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_transition_calc_lineage"
down_revision: str | None = "0019_research_source_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "research_transition_eval"
CONSTRAINT = "uq_research_transition_identity"
OLD_KEY = (
    "event_trade_date", "ts_code", "event_key", "algo_version",
    "strategy_config_hash", "opportunity_config_hash",
    "research_version", "research_config_hash",
)
NEW_KEY = OLD_KEY[:4] + ("trend_calc_version", "opportunity_calc_version") + OLD_KEY[4:]


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("opportunity_calc_version", sa.String(32)))
    table = sa.table(TABLE, sa.column("opportunity_calc_version", sa.String(32)))
    op.execute(table.update().values(opportunity_calc_version="legacy-unverified"))
    op.alter_column(TABLE, "opportunity_calc_version", nullable=False)
    op.drop_constraint(CONSTRAINT, TABLE, type_="unique")
    op.create_unique_constraint(CONSTRAINT, TABLE, NEW_KEY)


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, type_="unique")
    op.create_unique_constraint(CONSTRAINT, TABLE, OLD_KEY)
    op.drop_column(TABLE, "opportunity_calc_version")
