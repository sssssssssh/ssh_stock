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
    claim_by_id = {claim.claim_id: claim for claim in parsed}
    direct_status = {}
    duplicate_claims = len(claim_by_id) != len(parsed)
    # Facts and comparisons precede inferences regardless of input ordering.
    for claim in sorted(parsed, key=lambda item: (item.claim_type == "INFERENCE", item.claim_id)):
        check_deadline()
        reasons = set(unsupported)
        failed_fields = []
        facts_applicable = claim.claim_type != "INFERENCE"
        facts_status = "VERIFIED" if facts_applicable else "UNVERIFIABLE"
        check_kind = (
            "INFERENCE_SUPPORT"
            if claim.claim_type == "INFERENCE"
            else "COMPARISON_CONTEXT"
            if claim.claim_type == "COMPARISON"
            else "DIRECT_FACT"
        )
        support_status = None
        comparison_state = None
        if duplicate_claims:
            reasons.add("DUPLICATE_FROZEN_CLAIM_ID")
            status = "MISMATCH"
            facts_status = "MISMATCH" if facts_applicable else "UNVERIFIABLE"
        elif unsupported:
            facts_status = "UNVERIFIABLE"
            status = "UNVERIFIABLE"
        elif claim.claim_type == "INFERENCE":
            supports = claim.inference.supporting_claim_ids if claim.inference else []
            supporters = [claim_by_id.get(claim_id) for claim_id in supports]
            if claim.structured_facts:
                reasons.add("INFERENCE_DIRECT_FACTS_UNSUPPORTED")
                status = "MISMATCH"
            elif claim.inference is None:
                reasons.add("LEGACY_BOUNDED_INFERENCE")
                status = "UNVERIFIABLE"
            elif len(supports) != len(set(supports)) or claim.claim_id in supports:
                reasons.add("INFERENCE_SUPPORT_INVALID")
                status = "MISMATCH"
            elif any(
                support is None or support.claim_type == "INFERENCE" for support in supporters
            ):
                reasons.add("INFERENCE_SUPPORT_UNVERIFIABLE")
                status = "UNVERIFIABLE"
            else:
                allowed_evidence = {eid for support in supporters for eid in support.evidence_ids}
                expected_refs = list(
                    dict.fromkeys(
                        ref for support in supporters for ref in support.verified_fact_refs
                    )
                )
                if (
                    not claim.evidence_ids
                    or len(set(claim.evidence_ids)) != len(claim.evidence_ids)
                    or not set(claim.evidence_ids) <= allowed_evidence
                ):
                    reasons.add("INFERENCE_EVIDENCE_NOT_SUPPORTED")
                    status = "MISMATCH"
                elif claim.verified_fact_refs != expected_refs:
                    reasons.add("INFERENCE_FIELD_REFS_INVALID")
                    status = "MISMATCH"
                elif any(direct_status.get(item) != "VERIFIED" for item in supports):
                    reasons.add("INFERENCE_SUPPORT_UNVERIFIABLE")
                    status = "UNVERIFIABLE"
                else:
                    reasons.add("INFERENCE_NOT_CAUSAL_PROOF")
                    status = "VERIFIED"
            support_status = status
        else:
            status = "VERIFIED"
            if (
                not claim.structured_facts
                or len(claim.verified_fact_refs) != len(claim.structured_facts)
                or len(set(claim.verified_fact_refs)) != len(claim.verified_fact_refs)
                or len(set(claim.evidence_ids)) != len(claim.evidence_ids)
            ):
                reasons.add("FROZEN_FACT_BINDING_INVALID")
                status = facts_status = "MISMATCH"
            else:
                contexts = []
                for fact, fact_ref in zip(
                    claim.structured_facts, claim.verified_fact_refs, strict=True
                ):
                    check_deadline()
                    suffix = f":{fact.path}"
                    eid = fact_ref[: -len(suffix)] if fact_ref.endswith(suffix) else None
                    if not eid or eid not in claim.evidence_ids:
                        reasons.add("FROZEN_FACT_BINDING_INVALID")
                        status = facts_status = "MISMATCH"
                        continue
                    binding = bindings.get(eid)
                    if binding is None:
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
                        comparison_state = "INCOMPATIBLE"
                    elif claim.comparison_type == "TRAIN_VS_OOS":
                        reasons.add("FROZEN_M15_WINDOW_LINEAGE_REQUIRED")
                        status = "UNVERIFIABLE"
                        comparison_state = "INCOMPATIBLE"
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
                        comparison_state = decision.state
                        if (
                            decision.state == "INCOMPATIBLE"
                            or decision.state != claim.comparison_state
                        ):
                            status = "MISMATCH"
                            reasons.add("FROZEN_COMPARISON_DECISION_MISMATCH")
                        elif decision.state == "CONTEXT_REQUIRED":
                            status = "UNVERIFIABLE"
                            reasons.add("COMPARISON_CONTEXT_REQUIRED")
            direct_status[claim.claim_id] = status
        results.append(
            {
                "claim_id": claim.claim_id,
                "status": status,
                "facts_status": facts_status,
                "facts_applicable": facts_applicable,
                "check_kind": check_kind,
                "support_status": support_status,
                "evidence_ids": sorted(claim.evidence_ids),
                "reason_codes": sorted(reasons),
                "failed_fields": failed_fields,
                "verified_fact_refs": claim.verified_fact_refs,
                "comparison_state": comparison_state,
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
    fact_states = {row["facts_status"] for row in results if row["facts_applicable"]}
    fact_state = (
        "MISMATCH"
        if "MISMATCH" in fact_states
        else "UNVERIFIABLE"
        if "UNVERIFIABLE" in fact_states or not fact_states
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
            "status": fact_state,
            "policy_version": RECHECK_VERSION,
            "checked_claim_count": len(results),
            "results": results,
        },
        "claim_recheck_summary": {
            "status": state,
            "verified_count": sum(row["status"] == "VERIFIED" for row in results),
            "mismatch_count": sum(row["status"] == "MISMATCH" for row in results),
            "unverifiable_count": sum(row["status"] == "UNVERIFIABLE" for row in results),
        },
        "reproduction_level": "FROZEN_FACT_RECHECK" if not unsupported else "SNAPSHOT_ONLY",
        "verification_level": "FACT_REVERIFIED" if state == "VERIFIED" else state,
        "calculation_reproduced": False,
        "warnings": ["HISTORICAL_TOOL_RESULT_ONLY", "CALCULATION_NOT_REEXECUTED", *unsupported],
    }
