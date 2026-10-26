"""20261027 review L0/file-DB contracts; no PG, runtime, cgroup or credentials."""

import copy
from types import SimpleNamespace as NS

import pytest

from scripts.a42361_contract import Fault as PreviousFault
from scripts.a42362_contract import resources
from scripts.a42363_contract import Fault, receipt
from scripts.a42363_harness import PgFixtureRuntime
from scripts.a42363_resources import RecoveryEngine, ResourceDriver
from tests.unit.test_a42363_complete import identity
from tests.unit.test_a42363_contracts import ModelDriver, ModelLedger, ModelStore, scope


def raw_resource(kind):
    item = next(r for r in resources(scope()) if r.kind == kind)
    labels = ResourceDriver.labels(scope())
    raw = dict(ID="a" * (25 if kind == "SECRET" else 64), CreatedAt="original")
    if kind == "SECRET":
        raw["Spec"] = dict(Name=item.name, Labels=labels)
    elif kind == "VOLUME":
        raw.update(Name=item.name, Labels=labels, Mountpoint="MODEL_ONLY")
    else:
        raw.update(
            Name=item.name,
            ImageDigest=scope().image_digest,
            Config=dict(User="999:999", Labels=labels),
            HostConfig=dict(
                NetworkMode="none",
                ReadonlyRootfs=True,
                Privileged=False,
                PidsLimit=32,
                Memory=536870912,
                NanoCpus=1000000000,
                CapDrop=["ALL"],
                SecurityOpt=["no-new-privileges"],
                PidMode="private",
                IpcMode="private",
            ),
            Mounts=[dict(Name=resources(scope())[1].name, Destination="/var/lib/postgresql/data")],
        )
    return item, raw


@pytest.mark.parametrize("kind", ["SECRET", "CONTAINER"])
def test_RF_AT06_AT07_existing_re_import_reaches_valid_model_delete(kind):
    item, raw = raw_resource(kind)
    calls = []
    driver = ResourceDriver(NS(run=lambda args: calls.append(args) or (0, b"")), None, None, None)
    driver.remove(item, raw)
    assert calls == [(kind.lower(), "rm", raw["ID"])]


@pytest.mark.parametrize("kind", ["SECRET", "CONTAINER"])
def test_RF_AT07_remove_backend_exception_is_sanitized(kind):
    item, raw = raw_resource(kind)

    def unavailable(_):
        raise OSError("PRIVATE_SENTINEL")

    with pytest.raises(Fault, match="REMOVE_ACK_UNKNOWN") as caught:
        ResourceDriver(NS(run=unavailable), None, None, None).remove(item, raw)
    assert "PRIVATE_SENTINEL" not in str(caught.value)


@pytest.mark.parametrize("kind", ["SECRET", "CONTAINER"])
def test_RF_AT35_driver_cannot_repeat_an_unknown_delete(kind):
    item, raw = raw_resource(kind)
    calls = []
    driver = ResourceDriver(NS(run=lambda args: calls.append(args) or (125, b"")), None, None, None)
    for _ in range(2):
        with pytest.raises(Fault, match="REMOVE_ACK_UNKNOWN|NO_SECOND_REMOVE"):
            driver.remove(item, raw)
    assert len(calls) == 1


def test_RF_AT14_command_budget_has_its_own_pre_effect_denial():
    from scripts.a42363_proposals import InitializationCost

    cost = InitializationCost(sql=0, commands=17)
    assert cost.violations() == ("INITIALIZATION_COMMAND_BUDGET",)
    with pytest.raises(Fault, match="INITIALIZATION_COMMAND_BUDGET"):
        cost.enforce_current()


def test_RF_AT13_AT15_bootstrap_report_counts_both_independent_blockers():
    from scripts.a42363_proposals import BootstrapProposal

    p = BootstrapProposal.fresh(identity())
    assert p.cost.sql >= 9 and p.cost.commands >= 17
    assert p.decision == "NOT_APPROVED" and p.cold_start_p95 is None
    assert set(p.cost.violations()) == {
        "INIT_BUDGET_INFEASIBLE",
        "INITIALIZATION_COMMAND_BUDGET",
        "INITIALIZATION_TIMEOUT",
    }
    assert p.operations and all(o.phase and o.cost_counted for o in p.operations)


def test_RF_AT17_owner_self_hash_does_not_make_raw_audit_or_health():
    s, i = scope(), identity()
    owner = ModelStore("pg_owner")
    forged = owner.append(s, "OWNER_RAW", dict(fixture_identity=i.model_dump(), qualifies=False))
    h = PgFixtureRuntime(i, None, None, ModelStore("controller"), owner)
    h.state = "READY_FOR_OWNER_AUDIT"
    with pytest.raises(Fault, match="OWNER_RAW|PG_|OWNER_HEALTH"):
        h.owner_audited(forged.model_dump())
    assert h.ready is False


def test_RF_AT18_stop_committed_replay_does_no_runtime_calls():
    i, store, calls = identity(), ModelStore("controller"), []
    h = PgFixtureRuntime(i, NS(begin_cleanup=lambda: None), None, store)
    h.container_id, h.state = "a" * 64, "STOPPED"
    h._record("STOPPED", dict(State=dict(Running=False)))
    h._inspect = lambda: calls.append("inspect") or dict(State=dict(Running=False))
    first = h.stop()
    second = h.stop()
    assert first == second and not calls


def test_RF_AT40_uninstalled_e_read_cannot_bypass_visibility(tmp_path):
    import os

    from scripts.a42363_absence import DelegatedReadOnlyCollector

    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    calls = []
    try:
        runner = NS(read=lambda args: calls.append(args) or (1, b""))
        c = DelegatedReadOnlyCollector(runner, fd, fd, {}, None)
        with pytest.raises(Fault, match="READONLY_DELEGATION_REQUIRED"):
            c.read_exact(resources(scope())[1])
        assert not calls
    finally:
        os.close(fd)


def test_RF_AT42_destruction_receipt_drift_after_final_round_blocks_e_commit():
    from scripts.a42363_absence import AbsenceService

    s, ledger, driver = scope(), ModelLedger(), ModelDriver()
    engine = RecoveryEngine(ledger, driver)
    engine.create(s)
    engine.recover(s)
    c, e = ModelStore("controller"), ModelStore("absence_auditor")
    c.append(s, "DESTROY_REQUESTED", {})
    c.append(s, "RECONCILED", dict(status="DESTROYED_PENDING_INDEPENDENT_E", destroyed_ns=1))
    reads, count = [], []

    def read(value, event):
        reads.append(event)
        r = c.read(value, event)
        if len(reads) >= 7 and event == "RECONCILED":
            return receipt("controller", s, event, r.sequence + 1, dict(r.record, replaced=True))
        return r

    def observe(item):
        count.append(item.kind)
        return dict(resource=item.model_dump(), result="ABSENT", observed_ns=10 + len(count))

    with pytest.raises(Fault, match="AUDIT_DESTRUCTION_CHANGED"):
        AbsenceService(NS(observe=observe), e, NS(read=read), ledger).dispatch(
            "absent", dict(scope=s.model_dump())
        )
    assert len(count) == 8 and not e.rows


def test_RF_AT26_candidate_parser_handles_empty_plan_without_inventing_counters():
    from scripts.a42363_proposals import parse_target_projection

    result = parse_target_projection(
        [("100ms", True, None, None, None, None, None)], (25, 16, 25, 1028, 16, 20, 20)
    )
    assert result["target_session_settings_observed"] is False
    assert result["candidate_vectors_valid"] is True and result["plans"] == []
    assert result["qualifies"] is False


def test_RF_AT60_machine_readable_gates_keep_four_distinct_unknowns():
    from scripts.a42363_installation import capability_matrix

    m = capability_matrix()
    assert m["safe_volume_disposal"]["source"] == "NOT_IMPLEMENTED"
    assert m["target_session_guc"]["approval"] == "NOT_APPROVED"
    assert m["pg_fixture"]["installation"] == "NOT_DEPLOYED"
    assert m["pg_fixture"]["physical"] == "NOT_RUN"
    assert all(v["qualifies"] is False for v in m.values())


@pytest.mark.parametrize("kind", ["SECRET", "CONTAINER"])
@pytest.mark.parametrize("damage", ["id", "epoch", "label", "name", "missing_id"])
def test_RF_AT08_resource_damage_never_reaches_delete(kind, damage):
    item, raw = raw_resource(kind)
    if damage == "id":
        raw["ID"] = "foreign-name"
    elif damage == "missing_id":
        raw.pop("ID")
    else:
        config = raw["Spec"] if kind == "SECRET" else raw["Config"]
        if damage == "epoch":
            config["Labels"]["a42363_epoch"] = "different"
        elif damage == "label":
            config["Labels"]["a42363_scope"] = "f" * 64
        elif kind == "SECRET":
            config["Name"] = "foreign"
        else:
            raw["Name"] = "foreign"
    calls = []
    driver = ResourceDriver(NS(run=lambda args: calls.append(args)), None, None, None)
    with pytest.raises(Fault):
        driver.remove(item, raw)
    assert not calls


@pytest.mark.parametrize("kind", ["VOLUME", "SECRET", "CONTAINER"])
def test_RF_AT32_inspect_nonzero_is_not_an_owned_resource(kind):
    item, _ = raw_resource(kind)
    driver = ResourceDriver(NS(run=lambda args: (125, b"PRIVATE_ERROR")), None, None, None)
    with pytest.raises(Fault, match="RESOURCE_INSPECT_UNKNOWN"):
        driver.inspect(item)


@pytest.mark.parametrize("field", ["ID", "StorageID", "none"])
def test_RF_AT09_AT10_volume_has_no_executable_delete_target(field):
    item, raw = raw_resource("VOLUME")
    raw.pop("ID")
    if field != "none":
        raw[field] = "a" * 64
    calls = []
    driver = ResourceDriver(NS(run=lambda args: calls.append(args)), None, None, None)
    expected = "SAFE_DELETE_UNPROVEN" if field == "ID" else "REMOVE_ID_REQUIRED"
    with pytest.raises(Fault, match=expected):
        driver.remove(item, raw)
    assert not calls


@pytest.mark.parametrize("kind", ["SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER"])
@pytest.mark.parametrize("cut", ["RESERVED", "CREATE_ATTEMPTED", "OBSERVED_CREATED", "create"])
def test_RF_AT31_AT33_persistent_creation_cut_never_retries(kind, cut):
    store = ModelStore("controller")
    ledger = ModelLedger(None if cut == "create" else (kind, cut))
    driver = ModelDriver((kind, "create") if cut == "create" else None)
    with pytest.raises(Fault):
        RecoveryEngine(ledger, driver, store).create(scope())
    before = copy.deepcopy(driver.created)
    with pytest.raises(Fault, match="NO_SECOND_CREATE"):
        RecoveryEngine(ledger, driver, store).create(scope())
    RecoveryEngine(ledger, driver, store).recover(scope())
    assert driver.created == before


@pytest.mark.parametrize("kind", ["SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER"])
@pytest.mark.parametrize("cut", ["before_remove", "remove_ack", "after_remove", "absence_ack"])
def test_RF_AT34_AT35_delete_cut_restarts_preserve_original_and_no_second_remove(kind, cut):
    s, ledger, driver, store = scope(), ModelLedger(), ModelDriver(), ModelStore("controller")
    engine = RecoveryEngine(ledger, driver, store)
    engine.create(s)
    if cut == "before_remove":
        ledger.fault = (kind, "REMOVE_ATTEMPTED")
    elif cut == "remove_ack":
        driver.fault = (kind, "remove")
    elif cut == "after_remove":
        original = driver.absent
        driver.absent = lambda item: False if item.kind == kind else original(item)
    else:
        ledger.fault = (kind, "OBSERVED_ABSENT")
    first = engine.recover(s)
    assert first["first_error"]
    removals = copy.deepcopy(driver.removed)
    ledger.fault = None
    driver.fault = None
    driver.absent = lambda item: item.kind not in driver.raw
    second = RecoveryEngine(ledger, driver, store).recover(s)
    assert driver.removed == removals
    assert second["first_error"] == first["first_error"]
    assert second["qualifies"] is False and second["status"] == "INCOMPLETE_QUARANTINED"


@pytest.mark.parametrize("kind", ["SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER"])
def test_RF_AT34_aba_new_object_is_not_the_original(kind):
    s, ledger, driver, store = scope(), ModelLedger(), ModelDriver(), ModelStore("controller")
    RecoveryEngine(ledger, driver, store).create(s)
    driver.raw[kind] = dict(id="REPLACED", epoch=s.epoch)
    value = RecoveryEngine(ledger, driver, store).recover(s)
    assert value["first_error"] and kind not in driver.removed
    assert driver.raw[kind]["id"] == "REPLACED"
    assert store.read(s, "CREATION_" + kind).record["original_id"] != "REPLACED"


@pytest.mark.parametrize(
    "damage",
    [
        "timeout",
        "bool_int",
        "missing_guc",
        "row_count",
        "oid",
        "mixed_null",
        "from_sql",
        "wrong_parameter",
        "counter",
        "name",
    ],
)
def test_RF_AT26_candidate_parser_fails_closed_and_does_not_authorize(damage):
    from scripts.a42363_proposals import TARGET_OIDS, parse_target_projection

    rows = [["100ms", True, "_pg3_0", [23], False, 0, 5]]
    oids = TARGET_OIDS
    if damage == "timeout":
        rows[0][0] = "0"
    elif damage == "bool_int":
        rows[0][1] = 1
    elif damage == "missing_guc":
        rows[0] = rows[0][2:]
    elif damage == "row_count":
        rows *= 9
    elif damage == "oid":
        oids = (25,) * 7
    elif damage == "mixed_null":
        rows[0][2] = None
    elif damage == "from_sql":
        rows[0][4] = True
    elif damage == "wrong_parameter":
        rows[0][3] = [25]
    elif damage == "counter":
        rows[0][5] = True
    else:
        rows[0][2] = "user_statement"
    with pytest.raises(Fault):
        parse_target_projection(rows, oids)


def test_RF_AT26_candidate_projection_reuses_frozen_counter_continuity():
    from scripts.a42363_proposals import TARGET_OIDS, parse_target_projection

    first = parse_target_projection([["100ms", True, "_pg3_0", [23], False, 0, 5]], TARGET_OIDS)
    assert first["qualifies"] is False
    with pytest.raises(Fault, match="CANDIDATE_PLAN_POLICY"):
        parse_target_projection(
            [["100ms", True, None, None, None, None, None]], TARGET_OIDS, first["continuity"]
        )


@pytest.mark.parametrize("value", [True, -1, "17", None])
def test_RF_AT14_cost_schema_has_no_implicit_conversion(value):
    from scripts.a42363_proposals import InitializationCost

    with pytest.raises(Fault, match="INITIALIZATION_COST_SCHEMA"):
        InitializationCost(sql=value, commands=0)


@pytest.mark.parametrize("field", [None, "uid", "scope", "epoch", "source", "expiry", "code"])
def test_RF_AT53_installed_FDs_are_exact_and_independently_read(tmp_path, monkeypatch, field):
    import os

    from scripts import a42363_installation as m
    from scripts.a42361_contract import canonical, sha
    from scripts.a42363_contract import scope_hash

    s = scope()
    raw_code = b"OFFLINE_INSTALLED_CODE_MODEL"
    code = tmp_path / "code"
    code.write_bytes(raw_code)
    code.chmod(0o400)
    body = dict(
        schema_version="a42363.installed-fds.v1",
        domain="pg_owner",
        uid=1006,
        scope_sha256=scope_hash(s),
        epoch=s.epoch,
        source_sha256=s.binding.identity.source_sha256,
        capability_digests={k: sha(raw_code) for k in m.CAPABILITIES["pg_owner"]},
        expires_at=200,
    )
    if field == "uid":
        body["uid"] = 1009
    if field in ("scope", "epoch", "source"):
        body[{"scope": "scope_sha256", "epoch": "epoch", "source": "source_sha256"}[field]] = (
            "f" * 64
        )
    if field == "expiry":
        body["expires_at"] = 99
    if field == "code":
        body["capability_digests"]["owner_runtime"] = "e" * 64
    raw = canonical(body)
    doc = tmp_path / "document"
    doc.write_bytes(raw)
    doc.chmod(0o400)
    fds = [os.open(doc, os.O_RDONLY), os.open(code, os.O_RDONLY)]
    real_stat = os.fstat

    def model_root(fd):
        meta = real_stat(fd)
        return NS(
            **{
                k: 0 if k == "st_uid" else getattr(meta, k)
                for k in dir(meta)
                if k.startswith("st_")
            }
        )

    monkeypatch.setattr(m.os, "fstat", model_root)  # VIRTUAL_ROOT_MODEL, no chown/deployment.

    def verify():
        return (
            m.InstalledFDDocument.read(fds[0], sha(raw), "pg_owner", 1006)
            .verify_scope(s, 100)
            .verify_code_fds({k: fds[1] for k in m.CAPABILITIES["pg_owner"]})
        )

    try:
        if field:
            with pytest.raises(Fault, match="INSTALLATION_"):
                verify()
        else:
            assert verify().domain == "pg_owner"
    finally:
        for fd in fds:
            os.close(fd)


@pytest.mark.parametrize("fault", ["mutable", "unowned", "digest", "extra", "missing"])
def test_RF_AT53_untrusted_document_never_composes(tmp_path, monkeypatch, fault):
    import os

    from scripts import a42363_installation as m
    from scripts.a42361_contract import canonical, sha
    from scripts.a42363_contract import scope_hash

    s = scope()
    body = dict(
        schema_version="a42363.installed-fds.v1",
        domain="approval",
        uid=1006,
        scope_sha256=scope_hash(s),
        epoch=s.epoch,
        source_sha256=s.binding.identity.source_sha256,
        capability_digests={},
        expires_at=200,
    )
    if fault == "extra":
        body["unsafe"] = True
    if fault == "missing":
        body.pop("epoch")
    raw = canonical(body)
    p = tmp_path / "document"
    p.write_bytes(raw)
    fd = os.open(p, os.O_RDWR if fault == "mutable" else os.O_RDONLY)
    p.chmod(0o400)
    real_stat = os.fstat

    def model_root(value):
        meta = real_stat(value)
        return NS(
            **{
                k: (1000 if fault == "unowned" else 0) if k == "st_uid" else getattr(meta, k)
                for k in dir(meta)
                if k.startswith("st_")
            }
        )

    monkeypatch.setattr(m.os, "fstat", model_root)
    try:
        with pytest.raises(PreviousFault, match="INSTALLATION_|SCHEMA_INVALID"):
            m.InstalledFDDocument.read(
                fd, "f" * 64 if fault == "digest" else sha(raw), "approval", 1006
            )
    finally:
        os.close(fd)


def test_RF_AT51_publication_uncertainty_is_persistent_no_replay(monkeypatch):
    from scripts import a42363_supervisor as d

    s, store, calls = scope(), ModelStore("supervisor"), []
    monkeypatch.setattr(d, "session_method", lambda: None)

    def publish(_):
        calls.append("publish")
        raise Fault("A42363_ARTIFACT_ACK_UNKNOWN")

    cg = NS(
        scope_sha256=d.scope_hash(s),
        epoch=s.epoch,
        terminate=lambda _: dict(
            execution_scope_terminated=True,
            scope_sha256=d.scope_hash(s),
            epoch=s.epoch,
            cgroup_inode=1,
        ),
    )
    supervisor = d.SupervisorService(
        NS(launch=lambda *_: None), None, cg, store, NS(publish=publish)
    )
    supervisor.dispatch("run", dict(scope=s.model_dump()))
    with pytest.raises(Fault, match="ARTIFACT_ACK_UNKNOWN"):
        supervisor.dispatch("terminate", dict(scope=s.model_dump()))
    receiver = d.SupervisorService(None, None, cg, store, NS(publish=publish))
    with pytest.raises(Fault, match="PUBLICATION_ACK_UNKNOWN_NO_RETRY"):
        receiver.dispatch("terminate", dict(scope=s.model_dump()))
    assert calls == ["publish"] and store.maybe_read(s, "TERMINATED") is None
    assert (
        store.read(s, "TERMINATION_PROVEN").sequence
        < store.read(s, "PUBLICATION_ATTEMPTED").sequence
    )


def test_RF_AT49_guardian_abandon_fires_held_FD_without_PID_input(tmp_path):
    import os

    from scripts.a42363_supervisor import FDDeadlineGuardian

    fd = os.open(tmp_path / "private-model", os.O_CREAT | os.O_RDWR | os.O_EXCL, 0o600)
    try:
        guardian = FDDeadlineGuardian(fd, 3000)
        assert guardian.abandon() == "DEADLINE_FIRED"
        assert os.pread(fd, 1, 0) == b"1"
        with pytest.raises(Fault, match="ALREADY_REAPED"):
            guardian.finish()
    finally:
        os.close(fd)


def test_RF_AT49_guardian_parent_death_fires_without_cancel(tmp_path):
    import os
    import time

    from scripts.a42363_supervisor import FDDeadlineGuardian

    fd = os.open(tmp_path / "private-model", os.O_CREAT | os.O_RDWR | os.O_EXCL, 0o600)
    child = os.fork()
    if child == 0:
        FDDeadlineGuardian(fd, 300)
        os._exit(0)
    try:
        assert os.waitpid(child, 0)[1] == 0
        end = time.monotonic() + 1
        while not os.pread(fd, 1, 0) and time.monotonic() < end:
            time.sleep(0.005)
        assert os.pread(fd, 1, 0) == b"1"
    finally:
        os.close(fd)


@pytest.mark.parametrize("operation", ["child_fork", "guardian_pipe", "guardian_fork"])
def test_RF_AT49_early_syscall_failure_closes_every_allocated_FD(monkeypatch, operation):
    import os

    from scripts import a42363_supervisor as d

    original_pipe, allocated = os.pipe, []

    def pipe():
        if operation == "guardian_pipe" and allocated:
            raise OSError("MODEL_PIPE_FAILURE")
        pair = original_pipe()
        allocated.extend(pair)
        return pair

    def failed_fork():
        raise OSError("MODEL_FORK_FAILURE")

    monkeypatch.setattr(d.os, "pipe", pipe)
    monkeypatch.setattr(d.os, "fork", failed_fork)
    with pytest.raises(OSError, match="MODEL_"):
        if operation == "child_fork":
            d.bounded_child(lambda: None)
        else:
            d.FDDeadlineGuardian(-1, 100)
    for fd in allocated:
        with pytest.raises(OSError):
            os.fstat(fd)
