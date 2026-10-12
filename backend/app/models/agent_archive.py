import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.naming import conv

from app.models.base import Base


class ArchiveColumns:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    chat_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    turn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def owner_constraints(name):
    return (
        ForeignKeyConstraint(
            ["chat_id", "owner_user_id"],
            ["agent_chat_session.id", "agent_chat_session.owner_user_id"],
            name=f"fk_{name}_chat_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["turn_id", "chat_id"],
            ["agent_chat_turn.id", "agent_chat_turn.session_id"],
            name=f"fk_{name}_turn_chat",
            ondelete="RESTRICT",
        ),
        Index(f"idx_{name}_owner_turn", "owner_user_id", "turn_id"),
    )


class AgentToolResultArchive(ArchiveColumns, Base):
    __tablename__ = "agent_tool_result_archive"
    __table_args__ = (
        *owner_constraints("agent_tool_archive"),
        UniqueConstraint("turn_id", "tool_call_id", name=conv("uq_agent_tool_archive_call")),
        UniqueConstraint(
            "id", "owner_user_id", "turn_id", name=conv("uq_agent_tool_archive_owner")
        ),
        ForeignKeyConstraint(
            ["turn_id", "tool_call_id"],
            ["agent_chat_tool_call.turn_id", "agent_chat_tool_call.tool_call_id"],
            name="fk_agent_tool_archive_audit",
            ondelete="RESTRICT",
        ),
        CheckConstraint("status = 'READY'", name=conv("ck_agent_tool_archive_status")),
        CheckConstraint(
            "payload_size_bytes BETWEEN 1 AND 65536 AND octet_length(payload_json::text) <= 65536",
            name=conv("ck_agent_tool_archive_size"),
        ),
        CheckConstraint(
            "arguments_hash ~ '^[0-9a-f]{64}$' AND "
            "registry_schema_hash ~ '^[0-9a-f]{64}$' AND payload_hash ~ '^[0-9a-f]{64}$'",
            name=conv("ck_agent_tool_archive_hashes"),
        ),
    )
    tool_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(32), nullable=False)
    archive_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    projector_version: Mapped[str] = mapped_column(String(64), nullable=False)
    arguments_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    input_schema_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    registry_schema_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    cache_origin_call_id: Mapped[str | None] = mapped_column(String(128))


class AgentEvidenceArchiveBinding(ArchiveColumns, Base):
    __tablename__ = "agent_evidence_archive_binding"
    __table_args__ = (
        *owner_constraints("agent_evidence_binding"),
        UniqueConstraint("turn_id", "evidence_id", name=conv("uq_agent_evidence_binding_ref")),
        ForeignKeyConstraint(
            ["tool_result_archive_id", "owner_user_id", "turn_id"],
            [
                "agent_tool_result_archive.id",
                "agent_tool_result_archive.owner_user_id",
                "agent_tool_result_archive.turn_id",
            ],
            name="fk_agent_evidence_binding_tool_owner",
            ondelete="RESTRICT",
        ),
        Index("idx_agent_evidence_binding_tool", "tool_result_archive_id"),
        CheckConstraint(
            "ref_hash ~ '^[0-9a-f]{64}$' AND source_projection_hash ~ '^[0-9a-f]{64}$'",
            name=conv("ck_agent_evidence_binding_hashes"),
        ),
        CheckConstraint(
            "octet_length(source_projection_json::text) <= 655360",
            name=conv("ck_agent_evidence_binding_size"),
        ),
    )
    tool_result_archive_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(128), nullable=False)
    ref_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ref_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_projection_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_projection_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    projection_version: Mapped[str] = mapped_column(String(64), nullable=False)
    record_path: Mapped[str] = mapped_column(String(160), nullable=False)


class AgentTurnArchiveManifest(ArchiveColumns, Base):
    __tablename__ = "agent_turn_archive_manifest"
    __table_args__ = (
        *owner_constraints("agent_archive_manifest"),
        UniqueConstraint("turn_id", name=conv("uq_agent_archive_manifest_turn")),
        ForeignKeyConstraint(
            ["assistant_message_id", "chat_id"],
            ["agent_chat_message.id", "agent_chat_message.session_id"],
            name="fk_agent_archive_manifest_assistant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "archive_status IN ('COMPLETE', 'PARTIAL', 'UNAVAILABLE')",
            name=conv("ck_agent_archive_manifest_status"),
        ),
        CheckConstraint(
            "manifest_hash ~ '^[0-9a-f]{64}$' AND "
            "claim_digest ~ '^[0-9a-f]{64}$' AND compiled_message_digest ~ '^[0-9a-f]{64}$'",
            name=conv("ck_agent_archive_manifest_hashes"),
        ),
        CheckConstraint(
            "octet_length(manifest_json::text) <= 655360",
            name=conv("ck_agent_archive_manifest_size"),
        ),
    )
    assistant_message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    manifest_version: Mapped[str] = mapped_column(String(64), nullable=False)
    archive_status: Mapped[str] = mapped_column(String(16), nullable=False)
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    compiled_message_digest: Mapped[str] = mapped_column(String(64), nullable=False)
