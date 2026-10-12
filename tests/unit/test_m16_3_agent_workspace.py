import json

from app.services.agent.chat.application import _normalized_answer_metadata
from app.services.agent.chat.evidence_compiler import EvidenceCompiler
from app.services.agent.chat.orchestrator import ToolResultContext


def _claim(claim_id: str, evidence_id: str) -> dict:
    return {
        "claim_id": claim_id,
        "claim_type": "FACT",
        "text": f"untrusted model text {claim_id}",
        "evidence_ids": [evidence_id],
        "structured_facts": [
            {
                "path": "records.0.value",
                "value": 7,
                "unit": "decimal",
                "trade_date": "2026-01-02",
                "entity": "sample",
                "sample_role": "UNKNOWN",
            }
        ],
    }


def _compile(claims: list[dict]):
    context = ToolResultContext(
        tool_call_id="call-1",
        tool_name="test.read",
        payload={
            "records": [{"value": 7}],
            "as_of_date": "2026-01-02",
            "identity": {},
            "evidence": [
                {
                    "evidence_id": "evidence-ok",
                    "evidence_version": "v2",
                    "entity_id": "sample",
                    "trade_date": "2026-01-02",
                    "quality_status": "PASS",
                }
            ],
        },
    )
    return EvidenceCompiler(max_answer_chars=8000).compile(
        final_text=json.dumps(
            {
                "answer": "draft",
                "evidence_ids": ["evidence-ok"],
                "claims": claims,
                "warnings": [],
                "needs_clarification": False,
            }
        ),
        tool_results=[context],
        inherited_warnings=[],
    )


def test_answer_status_distinguishes_complete_partial_and_insufficient() -> None:
    complete = _compile([_claim("valid", "evidence-ok")])
    assert complete.answer_status == "COMPLETED"
    assert [item.claim_id for item in complete.claims] == ["valid"]
    assert complete.rejected_claims == []

    partial = _compile(
        [_claim("valid", "evidence-ok"), _claim("forged", "unknown-evidence")]
    )
    assert partial.answer_status == "PARTIAL_VERIFIED"
    assert [item.claim_id for item in partial.claims] == ["valid"]
    assert partial.rejected_claims[0].model_dump() == {
        "claim_id": "forged",
        "claim_type": "FACT",
        "reason_codes": ["UNKNOWN_EVIDENCE_ID"],
        "comparison_state": None,
        "policy_version": None,
    }
    assert "structured_facts" not in partial.rejected_claims[0].model_dump()
    assert "text" not in partial.rejected_claims[0].model_dump()

    insufficient = _compile([_claim("forged", "unknown-evidence")])
    assert insufficient.answer_status == "INSUFFICIENT_EVIDENCE"
    assert insufficient.claims == []
    assert insufficient.citations == []


def test_historical_mixed_metadata_is_sanitized_without_unverified_values() -> None:
    accepted = _claim("valid", "evidence-ok")
    accepted.update(
        {
            "quality_status": "PASS",
            "reason_codes": [],
            "verified_fact_refs": ["evidence-ok:records.0.value"],
        }
    )
    rejected = _claim("legacy-rejected", "evidence-ok")
    rejected.update(
        {
            "comparison_state": "INCOMPATIBLE",
            "reason_codes": ["RUN_ID_MISMATCH"],
        }
    )
    normalized = _normalized_answer_metadata(
        {
            "status": "INSUFFICIENT_EVIDENCE",
            "claims": [accepted, rejected],
            "warnings": [
                "CLAIM_REJECTED:legacy-rejected:COMPARISON_INCOMPATIBLE"
            ],
        }
    )

    assert normalized["answer_status"] == "PARTIAL_VERIFIED"
    assert [item["claim_id"] for item in normalized["verified_claims"]] == ["valid"]
    assert normalized["rejected_claims"] == [
        {
            "claim_id": "legacy-rejected",
            "claim_type": "FACT",
            "reason_codes": ["COMPARISON_INCOMPATIBLE", "RUN_ID_MISMATCH"],
            "comparison_state": "INCOMPATIBLE",
            "policy_version": None,
        }
    ]
    assert "structured_facts" not in normalized["rejected_claims"][0]
