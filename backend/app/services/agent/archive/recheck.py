import time

from app.core.agent_archive_config import AgentArchiveConfig
from app.domain.agent.archive import INTEGRITY_VERSION, RECHECK_VERSION, archive_error
from app.domain.agent.chat import StructuredClaim
from app.services.agent.archive.integrity import ArchiveBundle, verify_archive_integrity
from app.services.agent.chat.comparison_policy import (
    ComparisonEvidenceContext,
    EvidenceComparisonPolicy,
)
from app.services.agent.chat.fact_validation import (
    _ClaimValidationError,
    _EvidenceBinding,
    _validate_fact_binding,
)
from app.services.agent.chat.orchestrator import ToolResultContext


def recheck_archive(
    bundle: ArchiveBundle,
    *,
    config: AgentArchiveConfig,
    claims=None,
    max_evidence=None,
    monotonic=time.monotonic,
    started_at=None,
):
    deadline = (monotonic() if started_at is None else started_at) + config.verify_timeout_seconds

    def check_deadline():
        if monotonic() >= deadline:
            raise archive_error("ARCHIVE_VERIFY_TIMEOUT", status_code=504)

    if len(bundle.bindings) > (max_evidence or config.max_bindings):
        raise archive_error("ARCHIVE_LIMIT_EXCEEDED", status_code=422)
    unsupported = verify_archive_integrity(bundle, config, check_deadline)
    source = bundle.assistant.metadata_json.get("verified_claims", []) if claims is None else claims
    parsed = [StructuredClaim.model_validate(item) for item in source]
    tools = {row.id: row for row in bundle.tools}
    bindings = {row.evidence_id: row for row in bundle.bindings}
    results = []
    verified = set()
    # Facts and comparisons precede inferences regardless of input ordering.
    for claim in sorted(parsed, key=lambda item: (item.claim_type == "INFERENCE", item.claim_id)):
        check_deadline()
        reasons = set(unsupported)
        failed_fields = []
        facts_status = "VERIFIED"
        if unsupported:
            facts_status = "UNVERIFIABLE"
            status = "UNVERIFIABLE"
        elif claim.claim_type == "INFERENCE":
            supports = claim.inference.supporting_claim_ids if claim.inference else []
            if not supports or not set(supports) <= verified:
                reasons.add("INFERENCE_SUPPORT_UNVERIFIABLE")
                status = "UNVERIFIABLE"
            else:
                reasons.add("INFERENCE_NOT_CAUSAL_PROOF")
                status = "VERIFIED"
        else:
            status = "VERIFIED"
            if len(claim.verified_fact_refs) != len(claim.structured_facts):
                reasons.add("UNRESOLVED_EVIDENCE_BINDING")
                status = facts_status = "UNVERIFIABLE"
            else:
                contexts = []
                for fact, fact_ref in zip(
                    claim.structured_facts, claim.verified_fact_refs, strict=True
                ):
                    check_deadline()
                    suffix = f":{fact.path}"
                    eid = fact_ref[: -len(suffix)] if fact_ref.endswith(suffix) else None
                    binding = bindings.get(eid)
                    if binding is None or eid not in claim.evidence_ids:
                        reasons.add("ARCHIVE_EVIDENCE_MISSING")
                        if status != "MISMATCH":
                            status = facts_status = "UNVERIFIABLE"
                        continue
                    tool = tools[binding.tool_result_archive_id]
                    refs = tool.payload_json["evidence"]
                    indices = [i for i, ref in enumerate(refs) if ref["evidence_id"] == eid]
                    try:
                        context = _validate_fact_binding(
                            fact,
                            _EvidenceBinding(
                                ToolResultContext(
                                    tool.tool_call_id, tool.tool_name, tool.payload_json
                                ),
                                binding.ref_json,
                                indices[0],
                            ),
                        )
                        contexts.append(context)
                    except _ClaimValidationError as exc:
                        reasons.add(exc.code)
                        failed_fields.append(
                            {"path": fact.path, "evidence_id": eid, "code": exc.code}
                        )
                        status = facts_status = "MISMATCH"
                if claim.claim_type == "COMPARISON" and status == "VERIFIED":
                    if claim.comparison_type == "INDEPENDENT_BACKTESTS":
                        reasons.add("EXACT_M14_BUNDLE_NOT_ARCHIVED")
                        status = "UNVERIFIABLE"
                    elif claim.comparison_type == "TRAIN_VS_OOS":
                        reasons.add("FROZEN_M15_WINDOW_LINEAGE_REQUIRED")
                        status = "UNVERIFIABLE"
                    elif claim.comparison_state == "CONTEXT_REQUIRED":
                        reasons.add("COMPARISON_CONTEXT_REQUIRED")
                    if claim.comparison_type not in {"INDEPENDENT_BACKTESTS", "TRAIN_VS_OOS"}:
                        decision = EvidenceComparisonPolicy().evaluate(
                            claim,
                            contexts,
                            [
                                ComparisonEvidenceContext(
                                    item.tool_name, item.evidence, item.identity
                                )
                                for item in contexts
                            ],
                        )
                        reasons.update(decision.reason_codes)
                        if (
                            decision.state == "INCOMPATIBLE"
                            or decision.state != claim.comparison_state
                        ):
                            status = "MISMATCH"
                            reasons.add("FROZEN_COMPARISON_DECISION_MISMATCH")
        if status == "VERIFIED" and claim.claim_type != "INFERENCE":
            verified.add(claim.claim_id)
        results.append(
            {
                "claim_id": claim.claim_id,
                "status": status,
                "facts_status": facts_status,
                "evidence_ids": sorted(claim.evidence_ids),
                "reason_codes": sorted(reasons),
                "failed_fields": failed_fields,
                "verified_fact_refs": claim.verified_fact_refs,
            }
        )
    states = {row["status"] for row in results}
    state = (
        "MISMATCH"
        if "MISMATCH" in states
        else "UNVERIFIABLE"
        if ("UNVERIFIABLE" in states or not results)
        else "VERIFIED"
    )
    check_deadline()
    return {
        "archive_status": bundle.manifest.archive_status,
        "integrity": {
            "status": "UNVERIFIABLE" if unsupported else "VERIFIED",
            "policy_version": INTEGRITY_VERSION,
        },
        "fact_recheck": {
            "status": state,
            "policy_version": RECHECK_VERSION,
            "checked_claim_count": len(results),
            "results": results,
        },
        "reproduction_level": "FROZEN_FACT_RECHECK" if not unsupported else "SNAPSHOT_ONLY",
        "verification_level": "FACT_REVERIFIED" if state == "VERIFIED" else state,
        "calculation_reproduced": False,
        "warnings": ["HISTORICAL_TOOL_RESULT_ONLY", "CALCULATION_NOT_REEXECUTED", *unsupported],
    }
