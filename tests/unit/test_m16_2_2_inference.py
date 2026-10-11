import json
from typing import Any

from app.services.agent.chat.evidence_compiler import EvidenceCompiler
from app.services.agent.chat.orchestrator import ToolResultContext


def _context() -> ToolResultContext:
    return ToolResultContext(
        tool_call_id="market-call",
        tool_name="market.snapshot",
        payload={
            "as_of_date": "2026-10-11",
            "identity": {"calc_version": "market-v1", "config_hash": "c" * 64},
            "records": [{"market_score": "65"}],
            "evidence": [
                {
                    "evidence_id": "market-evidence",
                    "evidence_version": "v2",
                    "entity_id": "market",
                    "trade_date": "2026-10-11",
                    "quality_status": "PASS",
                    "calc_version": "market-v1",
                    "config_hash": "c" * 64,
                    "content_hash": "d" * 64,
                }
            ],
            "warnings": [],
            "readiness": {"ready": True, "code": "READY"},
        },
    )


def _fact() -> dict[str, Any]:
    return {
        "claim_id": "fact-market",
        "claim_type": "FACT",
        "text": "模型原文 999 不可信。",
        "evidence_ids": ["market-evidence"],
        "structured_facts": [
            {
                "path": "records.0.market_score",
                "value": 65,
                "unit": "score",
                "trade_date": "2026-10-11",
                "entity": "market",
            }
        ],
        "quality_status": "UNKNOWN",
    }


def _inference(**changes) -> dict[str, Any]:
    value = {
        "claim_id": "inference-market",
        "claim_type": "INFERENCE",
        "text": "模型声称确定上涨 88%。",
        "evidence_ids": ["market-evidence"],
        "structured_facts": [],
        "quality_status": "UNKNOWN",
        "inference": {
            "hypothesis": "POSSIBLE_REGIME_SENSITIVITY",
            "supporting_claim_ids": ["fact-market"],
            "uncertainties": ["CAUSALITY_NOT_ESTABLISHED"],
            "limitations": [
                "HISTORICAL_EVIDENCE_ONLY",
                "NOT_A_RETURN_GUARANTEE",
            ],
        },
    }
    value.update(changes)
    return value


def _compile(claims: list[dict[str, Any]]):
    return EvidenceCompiler(max_answer_chars=8000).compile(
        final_text=json.dumps(
            {
                "answer": "模型原始回答不应展示。",
                "evidence_ids": ["market-evidence"],
                "claims": claims,
                "warnings": [],
                "needs_clarification": False,
            },
            ensure_ascii=False,
        ),
        tool_results=[_context()],
        inherited_warnings=[],
    )


def test_verified_fact_supports_bounded_template_inference() -> None:
    compiled = _compile([_fact(), _inference()])
    inference = next(item for item in compiled.claims if item.claim_type == "INFERENCE")

    assert compiled.insufficient_evidence is False
    assert inference.quality_status == "WARNING"
    assert inference.policy_version == "m16.2.2-inference-v1"
    assert inference.reason_codes == ["BOUNDED_QUALITATIVE_INFERENCE"]
    assert inference.verified_fact_refs == [
        "market-evidence:records.0.market_score"
    ]
    assert "可能" in inference.text
    assert "确定上涨" not in compiled.answer
    assert "88" not in compiled.answer


def test_unknown_supporting_claim_id_rejects_inference_but_keeps_fact() -> None:
    inference = _inference()
    inference["inference"]["supporting_claim_ids"] = ["forged-claim"]
    compiled = _compile([_fact(), inference])

    assert compiled.insufficient_evidence is True
    assert [item.claim_id for item in compiled.claims] == ["fact-market"]
    assert "CLAIM_REJECTED:inference-market:UNKNOWN_SUPPORTING_CLAIM_ID" in (
        compiled.warnings
    )
    assert "records.0.market_score=65" in compiled.answer


def test_inference_cannot_use_evidence_not_owned_by_supporting_claim() -> None:
    inference = _inference(evidence_ids=["forged-evidence"])
    compiled = _compile([_fact(), inference])
    assert compiled.insufficient_evidence is True
    assert "CLAIM_REJECTED:inference-market:UNKNOWN_EVIDENCE_ID" in compiled.warnings


def test_empty_inference_references_are_rejected() -> None:
    inference = _inference(evidence_ids=[])
    compiled = _compile([_fact(), inference])
    assert compiled.insufficient_evidence is True
    assert "CLAIM_REJECTED:inference-market:MISSING_EVIDENCE" in compiled.warnings


def test_legacy_inference_remains_safe_and_never_echoes_provider_text() -> None:
    legacy = _inference()
    legacy.pop("inference")
    compiled = _compile([legacy])
    assert compiled.insufficient_evidence is False
    assert compiled.claims[0].reason_codes == ["LEGACY_BOUNDED_INFERENCE"]
    assert "确定上涨" not in compiled.answer
    assert "有限推断" in compiled.answer
