import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.naming import conv

from app.models.base import Base


class AgentResearchReport(Base):
    __tablename__ = "agent_research_report"
    __table_args__ = (
        CheckConstraint(
            "report_type IN ('market_review', 'opportunity_review', "
            "'strategy_review', 'oos_review')",
            name=conv("ck_agent_research_report_type"),
        ),
        CheckConstraint(
            "source_answer_status IN ('COMPLETED', 'PARTIAL_VERIFIED')",
            name=conv("ck_agent_research_report_answer_status"),
        ),
        CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$' AND snapshot_hash ~ '^[0-9a-f]{64}$'",
            name=conv("ck_agent_research_report_hashes"),
        ),
        CheckConstraint(
            "octet_length(snapshot_json::text) <= 262144",
            name=conv("ck_agent_research_report_snapshot_size"),
        ),
        UniqueConstraint(
            "owner_user_id", "request_id", name=conv("uq_agent_research_report_request")
        ),
        UniqueConstraint(
            "id", "owner_user_id", name=conv("uq_agent_research_report_owner")
        ),
        ForeignKeyConstraint(
            ["source_message_id", "source_chat_id"],
            ["agent_chat_message.id", "agent_chat_message.session_id"],
            name=conv("fk_agent_research_report_source_message"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["parent_report_id", "owner_user_id"],
            ["agent_research_report.id", "agent_research_report.owner_user_id"],
            name=conv("fk_agent_research_report_parent_owner"),
            ondelete="RESTRICT",
        ),
        Index(
            "idx_agent_research_report_owner_created", "owner_user_id", "created_at"
        ),
        Index(
            "idx_agent_research_report_owner_source_message",
            "owner_user_id",
            "source_message_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    source_chat_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_turn_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_chat_turn.id", ondelete="RESTRICT")
    )
    parent_report_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    report_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="m16.4-v1", server_default="m16.4-v1"
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    as_of_date: Mapped[date | None] = mapped_column(Date)
    source_answer_status: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_contract_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AgentResearchReportComparison(Base):
    __tablename__ = "agent_research_report_comparison"
    __table_args__ = (
        CheckConstraint(
            "state IN ('COMPARABLE', 'CONTEXT_REQUIRED', 'INCOMPATIBLE')",
            name=conv("ck_agent_research_report_comparison_state"),
        ),
        CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$' AND "
            "left_snapshot_hash ~ '^[0-9a-f]{64}$' AND "
            "right_snapshot_hash ~ '^[0-9a-f]{64}$' AND "
            "comparison_hash ~ '^[0-9a-f]{64}$'",
            name=conv("ck_agent_research_report_comparison_hashes"),
        ),
        CheckConstraint(
            "left_report_id <> right_report_id",
            name=conv("ck_agent_research_report_comparison_distinct"),
        ),
        UniqueConstraint(
            "owner_user_id",
            "request_id",
            name=conv("uq_agent_research_report_comparison_request"),
        ),
        ForeignKeyConstraint(
            ["left_report_id", "owner_user_id"],
            ["agent_research_report.id", "agent_research_report.owner_user_id"],
            name=conv("fk_agent_research_report_comparison_left_owner"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["right_report_id", "owner_user_id"],
            ["agent_research_report.id", "agent_research_report.owner_user_id"],
            name=conv("fk_agent_research_report_comparison_right_owner"),
            ondelete="RESTRICT",
        ),
        Index(
            "idx_agent_research_report_comparison_owner_created",
            "owner_user_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    left_report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    right_report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_codes_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    left_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    right_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    comparison_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
