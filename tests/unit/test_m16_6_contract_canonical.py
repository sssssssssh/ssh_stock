from datetime import date
from decimal import Decimal

import pytest
from app.domain.agent.frozen_contracts import (
    M14_CONTRACT_VERSION,
    FrozenContractDraft,
)
from app.services.agent.contracts.canonical import contract_hash, contract_json
from app.services.agent.evidence import canonical_content_hash
from pydantic import ValidationError


def test_new_contract_canonical_matches_published_evidence_v2_without_order_drift():
    left = {"amount": Decimal("1.20"), "dates": [date(2026, 10, 1), date(2026, 10, 2)]}
    right = {"dates": [date(2026, 10, 1), date(2026, 10, 2)], "amount": Decimal("1.20")}
    assert contract_json(left) == {"amount": "1.2", "dates": ["2026-10-01", "2026-10-02"]}
    assert contract_hash(left) == contract_hash(right) == canonical_content_hash(left)
    assert contract_hash({"dates": list(reversed(left["dates"]))}) != contract_hash(
        {"dates": left["dates"]}
    )


def test_contract_kind_version_and_study_scope_are_strict():
    valid = dict(
        tool_call_id="call-1",
        contract_kind="M14_EXACT_BUNDLE",
        subject_id="run-1",
        role="LIVE",
        schema_version=M14_CONTRACT_VERSION,
        verification_scope="FROZEN_CONTRACT_RECHECK",
        contract_json={"run_id": "run-1"},
    )
    FrozenContractDraft.model_validate(valid)
    with pytest.raises(ValidationError):
        FrozenContractDraft.model_validate({**valid, "schema_version": "unknown"})
    with pytest.raises(ValidationError):
        FrozenContractDraft.model_validate({**valid, "sql": "SELECT *"})
    with pytest.raises(ValidationError):
        FrozenContractDraft.model_validate(
            {
                **valid,
                "contract_kind": "M15_STUDY_AGGREGATE",
                "schema_version": "m16.6-m15-aggregate-v1",
            }
        )
