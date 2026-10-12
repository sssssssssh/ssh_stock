from __future__ import annotations

from typing import Any

from app.domain.agent.chat import AnswerStatus, RejectedClaim, StructuredClaim


def normalized_answer_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Normalize persisted assistant metadata across M16.2/M16.3 schemas."""

    raw_claims = metadata.get("verified_claims", metadata.get("claims", []))
    verified: list[dict[str, Any]] = []
    rejected: dict[str, dict[str, Any]] = {}
    if isinstance(raw_claims, list):
        for raw in raw_claims:
            if not isinstance(raw, dict):
                continue
            if raw.get("comparison_state") == "INCOMPATIBLE":
                safe = safe_rejected_claim(raw, ["COMPARISON_INCOMPATIBLE"])
                if safe is not None:
                    rejected[safe["claim_id"]] = safe
                continue
            try:
                verified.append(StructuredClaim.model_validate(raw).model_dump(mode="json"))
            except ValueError:
                continue

    raw_rejected = metadata.get("rejected_claims", [])
    if isinstance(raw_rejected, list):
        for raw in raw_rejected:
            if isinstance(raw, dict):
                safe = safe_rejected_claim(raw, [])
                if safe is not None:
                    rejected[safe["claim_id"]] = safe

    warnings = [
        str(item) for item in metadata.get("warnings", []) if isinstance(item, str)
    ]
    for warning in warnings:
        parts = warning.split(":", 2)
        if len(parts) == 3 and parts[0] == "CLAIM_REJECTED":
            claim_id, reason = parts[1], parts[2]
            existing = rejected.get(claim_id)
            if existing is None:
                safe = safe_rejected_claim(
                    {"claim_id": claim_id, "claim_type": "FACT"}, [reason]
                )
                if safe is not None:
                    rejected[claim_id] = safe
            elif reason not in existing["reason_codes"]:
                existing["reason_codes"].append(reason)

    stored_status = metadata.get("answer_status", metadata.get("status"))
    if verified and rejected:
        answer_status: AnswerStatus = "PARTIAL_VERIFIED"
    elif verified:
        answer_status = "COMPLETED"
    elif stored_status == "PARTIAL_VERIFIED":
        answer_status = "INSUFFICIENT_EVIDENCE"
    elif stored_status in {"COMPLETED", "INSUFFICIENT_EVIDENCE"}:
        answer_status = stored_status
    else:
        answer_status = "INSUFFICIENT_EVIDENCE"
    return {
        "status": answer_status,
        "answer_status": answer_status,
        "claims": verified,
        "verified_claims": verified,
        "rejected_claims": list(rejected.values()),
        "needs_clarification": bool(metadata.get("needs_clarification", False)),
        "citations": metadata.get("citations", []),
        "warnings": warnings,
        "tool_calls": metadata.get("tool_calls", []),
        "usage": metadata.get("usage", {}),
        "trace_id": metadata.get("trace_id"),
    }


def safe_rejected_claim(
    raw: dict[str, Any], fallback_reasons: list[str]
) -> dict[str, Any] | None:
    reasons = [
        str(item)
        for item in raw.get("reason_codes", [])
        if isinstance(item, str) and item
    ]
    reasons = list(dict.fromkeys([*fallback_reasons, *reasons])) or ["CLAIM_REJECTED"]
    try:
        return RejectedClaim(
            claim_id=raw.get("claim_id"),
            claim_type=raw.get("claim_type", "FACT"),
            reason_codes=reasons,
            comparison_state=raw.get("comparison_state"),
            policy_version=raw.get("policy_version"),
        ).model_dump(mode="json")
    except ValueError:
        return None
