"""Add M16.2 evidence-backed Agent chat persistence.

Revision ID: 0046_m16_2_agent_chat
Revises: 0045_m15_3_2_validation_identity
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0046_m16_2_agent_chat"
down_revision: str | None = "0045_m15_3_2_validation_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_chat_session",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')",
            name=op.f("ck_agent_chat_session_status"),
        ),
    )
    op.create_index(
        "idx_agent_chat_session_owner_updated",
        "agent_chat_session",
        ["owner_user_id", "updated_at"],
    )

    op.create_table(
        "agent_chat_message",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_chat_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="COMPLETED"),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "role IN ('USER', 'ASSISTANT')",
            name=op.f("ck_agent_chat_message_role"),
        ),
        sa.CheckConstraint(
            "status IN ('COMPLETED', 'FAILED')",
            name=op.f("ck_agent_chat_message_status"),
        ),
        sa.CheckConstraint(
            "char_length(content) BETWEEN 1 AND 16000",
            name=op.f("ck_agent_chat_message_content_length"),
        ),
        sa.CheckConstraint(
            "sequence_no > 0",
            name=op.f("ck_agent_chat_message_sequence_positive"),
        ),
        sa.UniqueConstraint(
            "session_id", "sequence_no", name="uq_agent_chat_message_sequence"
        ),
        sa.UniqueConstraint("id", "session_id", name="uq_agent_chat_message_owner"),
    )
    op.create_index(
        "idx_agent_chat_message_session_created",
        "agent_chat_message",
        ["session_id", "created_at"],
    )

    op.create_table(
        "agent_chat_turn",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_chat_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_chat_message.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "assistant_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_chat_message.id", ondelete="RESTRICT"),
        ),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="RUNNING"),
        sa.Column("error_code", sa.String(64)),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "usage_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')",
            name=op.f("ck_agent_chat_turn_status"),
        ),
        sa.UniqueConstraint(
            "session_id", "request_id", name="uq_agent_chat_turn_request"
        ),
        sa.UniqueConstraint(
            "user_message_id", name="uq_agent_chat_turn_user_message"
        ),
        sa.UniqueConstraint(
            "assistant_message_id", name="uq_agent_chat_turn_assistant_message"
        ),
        sa.UniqueConstraint("trace_id", name="uq_agent_chat_turn_trace"),
    )
    op.create_index(
        "idx_agent_chat_turn_session_started",
        "agent_chat_turn",
        ["session_id", "started_at"],
    )
    op.create_index(
        "uq_agent_chat_turn_running_session",
        "agent_chat_turn",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("status = 'RUNNING'"),
    )

    op.create_table(
        "agent_chat_tool_call",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "turn_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_chat_turn.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool_call_id", sa.String(128), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("args_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "evidence_ids_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(64)),
        sa.Column("cache_reused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint(
            "status IN ('READY', 'ERROR')",
            name=op.f("ck_agent_chat_tool_call_status"),
        ),
        sa.CheckConstraint(
            "duration_ms >= 0",
            name=op.f("ck_agent_chat_tool_call_duration"),
        ),
        sa.UniqueConstraint(
            "turn_id", "tool_call_id", name="uq_agent_chat_tool_call_id"
        ),
    )
    op.create_index(
        "idx_agent_chat_tool_call_turn", "agent_chat_tool_call", ["turn_id"]
    )


def downgrade() -> None:
    connection = op.get_bind()
    for table in (
        "agent_chat_tool_call",
        "agent_chat_turn",
        "agent_chat_message",
        "agent_chat_session",
    ):
        if connection.scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError(
                "cannot downgrade M16.2 while Agent chat history exists; "
                "archive or export it before an explicit destructive rollback"
            )

    op.drop_table("agent_chat_tool_call")
    op.drop_table("agent_chat_turn")
    op.drop_table("agent_chat_message")
    op.drop_table("agent_chat_session")
