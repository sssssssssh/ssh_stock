import time
import uuid
from types import SimpleNamespace

import pytest
from app.core.agent_frozen_contract_config import AgentFrozenContractConfig
from app.domain.agent.archive import AgentArchiveError
from app.repositories.agent_frozen_contract import AgentFrozenContractRepository
from app.services.agent.contracts.application import AgentFrozenContractApplication
from app.services.agent.contracts.canonical import remember_contract_evidence
from app.services.agent.contracts.integrity import verify_contract_archive
from test_m16_6_contract_integrity import synthetic_archive


@pytest.mark.parametrize("count,size", [(101, 1), (1, 1048577)])
def test_preflight_limits_refuse_before_loading_contract_json(count, size):
    class DB:
        def scalar(self, query):
            return SimpleNamespace(contract_count=count)

        def execute(self, query):
            return SimpleNamespace(one=lambda: (count, size))

        def scalars(self, query):
            pytest.fail("large JSON rows must not be fetched")

    with pytest.raises(AgentArchiveError) as caught:
        AgentFrozenContractRepository(DB()).load_for_turn(
            owner_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            config=AgentFrozenContractConfig(),
        )
    assert caught.value.code == "CONTRACT_LIMIT_EXCEEDED"


def test_expired_shared_deadline_refuses_before_database_access():
    settings = SimpleNamespace(
        agent_config=SimpleNamespace(frozen_contract=AgentFrozenContractConfig())
    )
    with pytest.raises(AgentArchiveError) as caught:
        AgentFrozenContractApplication(None, settings).check_turn(
            owner_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            deadline=time.monotonic() - 1,
        )
    assert caught.value.status_code == 504


def test_offline_contract_check_observes_budget_callback():
    manifest, rows, base = synthetic_archive()

    def expired():
        raise AgentArchiveError("CONTRACT_VERIFY_TIMEOUT", "synthetic budget", status_code=504)

    with pytest.raises(AgentArchiveError) as caught:
        verify_contract_archive(manifest, rows, base, AgentFrozenContractConfig(), expired)
    assert caught.value.status_code == 504


def test_private_contract_conflict_with_same_evidence_subject_role_is_rejected_before_sql():
    from copy import deepcopy

    _, rows, _ = synthetic_archive()
    first = rows[0]
    second = deepcopy(first)
    second.contract_json["bundle_rows"]["run"]["initial_cash"] = "2000000"
    second.contract_json["comparison_contract"]["initial_cash"] = "2000000"
    with pytest.raises(AgentArchiveError) as caught:
        AgentFrozenContractRepository(object()).insert_drafts(
            base_manifest=None,
            drafts=[first, second],
            config=AgentFrozenContractConfig(),
        )
    assert caught.value.code == "CONTRACT_EVIDENCE_CONFLICT"


def test_cache_identical_contract_or_distinct_endpoint_role_is_not_a_conflict():
    from copy import deepcopy

    _, rows, _ = synthetic_archive()
    first = rows[0]
    seen = {}
    remember_contract_evidence(first, seen)
    remember_contract_evidence(deepcopy(first), seen)
    endpoint = deepcopy(first)
    endpoint.role = "OOS"
    endpoint.contract_json["record"] = {"window_metrics": {"annualized_return": "0.2"}}
    remember_contract_evidence(endpoint, seen)
    assert len(seen) == 2


def test_report_base_and_child_contract_reads_share_one_deadline(monkeypatch):
    from app.domain.agent.report_errors import AgentReportError
    from app.services.agent.report.application import AgentReportApplication

    clock = SimpleNamespace(value=10)
    timer = SimpleNamespace(monotonic=lambda: clock.value)
    monkeypatch.setattr("app.services.agent.report.application.time", timer)
    monkeypatch.setattr("app.services.agent.contracts.application.time", timer)

    class BaseArchive:
        def __init__(self, db, settings):
            pass

        def report_bundle(self, **kwargs):
            assert self._deadline == 15
            clock.value = 16
            return None, None, object()

    monkeypatch.setattr(
        "app.services.agent.report.application.AgentArchiveApplication", BaseArchive
    )
    settings = SimpleNamespace(
        agent_config=SimpleNamespace(frozen_contract=AgentFrozenContractConfig())
    )
    service = object.__new__(AgentReportApplication)
    service.settings = settings
    service.db = None
    row = SimpleNamespace(
        id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        source_turn_id=uuid.uuid4(),
        snapshot_json={"archive_reference": {}, "contract_reference": {}},
    )
    with pytest.raises(AgentReportError) as caught:
        service._verify_archive(row)
    assert caught.value.status_code == 504
    assert caught.value.code == "CONTRACT_VERIFY_TIMEOUT"
