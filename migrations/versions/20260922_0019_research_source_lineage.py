"""Record source strategy lineage on Production opportunity and theme factors.

Revision ID: 0019_research_source_lineage
Revises: 0018_research_closeout
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_research_source_lineage"
down_revision: str | None = "0018_research_closeout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLES = ("stock_opportunity_daily", "theme_factor_daily")


def upgrade() -> None:
    for name in TABLES:
        op.add_column(name, sa.Column("source_strategy_config_hash", sa.String(64)))
        table = sa.table(name, sa.column("source_strategy_config_hash", sa.String(64)))
        op.execute(table.update().values(source_strategy_config_hash="legacy-unverified"))
        op.alter_column(name, "source_strategy_config_hash", nullable=False)


def downgrade() -> None:
    for name in TABLES:
        op.drop_column(name, "source_strategy_config_hash")
