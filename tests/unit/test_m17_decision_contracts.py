import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from app.core.paper_config import DecisionConfig
from app.domain.decision.contracts import PaperError
from app.domain.decision.requests import CreateObservation, CreateProposal
from app.models.paper import PaperAccount
from app.services.paper.records import (
    make_record,
    open_cutoff,
    source_value,
    utc_now,
    verify_record,
)
from pydantic import ValidationError


def test_strict_decision_inputs_and_independent_policy():
    with pytest.raises(ValidationError):
        CreateObservation(request_id="x", signal_date="2026-10-14", owner_user_id=str(uuid.uuid4()))
    with pytest.raises(ValidationError):
        CreateObservation(request_id="x", signal_date="2026-10-14", include_codes=["000001.SZ"] * 2)
    with pytest.raises(ValidationError):
        DecisionConfig(allowed_stages=("TREND", "TREND"))
    assert "LEFT_REVERSAL" in DecisionConfig().allowed_stages


@pytest.mark.parametrize(
    "values",
    [
        {"target_weight": 0.1},
        {"target_weight": "NaN"},
        {"target_weight": "Infinity"},
        {"target_weight": "1.01"},
        {"mode": "LIVE"},
        {"action": "WATCH", "target_weight": "0.1"},
        {"action": "PROPOSE_BUY", "target_weight": "0"},
        {"source_report_id": str(uuid.uuid4())},
    ],
)
def test_proposal_payload_fail_closed(values):
    body = dict(
        request_id="x",
        account_id=uuid.uuid4(),
        observation_id=uuid.uuid4(),
        ts_code="000001.SZ",
        action="PROPOSE_BUY",
        target_weight="0.1",
    )
    with pytest.raises(ValidationError):
        CreateProposal(**{**body, **values})


def test_record_digest_binds_all_frozen_typed_facts_but_not_mutable_head():
    now = utc_now()
    row = make_record(
        PaperAccount,
        uuid.uuid4(),
        "create",
        now=now,
        name="test",
        initial_cash=Decimal("1000"),
        benchmark_code="000300.SH",
        first_trade_date=now.date() + timedelta(days=1),
        config_version="v1",
        config_hash="a" * 64,
        config_snapshot_json={"schema_version": "v1"},
        request_id="create",
        request_hash="b" * 64,
    )
    assert verify_record(row) == {}
    row.state, row.version = "ACTIVE", 2
    assert verify_record(row) == {}
    row.initial_cash = Decimal("1001")
    with pytest.raises(PaperError, match="INTEGRITY_ERROR"):
        verify_record(row)


def test_raw_float_conversion_is_explicit_and_missing_not_zero():
    assert source_value({"close": 10.1, "missing": None}) == {
        "close": Decimal("10.1"),
        "missing": None,
    }
    with pytest.raises(PaperError, match="SOURCE_INVALID_NUMBER"):
        source_value(float("nan"))
    cutoff = open_cutoff(utc_now().date())
    assert cutoff.hour == 1 and cutoff.minute == 30
