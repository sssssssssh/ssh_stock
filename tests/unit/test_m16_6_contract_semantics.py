import uuid
from copy import deepcopy

import pytest
from app.services.agent.contracts.m14 import m14_contract_body
from app.services.agent.contracts.semantics import _decode, verify_m14
from app.services.performance.analytics_bundle import AnalyticsArtifactBundle, AnalyticsBundleError
from m16_6_fixtures import synthetic_m14


def test_complete_m14_uses_real_identity_validators_and_no_database():
    body = synthetic_m14()
    contract = verify_m14(body)
    assert str(contract.run_id) == body["selected"]["run_id"]
    assert contract.trade_dates == ("2026-01-02", "2026-01-05")


@pytest.mark.parametrize(
    "change",
    [
        lambda body: body["comparison_contract"].update(trade_dates=["2026-01-02", "2026-01-02"]),
        lambda body: body["comparison_contract"].update(trade_dates=["2026-01-05", "2026-01-02"]),
        lambda body: body["comparison_contract"].update(trade_days=3),
        lambda body: body["bundle_rows"]["risk"].update(run_id=str(uuid.uuid4())),
        lambda body: body["bundle_rows"]["period"].update(performance_id=str(uuid.uuid4())),
        lambda body: body["bundle_rows"]["risk"].update(risk_source_hash="0" * 64),
        lambda body: body["record"]["performance"].update(annualized_return="9"),
        lambda body: body["execution_snapshot"]["trading_cost"].update(slippage_bps="999"),
        lambda body: body["comparison_contract"].update(currency="USD"),
        lambda body: body["comparison_contract"].update(frequency="WEEKLY"),
        lambda body: body["bundle_rows"]["performance"].update(max_drawdown="0.05"),
        lambda body: body["comparison_contract"].update(extra_assumption="default"),
    ],
)
def test_m14_offline_rejects_relations_dates_values_unknown_assumptions_and_sign(change):
    body = deepcopy(synthetic_m14())
    change(body)
    with pytest.raises((ValueError, AnalyticsBundleError)):
        verify_m14(body)


@pytest.mark.parametrize(
    "fault,code",
    [
        ("period", "PERIOD_REPORT_MISSING"),
        ("dates", "PERFORMANCE_DATE_SERIES_INCOMPLETE"),
        ("assumptions", "EXECUTION_ACCOUNTING_SNAPSHOT_INCOMPLETE"),
    ],
)
def test_capture_missing_proof_is_explicit_gap_not_complete(fault, code):
    source = synthetic_m14()
    rows = {name: _decode(values) for name, values in source["bundle_rows"].items()}
    rows["run"].config_snapshot = {
        "execution": source["execution_snapshot"],
        "accounting": source["accounting_snapshot"],
    }
    dates = tuple(source["comparison_contract"]["trade_dates"])
    if fault == "period":
        rows["period"] = None
    elif fault == "dates":
        dates = ()
    else:
        rows["run"].config_snapshot = {}
    body = m14_contract_body(
        AnalyticsArtifactBundle(**rows),
        dates,
        evidence=source["evidence"],
        record=source["record"],
        limitations=[],
    )
    assert body["status"] == "GAP" and body["reason_codes"] == [code]
    assert "comparison_contract" not in body
