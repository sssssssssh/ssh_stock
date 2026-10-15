import time
import uuid
from copy import deepcopy
from types import SimpleNamespace

import pytest
from app.core.agent_frozen_contract_config import AgentFrozenContractConfig
from app.core.agent_report_config import AgentReportConfig
from app.domain.agent.archive import AgentArchiveError
from app.domain.agent.report_errors import AgentReportError
from app.services.agent.contracts.application import AgentFrozenContractApplication
from app.services.agent.contracts.projection import safe_contract_projection
from app.services.agent.contracts.report_binding import contract_report_refs
from app.services.agent.report.application import AgentReportApplication
from app.services.agent.report.integrity import verify_report
from app.services.agent.report.render import render_html, render_markdown
from test_m16_4_1_integrity import stored_report
from test_m16_5_report_binding import archived_report
from test_m16_6_report_binding import contract_report


def export_case(monkeypatch):
    row = contract_report()
    snapshot, contract = verify_report(row)
    refs = contract.contract_refs
    verification = SimpleNamespace(
        manifest=SimpleNamespace(
            contract_ids_hash=snapshot.contract_reference.contract_ids_hash,
        ),
        rows={
            str(ref.contract_id): SimpleNamespace(
                tool_result_archive_id=ref.tool_result_archive_id,
                contract_kind=ref.contract_kind,
                schema_version=ref.schema_version,
                verification_scope="FROZEN_CONTRACT_RECHECK",
                contract_json={"status": "GAP", "reason_codes": ref.reason_codes},
            )
            for ref in refs
        },
        verified={},
        check={
            "results": [
                ref.model_dump(mode="json", exclude={"tool_result_archive_id"}) for ref in refs
            ]
        },
    )
    calls = {"archive": [], "contracts": [], "owned": []}
    corrupt = SimpleNamespace(value=False)

    class Archive:
        def __init__(self, db, settings):
            pass

        def report_bundle(self, **kwargs):
            calls["archive"].append(self._deadline)
            return row, snapshot, object()

    class Contracts:
        def __init__(self, db, settings):
            pass

        def check_turn(self, **kwargs):
            calls["contracts"].append(kwargs["deadline"])
            if corrupt.value:
                raise AgentArchiveError("CONTRACT_SET_MISMATCH", "invalid", status_code=409)
            if time.monotonic() >= kwargs["deadline"]:
                raise AgentArchiveError("CONTRACT_VERIFY_TIMEOUT", "expired", status_code=504)
            return verification

    monkeypatch.setattr("app.services.agent.report.application.AgentArchiveApplication", Archive)
    monkeypatch.setattr(
        "app.services.agent.report.application.AgentFrozenContractApplication", Contracts
    )
    settings = SimpleNamespace(
        agent_config=SimpleNamespace(
            reports=AgentReportConfig(), frozen_contract=AgentFrozenContractConfig()
        )
    )
    service = AgentReportApplication(SimpleNamespace(), settings)

    def owned(**kwargs):
        calls["owned"].append(kwargs)
        return row if kwargs["owner_user_id"] == row.owner_user_id else None

    service.repo = SimpleNamespace(get_owned_report=owned)
    return service, row, verification, calls, corrupt


@pytest.mark.parametrize("fmt,renderer", [("markdown", render_markdown), ("html", render_html)])
def test_export_verifies_once_and_preserves_frozen_hashes_and_exact_bytes(
    monkeypatch, fmt, renderer,
):
    service, row, verification, calls, _ = export_case(monkeypatch)
    before = deepcopy((row.snapshot_json, row.source_contract_json, row.snapshot_hash))
    snapshot, _ = verify_report(row)
    projections = [
        {
            "metadata": ref.model_dump(mode="json"),
            "projection": safe_contract_projection(verification.rows[str(ref.contract_id)]),
        }
        for ref in contract_report_refs(verification)
    ]
    expected = renderer(snapshot, row.snapshot_hash, projections).encode("utf-8")
    content, media_type, filename = service.export_report(
        user=SimpleNamespace(id=row.owner_user_id), report_id=row.id, export_format=fmt
    )
    assert len(calls["contracts"]) == len(calls["archive"]) == 1
    assert len(calls["owned"]) == 1
    assert calls["contracts"] == calls["archive"]
    assert content.encode("utf-8") == expected
    assert (row.snapshot_json, row.source_contract_json, row.snapshot_hash) == before
    assert media_type.endswith("charset=utf-8")
    assert filename.endswith(".md" if fmt == "markdown" else ".html")


def test_each_export_rechecks_even_on_same_application_instance(monkeypatch):
    service, row, _, calls, corrupt = export_case(monkeypatch)
    args = dict(user=SimpleNamespace(id=row.owner_user_id), report_id=row.id, export_format="html")
    service.export_report(**args)
    corrupt.value = True
    with pytest.raises(AgentReportError) as caught:
        service.export_report(**args)
    assert caught.value.code == "CONTRACT_SET_MISMATCH"
    assert len(calls["contracts"]) == len(calls["archive"]) == 2


def test_export_deadline_is_not_reset_after_base_archive_read(monkeypatch):
    service, row, _, calls, _ = export_case(monkeypatch)
    clock = SimpleNamespace(value=10)
    monkeypatch.setattr(
        "app.services.agent.report.application.time", SimpleNamespace(monotonic=lambda: clock.value)
    )

    class SlowArchive:
        def __init__(self, db, settings):
            pass

        def report_bundle(self, **kwargs):
            calls["archive"].append(self._deadline)
            clock.value = 16
            return row, None, object()

    monkeypatch.setattr(
        "app.services.agent.report.application.AgentArchiveApplication", SlowArchive
    )
    monkeypatch.setattr(
        "app.services.agent.report.application.AgentFrozenContractApplication",
        # The real checker rejects the expired budget before touching the fake DB.
        AgentFrozenContractApplication,
    )
    monkeypatch.setattr(
        "app.services.agent.contracts.application.time",
        SimpleNamespace(monotonic=lambda: clock.value),
    )
    with pytest.raises(AgentReportError) as caught:
        service.export_report(
            user=SimpleNamespace(id=row.owner_user_id), report_id=row.id, export_format="html"
        )
    assert caught.value.code == "CONTRACT_VERIFY_TIMEOUT"
    assert calls["archive"] == [15]


@pytest.mark.parametrize(
    "factory", [lambda: stored_report(legacy=True), stored_report, archived_report]
)
def test_legacy_exports_do_not_load_later_frozen_contracts(monkeypatch, factory):
    service, _, _, _, _ = export_case(monkeypatch)
    row = factory()
    service.repo = SimpleNamespace(get_owned_report=lambda **kwargs: row)
    monkeypatch.setattr(service, "_verify_archive", lambda *args, **kwargs: None)
    snapshot, _ = verify_report(row)
    content, _, _ = service.export_report(
        user=SimpleNamespace(id=row.owner_user_id), report_id=row.id, export_format="markdown"
    )
    assert content == render_markdown(snapshot, row.snapshot_hash)


def test_export_owner_is_checked_before_loading_evidence(monkeypatch):
    service, row, _, calls, _ = export_case(monkeypatch)
    with pytest.raises(AgentReportError) as caught:
        service.export_report(user=SimpleNamespace(id=uuid.uuid4()), report_id=row.id,
                              export_format="html")
    assert caught.value.status_code == 404
    assert calls["archive"] == calls["contracts"] == []
