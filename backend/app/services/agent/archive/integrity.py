from dataclasses import dataclass
from typing import Any

from app.core.agent_archive_config import AgentArchiveConfig
from app.domain.agent.archive import (
    ARCHIVE_VERSION,
    PROJECTOR_VERSION,
    AgentArchiveError,
    FrozenEvidenceBinding,
    FrozenToolResult,
    archive_error,
)
from app.domain.agent.chat import ChatCitation
from app.repositories.agent_archive import compiled_message_digest
from app.services.agent.archive.canonical import archive_hash, archive_storage_size
from app.services.agent.archive.projectors import validate_projection, verify_citation
from app.services.agent.chat.orchestrator import _args_hash


@dataclass
class ArchiveBundle:
    manifest: Any
    tools: list[Any]
    bindings: list[Any]
    audits: list[Any]
    turn: Any
    assistant: Any
    owner_id: Any


def tool_dto(row) -> FrozenToolResult:
    return FrozenToolResult(
        **{field: getattr(row, field) for field in FrozenToolResult.model_fields}
    )


def binding_dto(row, tool_call_id) -> FrozenEvidenceBinding:
    return FrozenEvidenceBinding(
        tool_call_id=tool_call_id,
        **{
            field: getattr(row, field)
            for field in FrozenEvidenceBinding.model_fields
            if field != "tool_call_id"
        },
    )


def verify_archive_integrity(
    bundle: ArchiveBundle, config: AgentArchiveConfig, check_deadline=lambda: None
) -> list[str]:
    """Pure read boundary. The bundle is preloaded; no Session or business resolvers."""
    unsupported = set()
    try:
        manifest = bundle.manifest
        body = manifest.manifest_json
        if archive_hash(body) != manifest.manifest_hash:
            raise ValueError("manifest digest")
        if manifest.owner_user_id != bundle.owner_id:
            raise ValueError("manifest owner")
        for field in ("owner_user_id", "chat_id", "turn_id", "assistant_message_id"):
            if body[field] != str(getattr(manifest, field)):
                raise ValueError("manifest pointers")
        for field in (
            "manifest_version",
            "archive_status",
            "claim_digest",
            "compiled_message_digest",
        ):
            if body[field] != getattr(manifest, field):
                raise ValueError("manifest metadata")
        turn, message = bundle.turn, bundle.assistant
        if (
            turn.id != manifest.turn_id
            or turn.session_id != manifest.chat_id
            or turn.status != "COMPLETED"
            or turn.assistant_message_id != message.id
            or message.id != manifest.assistant_message_id
            or message.session_id != manifest.chat_id
            or message.role != "ASSISTANT"
            or message.status != "COMPLETED"
        ):
            raise ValueError("completed message binding")
        claims = message.metadata_json.get(
            "verified_claims", message.metadata_json.get("claims", [])
        )
        if (
            archive_hash(claims) != manifest.claim_digest
            or compiled_message_digest(message.content, message.metadata_json)
            != manifest.compiled_message_digest
        ):
            raise ValueError("compiled message binding")
        required = sorted({eid for claim in claims for eid in claim["evidence_ids"]})
        if required != body["required_evidence_ids"]:
            raise ValueError("required evidence")
        if len(bundle.tools) > config.max_tool_calls or len(bundle.bindings) > config.max_bindings:
            raise archive_error("ARCHIVE_LIMIT_EXCEEDED")
        audits = {row.tool_call_id: row for row in bundle.audits}
        tools = {row.id: row for row in bundle.tools}
        if len(tools) != len(bundle.tools) or len(
            {row.tool_call_id for row in bundle.tools}
        ) != len(tools):
            raise ValueError("duplicate tool identity")
        frozen_tools = []
        total = archive_storage_size(body)
        for row in bundle.tools:
            check_deadline()
            dto = tool_dto(row)
            if (
                row.owner_user_id != bundle.owner_id
                or row.turn_id != manifest.turn_id
                or row.chat_id != manifest.chat_id
            ):
                raise ValueError("tool owner")
            payload = row.payload_json
            if (
                archive_hash(payload) != row.payload_hash
                or archive_hash(row.input_schema_json) != row.registry_schema_hash
                or _args_hash(row.tool_name, row.arguments_json) != row.arguments_hash
                or payload.get("tool_name") != row.tool_name
                or payload.get("tool_version") != row.tool_version
            ):
                raise ValueError("tool hash")
            size = archive_storage_size(payload)
            if size != row.payload_size_bytes or size > config.max_payload_bytes:
                raise ValueError("tool size")
            audit = audits.get(row.tool_call_id)
            if (
                audit is None
                or (audit.tool_name, audit.args_hash, audit.status)
                != (row.tool_name, row.arguments_hash, "READY")
                or set(audit.evidence_ids_json)
                != {ref["evidence_id"] for ref in payload["evidence"]}
            ):
                raise ValueError("tool audit")
            if audit.cache_reused != bool(row.cache_origin_call_id):
                raise ValueError("cache audit")
            if row.cache_origin_call_id:
                origin = audits.get(row.cache_origin_call_id)
                if origin is None or origin.args_hash != row.arguments_hash or origin.cache_reused:
                    raise ValueError("cache origin")
            frozen_tools.append(
                dto.model_dump(
                    mode="json", exclude={"payload_json", "arguments_json", "input_schema_json"}
                )
            )
            total += archive_storage_size(dto.model_dump(mode="json"))
            if row.archive_schema_version != ARCHIVE_VERSION:
                unsupported.add("UNSUPPORTED_ARCHIVE_VERSION")
            if row.projector_version != PROJECTOR_VERSION:
                unsupported.add("UNSUPPORTED_PROJECTOR_VERSION")
        if sorted(frozen_tools, key=archive_hash) != sorted(body["tools"], key=archive_hash):
            raise ValueError("manifest tools")
        bindings = {}
        frozen_bindings = []
        for row in bundle.bindings:
            check_deadline()
            tool = tools.get(row.tool_result_archive_id)
            if tool is None or (row.owner_user_id, row.turn_id, row.chat_id) != (
                bundle.owner_id,
                manifest.turn_id,
                manifest.chat_id,
            ):
                raise ValueError("binding owner")
            if row.evidence_id in bindings or row.ref_json.get("evidence_id") != row.evidence_id:
                raise ValueError("duplicate evidence")
            bindings[row.evidence_id] = row
            if (
                archive_hash(row.ref_json) != row.ref_hash
                or archive_hash(row.source_projection_json) != row.source_projection_hash
            ):
                raise ValueError("binding hash")
            refs = [
                ref
                for ref in tool.payload_json["evidence"]
                if ref["evidence_id"] == row.evidence_id
            ]
            if (
                len(refs) != 1
                or archive_hash(refs[0]) != row.ref_hash
                or refs[0]["quality_status"] == "ERROR"
            ):
                raise ValueError("actual ref")
            if not unsupported:
                try:
                    path = validate_projection(
                        tool.payload_json,
                        row.ref_json,
                        row.source_projection_json,
                        version=row.projection_version,
                    )
                    if path != row.record_path:
                        raise ValueError("record path")
                except AgentArchiveError as exc:
                    if exc.code.startswith("UNSUPPORTED_"):
                        unsupported.add(exc.code)
                    else:
                        raise
            dto = binding_dto(row, tool.tool_call_id)
            frozen_bindings.append(
                dto.model_dump(mode="json", exclude={"ref_json", "source_projection_json"})
            )
            total += archive_storage_size(dto.model_dump(mode="json"))
        if sorted(frozen_bindings, key=archive_hash) != sorted(body["bindings"], key=archive_hash):
            raise ValueError("manifest bindings")
        if not set(bindings) <= set(required) or (
            manifest.archive_status == "COMPLETE"
            and (not required or set(bindings) != set(required))
        ):
            raise ValueError("capture completeness")
        citations = [
            ChatCitation.model_validate(raw) for raw in message.metadata_json.get("citations", [])
        ]
        if {item.evidence_id for item in citations} != set(required) or len(citations) != len(
            required
        ):
            raise ValueError("compiled citations")
        for citation in citations:
            if citation.evidence_id in bindings:
                binding = bindings[citation.evidence_id]
                verify_citation(
                    citation, binding.ref_json, tools[binding.tool_result_archive_id].tool_name
                )
        if total > config.max_turn_bytes:
            raise archive_error("ARCHIVE_LIMIT_EXCEEDED")
        if manifest.manifest_version != ARCHIVE_VERSION:
            unsupported.add("UNSUPPORTED_MANIFEST_VERSION")
        return sorted(unsupported)
    except AgentArchiveError:
        raise
    except (ValueError, KeyError, AttributeError, TypeError) as exc:
        raise archive_error("ARCHIVE_INTEGRITY_MISMATCH") from exc
