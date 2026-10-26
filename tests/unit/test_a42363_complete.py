"""Complete-fix L0/DB_MODEL_ONLY contracts; these never open a PG/runtime connection."""

import copy
import os
from types import SimpleNamespace as NS

import pytest

from scripts.a42361_contract import canonical, sha
from scripts.a42363_contract import Fault
from tests.unit.test_a42363_contracts import ModelLedger, ModelStore, scope


def identity():
    from scripts.a42363_identity import FixtureIdentity, Installation

    return FixtureIdentity.derive(scope(), Installation(worker_uid=1010, socket_gid=1011))


def test_CF_AT06_AT07_one_fixture_target_is_derived_from_consumed_scope():
    i = identity()
    assert i.database == "a42361_" + scope().binding.fixture_uuid.replace("-", "")
    assert i.probe_role == "a42363_probe_" + scope().binding.fixture_uuid.replace("-", "")
    assert i.scope_sha256 == sha(canonical(scope().model_dump()))
    assert i.socket_host.endswith("/" + i.socket_name)
    assert i.worker_uid != i.controller_uid


@pytest.mark.parametrize(
    "field", ["database", "probe_role", "socket_host", "epoch", "image_digest"]
)
def test_CF_AT07_changed_identity_rejected_before_capabilities(field):
    i = identity()
    changed = i.model_copy(update={field: "FOREIGN"})
    with pytest.raises(Fault, match="FIXTURE_IDENTITY"):
        changed.verify(scope())


def test_CF_AT11_create_does_not_mean_running_or_pg_ready():
    from scripts.a42363_harness import PgFixtureRuntime

    h = PgFixtureRuntime(identity(), None, None, None)
    assert h.state == "NEW" and h.ready is False
    with pytest.raises(Fault, match="PG_NOT_PREPARED"):
        h.start()
    with pytest.raises(Fault, match="PG_NOT_RUNNING"):
        h.readiness()


def test_CF_AT16_AT17_database_bootstrap_never_hides_extra_sql():
    from scripts.a42363_harness import InitializationPlan

    p = InitializationPlan.build(identity())
    assert len(p.statements) == 9 and p.allowed_sql == 8
    assert p.statements[0].startswith("CREATE DATABASE ")
    with pytest.raises(Fault, match="INIT_BUDGET_INFEASIBLE"):
        p.preflight()


def test_CF_AT34_volume_id_field_alone_cannot_authorize_name_only_api():
    from scripts.a42362_contract import resources
    from scripts.a42363_resources import ResourceDriver

    item = resources(scope())[1]
    driver = ResourceDriver(NS(run=lambda *_: pytest.fail("unsafe rm")), None, None, None)
    raw = dict(
        Name=item.name,
        ID="name-masquerading-as-id",
        CreatedAt="epoch",
        Labels=driver.labels(scope()),
    )
    with pytest.raises(Fault, match="SAFE_DELETE_UNPROVEN"):
        driver.remove(item, raw)


def test_CF_AT29_preexisting_volume_cannot_be_certified_by_successful_create():
    from scripts.a42362_contract import resources
    from scripts.a42363_resources import ResourceDriver

    commands = NS(run=lambda *_, **kw: pytest.fail("preexisting resource must not be created"))
    observer = NS(observe=lambda _: dict(result="PRESENT"))
    driver = ResourceDriver(commands, None, None, observer, identity())
    with pytest.raises(Fault, match="RESOURCE_ALREADY_PRESENT_OR_UNKNOWN"):
        driver.create(resources(scope())[1])


def test_CF_AT43_recreation_between_rounds_invalidates_absence(monkeypatch):
    from scripts.a42363_absence import AbsenceService
    from scripts.a42363_resources import RecoveryEngine
    from tests.unit.test_a42363_contracts import ModelDriver

    s, ledger, driver = scope(), ModelLedger(), ModelDriver()
    engine = RecoveryEngine(ledger, driver)
    engine.create(s)
    engine.recover(s)
    c, e = ModelStore("controller"), ModelStore("absence_auditor")
    c.append(s, "DESTROY_REQUESTED", {})
    c.append(s, "RECONCILED", dict(status="DESTROYED_PENDING_INDEPENDENT_E", destroyed_ns=1))
    scans, observations = [], []
    original = ledger.scan

    def scan(body):
        scans.append(1)
        value = original(body)
        if len(scans) > 1:
            value["events"] = []
            value["snapshot_sha256"] = sha(canonical([]))
        return value

    def observe(item):
        observations.append(1)
        return dict(resource=item.model_dump(), result="ABSENT", observed_ns=10 + len(observations))

    ledger.scan = scan
    with pytest.raises(Fault, match="AUDIT_LEDGER_CHANGED"):
        AbsenceService(NS(observe=observe), e, c, ledger).dispatch(
            "absent", dict(scope=s.model_dump())
        )
    assert not e.rows and len(scans) >= 2


def test_CF_AT50_guardian_armed_before_worker_launch(monkeypatch):
    from scripts import a42363_supervisor as m
    from scripts.a42363_contract import scope_hash

    events = []
    monkeypatch.setattr(m.os, "getuid", lambda: 0)
    monkeypatch.setattr(m, "session_method", lambda: None)
    monkeypatch.setattr(
        m, "FDDeadlineGuardian", lambda *a: events.append("arm") or NS(finish=lambda: None)
    )
    s = scope()
    cg = NS(scope_sha256=scope_hash(s), epoch=s.epoch, kill_fd=-1)
    launcher = NS(launch=lambda *a: events.append("launch") or object())
    manager = m.RootManager(1007, s, cg, launcher, NS())
    manager.dispatch(1007, "run", dict(scope=s.model_dump()))
    assert events == ["arm", "launch"]


def test_CF_AT09_AT10_closed_method_schema_matrix():
    from scripts.a42363_rpc import request_contract
    from scripts.a42363_services import METHODS

    for domain, methods in METHODS.items():
        for method in methods:
            contract = request_contract(domain, method)
            assert contract.domain == domain and contract.method == method
            assert contract.level == "NONQUALIFYING"
            with pytest.raises(Fault, match="RPC_BODY_SCHEMA"):
                contract.validate(dict(scope=scope().model_dump(), argv=["rm", "foreign"]))


def test_CF_AT56_reviewer_rejects_owner_receipt_with_wrong_event():
    from scripts.a42363_contract import receipt
    from scripts.a42363_review import Reviewer
    from scripts.a42363_stores import ReceiptSet
    from tests.integration_offline.test_a42363_process import records

    s = scope()
    values = copy.deepcopy(records(s))
    old = values["pg_owner"]
    values["pg_owner"] = receipt("pg_owner", s, "FORGED_PHASE", old.sequence, old.record)
    sources = {d: NS(read=lambda s, event, value=v: value) for d, v in values.items()}
    with pytest.raises(Fault, match="STATE_PREFIX"):
        Reviewer(ReceiptSet(sources)).review(s, {d: v.model_dump() for d, v in values.items()})


def test_CF_AT25_signed_revocation_requires_full_schema_and_commit(monkeypatch):
    import base64

    from scripts import a42361_deployment as deploy
    from scripts import a42361_trust_verifier as crypto
    from scripts import a42362_service_host as installed
    from scripts.a42362_approval_registry_service import ApprovalRegistryService

    config = NS(
        attestation_public_key_hex="a" * 64,
        openssl_path="MODEL_ONLY",
        openssl_sha256="b" * 64,
        openssl_version="MODEL_ONLY",
    )
    monkeypatch.setattr(installed, "installation", lambda _: config)
    monkeypatch.setattr(deploy, "checked_executable", lambda *a: "MODEL_ONLY")
    monkeypatch.setattr(crypto, "Ed25519Verifier", lambda *a: NS(verify_signature=lambda *a: None))
    raw = dict(
        approval_id=scope().token_id,
        payload_sha256=scope().payload_sha256,
        reason_sha256="c" * 64,
        revision=1,
        expires_at=4102444800,
    )
    writes = []
    repo = NS(write_import=lambda *a: writes.append(a), read=lambda *a: (raw,))
    body = dict(
        kind="REVOCATION",
        record_hex=canonical(raw).hex(),
        signature_base64=base64.b64encode(b"x" * 64).decode(),
    )
    result = ApprovalRegistryService(object(), repo).import_record(body)
    assert result["committed"] is True and len(writes) == 1


def test_CF_AT53_runtime_commands_require_descendant_scope_before_spawn(monkeypatch):
    from scripts.a42363_supervisor import run_installed_command

    monkeypatch.setattr(os, "fork", lambda: pytest.fail("must not spawn"))
    with pytest.raises(Fault, match="COMMAND_SCOPE_REQUIRED"):
        run_installed_command("UNTRUSTED", ("container", "start", "foreign"))


def test_CF_AT52_failed_publication_cannot_leave_final_terminated_receipt():
    from scripts.a42363_supervisor import SupervisorService

    s, store = scope(), ModelStore("supervisor")
    store.append(s, "RUN_ATTEMPTED", {})
    cg = NS(
        scope_sha256=sha(canonical(s.model_dump())),
        epoch=s.epoch,
        terminate=lambda _: dict(execution_scope_terminated=True),
    )

    def fail(_):
        raise Fault("A42363_ARTIFACT_FAILED")

    service = SupervisorService(None, None, cg, store, NS(publish=fail))
    with pytest.raises(Fault, match="ARTIFACT_FAILED"):
        service.dispatch("terminate", dict(scope=s.model_dump()))
    assert "TERMINATED" not in store.rows


@pytest.mark.parametrize(
    "field",
    [
        "worker_uid",
        "scope_sha256",
        "namespace_sha256",
        "container_name",
        "volume_name",
        "secret_name",
        "socket_name",
        "controller_uid",
    ],
)
def test_CF_AT06_all_derived_fields_are_revalidated(field):
    i = identity()
    with pytest.raises(Fault, match="FIXTURE_IDENTITY"):
        i.model_copy(update={field: 9 if field.endswith("uid") else "foreign"}).verify(scope())


def test_CF_AT16_owner_budget_fails_before_opening_any_connection():
    from scripts.a42363_harness import PgFixtureRuntime
    from scripts.a42363_owner import OwnerRuntime, RawOwnerBackend

    i = identity()
    driver = NS(identity=i)
    fixture = PgFixtureRuntime(i, driver, None, None)
    runtime = OwnerRuntime(driver, None, None, None, identity=i, fixture=fixture)
    owner = RawOwnerBackend(lambda *_: pytest.fail("must not connect"), runtime, None)
    with pytest.raises(Fault, match="INIT_BUDGET_INFEASIBLE"):
        owner.initialize(scope())


def test_CF_AT17_harness_preflight_before_first_side_effect():
    from scripts.a42363_harness import PgFixtureRuntime

    bad = NS(create=lambda *_: pytest.fail("must not create"))
    h = PgFixtureRuntime(identity(), bad, bad, bad)
    with pytest.raises(Fault, match="INIT_BUDGET_INFEASIBLE"):
        h.prepare()
    assert h.state == "NEW" and h.first_error is None


@pytest.mark.parametrize("column", [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
def test_CF_AT15_AT18_owner_raw_version_and_each_privilege_are_audited(column):
    from scripts.a42363_owner import RawOwnerBackend
    from tests.integration_offline.test_a42363_process import records

    row = [170001, "DB_MODEL_SYSTEM", *([False] * 6), [], *([False] * 4)]
    row[column] = 160000 if column == 0 else ["pg_monitor"] if column == 8 else True
    r = records(scope())["pg_owner"].record["raw"]
    runtime = NS(
        verify_owner_connection=lambda *_: None,
        inspect_owner=lambda _: {
            k: r[k]
            for k in (
                "image_digest",
                "namespace_sha256",
                "marker_sha256",
                "fixture_uuid",
                "nonce",
                "container_id",
                "volume_id",
                "initialization_commands",
            )
        },
    )
    c = NS(execute=lambda _: NS(fetchone=lambda: row), commit=lambda: None, close=lambda: None)
    store = ModelStore("pg_owner")
    with pytest.raises(Fault, match="PG17_REQUIRED|OWNER_ROLE_ACL"):
        RawOwnerBackend(lambda _: c, runtime, store).initialize(scope())
    assert not store.rows


def test_CF_AT21_candidate_projection_bytes_and_hash_are_doc_only():
    import re
    from pathlib import Path

    from scripts.a4235_calibration_adapter_contract import digest
    from scripts.a4236_g1_probe import ALLOWLIST_SHA, TEMPLATES

    doc = Path("docs/acceptance/a42363_complete_protocol_ADR.md").read_text()
    sql = re.search(r"```sql\n([^\n]+)\n```", doc)[1].encode("ascii")
    assert (
        len(sql) == 406
        and sha(sql) == "2f2f912b70ec0fe9c81c17c9098d8c2208a54e78ba69277bfe49c1bcf5986b56"
    )
    assert ALLOWLIST_SHA == "d0aa6b635b0eb35eb373e0b1fa003593535eac68dd07bc3445b6c80d9ef752f8"
    templates = dict(TEMPLATES, PROJECTION=(sql, sql, (), 8))
    candidate = digest(
        {
            k: dict(
                driver=v[0].hex(),
                protocol=v[1].hex(),
                parameter_oids=v[2],
                max_rows=v[3],
                stage="G1_SYNTHETIC_ONLY",
            )
            for k, v in templates.items()
        }
    )
    assert candidate == "9b4a128a2cfb0c2c44d7eb70ab0e6d311162c902a53a3e96fb34eb0ca130d571"
    assert TEMPLATES["PROJECTION"][0] != sql


def test_CF_AT16_initialization_plan_cannot_accept_a_budget_override():
    from scripts.a42363_harness import InitializationPlan

    p = InitializationPlan.build(identity())
    forged = InitializationPlan(p.identity, p.statements, allowed_sql=9)
    with pytest.raises(Fault, match="INIT_PLAN_CHANGED"):
        forged.preflight()


def test_CF_AT19_preconnect_lease_never_contains_backend_start(tmp_path):
    from scripts.a42363_owner import validate_lease_v2

    with (tmp_path / "L0_fd_model").open("wb") as stream:
        lease = dict(
            version=2,
            scope_sha256=sha(canonical(scope().model_dump())),
            worker_pid=123,
            expires_at=1001,
            credential_fd=stream.fileno(),
            backend_start="guessed",
        )
        with pytest.raises(Fault, match="LEASE_SCHEMA"):
            validate_lease_v2(lease, scope(), 123, 1000)


@pytest.mark.parametrize(
    "field", ["worker_pid", "backend_pid", "role", "namespace_sha256", "connection_generation"]
)
def test_CF_AT20_postconnect_target_drift_stops_before_method_or_sql(field):
    from scripts.a42363_owner import validate_session_v2

    s = scope()
    lease = dict(scope_sha256=sha(canonical(s.model_dump())), worker_pid=123)
    session = dict(
        **lease,
        backend_pid=456,
        backend_start="observed",
        role=identity().probe_role,
        namespace_sha256=s.namespace_sha256,
        connection_generation=1,
        guc_source="BLOCKED",
    )
    session[field] = (
        0 if field in ("worker_pid", "backend_pid", "connection_generation") else "foreign"
    )
    with pytest.raises(Fault, match="SESSION_IDENTITY"):
        validate_session_v2(session, s, lease, identity())


@pytest.mark.parametrize("kind", ["VOLUME", "SECRET", "CONTAINER"])
def test_CF_AT31_nonzero_command_still_cannot_be_washed_by_inspect(kind):
    from scripts.a42362_contract import resources
    from scripts.a42363_resources import ResourceDriver

    calls = []
    driver = ResourceDriver(
        NS(run=lambda *a, **k: (125, b"")),
        None,
        123,
        NS(observe=lambda _: dict(result="ABSENT")),
        identity(),
    )
    driver.inspect = lambda *_: calls.append("inspect")
    with pytest.raises(Fault, match="CREATE_ACK_UNKNOWN"):
        driver.create(next(r for r in resources(scope()) if r.kind == kind))
    assert not calls


@pytest.mark.parametrize(
    "point", ["missing_mount", "read_only_mount", "wrong_source", "wrong_userns"]
)
def test_CF_AT12_socket_mount_and_uid_mapping_are_not_optional(point):
    from scripts.a42363_resources import ResourceDriver

    i = identity()
    raw = dict(
        Mounts=[dict(Destination="/run/postgresql", Source=i.socket_host, RW=True, Type="bind")],
        HostConfig=dict(UsernsMode="keep-id:uid=999,gid=999"),
    )
    if point == "missing_mount":
        raw["Mounts"] = []
    elif point == "read_only_mount":
        raw["Mounts"][0]["RW"] = False
    elif point == "wrong_source":
        raw["Mounts"][0]["Source"] = "/FOREIGN"
    else:
        raw["HostConfig"]["UsernsMode"] = "host"
    with pytest.raises(Fault, match="PG_(SOCKET_MOUNT|UID_MAPPING)_UNPROVEN"):
        ResourceDriver(None, None, None, None, i).verify_socket_mount(raw, i)


@pytest.mark.parametrize("point", ["ack", "not_running", "replacement"])
def test_CF_AT13_AT14_start_failure_is_sticky_and_cannot_be_retried(point):
    import time

    from scripts.a42362_contract import resources
    from scripts.a42363_harness import PgFixtureRuntime

    i = identity()
    calls = []
    raw = dict(ID="a" * 64, Created="original", State=dict(Running=False))

    def run(args):
        calls.append(args)
        if point == "ack":
            return 125, b""
        raw["State"]["Running"] = point != "not_running"
        if point == "replacement":
            raw["ID"] = "b" * 64
        return 0, b""

    driver = NS(inspect=lambda *_: copy.deepcopy(raw), verify=lambda *a: None, commands=NS(run=run))
    h = PgFixtureRuntime(i, driver, None, ModelStore("pg_owner"))
    h.state, h.container_id, h.started_ns = "PREPARED", raw["ID"], time.monotonic_ns()
    h.runtime_identity = h._stable(raw)
    with pytest.raises(Fault):
        h.start()
    assert h.state == "UNKNOWN" and h.first_error and not h.ready
    with pytest.raises(Fault, match="PG_NOT_PREPARED"):
        h.start()
    assert len(calls) == 1
    assert resources(scope())[3].name == i.container_name


def test_CF_AT35_remove_attempt_is_never_reissued_if_e_cannot_prove_absence():
    from scripts.a42363_resources import RecoveryEngine
    from tests.unit.test_a42363_contracts import ModelDriver

    ledger, driver = ModelLedger(), ModelDriver()
    engine = RecoveryEngine(ledger, driver)
    engine.create(scope())
    from scripts.a42362_contract import resources

    for r in resources(scope()):
        engine._event(r, "REMOVE_ATTEMPTED")
    driver.absent = lambda _: False
    result = engine.recover(scope())
    assert not driver.removed and result["status"] == "INCOMPLETE_QUARANTINED"


def test_CF_AT41_missing_delegated_collector_fd_fails_before_runtime_info(tmp_path, monkeypatch):
    from scripts.a42363_absence import DelegatedReadOnlyCollector

    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        expected = dict(observer_uid=1007, controller_uid=1005)
        monkeypatch.setattr(os, "getuid", lambda: 1007)
        collector = DelegatedReadOnlyCollector(
            NS(read=lambda *_: pytest.fail("must not run")), fd, fd, expected, None
        )
        with pytest.raises(Fault, match="READONLY_DELEGATION_REQUIRED"):
            collector.visibility({})
    finally:
        os.close(fd)


@pytest.mark.parametrize(
    "domain,method",
    [
        ("registry", "key-status"),
        ("registry", "import"),
        ("registry", "receipt"),
        ("approval", "approval"),
        ("approval", "receipt"),
        ("approval", "import"),
        ("approval", "revoke"),
        ("consumer", "consume"),
        ("consumer", "receipt"),
        ("consumer", "journal"),
        ("consumer", "resource-append"),
        ("consumer", "resource-scan"),
        ("consumer", "committed-receipt"),
        ("pg_owner", "create"),
        ("pg_owner", "receipt"),
        ("pg_owner", "run"),
        ("controller", "create"),
        ("controller", "destroy"),
        ("controller", "receipt"),
        ("controller", "reconcile"),
        ("absence_auditor", "journal"),
        ("absence_auditor", "absent"),
        ("absence_auditor", "receipt"),
        ("supervisor", "run"),
        ("supervisor", "terminate"),
        ("supervisor", "receipt"),
    ],
)
def test_CF_AT09_AT10_every_method_has_peer_and_closed_body_contract(monkeypatch, domain, method):
    from scripts import a42363_services as host
    from scripts.a42363_rpc import DomainClient

    p = NS(uid=os.getuid(), domain=domain, read_uids=(2001,), operator_uid=2002)
    policy = NS(deployment=object())
    monkeypatch.setattr(host, "installation", lambda _: p)
    monkeypatch.setattr(host, "installed", lambda _: NS(schema_version="a42363.deployment.v2"))
    service = host.ServiceHost(policy, {})
    with pytest.raises(Fault, match="PEER_ACL"):
        service.dispatch(2999, method, {})
    client = DomainClient(domain, NS(call=lambda *_: pytest.fail("must not send")))
    with pytest.raises(Fault, match="RPC_BODY_SCHEMA"):
        client.call(method, dict(DSN="postgresql://FORBIDDEN"))
