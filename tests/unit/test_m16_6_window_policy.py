import uuid
from types import SimpleNamespace

from app.domain.agent.chat import ChatCitation, StructuredClaim
from app.domain.agent.report import ResearchReportSnapshot
from app.services.agent.contracts.integrity import ContractVerification
from app.services.agent.contracts.policy import compare_frozen_research
from app.services.agent.contracts.semantics import verify_m14, verify_m15
from m16_6_fixtures import synthetic_m15


def window_report(body, endpoints, role):
    for endpoint in endpoints.values():
        verify_m14(endpoint)
    verify_m15(body, endpoints)
    ids = {key: str(uuid.uuid4()) for key in ("TRAIN", "OOS", "STUDY")}
    bodies = {ids["TRAIN"]: endpoints["TRAIN"], ids["OOS"]: endpoints["OOS"], ids["STUDY"]: body}
    rows = {
        ids[key]: SimpleNamespace(
            role=key,
            subject_id=endpoints[key]["selected"]["run_id"] if key != "STUDY" else "window",
            contract_kind="M14_EXACT_BUNDLE" if key != "STUDY" else "M15_WINDOW_LINEAGE",
        )
        for key in ids
    }
    verification = ContractVerification(
        check={
            key: {"status": "VERIFIED"}
            for key in (
                "archive_integrity",
                "frozen_fact_recheck",
                "contract_integrity",
                "contract_semantics",
            )
        },
        rows=rows,
        verified=bodies,
    )
    ref = body["evidence"][0]
    citation = ChatCitation(
        marker="[1]",
        evidence_id=ref["evidence_id"],
        evidence_version="v2",
        tool_name="walk_forward.window_lineage",
        entity_id=f"{body['study']['id']}:window:1",
        as_of_date=body["window"]["test_end_date"],
        report_id=body["validation"]["id"],
        content_hash=ref["content_hash"],
    )
    prefix = "train" if role == "TRAIN" else "oos"
    facts = [
        {
            "path": f"records.0.{prefix}_metrics.{key}",
            "value": value,
            "unit": "decimal",
            "trade_date": citation.as_of_date,
            "entity": citation.entity_id,
            "sample_role": role,
        }
        for key, value in body["record"][prefix + "_metrics"].items()
        if value is not None
    ]
    snapshot = ResearchReportSnapshot(
        report_type="oos_review",
        title="Synthetic window",
        source_answer_status="COMPLETED",
        source_chat_id=uuid.uuid4(),
        source_message_id=uuid.uuid4(),
        citations=[citation],
        claims=[
            StructuredClaim(
                claim_id="window-fact",
                claim_type="FACT",
                text="Synthetic window",
                evidence_ids=[ref["evidence_id"]],
                structured_facts=facts,
            )
        ],
    )
    return snapshot, verification


def test_window_degradation_is_explicit_and_does_not_use_generic_right_minus_left():
    body, endpoints = synthetic_m15()
    left, right = window_report(body, endpoints, "TRAIN"), window_report(body, endpoints, "OOS")
    state, reasons, result = compare_frozen_research(
        left[0],
        right[0],
        left_verification=left[1],
        right_verification=right[1],
        max_facts=100,
        comparison_intent="TRAIN_VS_OOS",
        comparison_mode="WINDOW_DEGRADATION",
    )
    assert state == "COMPARABLE" and reasons == []
    rows = {row["metric_key"]: row for row in result["facts"]}
    assert rows["annualized_return"]["delta"] == "0.12"
    assert rows["annualized_return"]["formula"] == "TRAIN_MINUS_OOS"
    assert rows["max_drawdown_abs"]["formula"] == "OOS_MINUS_TRAIN"
    assert result["sample_context"]["limitations"] == [
        "DIFFERENT_TRAIN_OOS_SAMPLES",
        "NO_GENERAL_ROI_RANKING",
    ]


def test_two_real_different_windows_cannot_be_paired_by_similar_dates():
    a, b = synthetic_m15(), synthetic_m15()
    left, right = window_report(*a, "TRAIN"), window_report(*b, "OOS")
    state, reasons, result = compare_frozen_research(
        left[0],
        right[0],
        left_verification=left[1],
        right_verification=right[1],
        max_facts=100,
        comparison_intent="TRAIN_VS_OOS",
        comparison_mode="WINDOW_DEGRADATION",
    )
    assert state == "INCOMPATIBLE" and "FROZEN_WINDOW_CONTRACT_MISMATCH" in reasons
    assert result["facts"] == [] and not result["comparison_permissions"]["allowed"]
