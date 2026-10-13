import uuid
from copy import deepcopy
from types import SimpleNamespace

import pytest
from app.domain.agent.frozen_contracts import (
    CONTRACT_MANIFEST_VERSION,
    CONTRACT_REPORT_VERSION,
)
from app.domain.agent.report import CreateReportComparison
from app.domain.agent.report_errors import AgentReportError
from app.services.agent.contracts.integrity import missing_contracts
from app.services.agent.contracts.report_binding import bind_contract_report
from app.services.agent.report.application import AgentReportApplication
from app.services.agent.report.canonical import canonical_hash
from app.services.agent.report.integrity import verify_report
from test_m16_5_report_binding import archived_report


def contract_report():
    # Synthetic GAP fixture: no invented M14 comparability or business source.
    row = archived_report()
    snapshot, contract = verify_report(row)
    contract_id = uuid.uuid4()
    verification = SimpleNamespace(
        manifest=SimpleNamespace(
            id=uuid.uuid4(),
            base_manifest_id=snapshot.archive_reference.manifest_id,
            manifest_hash="c" * 64,
            contract_ids_hash="d" * 64,
            policy_version=CONTRACT_MANIFEST_VERSION,
        ),
        verified={},
        rows={str(contract_id): SimpleNamespace(tool_result_archive_id=uuid.uuid4())},
        check={
            "contract_integrity": {"status": "VERIFIED"},
            "results": [
                {
                    "contract_id": str(contract_id),
                    "contract_kind": "M14_EXACT_BUNDLE",
                    "subject_id": str(uuid.uuid4()),
                    "role": "LIVE",
                    "schema_version": "m16.6-m14-bundle-v1",
                    "contract_hash": "e" * 64,
                    "status": "UNVERIFIABLE",
                    "reason_codes": ["EXACT_M14_BUNDLE_NOT_ARCHIVED"],
                }
            ],
        },
    )
    bind_contract_report(snapshot, contract, verification)
    row.report_version = contract.report_version
    row.source_contract_json = contract.model_dump(mode="json")
    row.snapshot_json = snapshot.model_dump(mode="json")
    row.snapshot_hash = canonical_hash(row.snapshot_json)
    return row


def reseal(row):
    row.snapshot_json["source_contract_hash"] = canonical_hash(row.source_contract_json)
    row.snapshot_hash = canonical_hash(row.snapshot_json)


def test_v4_dual_anchor_gap_and_truthful_reproduction_level():
    snapshot, contract = verify_report(contract_report())
    assert contract.report_version == CONTRACT_REPORT_VERSION
    assert snapshot.archive_reference.manifest_id != snapshot.contract_reference.manifest_id
    assert snapshot.contract_reference.reproduction_level == "FROZEN_CONTRACT_RECHECK"
    assert contract.contract_scope == []
    assert "EXACT_M14_BUNDLE_NOT_ARCHIVED" in contract.gap_codes
    assert "CALCULATION_NOT_REEXECUTED" in contract.limitations


@pytest.mark.parametrize(
    "field",
    [
        "manifest_id",
        "manifest_hash",
        "policy_version",
        "contract_refs_hash",
        "contract_count",
        "contract_scope",
        "gap_codes",
    ],
)
def test_rehashed_v4_broken_double_anchor_rejected(field):
    row = contract_report()
    reference = row.snapshot_json["contract_reference"]
    reference[field] = {
        "manifest_id": str(uuid.uuid4()),
        "manifest_hash": "f" * 64,
        "policy_version": "future",
        "contract_refs_hash": "f" * 64,
        "contract_count": 2,
        "contract_scope": ["M14_EXACT_BUNDLE"],
        "gap_codes": [],
    }[field]
    reseal(row)
    with pytest.raises(AgentReportError):
        verify_report(row)


def test_old_v3_bytes_unchanged_and_cannot_be_elevated_even_with_resealed_hash():
    row = archived_report()
    original = deepcopy(row.snapshot_json)
    original_contract = deepcopy(row.source_contract_json)
    snapshot, contract = verify_report(row)
    assert snapshot.model_dump(mode="json") == original
    assert contract.model_dump(mode="json") == original_contract
    future = contract_report()
    row.snapshot_json["contract_reference"] = future.snapshot_json["contract_reference"]
    row.source_contract_json["contract_manifest_id"] = str(uuid.uuid4())
    reseal(row)
    with pytest.raises(AgentReportError):
        verify_report(row)


def test_old_report_contract_endpoint_never_loads_a_later_child(monkeypatch):
    row = archived_report()
    service = object.__new__(AgentReportApplication)
    service.repo = SimpleNamespace(get_owned_report=lambda **kwargs: row)
    monkeypatch.setattr(service, "_verify_archive", lambda *args: pytest.fail("no backfill"))
    result = service._report_contracts(user=SimpleNamespace(id=uuid.uuid4()), report_id=row.id)
    assert result.check == missing_contracts().check


def test_old_auto_request_preserves_shape_and_modes_are_strict():
    values = dict(left_report_id=uuid.uuid4(), right_report_id=uuid.uuid4(), request_id="same")
    assert "comparison_mode" not in CreateReportComparison(**values).model_dump(mode="json")
    for extra in (
        {"comparison_mode": "unknown"},
        {"comparison_mode": "WINDOW_DEGRADATION", "comparison_intent": "INDEPENDENT_BACKTESTS"},
        {"comparison_mode": "STRICT_SAME_SAMPLE", "comparison_intent": "TRAIN_VS_OOS"},
        {"execute": True},
    ):
        with pytest.raises(ValueError):
            CreateReportComparison(**values, **extra)
