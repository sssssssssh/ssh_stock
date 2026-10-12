import pytest
from app.domain.agent.chat import StructuredFact
from app.services.agent.chat.fact_validation import _ClaimValidationError, _compare_value
from test_m16_4_1_metric_identity import compare, no_delta, report


def test_numeric_date_identifier_mixture_retains_numeric_gate_and_context_without_decimal_cast():
    a, b = report([("A", "10")]), report([("A", "12")])
    for snapshot, _ in (a, b):
        claim = snapshot.claims[0]
        claim.structured_facts.append(
            StructuredFact(
                path="records.0.ts_code",
                value="A",
                unit="identifier",
                trade_date=claim.structured_facts[0].trade_date,
                entity="A",
                sample_role="LIVE",
            )
        )
    result = compare(a, b)
    assert result[0] == "COMPARABLE"
    assert result[2]["facts"][0]["delta"] == "2"
    assert result[2]["context_facts"]["left"][0]["value_type"] == "IDENTIFIER"
    assert "delta" not in str(result[2]["context_facts"])
    dates = compare(
        report(
            [("theme", "2026-10-01")], tool="theme.top", path="member_snapshot_date", unit="date"
        ),
        report(
            [("theme", "2026-10-02")], tool="theme.top", path="member_snapshot_date", unit="date"
        ),
    )
    assert dates[0] == "CONTEXT_REQUIRED"
    assert "NON_NUMERIC_METRIC" not in dates[1]
    assert dates[2]["context_facts"]["left"][0]["value_type"] == "DATE"
    no_delta(dates)


@pytest.mark.parametrize("intent", ["AUTO", "CROSS_ENTITY_SAME_DATE"])
def test_actual_a_only_vs_b_only_is_explicit_parallel_context_not_paired_delta(intent):
    result = compare(report([("A", "10")]), report([("B", "12")]), comparison_intent=intent)
    assert result[0] == "CONTEXT_REQUIRED"
    assert "EXPLICIT_ENTITY_PAIR_MAPPING_REQUIRED" in result[1]
    assert "NO_COMPARABLE_FACTS" not in result[1]
    assert result[2]["facts"] == []
    assert result[2]["side_by_side_facts"]["left"][0]["metric_identity"]["entity_id"] == "A"
    assert result[2]["side_by_side_facts"]["right"][0]["metric_identity"]["entity_id"] == "B"
    assert result[2]["delta_policy"] == "DISABLED"


def test_a_b_context_cannot_swallow_unknown_units_or_calculation_identity_conflict():
    assert (
        compare(report([("A", "10")]), report([("B", "12")], config="c" * 64))[0] == "INCOMPATIBLE"
    )
    assert compare(report([("A", "10")]), report([("B", "12")], unit="nav"))[0] == "INCOMPATIBLE"


@pytest.mark.parametrize(
    "unit,value,path",
    [("date", "2026-02-30", "records.0.start_date"), ("identifier", "B", "records.0.ts_code")],
)
def test_shared_validator_rejects_bad_context_fact(unit, value, path):
    with pytest.raises(_ClaimValidationError):
        _compare_value("2026-01-02" if unit == "date" else "A", value, unit, path)
