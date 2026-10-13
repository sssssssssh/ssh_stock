import uuid
from copy import deepcopy

import pytest
from app.core.agent_frozen_contract_config import AgentFrozenContractConfig
from app.core.config import get_settings
from app.domain.agent.chat import ChatCitation, StructuredClaim
from app.domain.agent.report import ResearchReportSnapshot
from app.services.agent.contracts.integrity import verify_contract_archive
from app.services.agent.contracts.policy import compare_frozen_research
from m16_6_fixtures import synthetic_m14
from test_m16_6_contract_integrity import synthetic_archive


def report_and_verification(body, unit="decimal", context=False):
    manifest, rows, base = synthetic_archive(body)
    verification = verify_contract_archive(manifest, rows, base, AgentFrozenContractConfig())
    verification.check["archive_integrity"] = {"status": "VERIFIED"}
    verification.check["frozen_fact_recheck"] = {"status": "VERIFIED"}
    ref = body["evidence"][0]
    citation = ChatCitation(
        marker="[1]",
        evidence_id=ref["evidence_id"],
        evidence_version="v2",
        tool_name="performance.summary",
        entity_id=body["selected"]["run_id"],
        as_of_date=body["comparison_contract"]["end_date"],
        report_id=ref["report_id"],
        calc_run_id=body["selected"]["run_id"],
        content_hash=ref["content_hash"],
    )
    value = body["record"]["performance"]["annualized_return"]
    if unit == "percent":
        from decimal import Decimal

        value = str(Decimal(value) * 100)
    facts = [
        {
            "path": "records.0.performance.annualized_return",
            "value": value,
            "unit": unit,
            "trade_date": citation.as_of_date,
            "entity": citation.entity_id,
            "sample_role": "LIVE",
        }
    ]
    if context:
        facts.append(
            {
                **facts[0],
                "path": "records.0.performance.start_date",
                "value": body["comparison_contract"]["start_date"],
                "unit": "date",
            }
        )
    claim = StructuredClaim(
        claim_id="fact",
        claim_type="FACT",
        text="Synthetic test facts",
        evidence_ids=[ref["evidence_id"]],
        structured_facts=facts,
    )
    snapshot = ResearchReportSnapshot(
        report_type="strategy_review",
        title="Synthetic fixture",
        source_answer_status="COMPLETED",
        source_chat_id=uuid.uuid4(),
        source_message_id=uuid.uuid4(),
        claims=[claim],
        citations=[citation],
    )
    return snapshot, verification


def compare(left, right, mode="STRICT_SAME_SAMPLE", max_facts=100):
    return compare_frozen_research(
        left[0],
        right[0],
        left_verification=left[1],
        right_verification=right[1],
        max_facts=max_facts,
        comparison_intent="INDEPENDENT_BACKTESTS",
        comparison_mode=mode,
    )


def test_strict_frozen_same_sample_grants_exact_decimal_and_date_is_context_only():
    left = report_and_verification(synthetic_m14(annualized="0.10"), context=True)
    right = report_and_verification(synthetic_m14(annualized="0.12"), context=True)
    state, reasons, result = compare(left, right)
    assert state == "COMPARABLE" and reasons == []
    assert result["comparison_permissions"]["allowed"] is True
    assert result["facts"][0]["delta"] == "0.02"
    assert result["facts"][0]["comparison_permission"]["allowed"] is True
    assert result["context_facts"]["left"][0]["value_type"] == "DATE"


@pytest.mark.parametrize("mode,limit", [("DIFFERENT_ASSUMPTIONS", 100), ("STRICT_SAME_SAMPLE", 1)])
def test_context_mode_or_resource_truncation_closes_global_and_pair_deltas(mode, limit):
    state, _, result = compare(
        report_and_verification(synthetic_m14()),
        report_and_verification(synthetic_m14()),
        mode,
        limit,
    )
    assert state == "CONTEXT_REQUIRED"
    assert result["comparison_permissions"]["allowed"] is False
    assert all("delta" not in row for row in result["facts"])


def test_different_actual_trade_dates_or_execution_costs_are_context_not_delta():
    left = report_and_verification(synthetic_m14(dates=("2026-01-02", "2026-01-05", "2026-01-07")))
    right = report_and_verification(synthetic_m14(dates=("2026-01-02", "2026-01-06", "2026-01-07")))
    state, reasons, result = compare(left, right)
    assert state == "CONTEXT_REQUIRED" and "TRADE_DATE_SET_MISMATCH" in reasons
    assert all("delta" not in row for row in result["facts"])
    execution = deepcopy(get_settings().execution_config.model_dump(mode="json"))
    execution["trading_cost"]["slippage_bps"] = "10"
    right = report_and_verification(synthetic_m14(execution=execution))
    state, reasons, result = compare(report_and_verification(synthetic_m14()), right)
    assert state == "CONTEXT_REQUIRED" and "EXECUTION_CONFIG_MISMATCH" in reasons
    assert all("delta" not in row for row in result["facts"])


def test_percent_delta_is_explicit_percentage_points_and_failed_fact_check_closes_permission():
    left = report_and_verification(synthetic_m14(annualized="0.1"), "percent")
    right = report_and_verification(synthetic_m14(annualized="0.12"), "percent")
    assert compare(left, right)[2]["facts"][0]["delta"] == "2"
    right[1].check["frozen_fact_recheck"]["status"] = "UNVERIFIABLE"
    result = compare(left, right)[2]
    assert not result["comparison_permissions"]["allowed"] and result["facts"] == []
