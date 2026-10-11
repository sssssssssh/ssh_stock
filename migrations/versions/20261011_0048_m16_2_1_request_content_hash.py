"""Bind new M16.2.1 turns to normalized request content.

Revision ID: 0048_m16_2_1_request_hash
Revises: 0047_m16_2_constraint_names
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_m16_2_1_request_hash"
down_revision: str | None = "0047_m16_2_constraint_names"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Historical turns intentionally remain NULL: their original normalized
    # request contract cannot be reconstructed safely after the fact.
    op.add_column(
        "agent_chat_turn",
        sa.Column("request_content_hash", sa.String(64), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_agent_chat_turn_request_content_hash"),
        "agent_chat_turn",
        "request_content_hash IS NULL OR request_content_hash ~ '^[0-9a-f]{64}$'",
    )


def downgrade() -> None:
    # This removes only the replay guard. Messages, turns, Evidence references,
    # and tool audit history remain intact.
    op.drop_constraint(
        op.f("ck_agent_chat_turn_request_content_hash"),
        "agent_chat_turn",
        type_="check",
    )
    op.drop_column("agent_chat_turn", "request_content_hash")
