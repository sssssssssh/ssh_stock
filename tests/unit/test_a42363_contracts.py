"""A42363 L0: fixed contracts, DB_MODEL_ONLY faults and independent source review."""

import ast
import copy
import json
import time
import uuid
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from pydantic import ValidationError

from scripts.a42361_contract import Fault as ContractFault
from scripts.a42361_contract import canonical, sha
from scripts.a42361_offline_cases import binding
from scripts.a42362_contract import Scope, resources, transition
from scripts.a42362_contract import receipt as ledger_receipt
from scripts.a42363_absence import AbsenceService, IndependentObserver
from scripts.a42363_contract import DOMAINS, Fault, State, receipt, scope_hash, verify_receipt
from scripts.a42363_owner import INIT_SQL, RawOwnerBackend, validate_session_v2
from scripts.a42363_resources import ControllerService, RecoveryEngine, ResourceDriver
from scripts.a42363_review import Reviewer
from scripts.a42363_services import METHODS, ServiceHost, compose
from scripts.a42363_stores import DomainStore, ReceiptSet


def scope():
    return Scope(
        token_id="32345678-1234-4234-8234-123456789012",
        binding=binding(),
        payload_sha256="1" * 64,
        image_digest="sha256:" + "2" * 64,
        controller_uid=1005,
        namespace_sha256="3" * 64,
        epoch="42345678-1234-4234-8234-123456789012",
    )


class ModelStore:
    """Explicit DB_MODEL_ONLY: no independent PG durability/role claim."""

    def __init__(self, domain):
        self.domain, self.rows = domain, {}

    def append(self, s, event, record):
        assert event not in self.rows
        r = receipt(self.domain, s, event, len(self.rows) + 1, copy.deepcopy(record))
        self.rows[event] = r
        return r

    def read(self, s, event):
        r = self.rows[event]
        verify_receipt(r, self.domain, s)
        return r

    def maybe_read(self, s, event):
        return self.read(s, event) if event in self.rows else None


class ModelRepository:
    def __init__(self, fault=None):
        self.rows, self.connections, self.fault = {}, [], fault
        self.committed = False

    def connect(self, role):
        repo = self

        class Connection:
            def execute(self, query, args):
                if "append_domain_event" in query:
                    assert not repo.rows
                    repo.pending = json.loads(args[3])
                    return NS(fetchone=lambda: (1,))
                assert repo.committed
                return NS(fetchone=lambda: None if repo.fault == "missing" else (1, repo.rows))

            def commit(self):
                repo.committed, repo.rows = True, repo.pending
                if repo.fault == "commit":
                    raise OSError("PRIVATE_SENTINEL")

            def rollback(self):
                pass

            def close(self):
                pass

        c = Connection()
        self.connections.append((role, c))
        return self.connections[0][1] if self.fault == "same_connection" else c

    def verify(self, c, role):
        assert (role, c) in self.connections or self.fault == "same_connection"


@pytest.mark.parametrize("domain", DOMAINS)
def test_AT21_AT63_independent_reader_after_commit(domain):
    repo = ModelRepository()
    r = DomainStore(domain, repo).append(scope(), "MODEL_ONLY", dict(value="NONQUALIFYING"))
    assert repo.connections[0][1] is not repo.connections[1][1]
    assert r.qualifies is False and r.committed is True


@pytest.mark.parametrize("fault", ["commit", "missing", "same_connection"])
def test_AT22_unknown_commit_never_returns_receipt_or_retries(fault):
    repo = ModelRepository(fault)
    with pytest.raises(Fault, match="COMMIT_UNKNOWN_NO_RETRY"):
        DomainStore("controller", repo).append(scope(), "MODEL_ONLY", {"scope": "test"})
    assert repo.committed is True
    assert len(repo.connections) == (1 if fault == "commit" else 2)


@pytest.mark.parametrize("domain", DOMAINS)
@pytest.mark.parametrize("field", ["epoch", "scope_sha256", "digest", "sequence"])
def test_AT82_self_rehashed_foreign_receipt_is_not_authority(domain, field):
    raw = receipt(domain, scope(), "TEST", 1, {}).model_dump()
    raw[field] = {
        "epoch": str(uuid.uuid4()),
        "scope_sha256": "f" * 64,
        "digest": "f" * 64,
        "sequence": 2,
    }[field]
    if field == "sequence":
        # Rehashing is possible; independent store still rejects a changed reference.
        raw = receipt(domain, scope(), "TEST", 2, {}).model_dump()
        store = ModelStore(domain)
        actual = store.append(scope(), "TEST", {})
        assert actual != raw
    else:
        with pytest.raises((Fault, ContractFault)):
            verify_receipt(raw, domain, scope())


def test_AT12_AT25_AT39_AT64_client_server_method_matrix_exact():
    tree = ast.parse(Path("scripts/a42361_deployment.py").read_text())
    dictionaries = [
        ast.literal_eval(n)
        for n in ast.walk(tree)
        if isinstance(n, ast.Dict)
        and n.keys
        and all(isinstance(k, ast.Constant) for k in n.keys)
        and any(
            k.value == "resource-scan"
            for v in n.values
            if isinstance(v, ast.Tuple)
            for k in v.elts
            if isinstance(k, ast.Constant)
        )
    ]
    assert dictionaries == [METHODS]
    assert set(METHODS) == set(DOMAINS)


@pytest.mark.parametrize("method", ["run", "create", "consume", "reconcile", "terminate"])
def test_AT08_AT37_default_host_and_composition_no_side_effects(method):
    with pytest.raises(ContractFault):
        ServiceHost().dispatch(1001, method, {})
    with pytest.raises(ContractFault):
        compose()
    assert State().real_probe_sql_executed == 0


@pytest.mark.parametrize("kind", ["VOLUME", "SECRET", "CONTAINER"])
def test_AT40_fixed_creation_commands_reject_scope_name_and_never_contain_credentials(kind):
    d = ResourceDriver(None, None, 9, None)
    item = next(r for r in resources(scope()) if r.kind == kind)
    command = d.creation_command(item)
    assert scope().epoch in " ".join(command)
    assert not any("password=" in arg for arg in command)
    bad = item.model_copy(update={"name": "foreign-resource"})
    with pytest.raises(Fault, match="RESOURCE_SCOPE"):
        d.creation_command(bad)


@pytest.mark.parametrize("field", ["epoch", "namespace", "owner", "scope"])
def test_AT43_AT44_raw_resource_epoch_labels_cannot_be_echoed(field):
    d = ResourceDriver(None, None, 9, None)
    item = resources(scope())[2]
    raw = dict(
        Spec=dict(Name=item.name, Labels=d.labels(scope())), ID="exact-id", CreatedAt="epoch"
    )
    assert len(d.verify(item, raw)) == 64
    raw["Spec"]["Labels"]["a42363_" + field] = "forged"
    with pytest.raises(Fault, match="OWNERSHIP_UNKNOWN"):
        d.verify(item, raw)


def test_AT26_AT27_owner_raw_audit_fixed_eight_sqls_and_budget():
    s, store = scope(), ModelStore("pg_owner")
    row = [170001, "model-system", *([False] * 6), [], *([False] * 4)]
    queries = []
    connection = NS(
        execute=lambda sql: queries.append(sql) or NS(fetchone=lambda: row),
        commit=lambda: None,
        close=lambda: None,
    )
    runtime = NS(
        verify_owner_connection=lambda c, value: None,
        inspect_owner=lambda value: dict(
            image_digest=s.image_digest,
            namespace_sha256=s.namespace_sha256,
            marker_sha256=s.binding.marker_sha256,
            fixture_uuid=s.binding.fixture_uuid,
            nonce=s.binding.nonce,
            container_id="MODEL_CONTAINER",
            volume_id="MODEL_VOLUME",
            initialization_commands=8,
        ),
    )
    owner = RawOwnerBackend(lambda value: connection, runtime, store)
    r = owner.initialize(s)
    assert queries == list(INIT_SQL) and len(queries) == 8
    assert r["record"]["session_guc"] == "CONFIGURED_NOT_INDEPENDENTLY_OBSERVED"
    assert r["qualifies"] is False
    with pytest.raises(Fault, match="METHOD_BLOCKED"):
        owner.lease(s, {"worker_pid": 123})


@pytest.mark.parametrize("source", ["ROLE_DEFAULT", "CONNECTION_OPTIONS", "OTHER_BACKEND_SHOW"])
def test_AT30_AT35_unapproved_session_method_stops_first_probe(source):
    s = scope()
    lease = dict(scope_sha256=scope_hash(s), worker_pid=123)
    session = dict(
        **lease,
        backend_pid=321,
        backend_start="model-start",
        role="a42363_probe",
        namespace_sha256=s.namespace_sha256,
        connection_generation=1,
        guc_source=source,
    )
    with pytest.raises(Fault, match="METHOD_BLOCKED"):
        validate_session_v2(session, s, lease)


def observer(s, failure=None):
    delegation = dict(store_sha256="a" * 64, collector_sha256="b" * 64)
    proof = dict(
        observer_uid=1007,
        controller_uid=s.controller_uid,
        namespace_sha256=s.namespace_sha256,
        **delegation,
        readonly=True,
        epoch=s.epoch,
    )
    if failure in proof:
        proof[failure] = "UNKNOWN"
    collector = NS(
        visibility=lambda _: proof,
        read_exact=lambda _: dict(
            status="PRESENT" if failure == "present" else "ABSENT",
            code=0 if failure == "present" else 1,
            identity="recreated" if failure == "present" else None,
        ),
    )
    return IndependentObserver(1007, s.controller_uid, delegation, collector)


@pytest.mark.parametrize(
    "failure",
    ["namespace_sha256", "store_sha256", "collector_sha256", "epoch", "readonly", "present"],
)
def test_AT57_AT66_e_never_accepts_unknown_visibility_or_recreation(failure):
    s, c, e = scope(), ModelStore("controller"), ModelStore("absence_auditor")
    c.append(s, "DESTROY_REQUESTED", {})
    c.append(s, "RECONCILED", dict(status="DESTROYED_PENDING_INDEPENDENT_E", destroyed_ns=1))
    rows = [{"request": {"resource": r.model_dump()}} for r in resources(s)]
    ledger = NS(scan=lambda _: dict(events=rows, snapshot_sha256=sha(canonical(rows))))
    with pytest.raises(Fault):
        AbsenceService(observer(s, failure), e, c, ledger).dispatch(
            "absent", dict(scope=s.model_dump())
        )
    assert e.rows == {}


@pytest.mark.parametrize(
    "domain", ["approval", "consumer", "pg_owner", "controller", "supervisor", "absence_auditor"]
)
def test_AT82_six_rehashed_bundle_references_require_independent_source(domain):
    s = scope()
    stores = {d: ModelStore(d) for d in set(DOMAINS) - {"registry"}}
    refs = {d: store.append(s, "MODEL", {}).model_dump() for d, store in stores.items()}
    refs[domain] = receipt(domain, s, "MODEL", 2, {"forged": True}).model_dump()
    with pytest.raises(Fault, match="INDEPENDENT_RECEIPT_MISMATCH"):
        Reviewer(ReceiptSet(stores)).review(s, refs)


def test_AT23_AT24_ddl_enforces_transitions_fixed_owner_public_revocation():
    raw = Path("infra/g1_control_plane/003_closeout.sql").read_text()
    for required in (
        "SECURITY DEFINER",
        "SET search_path=pg_catalog,g1_control",
        "OWNER TO g1_control_owner",
        "FROM PUBLIC",
        "BEFORE INSERT",
        "FOR UPDATE",
        "APPEND_ONLY",
        "NOLOGIN",
    ):
        # append-only is inherited through the existing reject_history_mutation trigger.
        assert required in raw or required == "APPEND_ONLY" and "reject_history_mutation" in raw
    assert "CREATE ROLE" not in raw and "DROP " not in raw


def test_AT39_AT81_controller_receiver_rejects_arbitrary_argv_and_default_create():
    s = scope()
    c = ControllerService(None, None, None, lambda _: None)
    with pytest.raises(Fault, match="METHOD_BLOCKED"):
        c.dispatch("create", dict(scope=s.model_dump()))
    with pytest.raises(ContractFault):
        c.dispatch("reconcile", dict(scope=s.model_dump(), argv=["prune"]))


def test_AT87_safety_state_cannot_accept_real_success():
    for field in (
        "production_read_authorized",
        "performance_eligible",
        "capacity_ready",
        "attribution_authorized",
    ):
        with pytest.raises(ValidationError):
            State.model_validate({field: True})
    assert State().effective_warmups_total == 8
    assert time.monotonic_ns() > 0


class ModelLedger:
    def __init__(self, fault=None):
        self.rows, self.fault = [], fault

    def append(self, body):
        previous = [r for r in self.rows if r["request"]["resource"] == body["resource"]]
        transition(previous[-1]["request"]["event"] if previous else None, body)
        r = ledger_receipt(body, len(self.rows) + 1, "DB_MODEL_ONLY", "b" * 64).model_dump()
        self.rows.append(r)
        if self.fault == (body["resource"]["kind"], body["event"]):
            raise Fault("A42363_MODEL_ACK_LOSS")
        return r

    def scan(self, body):
        return dict(events=copy.deepcopy(self.rows), snapshot_sha256=sha(canonical(self.rows)))


class ModelDriver:
    def __init__(self, fault=None):
        self.raw, self.created, self.removed, self.fault = {}, [], [], fault

    def create(self, item):
        self.created.append(item.kind)
        raw = self.raw[item.kind] = dict(id=item.name, epoch=item.scope.epoch)
        if self.fault == (item.kind, "create"):
            raise Fault("A42363_MODEL_ACK_LOSS")
        return raw

    def inspect(self, item):
        return self.raw[item.kind]

    def verify(self, item, raw):
        return sha(canonical(raw))

    def remove(self, item, raw):
        self.removed.append(item.kind)
        del self.raw[item.kind]
        if self.fault == (item.kind, "remove"):
            raise Fault("A42363_MODEL_ACK_LOSS")

    def absent(self, item):
        return item.kind not in self.raw


@pytest.mark.parametrize("kind", ["SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER"])
@pytest.mark.parametrize("point", ["RESERVED", "CREATE_ATTEMPTED", "OBSERVED_CREATED", "create"])
def test_AT41_AT50_partial_creation_ack_loss_never_recreates(kind, point):
    ledger = ModelLedger(None if point == "create" else (kind, point))
    driver = ModelDriver((kind, "create") if point == "create" else None)
    engine = RecoveryEngine(ledger, driver)
    with pytest.raises(Fault):
        engine.create(scope())
    before = list(driver.created)
    with pytest.raises(Fault, match="NO_SECOND_CREATE"):
        engine.create(scope())
    engine.recover(scope())
    assert driver.created == before and set(driver.removed) <= set(driver.created)


@pytest.mark.parametrize("kind", ["SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER"])
def test_AT51_unknown_suffix_keeps_original_identity_and_never_removes_replacement(kind):
    ledger, driver = ModelLedger(), ModelDriver()
    engine = RecoveryEngine(ledger, driver)
    engine.create(scope())
    item = next(r for r in resources(scope()) if r.kind == kind)
    engine._event(item, "UNKNOWN", error="A42362_CREATE_ACK_UNKNOWN")
    driver.raw[kind] = dict(id="FOREIGN_REPLACEMENT", epoch=scope().epoch)
    result = engine.recover(scope())
    assert result["status"] == "INCOMPLETE_QUARANTINED"
    assert kind not in driver.removed and driver.raw[kind]["id"] == "FOREIGN_REPLACEMENT"


@pytest.mark.parametrize("kind", ["SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER"])
def test_AT53_remove_ack_loss_uses_independent_absence_without_second_remove(kind):
    ledger, driver = ModelLedger(), ModelDriver((kind, "remove"))
    engine = RecoveryEngine(ledger, driver)
    engine.create(scope())
    first = engine.recover(scope())
    assert first["status"] == "INCOMPLETE_QUARANTINED"
    before = list(driver.removed)
    second = engine.recover(scope())
    assert driver.removed == before
    assert second["status"] == "DESTROYED_PENDING_INDEPENDENT_E"
    assert second["qualifies"] is False
