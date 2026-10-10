import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.naming import conv

from app.models.base import Base


class AgentChatSession(Base):
    __tablename__ = "agent_chat_session"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')",
            name=conv("ck_agent_chat_session_status"),
        ),
        Index("idx_agent_chat_session_owner_updated", "owner_user_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AgentChatMessage(Base):
    __tablename__ = "agent_chat_message"
    __table_args__ = (
        CheckConstraint(
            "role IN ('USER', 'ASSISTANT')",
            name=conv("ck_agent_chat_message_role"),
        ),
        CheckConstraint(
            "status IN ('COMPLETED', 'FAILED')",
            name=conv("ck_agent_chat_message_status"),
        ),
        CheckConstraint(
            "char_length(content) BETWEEN 1 AND 16000",
            name=conv("ck_agent_chat_message_content_length"),
        ),
        CheckConstraint(
            "sequence_no > 0",
            name=conv("ck_agent_chat_message_sequence_positive"),
        ),
        UniqueConstraint(
            "session_id",
            "sequence_no",
            name=conv("uq_agent_chat_message_sequence"),
        ),
        UniqueConstraint(
            "id",
            "session_id",
            name=conv("uq_agent_chat_message_owner"),
        ),
        Index("idx_agent_chat_message_session_created", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_chat_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="COMPLETED", server_default="COMPLETED"
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AgentChatTurn(Base):
    __tablename__ = "agent_chat_turn"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')",
            name=conv("ck_agent_chat_turn_status"),
        ),
        UniqueConstraint(
            "session_id", "request_id", name=conv("uq_agent_chat_turn_request")
        ),
        UniqueConstraint(
            "user_message_id", name=conv("uq_agent_chat_turn_user_message")
        ),
        UniqueConstraint(
            "assistant_message_id", name=conv("uq_agent_chat_turn_assistant_message")
        ),
        UniqueConstraint("trace_id", name=conv("uq_agent_chat_turn_trace")),
        Index("idx_agent_chat_turn_session_started", "session_id", "started_at"),
        Index(
            "uq_agent_chat_turn_running_session",
            "session_id",
            unique=True,
            postgresql_where=text("status = 'RUNNING'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_chat_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_chat_message.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assistant_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_chat_message.id", ondelete="RESTRICT"),
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="RUNNING", server_default="RUNNING"
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    usage_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentChatToolCall(Base):
    __tablename__ = "agent_chat_tool_call"
    __table_args__ = (
        CheckConstraint(
            "status IN ('READY', 'ERROR')",
            name=conv("ck_agent_chat_tool_call_status"),
        ),
        CheckConstraint(
            "duration_ms >= 0",
            name=conv("ck_agent_chat_tool_call_duration"),
        ),
        UniqueConstraint(
            "turn_id", "tool_call_id", name=conv("uq_agent_chat_tool_call_id")
        ),
        Index("idx_agent_chat_tool_call_turn", "turn_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    turn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_chat_turn.id", ondelete="CASCADE"),
        nullable=False,
    )
    tool_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    args_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_ids_json: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    cache_reused: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
