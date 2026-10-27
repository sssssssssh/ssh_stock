"""Actual SQLite/FD/L1 entrypoints; these tests never confer physical G1 proof."""

import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from scripts.a42362_contract import resources
from scripts.a42363_contract import Fault
from scripts.a42365_budget import BudgetService
from scripts.a42365_controlled import ControlledFileDriver, controlled_installation
from scripts.a42365_journal import DurableJournal
from scripts.a42365_lifecycle import ResourceLifecycle
from scripts.a42365_runtime_factory import build_installed_runtime
from tests.unit.test_a42364_owner import identity


@pytest.fixture
def private_fd(tmp_path):
    tmp_path.chmod(0o700)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        yield fd
    finally:
        os.close(fd)


class ClosedAuthority:
    def require(self, kind):
        raise Fault("A42363_EXTERNAL_DECISION_REQUIRED")


class OfflineAuthority:
    def require(self, kind):
        return dict(qualifies=False, approved=False)


def test_AT05_AT08_AT47_same_factory_real_sqlite_unix_scm_child_and_two_round_l1(private_fd):
    runtime = build_installed_runtime(controlled_installation(identity().scope, private_fd))
    try:
        result = runtime.run_scope()
        assert result["qualifies"] is False
        assert result["status"] == "PENDING_INDEPENDENT_REVIEW"
        assert result["physical"] == "NOT_RUN_NOT_AUTHORIZED"
        assert runtime.supervisor.journal.read(runtime.scope, "CONTROLLED_CHILD_REAPED")
        audit = runtime.auditor.journal.read(runtime.scope, "MODELED_ABSENT").record
        assert len(audit["observations"]) == 8
        assert audit["physical_independence"] is False
        assert runtime.owner.journal.read(runtime.scope, "MODELED_OWNER").record["g1_sql"] == 0
        with pytest.raises(Fault, match="JOURNAL_DUPLICATE_NO_REPLAY"):
            runtime.run_scope()
        assert (
            len(
                [e for e in runtime.consumer.journal.events(runtime.scope) if e.event == "CONSUMED"]
            )
            == 1
        )
    finally:
        for fd in runtime.controlled_fds:
            os.close(fd)


def test_AT16_AT19_AT20_persistent_budget_concurrent_exact_limits_and_restart(private_fd):
    j = DurableJournal(private_fd, "consumer")
    i = identity()
    b = BudgetService(i, OfflineAuthority(), j, "CONTROLLED_BOOT_ID")
    b.start()

    def attempt(index):
        try:
            return j.reserve(
                i.scope,
                "RESERVE_" + str(index),
                dict(costs=dict(sql=1, commands=0)),
                dict(sql=8, commands=12),
            )
        except Fault:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(attempt, range(16)))
    assert sum(r is not None for r in receipts) == 8
    reopened = DurableJournal(private_fd, "consumer")
    assert len([r for r in reopened.events(i.scope) if r.event.startswith("RESERVE_")]) == 8
    with pytest.raises(Fault, match="GLOBAL_BUDGET_EXHAUSTED"):
        reopened.reserve(
            i.scope, "RESERVE_17", dict(costs=dict(sql=1, commands=0)), dict(sql=8, commands=12)
        )


def test_AT18_AT21_AT45_extra_audit_slots_separate_and_active_limits_unchanged(private_fd):
    b = BudgetService(identity(), OfflineAuthority(), DurableJournal(private_fd, "consumer"), "L1")
    with pytest.raises(Fault, match="ACTIVE_BOOTSTRAP_LIMIT_EXCEEDED"):
        b.require_active_plan()
    b.start()
    for index in (1, 2):
        for kind in ("AUTH", "SQL"):
            assert b.reserve_audit(index, kind)
    with pytest.raises(Fault, match="BUDGET_ACK_UNKNOWN_NO_RETRY"):
        b.reserve_audit(1, "AUTH")
    with pytest.raises(Fault, match="AUDIT_BUDGET_SLOT"):
        b.reserve_audit(3, "SQL")
    assert b.report()["measured"] is False


@pytest.mark.parametrize("kind", ["SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER"])
@pytest.mark.parametrize("verb", ["CREATE", "INSPECT", "REMOVE"])
def test_AT27_AT28_AT29_AT33_restart_unknown_ack_never_replays(private_fd, kind, verb):
    scope = identity().scope
    j = DurableJournal(private_fd, "controller")
    driver = ControlledFileDriver(private_fd)
    lifecycle = ResourceLifecycle(scope, j, driver)
    item = next(r for r in resources(scope) if r.kind == kind)
    if verb != "CREATE":
        lifecycle.perform(item, "CREATE")
    j.append(scope, kind + "_" + verb + "_ATTEMPTED", dict(qualifies=False))
    reopened = ResourceLifecycle(scope, DurableJournal(private_fd, "controller"), driver)
    with pytest.raises(Fault, match="RESOURCE_ACK_UNKNOWN_NO_REPLAY"):
        reopened.perform(item, verb)
    if verb == "CREATE":
        with pytest.raises(FileNotFoundError):
            driver.inspect(item)
    else:
        assert driver.inspect(item) == lifecycle.original(item)["raw"]


@pytest.mark.parametrize("verb", ["START", "STOP"])
def test_AT27_AT29_container_start_stop_unknown_ack_is_not_replayed(private_fd, verb):
    scope = identity().scope
    j = DurableJournal(private_fd, "controller")
    driver = ControlledFileDriver(private_fd)
    life = ResourceLifecycle(scope, j, driver)
    item = resources(scope)[3]
    life.perform(item, "CREATE")
    j.append(scope, "CONTAINER_" + verb + "_ATTEMPTED", dict(qualifies=False))
    with pytest.raises(Fault, match="RESOURCE_ACK_UNKNOWN_NO_REPLAY"):
        ResourceLifecycle(scope, DurableJournal(private_fd, "controller"), driver).perform(
            item, verb
        )


def test_AT31_AT32_original_identity_aba_and_first_error_survive_restart(private_fd):
    scope = identity().scope
    j = DurableJournal(private_fd, "controller")
    d = ControlledFileDriver(private_fd)
    life = ResourceLifecycle(scope, j, d)
    item = resources(scope)[1]
    life.perform(item, "CREATE")
    original = life.original(item)
    os.unlink(item.kind, dir_fd=private_fd)
    d.create(item)
    with pytest.raises(Fault, match="OWNERSHIP_UNKNOWN_QUARANTINE"):
        life.perform(item, "REMOVE")
    life.record_error("A42363_FIRST", "PRIMARY")
    life.record_error("A42363_SECOND", "CLEANUP")
    reopened = ResourceLifecycle(scope, DurableJournal(private_fd, "controller"), d)
    assert reopened.original(item) == original
    assert (
        reopened.journal.read(scope, "FIRST_ERROR").record["code"]
        == "A42363_OWNERSHIP_UNKNOWN_QUARANTINE"
    )
    assert d.inspect(item) != original["raw"]


def test_AT10_AT15_broker_no_global_proof_never_routes_a_command(private_fd):
    from scripts.a42365_writer_broker import InstalledWriterBroker

    scope = identity().scope

    class Runner:
        def run(self, *args):
            pytest.fail("Must not issue any Podman command")

    broker = InstalledWriterBroker(
        scope,
        OfflineAuthority(),
        DurableJournal(private_fd, "writer_broker"),
        private_fd,
        private_fd,
        private_fd,
        Runner(),
    )
    with pytest.raises(Fault, match="ENGINEERING_BLOCKED_BY_RUNTIME_CAPABILITY"):
        broker.dispatch(resources(scope)[1], "rm", {})
    assert broker.status()["all_writer_proof"] is False


def test_AT35_AT36_ordinary_directory_fd_is_not_readonly_mount(private_fd):
    from scripts.a42363_contract import scope_hash
    from scripts.a42365_provisioner import ReadOnlyProvisioner

    scope = identity().scope
    m = os.fstat(private_fd)
    p = ReadOnlyProvisioner(
        scope,
        ClosedAuthority(),
        DurableJournal(private_fd, "root_manager"),
        None,
        dict(
            graph_identity=[m.st_dev, m.st_ino],
            run_identity=[m.st_dev, m.st_ino],
            observer_uid=os.getuid(),
            scope_sha256=scope_hash(scope),
            epoch=scope.epoch,
        ),
    )
    with pytest.raises(Fault, match="AUDIT_WRITABLE_DELEGATION"):
        p.accept(private_fd, private_fd, private_fd, private_fd, private_fd)


def test_AT44_AT46_unapproved_owner_audit_factory_never_connects(private_fd, monkeypatch):
    import psycopg

    from scripts.a42365_owner import AuditConnectionFactory

    def forbidden(*args, **kwargs):
        pytest.fail("Unapproved audit must not execute SQL/connect")

    monkeypatch.setattr(psycopg, "connect", forbidden)
    with pytest.raises(Fault, match="EXTERNAL_DECISION_REQUIRED"):
        AuditConnectionFactory(identity(), ClosedAuthority(), None, None).open()


def test_AT43_publication_keeps_marker_if_termination_or_reviewer_missing(private_fd):
    from scripts.a42365_supervisor import StagedPublisher

    scope = identity().scope
    journal = DurableJournal(private_fd, "supervisor")
    p = StagedPublisher(scope, private_fd, journal)
    p.stage(dict(qualifies=False, source="CONTROLLED_L1"))
    with pytest.raises(Fault, match="COMMITTED_RECEIPT_MISSING"):
        p.finalize(journal, journal, journal)
    assert os.stat(".incomplete", dir_fd=private_fd).st_size > 0
    assert journal.maybe_read(scope, "PUBLISHED") is None


def test_AT06_AT07_strict_envelope_rejects_injected_capability():
    from scripts.a42365_contract import message, verify_envelope

    scope = identity().scope
    for name in ("class", "factory", "shell", "argv", "dsn", "root", "approved"):
        q = message(scope, "a" * 64, "b" * 64, "controller", "create", {name: "unsafe"})
        with pytest.raises(Fault, match="RUNTIME_INJECTED_CAPABILITY"):
            verify_envelope(q.model_dump(), scope, "a" * 64, "b" * 64, "controller", ("create",))


@pytest.mark.parametrize(
    "kind,verb",
    [
        (kind, verb)
        for kind in ("SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER")
        for verb in ("CREATE", "REMOVE")
    ]
    + [("CONTAINER", "START"), ("CONTAINER", "STOP")],
)
def test_AT24_AT29_ack_lost_after_actual_file_effect_is_never_repeated(
    private_fd, monkeypatch, kind, verb
):
    scope = identity().scope
    journal = DurableJournal(private_fd, "controller")
    driver = ControlledFileDriver(private_fd)
    life = ResourceLifecycle(scope, journal, driver)
    item = next(item for item in resources(scope) if item.kind == kind)
    if verb != "CREATE":
        life.perform(item, "CREATE")
    append = journal.append

    def lost_ack(scope, event, record):
        result = append(scope, event, record)
        if event == kind + "_" + verb + "_DONE":
            raise Fault("A42363_SIMULATED_ACK_LOSS_AFTER_COMMIT")
        return result

    monkeypatch.setattr(journal, "append", lost_ack)
    with pytest.raises(Fault, match="SIMULATED_ACK_LOSS_AFTER_COMMIT"):
        life.perform(item, verb)
    restarted = ResourceLifecycle(scope, DurableJournal(private_fd, "controller"), driver)
    with pytest.raises(Fault, match="RESOURCE_ACK_UNKNOWN_NO_REPLAY"):
        restarted.perform(item, verb)
    assert restarted.journal.read(scope, kind + "_" + verb + "_DONE")


def test_AT01_AT02_AT03_exact_overlay_rejects_unregistered_paths_and_preserves_nine_manifests():
    import hashlib
    import json
    import subprocess
    from pathlib import Path

    from scripts.a42365_source_guard import BASELINE, MANIFEST, validate_paths

    root = Path(__file__).resolve().parents[2]
    data = json.loads((root / MANIFEST).read_bytes())
    assert len(data["historical_manifest_sha256"]) == 9
    for path, digest in data["historical_manifest_sha256"].items():
        original = subprocess.check_output(["git", "show", BASELINE + ":" + path], cwd=root)
        assert (root / path).read_bytes() == original
        assert hashlib.sha256(original).hexdigest() == digest
    for path in (
        "backend/app/x.py",
        ".github/workflows/ci.yml",
        "config/strategy.yaml",
        "migrations/extra.py",
        "tests/unit/test_a42364_owner.py",
        "infra/new-helper.c",
    ):
        with pytest.raises(Fault, match="A42365_UNREGISTERED_PATH"):
            validate_paths({path})


def test_AT04_default_installed_service_calls_fixed_factory_without_rpc_injection():
    import ast
    import inspect

    from scripts.a42364_manager import serve_installed

    tree = ast.parse(inspect.getsource(serve_installed))
    factory = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "build_installed_runtime"
    ]
    assert len(factory) == 1
    assert [ast.unparse(arg) for arg in factory[0].args] == ["package"]
    assert not factory[0].keywords


def test_AT48_budget_proposals_are_version_bound_unsigned_and_include_extra_audit():
    from scripts.a42365_protocol import proposal_hashes, runtime_budget_plan

    plan = runtime_budget_plan(identity())
    assert plan["active"] == dict(sql=8, commands=12, window_ms=2000)
    assert plan["candidate"] == dict(sql=12, commands=32, window_ms=30000)
    assert plan["extra_target_audit"] == dict(sql=2, authentications=2)
    assert plan["native_transitive_census"] == "NOT_IMPLEMENTED"
    assert plan["prebuilt"] == "NOT_IMPLEMENTED"
    assert plan["approved"] is plan["measured"] is plan["qualifies"] is False
    assert proposal_hashes(identity(), "a" * 64) != proposal_hashes(identity(), "b" * 64)


def test_AT19_real_processes_share_budget_without_reset_or_refund(private_fd):
    scope = identity().scope
    j = DurableJournal(private_fd, "consumer")
    children = []
    for process in range(4):
        pid = os.fork()
        if pid == 0:
            try:
                own = DurableJournal(private_fd, "consumer")
                for slot in range(4):
                    try:
                        own.reserve(
                            scope,
                            "RESERVE_P" + str(process) + "_" + str(slot),
                            dict(costs=dict(sql=1)),
                            dict(sql=8),
                        )
                    except Fault as error:
                        assert error.code == "A42363_GLOBAL_BUDGET_EXHAUSTED"
                os._exit(0)
            except BaseException:
                os._exit(1)
        children.append(pid)
    statuses = [os.waitpid(pid, 0)[1] for pid in children]
    assert statuses == [0] * 4
    assert len(j.events(scope)) == 8


def test_AT20_budget_expiration_is_sticky_across_clock_reversal(private_fd, monkeypatch):
    from scripts import a42365_budget as module

    b = BudgetService(identity(), OfflineAuthority(), DurableJournal(private_fd, "consumer"), "L1")
    b.start()
    real = module.time.monotonic_ns
    current = real()
    monkeypatch.setattr(module.time, "monotonic_ns", lambda: current + 31000000000)
    with pytest.raises(Fault, match="CANDIDATE_BOOTSTRAP_DEADLINE"):
        b.reserve_named(next(iter(b.operations)))
    monkeypatch.setattr(module.time, "monotonic_ns", real)
    with pytest.raises(Fault, match="CANDIDATE_BOOTSTRAP_DEADLINE"):
        b.reserve_named(next(iter(b.operations)))
