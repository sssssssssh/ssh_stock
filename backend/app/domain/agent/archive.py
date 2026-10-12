import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.agent.chat_errors import AgentChatError

ARCHIVE_VERSION = "m16.5-archive-v1"
PROJECTOR_VERSION = "m16.5-content-projector-v1"
INTEGRITY_VERSION = "m16.5-integrity-v1"
RECHECK_VERSION = "m16.5-frozen-recheck-v1"


class AgentArchiveError(AgentChatError):
    pass


def archive_error(code: str, *, status_code: int = 409) -> AgentArchiveError:
    return AgentArchiveError(code, "frozen evidence archive check failed", status_code=status_code)


class ArchiveDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FrozenToolResult(ArchiveDTO):
    tool_call_id: str
    tool_name: str
    tool_version: str
    archive_schema_version: str = ARCHIVE_VERSION
    projector_version: str = PROJECTOR_VERSION
    arguments_json: dict[str, Any]
    input_schema_json: dict[str, Any]
    arguments_hash: str
    registry_schema_hash: str
    payload_json: dict[str, Any]
    payload_hash: str
    payload_size_bytes: int
    status: Literal["READY"] = "READY"
    cache_origin_call_id: str | None = None


class FrozenEvidenceBinding(ArchiveDTO):
    tool_call_id: str
    evidence_id: str
    ref_json: dict[str, Any]
    ref_hash: str
    source_projection_json: dict[str, Any]
    source_projection_hash: str
    projection_version: str = PROJECTOR_VERSION
    record_path: str


class ArchiveDraft(ArchiveDTO):
    tools: list[FrozenToolResult]
    bindings: list[FrozenEvidenceBinding]
    required_evidence_ids: list[str]
    claim_digest: str
    archive_status: Literal["COMPLETE", "PARTIAL", "UNAVAILABLE"]


class VerifyArchiveRequest(ArchiveDTO):
    max_evidence: int = Field(default=64, ge=1, le=100)


ArchiveStatus = Literal["COMPLETE", "PARTIAL", "UNAVAILABLE"]
CheckStatus = Literal["VERIFIED", "MISMATCH", "UNVERIFIABLE"]
ReproductionLevel = Literal["SNAPSHOT_ONLY", "FROZEN_FACT_RECHECK", "FROZEN_CONTRACT_RECHECK"]


class ArchiveIntegrityView(ArchiveDTO):
    status: CheckStatus = "UNVERIFIABLE"
    policy_version: str = INTEGRITY_VERSION


class ArchiveSummary(ArchiveDTO):
    archive_status: ArchiveStatus = "UNAVAILABLE"
    manifest_id: uuid.UUID | None = None
    manifest_version: str | None = None
    manifest_hash: str | None = None
    source_turn_id: uuid.UUID | None = None
    created_at: datetime | None = None
    reproduction_level: ReproductionLevel = "SNAPSHOT_ONLY"
    required_evidence_count: int = 0
    archived_evidence_count: int = 0
    integrity: ArchiveIntegrityView = Field(default_factory=ArchiveIntegrityView)
    calculation_reproduced: Literal[False] = False
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ArchiveEvidenceSummary(ArchiveDTO):
    evidence_id: str
    tool_call_id: str
    tool_name: str
    tool_version: str
    as_of_date: date | None = None
    created_at: datetime
    record_path: str
    layer: str | None = None
    entity_id: str | None = None
    calc_version: str | None = None
    algo_version: str | None = None
    config_hash: str | None = None
    source_hash: str | None = None
    content_hash: str | None = None
    quality_status: str | None = None
    evidence_version: str | None = None
    calc_run_id: str | None = None
    report_id: str | None = None


class TurnArchiveView(ArchiveSummary):
    evidence: list[ArchiveEvidenceSummary] = Field(default_factory=list, max_length=100)


class EvidenceDetailView(ArchiveSummary):
    evidence_id: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_version: str | None = None
    as_of_date: date | None = None
    record_path: str | None = None
    layer: str | None = None
    entity_id: str | None = None
    calc_version: str | None = None
    algo_version: str | None = None
    config_hash: str | None = None
    source_hash: str | None = None
    content_hash: str | None = None
    quality_status: str | None = None
    evidence_version: str | None = None
    calc_run_id: str | None = None
    report_id: str | None = None
    arguments_summary: dict[str, Any] = Field(default_factory=dict)
    arguments_hash: str | None = None
    registry_schema_hash: str | None = None
    projection_version: str | None = None
    frozen_facts: list[dict[str, Any]] = Field(default_factory=list)


class ClaimRecheckView(ArchiveDTO):
    claim_id: str
    status: CheckStatus
    facts_status: CheckStatus
    evidence_ids: list[str]
    reason_codes: list[str]
    failed_fields: list[dict[str, str]]
    verified_fact_refs: list[str]


class FactRecheckView(ArchiveDTO):
    status: CheckStatus
    policy_version: str = RECHECK_VERSION
    checked_claim_count: int
    results: list[ClaimRecheckView]


class ArchiveVerifyView(ArchiveSummary):
    report_id: uuid.UUID | None = None
    fact_recheck: FactRecheckView = Field(
        default_factory=lambda: FactRecheckView(
            status="UNVERIFIABLE", checked_claim_count=0, results=[]
        )
    )
    verification_level: str = "UNVERIFIABLE"


class ArchiveEnvelope[T](ArchiveDTO):
    code: int
    message: str
    data: T
    meta: dict[str, Any]
