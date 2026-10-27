"""Candidate schedules/rejection only; successful raw projection parsing is Linux L1."""

import pytest
from pydantic import ValidationError

from scripts.a42363_contract import Fault, session_method
from scripts.a42364_protocol_decision import CandidateDecision
from scripts.a42364_session import (
    CandidateSessionExecutor,
    candidate_schedule,
    candidate_specification,
)
from tests.unit.test_a42364_owner import identity
from tests.unit.test_a42364_protocol import payload


def test_AT17_exact_schedule_oids_sql_window_and_separate_owner_cost():
    spec = candidate_specification()
    items = candidate_schedule()
    assert len(items) == 16 and [v["slot"] for v in items if v["kind"] == "PROJECTION"] == [
        6,
        8,
        14,
        16,
    ]
    assert spec["output_oids"] == (25, 16, 25, 1028, 16, 20, 20)
    assert spec["owner_identity_audit"]["queries"] == 2 and spec["sql_count"] == 16
    assert spec["window_ms"] == 2000 and spec["approved"] is False


def test_AT20_driver_cannot_enter_before_external_decision():
    with pytest.raises(Fault, match="EXTERNAL_DECISION_REQUIRED"):
        CandidateSessionExecutor(identity()).execute(object())
    with pytest.raises(Fault, match="METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION"):
        session_method()


@pytest.mark.parametrize(
    "extra", ["approved", "execute", "force", "target_session_settings_observed", "g1_live"]
)
def test_AT38_request_flags_cannot_approve_new_protocol(extra):
    with pytest.raises(ValidationError):
        CandidateDecision(**payload(**{extra: True}))


@pytest.mark.parametrize(
    "version", ["a42361.grant.v1", "a42363.credential.v2", "a42364.external-decision.v2"]
)
def test_AT38_old_or_fabricated_versions_do_not_route(version):
    with pytest.raises(ValidationError):
        CandidateDecision(**payload(version=version))
