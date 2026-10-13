import uuid
from copy import deepcopy
from types import SimpleNamespace

import pytest
from app.core.agent_report_config import AgentReportConfig
from app.domain.agent.report_errors import AgentReportError
from app.services.agent.report.archive_binding import bind_archive
from app.services.agent.report.canonical import canonical_hash
from app.services.agent.report.integrity import verify_report
from app.services.agent.report.snapshot import build_report_snapshot
from test_m16_2_2_inference import _compile, _fact, _inference
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


def compiled_mixed_report(raw_claims=None):
    compiled = _compile(raw_claims or [_fact(), _inference()])
    row = stored_report()
    snapshot, contract = build_report_snapshot(
        report_type="market_review",
        title="Frozen mixed claims",
        source_chat_id=row.source_chat_id,
        source_message_id=row.source_message_id,
        source_turn_id=row.source_turn_id,
        source_metadata={
            "answer_status": "COMPLETED",
            "verified_claims": [item.model_dump(mode="json") for item in compiled.claims],
            "citations": [item.model_dump(mode="json") for item in compiled.citations],
        },
        config=AgentReportConfig(),
    )
    inference = next(item for item in snapshot.claims if item.claim_type == "INFERENCE")
    assert inference.structured_facts == []
    assert inference.verified_fact_refs == ["market-evidence:records.0.market_score"]
    bind_archive(
        snapshot,
        contract,
        SimpleNamespace(
            id=uuid.uuid4(),
            manifest_version="m16.5-archive-v1",
            manifest_hash="b" * 64,
            archive_status="COMPLETE",
        ),
    )
    row.report_version = contract.report_version
    row.title = snapshot.title
    row.as_of_date = snapshot.as_of_date
    row.snapshot_json = snapshot.model_dump(mode="json")
    row.snapshot_hash = canonical_hash(row.snapshot_json)
    row.source_contract_json = contract.model_dump(mode="json")

    return row


def test_structured_inference_inherits_support_refs_without_direct_facts():
    verified, _ = verify_report(compiled_mixed_report())
    assert [claim.claim_type for claim in verified.claims] == ["FACT", "INFERENCE"]


def test_multiple_supporters_deduplicate_refs_independent_of_fact_input_order():
    first = _fact()
    second = deepcopy(first)
    second["claim_id"] = "fact-second"
    inference = _inference()
    inference["inference"]["supporting_claim_ids"] = ["fact-second", "fact-market"]
    for facts in ([first, second], [second, first]):
        snapshot, _ = verify_report(compiled_mixed_report([*facts, inference]))
        actual = next(claim for claim in snapshot.claims if claim.claim_type == "INFERENCE")
        assert actual.verified_fact_refs == ["market-evidence:records.0.market_score"]


def reseal_mixed_report(row):
    row.source_contract_json["frozen_fields"] = sorted(
        {ref for claim in row.snapshot_json["claims"] for ref in claim["verified_fact_refs"]}
    )
    row.snapshot_json["source_contract_hash"] = canonical_hash(row.source_contract_json)
    row.snapshot_hash = canonical_hash(row.snapshot_json)


@pytest.mark.parametrize(
    "fault, expected_code",
    [
        ("missing_support", "INFERENCE_SUPPORT_UNVERIFIABLE"),
        ("duplicate_support", "INFERENCE_SUPPORT_INVALID"),
        ("self_support", "INFERENCE_SUPPORT_INVALID"),
        ("inference_support", "INFERENCE_SUPPORT_UNVERIFIABLE"),
        ("extra_evidence", "INFERENCE_EVIDENCE_NOT_SUPPORTED"),
        ("extra_ref", "INFERENCE_FIELD_REFS_INVALID"),
        ("wrong_fact_path", "FROZEN_FACT_BINDING_INVALID"),
        ("duplicate_fact_ref", "FROZEN_FACT_BINDING_INVALID"),
        ("swapped_fact_refs", "FROZEN_FACT_BINDING_INVALID"),
        ("legacy_inference", "INFERENCE_SUPPORT_UNVERIFIABLE"),
        ("inference_direct_fact", "INFERENCE_SUPPORT_UNVERIFIABLE"),
        ("duplicate_claim", "DUPLICATE_FROZEN_CLAIM_ID"),
    ],
)
def test_resealed_invalid_mixed_claim_graph_is_rejected(fault, expected_code):
    row = compiled_mixed_report()
    fact, inference = row.snapshot_json["claims"]
    if fault == "missing_support":
        inference["inference"]["supporting_claim_ids"] = ["missing"]
    elif fault == "duplicate_support":
        inference["inference"]["supporting_claim_ids"] = [fact["claim_id"]] * 2
    elif fault == "self_support":
        inference["inference"]["supporting_claim_ids"] = [inference["claim_id"]]
    elif fault == "inference_support":
        fact["claim_type"] = "INFERENCE"
        fact["structured_facts"] = []
        fact["inference"] = deepcopy(inference["inference"])
        fact["inference"]["supporting_claim_ids"] = [inference["claim_id"]]
    elif fault == "extra_evidence":
        inference["evidence_ids"].append("forged-evidence")
    elif fault == "extra_ref":
        inference["verified_fact_refs"].append("market-evidence:records.1.market_score")
    elif fault == "wrong_fact_path":
        fact["verified_fact_refs"] = ["market-evidence:records.1.market_score"]
    elif fault == "duplicate_fact_ref":
        fact["structured_facts"].append(deepcopy(fact["structured_facts"][0]))
        fact["verified_fact_refs"].append(fact["verified_fact_refs"][0])
    elif fault == "swapped_fact_refs":
        second = deepcopy(fact["structured_facts"][0])
        second["path"] = "records.1.market_score"
        fact["structured_facts"].append(second)
        fact["verified_fact_refs"] = [
            "market-evidence:records.1.market_score",
            "market-evidence:records.0.market_score",
        ]
    elif fault == "legacy_inference":
        inference["inference"] = None
    elif fault == "inference_direct_fact":
        inference["structured_facts"] = deepcopy(fact["structured_facts"])
    else:
        inference["claim_id"] = fact["claim_id"]
    reseal_mixed_report(row)
    with pytest.raises(AgentReportError) as error:
        verify_report(row)
    assert error.value.code == expected_code


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
