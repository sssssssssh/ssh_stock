import uuid
from copy import deepcopy
from types import SimpleNamespace

import pytest
from app.domain.agent.report_errors import AgentReportError
from app.services.agent.report.archive_binding import bind_archive
from app.services.agent.report.canonical import canonical_hash
from app.services.agent.report.integrity import verify_report
from test_m16_4_1_integrity import stored_report


def archived_report():
    row = stored_report()
    snapshot, contract = verify_report(row)
    for claim in snapshot.claims:
        claim.verified_fact_refs = [
            f"{claim.evidence_ids[0]}:{fact.path}" for fact in claim.structured_facts
        ]
    manifest = SimpleNamespace(
        id=uuid.uuid4(),
        manifest_version="m16.5-archive-v1",
        manifest_hash="b" * 64,
        archive_status="COMPLETE",
    )
    bind_archive(snapshot, contract, manifest)
    row.report_version = contract.report_version
    row.source_contract_json = contract.model_dump(mode="json")
    row.snapshot_json = snapshot.model_dump(mode="json")
    row.snapshot_hash = canonical_hash(row.snapshot_json)
    return row


def test_historical_v1_v2_serialization_and_contract_signatures_do_not_change():
    for legacy in (True, False):
        row = stored_report(legacy=legacy)
        original = deepcopy(row.snapshot_json)
        snapshot, contract = verify_report(row)
        dumped = snapshot.model_dump(mode="json")
        if legacy:
            dumped.pop("source_contract_hash")
        assert dumped == original
        assert contract.model_dump(mode="json") == row.source_contract_json
        assert "archive_reference" not in dumped
        assert row.snapshot_hash == canonical_hash(original)


def test_v3_freezes_manifest_scope_and_truthful_limits_without_circular_digest():
    row = archived_report()
    snapshot, contract = verify_report(row)
    assert snapshot.snapshot_level == "FROZEN_TOOL_EVIDENCE"
    assert contract.archive_manifest_hash == snapshot.archive_reference.manifest_hash
    assert snapshot.source_contract_hash == canonical_hash(row.source_contract_json)
    assert "SOURCE_PAYLOAD_NOT_ARCHIVED" not in snapshot.warnings
    assert "CALCULATION_NOT_REEXECUTED" in contract.limitations


@pytest.mark.parametrize("fault", ["reference", "contract", "version", "scope", "fields", "legacy"])
def test_even_rehashed_bad_archive_reference_contract_is_rejected(fault):
    row = archived_report()
    if fault == "reference":
        row.snapshot_json["archive_reference"]["manifest_hash"] = "c" * 64
    elif fault == "contract":
        row.source_contract_json["archive_manifest_hash"] = "c" * 64
    elif fault == "version":
        row.snapshot_json["archive_reference"]["manifest_version"] = "future"
    elif fault == "scope":
        row.source_contract_json["verification_scope"] = []
    elif fault == "fields":
        row.source_contract_json["frozen_fields"] = []
    else:
        row.report_version = row.source_contract_json["report_version"] = "m16.4-v1"
    row.snapshot_json["source_contract_hash"] = canonical_hash(row.source_contract_json)
    row.snapshot_hash = canonical_hash(row.snapshot_json)
    with pytest.raises(AgentReportError):
        verify_report(row)
