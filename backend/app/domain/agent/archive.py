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
