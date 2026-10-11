"""Normalize the pre-release M16.2.1 request-hash constraint name.

Revision ID: 0049_m16_2_1_hash_name
Revises: 0048_m16_2_1_request_hash
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049_m16_2_1_hash_name"
down_revision: str | None = "0048_m16_2_1_request_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "agent_chat_turn"
_LEGACY_NAME = "ck_agent_chat_turn_ck_agent_chat_turn_request_content_hash"
_CANONICAL_NAME = "ck_agent_chat_turn_request_content_hash"


def upgrade() -> None:
    connection = op.get_bind()
    names = set(
        connection.scalars(
            sa.text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid=to_regclass(:table_name) AND contype='c'"
            ),
            {"table_name": _TABLE},
        )
    )
    if _CANONICAL_NAME in names:
        return
    if _LEGACY_NAME not in names:
        raise RuntimeError("cannot normalize missing M16.2.1 request-hash constraint")
    quote = connection.dialect.identifier_preparer.quote
    op.execute(
        sa.text(
            f"ALTER TABLE {quote(_TABLE)} RENAME CONSTRAINT "
            f"{quote(_LEGACY_NAME)} TO {quote(_CANONICAL_NAME)}"
        )
    )


def downgrade() -> None:
    # The canonical constraint is also the correct 0048 fresh-install schema.
    pass
