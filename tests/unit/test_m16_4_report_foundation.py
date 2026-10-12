import uuid
from datetime import date

import pytest
from app.core.agent_report_config import AgentReportConfig
from app.domain.agent.chat import ChatCitation, StructuredClaim, StructuredFact
from app.domain.agent.report import ResearchReportSnapshot
from app.domain.agent.report_errors import AgentReportError
from app.services.agent.report.canonical import canonical_hash
from app.services.agent.report.comparison import compare_report_snapshots
from app.services.agent.report.render import render_html, render_markdown
from app.services.agent.report.snapshot import build_report_snapshot

CHAT_ID = uuid.UUID("00000000-0000-0000-0000-000000000101")
MESSAGE_ID = uuid.UUID("00000000-0000-0000-0000-000000000102")
TURN_ID = uuid.UUID("00000000-0000-0000-0000-000000000103")


def _citation(evidence_id: str = "ev-1") -> dict[str, object]:
    return ChatCitation(
        marker="[1]",
        evidence_id=evidence_id,
        evidence_version="v2",
        tool_name="market.snapshot",
        entity_id="run-1",
        as_of_date=date(2026, 10, 10),
        calc_run_id="run-1",
        calc_version="m14-v1",
        config_hash="a" * 64,
        source_hash="b" * 64,
    ).model_dump(mode="json")


def _claim(
    value: str | float = "0.12", *, entity: str = "run-1", role: str = "LIVE"
) -> dict[str, object]:
    return StructuredClaim(
        claim_id="claim-1",
        claim_type="FACT",
        text="收益率为 12%",
        evidence_ids=["ev-1"],
        structured_facts=[
            StructuredFact(
                path="records.0.market_score",
                value=value,
                unit="score",
                trade_date=date(2026, 10, 10),
                entity=entity,
                sample_role=role,
            )
        ],
        quality_status="PASS",
    ).model_dump(mode="json")


def _snapshot(
    value: str, *, report_type: str = "strategy_review", role: str = "LIVE"
) -> ResearchReportSnapshot:
    snapshot, _ = build_report_snapshot(
        report_type=report_type,
        title="确定性报告",
        source_chat_id=CHAT_ID,
        source_message_id=MESSAGE_ID,
        source_turn_id=TURN_ID,
        source_metadata={
            "answer_status": "COMPLETED",
            "verified_claims": [_claim(value, role=role)],
            "citations": [_citation()],
        },
        config=AgentReportConfig(),
    )
    return snapshot


def test_snapshot_is_deterministic_and_records_claim_only_limitations() -> None:
    snapshot, contract = build_report_snapshot(
        report_type="strategy_review",
        title=None,
        source_chat_id=CHAT_ID,
        source_message_id=MESSAGE_ID,
        source_turn_id=TURN_ID,
        source_metadata={
            "answer_status": "COMPLETED",
            "verified_claims": [_claim(0.12)],
            "citations": [_citation()],
        },
        config=AgentReportConfig(),
    )
    dumped = snapshot.model_dump(mode="json")
    assert canonical_hash(dumped) == canonical_hash(dict(reversed(list(dumped.items()))))
    assert snapshot.snapshot_level == "CLAIM_SNAPSHOT_ONLY"
    assert snapshot.charts[0].chart_type == "table"
    assert "SERIES_NOT_AVAILABLE" in snapshot.warnings
    assert contract.limitations == ["SOURCE_PAYLOAD_NOT_ARCHIVED", "REPLAY_UNAVAILABLE"]


def test_missing_archived_evidence_cannot_be_promoted_to_a_report() -> None:
    with pytest.raises(AgentReportError, match="fully cited") as error:
        build_report_snapshot(
            report_type="market_review",
            title=None,
            source_chat_id=CHAT_ID,
            source_message_id=MESSAGE_ID,
            source_turn_id=TURN_ID,
            source_metadata={
                "answer_status": "COMPLETED",
                "verified_claims": [_claim()],
                "citations": [],
            },
            config=AgentReportConfig(),
        )
    assert error.value.code == "INSUFFICIENT_VERIFIED_FACTS"


def test_partial_verified_keeps_rejections_visible() -> None:
    snapshot, _ = build_report_snapshot(
        report_type="market_review",
        title="部分验证",
        source_chat_id=CHAT_ID,
        source_message_id=MESSAGE_ID,
        source_turn_id=TURN_ID,
        source_metadata={
            "verified_claims": [_claim()],
            "rejected_claims": [
                {
                    "claim_id": "claim-2",
                    "claim_type": "FACT",
                    "reason_codes": ["QUALITY_BLOCKED"],
                }
            ],
            "citations": [_citation()],
        },
        config=AgentReportConfig(),
    )
    assert snapshot.source_answer_status == "PARTIAL_VERIFIED"
    assert snapshot.rejected_claims[0].reason_codes == ["QUALITY_BLOCKED"]


def test_comparison_only_emits_decimal_delta_when_comparable() -> None:
    _, contract = build_report_snapshot(
        report_type="strategy_review",
        title=None,
        source_chat_id=CHAT_ID,
        source_message_id=MESSAGE_ID,
        source_turn_id=TURN_ID,
        source_metadata={"verified_claims": [_claim()], "citations": [_citation()]},
        config=AgentReportConfig(),
    )
    state, reasons, result = compare_report_snapshots(
        _snapshot("0.10"),
        _snapshot("0.12"),
        max_facts=100,
        left_contract=contract,
        right_contract=contract,
    )
    assert state == "COMPARABLE"
    assert reasons == []
    assert result["facts"][0]["delta"] == "0.02"

    state, reasons, result = compare_report_snapshots(
        _snapshot("0.10", role="TRAIN"),
        _snapshot("0.12", role="OOS"),
        max_facts=100,
    )
    assert state in {"CONTEXT_REQUIRED", "INCOMPATIBLE"}
    assert all("delta" not in row for row in result["facts"])


def test_exports_are_stable_and_html_escapes_claim_text() -> None:
    snapshot = _snapshot("0.12")
    snapshot.claims[0].text = "<script>alert(1)</script>"
    digest = canonical_hash(snapshot.model_dump(mode="json"))
    markdown = render_markdown(snapshot, digest)
    html = render_html(snapshot, digest)
    assert render_markdown(snapshot, digest) == markdown
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert digest in markdown
