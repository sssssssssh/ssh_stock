import uuid
from copy import deepcopy

import pytest
from app.services.agent.contracts.canonical import contract_hash
from app.services.agent.contracts.semantics import verify_m14, verify_m15
from m16_6_fixtures import synthetic_m15


def test_exact_window_contract_rechecks_all_relations_and_m15_decimal_degradation():
    body, endpoints = synthetic_m15()
    for endpoint in endpoints.values():
        verify_m14(endpoint)
    result = verify_m15(body, endpoints)
    assert str(result["return_degradation"]) == "0.12"
    assert result["drawdown_worsening"] == 0


@pytest.mark.parametrize(
    "change",
    [
        lambda body: body["trial"].update(run_id=str(uuid.uuid4())),
        lambda body: body["window"].update(oos_run_id=str(uuid.uuid4())),
        lambda body: body["trial_evaluation"].update(selection_rank=2),
        lambda body: body["validation"].update(study_id=str(uuid.uuid4())),
        lambda body: body["window"].update(window_no=2),
        lambda body: body["window"]["train_trade_dates"].pop(),
        lambda body: body["window"].update(selected_parameter_hash="0" * 64),
        lambda body: body["record"]["degradation"].update({"return": "0.5"}),
        lambda body: body["record"]["oos_metrics"].update(max_drawdown_abs="-0.1"),
        lambda body: body["record"]["train_metrics"].update(sharpe_ratio=None),
    ],
)
def test_window_roles_selection_dates_sign_and_metrics_cannot_be_fabricated(change):
    body, endpoints = synthetic_m15()
    body = deepcopy(body)
    change(body)
    with pytest.raises(ValueError):
        verify_m15(body, endpoints)


def test_null_sharpe_preserved_as_optional_gap_instead_of_zero():
    body, endpoints = synthetic_m15()
    endpoint = endpoints["TRAIN"]
    endpoint["bundle_rows"]["risk"]["sharpe_ratio"] = None
    endpoint["record"]["window_metrics"]["sharpe_ratio"] = None
    body["record"]["train_metrics"]["sharpe_ratio"] = None
    body["record"]["degradation"]["sharpe"] = None
    for ref in body["m14_contract_refs"]:
        ref["contract_hash"] = contract_hash(endpoints[ref["role"]])
    verify_m14(endpoint)
    assert verify_m15(body, endpoints)["sharpe_degradation"] is None
