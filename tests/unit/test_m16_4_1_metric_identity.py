import uuid
from datetime import date

import pytest
from app.core.agent_report_config import AgentReportConfig
from app.domain.agent.chat import ChatCitation, StructuredClaim, StructuredFact
from app.services.agent.report.canonical import canonical_hash
from app.services.agent.report.comparison import compare_report_snapshots
from app.services.agent.report.snapshot import build_report_snapshot


def report(
    items,
    *,
    day="2026-10-10",
    tool="opportunity.list",
    path="score",
    unit="score",
    role="LIVE",
    source="b" * 64,
    config="a" * 64,
):
    claims, citations = [], []
    for index, (entity, value) in enumerate(items):
        eid = f"ev-{entity}-{index}"
        citations.append(
            ChatCitation(
                marker=f"E{index}",
                evidence_id=eid,
                evidence_version="v2",
                tool_name=tool,
                entity_id=entity,
                as_of_date=date.fromisoformat(day),
                calc_version="v1",
                config_hash=config,
                source_hash=source,
                calc_run_id=f"calc-{entity}",
            ).model_dump(mode="json")
        )
        claims.append(
            StructuredClaim(
                claim_id=f"c-{index}",
                claim_type="FACT",
                text="verified",
                evidence_ids=[eid],
                quality_status="PASS",
                structured_facts=[
                    StructuredFact(
                        path=f"records.{index}.{path}",
                        value=value,
                        unit=unit,
                        entity=entity,
                        trade_date=date.fromisoformat(day),
                        sample_role=role,
                    )
                ],
            ).model_dump(mode="json")
        )
    return build_report_snapshot(
        report_type="market_review",
        title="test",
        source_chat_id=uuid.uuid4(),
        source_message_id=uuid.uuid4(),
        source_turn_id=uuid.uuid4(),
        source_metadata={"verified_claims": claims, "citations": citations},
        config=AgentReportConfig(),
    )


def compare(a, b, **kwargs):
    return compare_report_snapshots(
        a[0], b[0], left_contract=a[1], right_contract=b[1], max_facts=100, **kwargs
    )


def no_delta(result):
    assert all("delta" not in row for row in result[2]["facts"])


def test_reverse_stock_order_aligns_by_entity_and_permutations_are_stable():
    a = report([("A", "10"), ("B", "20")])
    b = report([("B", "21"), ("A", "12")])
    result = compare(a, b)
    assert result[0] == "COMPARABLE"
    assert [
        (row["left_fact"]["metric_identity"]["entity_id"], row["delta"])
        for row in result[2]["facts"]
    ] == [("A", "2"), ("B", "1")]
    before = canonical_hash(result[2])
    for snapshot, contract in (a, b):
        snapshot.claims.reverse()
        snapshot.citations.reverse()
        contract.evidence_identities.reverse()
    assert canonical_hash(compare(a, b)[2]) == before


def test_duplicate_conflict_cannot_hide_behind_another_legal_pair():
    a = report([("A", "10"), ("A", "11"), ("B", "20")])
    result = compare(a, report([("A", "12"), ("B", "21")]))
    assert result[0] == "INCOMPATIBLE"
    assert "DUPLICATE_METRIC_AMBIGUOUS" in result[1]
    assert result[2]["facts"][0]["left_fact"]["metric_identity"]["entity_id"] == "B"
    no_delta(result)


def test_identical_duplicates_are_deduplicated_only_with_same_evidence():
    a = report([("A", "10")])
    duplicate = a[0].claims[0].model_copy(deep=True)
    duplicate.claim_id = "duplicate"
    a[0].claims.append(duplicate)
    result = compare(a, report([("A", "12")]))
    assert result[0] == "COMPARABLE"
    assert result[2]["facts"][0]["left_fact"]["claim_ids"] == ["c-0", "duplicate"]


@pytest.mark.parametrize(
    "right_options",
    [
        {"tool": "sector.top", "path": "heat_score"},
        {"role": "OOS"},
        {"path": "trend_score"},
        {"unit": "decimal"},
    ],
)
def test_different_entity_kind_role_full_path_or_unit_never_match(right_options):
    result = compare(report([("A", "10")]), report([("A", "12")], **right_options))
    assert result[0] == "INCOMPATIBLE"
    assert "NO_COMPARABLE_FACTS" in result[1]
    no_delta(result)


def test_different_entities_are_unmatched_not_a_shared_metric():
    result = compare(report([("A", "10")]), report([("B", "12")]))
    assert result[0] == "INCOMPATIBLE"
    assert "UNMATCHED_METRICS" in result[1]
    assert result[2]["unmatched_facts"]["left"][0]["metric_identity"]["entity_id"] == "A"
    assert result[2]["unmatched_facts"]["right"][0]["metric_identity"]["entity_id"] == "B"
    no_delta(result)


def test_historical_dates_and_source_changes_are_context_not_blanket_mismatch():
    result = compare(
        report([("A", "10")]),
        report([("A", "12")], day="2026-10-11", source="c" * 64),
        comparison_intent="SAME_ENTITY_OVER_TIME",
    )
    assert result[0] == "CONTEXT_REQUIRED"
    assert result[1] == ["AS_OF_DATE_MISMATCH", "SOURCE_HASH_CHANGED"]
    assert result[2]["facts"][0]["left_fact"]["trade_date"] == "2026-10-10"
    no_delta(result)


@pytest.mark.parametrize("intent", ["AUTO", "INDEPENDENT_BACKTESTS"])
def test_cross_run_pairs_keep_distinct_runs_but_require_frozen_m14_bundle(intent):
    result = compare(
        report(
            [("run-A", "0.1")],
            tool="performance.summary",
            path="performance.annualized_return",
            unit="decimal",
        ),
        report(
            [("run-B", "0.2")],
            tool="performance.summary",
            path="performance.annualized_return",
            unit="decimal",
        ),
        comparison_intent=intent,
    )
    assert result[0] == "INCOMPATIBLE"
    assert "EXACT_M14_BUNDLE_REQUIRED" in result[1]
    assert len(result[2]["facts"]) == 1
    assert result[2]["facts"][0]["left_fact"]["metric_identity"]["entity_id"] == "run-A"
    no_delta(result)


def test_train_oos_paths_and_roles_require_real_archived_window_lineage():
    result = compare(
        report(
            [("window", "0.1")],
            tool="walk_forward.window_lineage",
            path="train_metrics.annualized_return",
            unit="decimal",
            role="TRAIN",
        ),
        report(
            [("window", "0.2")],
            tool="walk_forward.window_lineage",
            path="oos_metrics.annualized_return",
            unit="decimal",
            role="OOS",
        ),
    )
    assert result[0] == "INCOMPATIBLE"
    assert "FROZEN_M15_WINDOW_LINEAGE_REQUIRED" in result[1]
    assert result[2]["facts"] == []
    no_delta(result)


def test_unresolved_multiple_citations_and_legacy_path_are_blocked():
    a = report([("A", "10")])
    ref = a[0].citations[0].model_copy(deep=True)
    ref.evidence_id = "other-ev"
    a[0].citations.append(ref)
    a[0].claims[0].evidence_ids.append(ref.evidence_id)
    result = compare(a, report([("A", "12")]))
    assert "UNRESOLVED_EVIDENCE_BINDING" in result[1]
    no_delta(result)
    result = compare(report([("A", "10")], path="unknown.score"), report([("A", "12")]))
    assert "LEGACY_METRIC_IDENTITY_INCOMPLETE" in result[1]
    no_delta(result)


@pytest.mark.parametrize(
    "options, code",
    [
        ({"config": "c" * 64}, "CALCULATION_IDENTITY_MISMATCH"),
        ({"source": None}, "CALCULATION_IDENTITY_MISSING"),
        ({"source": "c" * 64}, "SOURCE_HASH_CHANGED"),
    ],
)
def test_source_contract_per_pair_gate(options, code):
    result = compare(report([("A", "10")]), report([("A", "12")], **options))
    assert code in result[1]
    no_delta(result)


def test_explicit_cross_entity_intent_does_not_grant_delta_or_ranking():
    result = compare(
        report([("A", "10")]), report([("A", "12")]), comparison_intent="CROSS_ENTITY_SAME_DATE"
    )
    assert result[0] == "CONTEXT_REQUIRED"
    assert "EXPLICIT_ENTITY_PAIR_MAPPING_REQUIRED" in result[1]
    no_delta(result)


def test_resource_limit_disables_deltas_instead_of_silently_claiming_complete():
    a = report([("A", "10"), ("B", "20")])
    b = report([("A", "12"), ("B", "21")])
    result = compare_report_snapshots(
        a[0], b[0], left_contract=a[1], right_contract=b[1], max_facts=1
    )
    assert result[0] == "CONTEXT_REQUIRED"
    assert "COMPARISON_FACTS_TRUNCATED" in result[1]
    no_delta(result)


def test_daily_and_monthly_counts_never_share_a_metric_identity():
    result = compare(
        report(
            [("run", "20")], tool="performance.summary", path="performance.trade_days", unit="count"
        ),
        report([("run", "2")], tool="performance.summary", path="period.month_count", unit="count"),
    )
    assert result[2]["facts"] == []
    assert "NO_COMPARABLE_FACTS" in result[1]
    no_delta(result)


def test_same_entity_both_train_and_oos_are_distinct_candidates():
    a = report([("A", "10")], role="TRAIN")
    other = a[0].claims[0].model_copy(deep=True)
    other.claim_id = "oos"
    other.structured_facts[0].sample_role = "OOS"
    other.structured_facts[0].value = "12"
    a[0].claims.append(other)
    from app.services.agent.report.metric_identity import collect_facts

    inventory = collect_facts(a[0])
    assert {key.sample_role for key in inventory.unique} == {"TRAIN", "OOS"}
    assert not inventory.issues
    result = compare(a, report([("A", "11")], role="TRAIN"))
    assert "FROZEN_M15_WINDOW_LINEAGE_REQUIRED" in result[1]
    no_delta(result)
