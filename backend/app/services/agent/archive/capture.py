from app.core.agent_archive_config import AgentArchiveConfig
from app.domain.agent.archive import (
    ArchiveDraft,
    FrozenEvidenceBinding,
    FrozenToolResult,
    archive_error,
)
from app.domain.agent.chat import ChatCitation, StructuredClaim
from app.services.agent.archive.canonical import archive_hash, archive_json, archive_storage_size
from app.services.agent.archive.projectors import check_safe, validate_projection
from app.services.agent.chat.orchestrator import ToolResultContext, _args_hash


def assemble_archive(
    *,
    tool_results: list[ToolResultContext],
    claims: list[StructuredClaim],
    citations: list[ChatCitation],
    config: AgentArchiveConfig,
) -> ArchiveDraft:
    required = sorted({eid for claim in claims for eid in claim.evidence_ids})
    if set(required) != {item.evidence_id for item in citations}:
        raise archive_error("ARCHIVE_CITATION_MISMATCH")
    if len(required) > config.max_bindings or len(tool_results) > config.max_tool_calls:
        raise archive_error("ARCHIVE_LIMIT_EXCEEDED")
    candidates = {}
    selected_tools = {}
    total_size = 0
    for context in tool_results:
        refs = context.payload.get("evidence", [])
        for ref in refs:
            eid = ref.get("evidence_id")
            if eid not in required:
                continue
            if ref.get("quality_status") == "ERROR":
                raise archive_error("ARCHIVE_EVIDENCE_QUALITY_ERROR")
            projection = context.source_projections.get(eid)
            if not isinstance(projection, dict):
                raise archive_error("ARCHIVE_PROJECTION_UNAVAILABLE")
            path = validate_projection(context.payload, ref, projection)
            signature = archive_hash(
                {
                    "payload": context.payload,
                    "projection": projection,
                    "ref": ref,
                    "tool": context.tool_name,
                }
            )
            if eid in candidates and candidates[eid][0] != signature:
                raise archive_error("EVIDENCE_DUPLICATE_CONFLICT")
            # Every actual/cached selected call is kept; evidence binding chooses a stable origin.
            selected_tools[context.tool_call_id] = context
            if eid not in candidates or context.tool_call_id < candidates[eid][1].tool_call_id:
                candidates[eid] = (signature, context, ref, projection, path)
    if set(candidates) != set(required):
        raise archive_error("ARCHIVE_EVIDENCE_MISSING")
    tools = []
    for call_id, context in sorted(selected_tools.items()):
        if context.payload.get("tool_name") != context.tool_name:
            raise archive_error("ARCHIVE_TOOL_IDENTITY_MISMATCH")
        if context.payload.get("tool_version") != context.tool_version:
            raise archive_error("UNSUPPORTED_TOOL_VERSION")
        if not context.input_schema:
            raise archive_error("ARCHIVE_SCHEMA_UNAVAILABLE")
        check_safe(context.arguments)
        payload = archive_json(context.payload)
        size = archive_storage_size(payload)
        if size > config.max_payload_bytes:
            raise archive_error("ARCHIVE_LIMIT_EXCEEDED")
        tool = FrozenToolResult(
            tool_call_id=call_id,
            tool_name=context.tool_name,
            tool_version=context.tool_version,
            arguments_json=context.arguments,
            input_schema_json=context.input_schema,
            arguments_hash=_args_hash(context.tool_name, context.arguments),
            registry_schema_hash=archive_hash(context.input_schema),
            payload_json=payload,
            payload_hash=archive_hash(payload),
            payload_size_bytes=size,
            cache_origin_call_id=context.cache_origin_call_id,
        )
        tools.append(tool)
        total_size += archive_storage_size(tool.model_dump(mode="json"))
    bindings = []
    for eid, (_, context, ref, projection, path) in sorted(candidates.items()):
        binding = FrozenEvidenceBinding(
            tool_call_id=context.tool_call_id,
            evidence_id=eid,
            ref_json=archive_json(ref),
            ref_hash=archive_hash(ref),
            source_projection_json=archive_json(projection),
            source_projection_hash=archive_hash(projection),
            record_path=path,
        )
        bindings.append(binding)
        total_size += archive_storage_size(binding.model_dump(mode="json"))
    if total_size > config.max_turn_bytes:
        raise archive_error("ARCHIVE_LIMIT_EXCEEDED")
    return ArchiveDraft(
        tools=tools,
        bindings=bindings,
        required_evidence_ids=required,
        claim_digest=archive_hash([item.model_dump(mode="json") for item in claims]),
        archive_status="COMPLETE" if required else "UNAVAILABLE",
    )
