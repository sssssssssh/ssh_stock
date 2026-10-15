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


def _draft(number=0, *, payload="gap", subject_length=0):
    from app.domain.agent.frozen_contracts import M14_CONTRACT_VERSION, FrozenContractDraft

    return FrozenContractDraft(
        tool_call_id="call",
        contract_kind="M14_EXACT_BUNDLE",
        subject_id=str(number).ljust(subject_length, "x"),
        role="LIVE",
        schema_version=M14_CONTRACT_VERSION,
        verification_scope="FROZEN_CONTRACT_RECHECK",
        contract_json={"status": "GAP", "reason_codes": [payload]},
    )


def _insert_case(*, permit_writes=False):
    base = SimpleNamespace(
        id=uuid.uuid4(), owner_user_id=uuid.uuid4(), chat_id=uuid.uuid4(),
        turn_id=uuid.uuid4(), manifest_hash="a" * 64,
    )
    tool = SimpleNamespace(
        id=uuid.uuid4(), tool_call_id="call", tool_name="performance.summary", status="READY"
    )

    class DB:
        added = None
        flush_count = 0

        def __init__(self):
            self.added = []

        def scalars(self, query):
            return [tool]

        def add(self, row):
            if not permit_writes:
                pytest.fail("capacity/dependency checks must precede the first add/flush")
            self.added.append(row)

        def flush(self):
            if not permit_writes:
                pytest.fail("capacity/dependency checks must precede the first add/flush")
            self.flush_count += 1
            for row in self.added:
                if row.id is None:
                    row.id = uuid.uuid4()

    return DB(), base, tool


@pytest.mark.parametrize("kind", ["single", "turn", "manifest", "dependency"])
def test_insert_complete_capacity_and_dependencies_checked_before_any_writes(kind):
    config = AgentFrozenContractConfig()
    if kind == "single":
        drafts = [_draft(), _draft(1, payload="x" * config.max_contract_bytes)]
    elif kind == "turn":
        drafts = [_draft(n, payload="x" * 120000) for n in range(9)]
    elif kind == "manifest":
        config = AgentFrozenContractConfig(max_contracts=200)
        drafts = [_draft(n, subject_length=160) for n in range(160)]
    else:
        from app.domain.agent.frozen_contracts import (
            M15_WINDOW_CONTRACT_VERSION,
            FrozenContractDraft,
        )

        drafts = [FrozenContractDraft(
            tool_call_id="call", contract_kind="M15_WINDOW_LINEAGE", subject_id="window",
            role="OOS", schema_version=M15_WINDOW_CONTRACT_VERSION,
            verification_scope="FROZEN_CONTRACT_RECHECK",
            contract_json={"m14_contract_refs": [
                {"subject_id": "missing", "role": "TRAIN", "contract_hash": "f" * 64}
            ]},
        )]
    db, base, tool = _insert_case()
    if kind == "dependency":
        tool.tool_name = "walk_forward.window_lineage"
    with pytest.raises(AgentArchiveError) as caught:
        AgentFrozenContractRepository(db).insert_drafts(
            base_manifest=base, drafts=drafts, config=config
        )
    expected = "CONTRACT_DEPENDENCY_MISMATCH" if kind == "dependency" else "CONTRACT_LIMIT_EXCEEDED"
    assert caught.value.code == expected
    assert db.added == [] and db.flush_count == 0


def test_insert_including_manifest_at_exact_byte_boundary_keeps_original_hash_format():
    from app.services.agent.contracts.canonical import contract_hash, contract_storage_size

    db, base, _ = _insert_case(permit_writes=True)
    drafts = [_draft(0, payload="x" * 65000)]
    repo = AgentFrozenContractRepository(db)
    manifest = repo.insert_drafts(
        base_manifest=base, drafts=drafts, config=AgentFrozenContractConfig()
    )
    row = db.added[0]
    ref = manifest.manifest_json["contracts"][0]
    assert ref["id"] == str(row.id)
    assert ref["contract_hash"] == contract_hash(drafts[0].contract_json) == row.contract_hash
    assert manifest.contract_ids_hash == contract_hash([ref])
    assert manifest.manifest_hash == contract_hash(manifest.manifest_json)
    size = contract_storage_size(row.contract_json) + contract_storage_size(manifest.manifest_json)
    assert 65536 <= size <= 1048576
    exact = AgentFrozenContractConfig(max_turn_bytes=size)
    boundary_db, _, _ = _insert_case(permit_writes=True)
    # UUID values differ but their storage lengths are fixed, preserving the exact boundary.
    boundary_db.scalars = db.scalars
    repo = AgentFrozenContractRepository(boundary_db)
    repo.insert_drafts(base_manifest=base, drafts=drafts, config=exact)
    assert len(boundary_db.added) == 2
    refused_db, _, _ = _insert_case()
    refused_db.scalars = db.scalars
    with pytest.raises(AgentArchiveError) as caught:
        AgentFrozenContractRepository(refused_db).insert_drafts(
            base_manifest=base, drafts=drafts,
            config=AgentFrozenContractConfig(max_turn_bytes=size - 1),
        )
    assert caught.value.code == "CONTRACT_LIMIT_EXCEEDED"


@pytest.mark.parametrize("windows,existing,maximum", [(36, 0, 100), (2, 95, 100), (1, 0, 2)])
def test_window_capacity_preflight_rejects_before_loading_any_source(windows, existing, maximum):
    from app.services.agent.contracts.capture import capture_research_contracts

    result = SimpleNamespace(
        status="READY", tool_name="walk_forward.window_lineage", records=[{}] * windows,
    )
    with pytest.raises(AgentArchiveError) as caught:
        capture_research_contracts(
            object(), result, tool_call_id="call", max_trade_dates=5000,
            max_contracts=maximum, existing_contract_count=existing,
        )
    assert caught.value.code == "CONTRACT_LIMIT_EXCEEDED"


def test_window_capacity_uses_runtime_remaining_allowance_without_clamping(monkeypatch):
    from app.services.agent.contracts.capture import capture_research_contracts
    from app.services.agent.contracts.m15 import capture_m15_contracts

    calls = []

    def capture(db, result, **kwargs):
        calls.append(kwargs)
        return ["captured"]

    monkeypatch.setattr("app.services.agent.contracts.m15.capture_m15_contracts", capture)
    result = SimpleNamespace(
        status="READY", tool_name="walk_forward.window_lineage", records=[{}] * 36,
    )
    assert capture_research_contracts(
        object(), result, tool_call_id="call", max_trade_dates=5000,
        max_contracts=200, existing_contract_count=10,
    ) == ["captured"]
    assert calls[0]["max_contracts"] == 190
    with pytest.raises(AgentArchiveError) as caught:
        capture_m15_contracts(
            object(), result, tool_call_id="call", max_trade_dates=5000, max_contracts=100
        )
    assert caught.value.code == "CONTRACT_LIMIT_EXCEEDED"


def test_prepared_window_dependencies_keep_existing_manifest_order_and_canonical_hashes():
    from copy import deepcopy

    from app.domain.agent.frozen_contracts import (
        CONTRACT_MANIFEST_VERSION,
        M15_WINDOW_CONTRACT_VERSION,
        FrozenContractDraft,
    )
    from app.services.agent.contracts.canonical import contract_hash, contract_json

    train = _draft().model_copy(update={"subject_id": "train", "role": "TRAIN"})
    oos = _draft().model_copy(update={"subject_id": "oos", "role": "OOS"})
    window = FrozenContractDraft(
        tool_call_id="call", contract_kind="M15_WINDOW_LINEAGE", subject_id="window",
        role="OOS", schema_version=M15_WINDOW_CONTRACT_VERSION,
        verification_scope="FROZEN_CONTRACT_RECHECK",
        contract_json={"m14_contract_refs": [
            {"subject_id": endpoint.subject_id, "role": endpoint.role,
             "contract_hash": contract_hash(endpoint.contract_json)}
            for endpoint in (train, oos)
        ]},
    )
    drafts = [window, train, oos]
    before = deepcopy([draft.model_dump() for draft in drafts])
    db, base, tool = _insert_case(permit_writes=True)
    tool.tool_name = "walk_forward.window_lineage"
    manifest = AgentFrozenContractRepository(db).insert_drafts(
        base_manifest=base, drafts=drafts, config=AgentFrozenContractConfig()
    )
    by_subject = {row.subject_id: row for row in db.added[:-1]}
    refs = [
        {
            "id": str(by_subject[draft.subject_id].id), "tool_call_id": "call",
            "tool_result_archive_id": str(tool.id), "contract_kind": draft.contract_kind,
            "subject_id": draft.subject_id, "role": draft.role,
            "schema_version": draft.schema_version,
            "contract_hash": contract_hash(draft.contract_json),
        }
        for draft in (oos, train, window)
    ]
    refs[-1]["dependencies"] = [
        {key: refs[index][key] for key in ("id", "role", "contract_hash")} for index in (1, 0)
    ]
    expected = {
        "policy_version": CONTRACT_MANIFEST_VERSION,
        "base_manifest_id": str(base.id), "base_manifest_hash": base.manifest_hash,
        "owner_user_id": str(base.owner_user_id), "chat_id": str(base.chat_id),
        "turn_id": str(base.turn_id), "contract_count": 3,
        "contract_ids_hash": contract_hash(refs), "contracts": refs,
    }
    assert manifest.manifest_json == contract_json(expected)
    assert manifest.manifest_hash == contract_hash(expected)
    assert manifest.contract_ids_hash == contract_hash(refs)
    assert [draft.model_dump() for draft in drafts] == before
    assert all(row.contract_hash == contract_hash(row.contract_json) for row in db.added[:-1])
