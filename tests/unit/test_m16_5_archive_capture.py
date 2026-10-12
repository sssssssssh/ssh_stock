from copy import deepcopy
from datetime import date

import pytest
from app.core.agent_archive_config import AgentArchiveConfig
from app.domain.agent.archive import AgentArchiveError
from app.domain.agent.chat import ChatCitation, StructuredClaim, StructuredFact
from app.domain.agent.contracts import AgentToolResult, MarketSnapshotInput, Readiness
from app.domain.agent.policy import serialized_result
from app.services.agent.archive.canonical import archive_hash
from app.services.agent.archive.capture import assemble_archive
from app.services.agent.archive.projectors import validate_projection
from app.services.agent.chat.orchestrator import ToolResultContext
from app.services.agent.evidence import evidence_ref


def market_context(value="80", call_id="call-a"):
    record = {"market_score": value, "regime": "RISK_ON"}
    ref = evidence_ref(
        layer="FACTOR_TREND",
        source_type="derived_record",
        entity_id="market",
        date_value=date(2026, 1, 2),
        calc_version="market_v1",
        config_hash="a" * 64,
        content=record,
        quality_status="PASS",
    )
    payload = serialized_result(
        AgentToolResult(
            tool_name="market.snapshot",
            status="READY",
            as_of_date=date(2026, 1, 2),
            records=[record],
            evidence=[ref],
            identity={"calc_version": "market_v1", "config_hash": "a" * 64},
            readiness=Readiness(ready=True, code="READY"),
        ),
        max_output_bytes=65536,
    )
    return ToolResultContext(
        call_id,
        "market.snapshot",
        payload,
        arguments={"trade_date": "2026-01-02"},
        input_schema=MarketSnapshotInput.model_json_schema(),
        source_projections={ref.evidence_id: ref._archive_projection},
    )


def claims_for(context):
    eid = context.payload["evidence"][0]["evidence_id"]
    claims = [
        StructuredClaim(
            claim_id="c1",
            claim_type="FACT",
            text="verified",
            quality_status="PASS",
            evidence_ids=[eid],
            structured_facts=[
                StructuredFact(
                    path="records.0.market_score",
                    value=context.payload["records"][0]["market_score"],
                    unit="score",
                    trade_date=date(2026, 1, 2),
                    entity="market",
                    sample_role="LIVE",
                )
            ],
        )
    ]
    citations = [
        ChatCitation(
            marker="E1",
            evidence_id=eid,
            evidence_version="v2",
            tool_name="market.snapshot",
            entity_id="market",
            as_of_date=date(2026, 1, 2),
        )
    ]
    return claims, citations


def assemble(contexts):
    claims, citations = claims_for(contexts[0])
    return assemble_archive(
        tool_results=contexts,
        claims=claims,
        citations=citations,
        config=AgentArchiveConfig(enabled=True),
    )


def test_capture_is_deterministic_and_private_projection_is_not_a_public_field():
    context = market_context()
    draft = assemble([context])
    assert draft.archive_status == "COMPLETE"
    assert archive_hash(draft.model_dump()) == archive_hash(assemble([context]).model_dump())
    assert "_archive_projection" not in str(context.payload)
    assert (
        draft.bindings[0].source_projection_hash == context.payload["evidence"][0]["content_hash"]
    )
    assert draft.bindings[0].record_path == "records.0"


def test_cached_call_retains_two_payload_audits_and_one_evidence_binding():
    context = market_context()
    cached = ToolResultContext(
        "call-b",
        context.tool_name,
        deepcopy(context.payload),
        arguments=context.arguments,
        input_schema=context.input_schema,
        source_projections=context.source_projections,
        cache_origin_call_id="call-a",
    )
    draft = assemble([context, cached])
    assert len(draft.tools) == 2 and len(draft.bindings) == 1
    assert draft.tools[1].cache_origin_call_id == "call-a"


@pytest.mark.parametrize(
    "fault", ["projection", "ref", "unknown_field", "secret", "size", "version"]
)
def test_capture_fails_closed_for_tamper_secrets_limits_and_versions(fault):
    context = market_context()
    eid = context.payload["evidence"][0]["evidence_id"]
    if fault == "projection":
        context.source_projections[eid]["market_score"] = "999"
    elif fault == "ref":
        context.payload["evidence"][0]["content_hash"] = "b" * 64
    elif fault == "unknown_field":
        context.payload["records"][0]["unexpected"] = "not allowed"
    elif fault == "secret":
        context.payload["identity"]["api_key"] = "test-only-secret"
    elif fault == "size":
        context.payload["warnings"] = ["x" * 65536]
    else:
        context.payload["tool_version"] = "2.0"
    with pytest.raises(AgentArchiveError):
        assemble([context])


def test_same_evidence_id_different_payload_is_not_silently_selected():
    context = market_context()
    modified = deepcopy(context.payload)
    modified["warnings"] = ["changed source context"]
    second = ToolResultContext(
        "call-b",
        context.tool_name,
        modified,
        arguments=context.arguments,
        input_schema=context.input_schema,
        source_projections=context.source_projections,
    )
    with pytest.raises(AgentArchiveError) as error:
        assemble([context, second])
    assert error.value.code == "EVIDENCE_DUPLICATE_CONFLICT"


def test_performance_projector_verifies_actual_bundle_content_not_records_approximation():
    identity = {"performance_id": "performance-a"}
    record = {"report_ids": identity, "performance": {"annualized_return": "0.1"}}
    projection = {
        "artifact_type": "PortfolioPerformanceReport",
        "bundle_identity": identity,
        "summary": record,
    }
    ref = evidence_ref(
        layer="STRATEGY_VALIDATION",
        source_type="report",
        entity_id="run-a",
        report_id="performance-a",
        content=projection,
    )
    payload = serialized_result(
        AgentToolResult(
            tool_name="performance.summary",
            status="READY",
            identity=identity,
            records=[record],
            evidence=[ref],
            readiness=Readiness(ready=True, code="READY"),
        ),
        max_output_bytes=65536,
    )
    ref_json = payload["evidence"][0]
    assert validate_projection(payload, ref_json, projection) == "records.0"
    with pytest.raises(AgentArchiveError):
        validate_projection(payload, ref_json, record)


def test_coverage_projector_keeps_original_daily_quality_material():
    summary = {"dataset": "daily", "coverage_rate": "1"}
    projection = {
        "summary": summary,
        "daily": [
            {"trade_date": "2026-01-02", "status": "PASS", "expected_rows": 10, "actual_rows": 10}
        ],
    }
    ref = evidence_ref(
        layer="DATA",
        source_type="dataset",
        entity_id="daily",
        date_value=date(2026, 1, 2),
        content=projection,
    )
    payload = serialized_result(
        AgentToolResult(
            tool_name="data.coverage",
            status="READY",
            records=[{"dataset_coverage": [summary]}],
            evidence=[ref],
            readiness=Readiness(ready=True, code="READY"),
        ),
        max_output_bytes=65536,
    )
    assert (
        validate_projection(payload, payload["evidence"][0], projection)
        == "records.0.dataset_coverage.0"
    )
    changed = deepcopy(projection)
    changed["daily"][0]["actual_rows"] = 9
    with pytest.raises(AgentArchiveError) as error:
        validate_projection(payload, payload["evidence"][0], changed)
    assert error.value.code == "ARCHIVE_EVIDENCE_IDENTITY_MISMATCH"
