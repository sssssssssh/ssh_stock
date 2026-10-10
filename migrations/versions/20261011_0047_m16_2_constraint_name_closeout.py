"""Normalize M16.2 check-constraint names after the pre-release 0046 draft.

Revision ID: 0047_m16_2_constraint_names
Revises: 0046_m16_2_agent_chat
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047_m16_2_constraint_names"
down_revision: str | None = "0046_m16_2_agent_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RENAMES = (
    (
        "agent_chat_session",
        "ck_agent_chat_session_ck_agent_chat_session_status",
        "ck_agent_chat_session_status",
    ),
    (
        "agent_chat_message",
        "ck_agent_chat_message_ck_agent_chat_message_role",
        "ck_agent_chat_message_role",
    ),
    (
        "agent_chat_message",
        "ck_agent_chat_message_ck_agent_chat_message_status",
        "ck_agent_chat_message_status",
    ),
    (
        "agent_chat_message",
        "ck_agent_chat_message_ck_agent_chat_message_content_length",
        "ck_agent_chat_message_content_length",
    ),
    (
        "agent_chat_message",
        "ck_agent_chat_message_ck_agent_chat_message_sequence_positive",
        "ck_agent_chat_message_sequence_positive",
    ),
    (
        "agent_chat_turn",
        "ck_agent_chat_turn_ck_agent_chat_turn_status",
        "ck_agent_chat_turn_status",
    ),
    (
        "agent_chat_tool_call",
        "ck_agent_chat_tool_call_ck_agent_chat_tool_call_status",
        "ck_agent_chat_tool_call_status",
    ),
    (
        "agent_chat_tool_call",
        "ck_agent_chat_tool_call_ck_agent_chat_tool_call_duration",
        "ck_agent_chat_tool_call_duration",
    ),
)


def upgrade() -> None:
    connection = op.get_bind()
    quote = connection.dialect.identifier_preparer.quote
    for table, legacy_name, canonical_name in _RENAMES:
        names = set(
            connection.scalars(
                sa.text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid=to_regclass(:table_name) AND contype='c'"
                ),
                {"table_name": table},
            )
        )
        if canonical_name in names:
            continue
        if legacy_name not in names:
            raise RuntimeError(
                f"cannot normalize missing M16.2 constraint on {table}"
            )
        op.execute(
            sa.text(
                f"ALTER TABLE {quote(table)} RENAME CONSTRAINT "
                f"{quote(legacy_name)} TO {quote(canonical_name)}"
            )
        )


def downgrade() -> None:
    # 0046's canonical schema already uses the normalized names. Reverting this
    # compatibility repair would intentionally recreate the pre-release defect.
    pass
