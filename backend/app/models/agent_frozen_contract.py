import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.naming import conv

from app.models.agent_archive import ArchiveColumns, owner_constraints
from app.models.base import Base


class AgentFrozenResearchContract(ArchiveColumns, Base):
    __tablename__ = "agent_frozen_research_contract"
    __table_args__ = (
        *owner_constraints("agent_frozen_contract"),
        ForeignKeyConstraint(
            ["tool_result_archive_id", "owner_user_id", "turn_id"],
            [
                "agent_tool_result_archive.id",
                "agent_tool_result_archive.owner_user_id",
                "agent_tool_result_archive.turn_id",
            ],
            name="fk_agent_frozen_contract_tool_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tool_result_archive_id", "contract_kind", "subject_id", "role",
            name=conv("uq_agent_frozen_contract_source"),
        ),
        UniqueConstraint(
            "id", "owner_user_id", "turn_id", name=conv("uq_agent_frozen_contract_owner")
        ),
        Index("idx_agent_frozen_contract_subject", "owner_user_id", "contract_kind", "subject_id"),
        CheckConstraint(
            "contract_kind IN ('M14_EXACT_BUNDLE', 'M15_WINDOW_LINEAGE', 'M15_STUDY_AGGREGATE')",
            name=conv("ck_agent_frozen_contract_kind"),
        ),
        CheckConstraint(
            "role IN ('LIVE', 'TRAIN', 'OOS', 'STUDY')",
            name=conv("ck_agent_frozen_contract_role"),
        ),
        CheckConstraint(
            "size_bytes BETWEEN 1 AND 131072 AND octet_length(contract_json::text) <= 131072",
            name=conv("ck_agent_frozen_contract_size"),
        ),
        CheckConstraint(
            "contract_hash ~ '^[0-9a-f]{64}$'",
            name=conv("ck_agent_frozen_contract_hash"),
        ),
    )

    tool_result_archive_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    contract_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_scope: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    contract_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)


class AgentFrozenContractManifest(ArchiveColumns, Base):
    __tablename__ = "agent_frozen_contract_manifest"
    __table_args__ = (
        *owner_constraints("agent_contract_manifest"),
        UniqueConstraint("turn_id", name=conv("uq_agent_contract_manifest_turn")),
        ForeignKeyConstraint(
            ["base_manifest_id", "owner_user_id", "turn_id"],
            [
                "agent_turn_archive_manifest.id",
                "agent_turn_archive_manifest.owner_user_id",
                "agent_turn_archive_manifest.turn_id",
            ],
            name="fk_agent_contract_manifest_base_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "contract_count BETWEEN 1 AND 800",
            name=conv("ck_agent_contract_manifest_count"),
        ),
        CheckConstraint(
            "octet_length(manifest_json::text) <= 65536",
            name=conv("ck_agent_contract_manifest_size"),
        ),
        CheckConstraint(
            "base_manifest_hash ~ '^[0-9a-f]{64}$' AND "
            "contract_ids_hash ~ '^[0-9a-f]{64}$' AND "
            "manifest_hash ~ '^[0-9a-f]{64}$'",
            name=conv("ck_agent_contract_manifest_hashes"),
        ),
    )

    base_manifest_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    base_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_ids_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_count: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
