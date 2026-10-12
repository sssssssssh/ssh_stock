import uuid
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.core.agent_report_config import AgentReportConfig
from app.domain.agent.report import (
    CreateReportComparison,
    CreateResearchReport,
    ReportComparisonView,
)
from app.domain.agent.report_errors import AgentReportError
from app.services.agent.report.application import AgentReportApplication, _comparison_view
from app.services.agent.report.canonical import canonical_hash
from app.services.agent.report.comparison import compare_report_snapshots
from app.services.agent.report.comparison_policy import REPORT_COMPARISON_POLICY_VERSION
from app.services.agent.report.integrity import verify_comparison, verify_report
from test_m16_4_1_metric_identity import report


def stored_report(value="10", *, legacy=False):
    snapshot, contract = report([("A", value)])
    if legacy:
        data = snapshot.model_dump(mode="json", exclude={"source_contract_hash"})
        data["schema_version"] = "m16.4-report-snapshot-v1"
    else:
        data = snapshot.model_dump(mode="json")
    return SimpleNamespace(
        id=uuid.uuid4(),
        owner_user_id=uuid.UUID(int=1),
        snapshot_json=data,
        snapshot_hash=canonical_hash(data),
        source_contract_json=contract.model_dump(mode="json"),
        report_type=snapshot.report_type,
        report_version=contract.report_version,
        title=snapshot.title,
        as_of_date=snapshot.as_of_date,
        source_chat_id=snapshot.source_chat_id,
        source_message_id=snapshot.source_message_id,
        source_turn_id=snapshot.source_turn_id,
        source_answer_status=snapshot.source_answer_status,
        parent_report_id=None,
        request_hash="a" * 64,
        archived_at=None,
        created_at=datetime.now(UTC),
    )


def stored_comparison(left, right, *, legacy=False):
    a, ac = verify_report(left)
    b, bc = verify_report(right)
    state, reasons, result = compare_report_snapshots(
        a, b, left_contract=ac, right_contract=bc, max_facts=100
    )
    policy = "m16.2.2-comparison-v1" if legacy else REPORT_COMPARISON_POLICY_VERSION
    result.update(
        policy_version=policy,
        left_report_id=str(left.id),
        right_report_id=str(right.id),
        left_snapshot_hash=left.snapshot_hash,
        right_snapshot_hash=right.snapshot_hash,
    )
    return SimpleNamespace(
        id=uuid.uuid4(),
        owner_user_id=left.owner_user_id,
        left_report_id=left.id,
        right_report_id=right.id,
        result_json=result,
        comparison_hash=canonical_hash(result),
        policy_version=policy,
        state=state,
        reason_codes_json=reasons,
        request_hash="a" * 64,
        left_snapshot_hash=left.snapshot_hash,
        right_snapshot_hash=right.snapshot_hash,
        created_at=datetime.now(UTC),
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_valid_report_and_comparison_integrity_preserves_exact_history(legacy):
    a, b = stored_report(legacy=legacy), stored_report("12", legacy=legacy)
    before = deepcopy(a.snapshot_json)
    row = stored_comparison(a, b, legacy=legacy)
    verify_comparison(row, a, b)
    assert a.snapshot_json == before
    assert canonical_hash(a.snapshot_json) == a.snapshot_hash


@pytest.mark.parametrize(
    "field, value",
    [
        ("title", "tampered"),
        ("report_type", "strategy_review"),
        ("source_chat_id", uuid.UUID(int=333)),
        ("source_message_id", uuid.UUID(int=334)),
        ("source_turn_id", uuid.UUID(int=335)),
        ("report_version", "unknown"),
        ("source_answer_status", "PARTIAL_VERIFIED"),
        ("as_of_date", None),
    ],
)
def test_report_metadata_tamper_is_rejected(field, value):
    row = stored_report()
    setattr(row, field, value)
    with pytest.raises(AgentReportError) as error:
        verify_report(row)
    assert error.value.code == "REPORT_SNAPSHOT_INTEGRITY_ERROR"
    assert error.value.status_code == 409


@pytest.mark.parametrize("legacy", [False, True])
def test_changed_source_contract_is_rejected_without_claiming_legacy_hash_coverage(legacy):
    row = stored_report(legacy=legacy)
    row.source_contract_json["evidence_identities"][0]["source_hash"] = "d" * 64
    with pytest.raises(AgentReportError) as error:
        verify_report(row)
    assert error.value.code == "REPORT_SNAPSHOT_INTEGRITY_ERROR"


def test_unresolved_legacy_metric_stays_readable_and_exportable():
    row = stored_report(legacy=True)
    row.snapshot_json["claims"][0]["structured_facts"][0]["path"] = "records.0.unknown.score"
    row.snapshot_hash = canonical_hash(row.snapshot_json)
    assert verify_report(row)[0].claims


@pytest.mark.parametrize(
    "fault", ["delta", "left_pointer", "left_hash", "state", "reasons", "policy", "contract"]
)
def test_comparison_hash_metadata_and_frozen_report_bindings(fault):
    a, b = stored_report(), stored_report("12")
    row = stored_comparison(a, b)
    if fault == "delta":
        row.result_json["facts"][0]["delta"] = "999"
    elif fault == "left_pointer":
        row.left_report_id = b.id
    elif fault == "left_hash":
        row.left_snapshot_hash = "d" * 64
    elif fault == "state":
        row.state = "INCOMPATIBLE"
    elif fault == "reasons":
        row.reason_codes_json = ["tampered"]
    elif fault == "policy":
        row.policy_version = "tampered"
    else:
        row.result_json["source_contract_hashes"]["left"] = "d" * 64
        row.comparison_hash = canonical_hash(row.result_json)
    with pytest.raises(AgentReportError) as error:
        verify_comparison(row, a, b)
    assert error.value.code == "REPORT_COMPARISON_INTEGRITY_ERROR"


def test_legacy_display_gate_hides_delta_without_changing_frozen_result():
    a, b = stored_report(legacy=True), stored_report("12", legacy=True)
    row = stored_comparison(a, b, legacy=True)
    before = deepcopy(row.result_json)
    verify_comparison(row, a, b)
    view = _comparison_view(row)
    assert view.result == before == row.result_json
    assert view.display_safety["legacy_policy"] is True
    assert view.display_safety["delta_allowed"] is False
    assert "delta" not in view.display_result["facts"][0]
    old_response = view.model_dump(mode="json", exclude={"display_safety", "display_result"})
    assert ReportComparisonView.model_validate(old_response).result == before


def application(a, b=None, comparison=None):
    service = AgentReportApplication(
        SimpleNamespace(),
        SimpleNamespace(agent_config=SimpleNamespace(reports=AgentReportConfig())),
    )
    reports = {row.id: row for row in (a, b) if row is not None}
    service.repo = SimpleNamespace(
        get_owned_report=lambda **kw: reports.get(kw["report_id"]),
        get_by_request=lambda **kw: a,
        get_comparison_by_request=lambda **kw: comparison,
        get_owned_comparison=lambda **kw: comparison,
    )
    return service


@pytest.mark.parametrize("operation", ["detail", "export", "compare", "replay", "archive"])
def test_report_tamper_blocks_every_application_read_boundary_before_writing(operation):
    a, b = stored_report(), stored_report("12")
    service = application(a, b)
    a.snapshot_json["claims"][0]["structured_facts"][0]["value"] = "999"
    user = SimpleNamespace(id=a.owner_user_id)
    body = CreateResearchReport(
        source_chat_id=a.source_chat_id,
        source_message_id=a.source_message_id,
        report_type=a.report_type,
        request_id="same",
    )
    a.request_hash = canonical_hash(body.model_dump(mode="json", exclude={"request_id"}))
    operations = {
        "detail": lambda: service.get_report(user=user, report_id=a.id),
        "export": lambda: service.export_report(user=user, report_id=a.id, export_format="html"),
        "compare": lambda: service.create_comparison(
            user=user,
            body=CreateReportComparison(
                left_report_id=a.id, right_report_id=b.id, request_id="compare"
            ),
        ),
        "replay": lambda: service.create_report(user=user, body=body),
        "archive": lambda: service.archive_report(user=user, report_id=a.id),
    }
    with pytest.raises(AgentReportError) as error:
        operations[operation]()
    assert error.value.code == "REPORT_SNAPSHOT_INTEGRITY_ERROR"


@pytest.mark.parametrize("operation", ["detail", "replay"])
def test_comparison_corruption_blocks_detail_and_idempotency(operation):
    a, b = stored_report(), stored_report("12")
    row = stored_comparison(a, b)
    body = CreateReportComparison(left_report_id=a.id, right_report_id=b.id, request_id="same")
    row.request_hash = canonical_hash(
        body.model_dump(mode="json", exclude={"request_id", "comparison_intent"})
    )
    row.result_json["facts"][0]["delta"] = "999"
    service = application(a, b, row)
    with pytest.raises(AgentReportError) as error:
        if operation == "detail":
            service.get_comparison(user=SimpleNamespace(id=a.owner_user_id), comparison_id=row.id)
        else:
            service.create_comparison(user=SimpleNamespace(id=a.owner_user_id), body=body)
    assert error.value.code == "REPORT_COMPARISON_INTEGRITY_ERROR"
