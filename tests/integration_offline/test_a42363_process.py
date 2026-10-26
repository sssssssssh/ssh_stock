"""L1 fork/Unix FD/files only. No PG17/Podman/cgroup/systemd or G1.

Immutable fixture stores are DB_MODEL_ONLY. Separate processes prove transport,
not multi-UID deployment. Physical kernel containment is not claimed by this test.
"""

import array
import copy
import fcntl
import os
import signal
import socket
import struct
import sys
import time
from contextlib import contextmanager
from types import SimpleNamespace as NS

import pytest

from scripts.a42361_contract import canonical, decode
from scripts.a42361_offline_cases import approval, binding, payload
from scripts.a42362_contract import Scope, resources
from scripts.a42363_contract import DOMAINS, Fault, receipt, scope_hash
from scripts.a42363_review import Reviewer
from scripts.a42363_stores import ReceiptSet
from scripts.a42363_supervisor import ArtifactPublisher, bounded_child


def fixture_scope():
    return Scope(
        token_id="32345678-1234-4234-8234-123456789012",
        binding=binding(),
        payload_sha256="1" * 64,
        image_digest="sha256:" + "2" * 64,
        controller_uid=1005,
        namespace_sha256="3" * 64,
        epoch="42345678-1234-4234-8234-123456789012",
    )


def records(s):
    c = receipt(
        "controller",
        s,
        "RECONCILED",
        2,
        dict(
            status="DESTROYED_PENDING_INDEPENDENT_E",
            scope_sha256=scope_hash(s),
            resource_ids={k: "a" * 64 for k in ("SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER")},
            first_error=None,
            cleanup_codes=[],
            destroyed_ns=1,
        ),
    )
    p = payload()
    a = approval(p, s.payload_sha256).model_dump()
    raw_owner = dict(
        pg_major=17,
        system_identifier_sha256="a" * 64,
        image_digest=s.image_digest,
        namespace_sha256=s.namespace_sha256,
        marker_sha256=s.binding.marker_sha256,
        fixture_uuid=s.binding.fixture_uuid,
        nonce=s.binding.nonce,
        container_id="MODEL_CONTAINER",
        volume_id="MODEL_VOLUME",
        initialization_sql=8,
        initialization_commands=12,
        initialization_ms=1,
        role_audit=dict(
            superuser=False,
            createdb=False,
            createrole=False,
            inherit=False,
            bypassrls=False,
            replication=False,
            memberships=[],
            public_write=False,
            public_execute=False,
            business_read=False,
            maintain=False,
            ddl=False,
            dml=False,
        ),
    )
    observations = [
        dict(
            resource=item.model_dump(),
            observer_uid=1007,
            result="ABSENT",
            raw=dict(status="ABSENT", code=1, identity=None),
            observed_ns=2 + i,
            visibility=dict(epoch=s.epoch, namespace_sha256=s.namespace_sha256),
        )
        for i, item in enumerate(resources(s) * 2)
    ]
    return {
        "approval": receipt("approval", s, "APPROVED", 1, a),
        "consumer": receipt(
            "consumer",
            s,
            "CONSUMED",
            1,
            dict(
                event="CONSUMED",
                committed=True,
                token_id=s.token_id,
                payload_sha256=s.payload_sha256,
                nonce=s.binding.nonce,
                approval_id=p.approval_id,
                head_sha=s.binding.identity.head_sha,
                run_id="local",
                attempt=1,
                control_instance_sha256="b" * 64,
            ),
        ),
        "pg_owner": receipt("pg_owner", s, "OWNER_RAW", 1, dict(raw=raw_owner)),
        "controller": c,
        "supervisor": receipt(
            "supervisor",
            s,
            "TERMINATED",
            1,
            dict(
                execution_scope_terminated=True,
                physical_proven=False,
                model="DB_MODEL_ONLY",
                scope_sha256=scope_hash(s),
                epoch=s.epoch,
                cgroup_inode=1,
            ),
        ),
        "absence_auditor": receipt(
            "absence_auditor",
            s,
            "ABSENT",
            1,
            dict(destruction_digest=c.digest, observations=observations),
        ),
    }


class RemoteSource:
    def __init__(self, channel, value):
        self.channel, self.value = channel, value

    def read(self, s, event):
        request = canonical(dict(scope_sha256=scope_hash(s), event=event))
        self.channel.sendall(struct.pack("!I", len(request)) + request)
        prefix, ancillary, flags, _ = self.channel.recvmsg(4, socket.CMSG_SPACE(4))
        assert flags == 0 and len(prefix) == 4
        size = struct.unpack("!I", prefix)[0]
        assert 0 < size <= 65536
        raw = bytearray()
        while len(raw) < size:
            chunk = self.channel.recv(size - len(raw))
            assert chunk
            raw.extend(chunk)
        fds = array.array("i")
        for level, kind, data in ancillary:
            assert (level, kind) == (socket.SOL_SOCKET, socket.SCM_RIGHTS)
            fds.frombytes(data[: len(data) - len(data) % fds.itemsize])
        assert len(fds) == 1
        try:
            assert os.read(fds[0], 64) == b"DB_MODEL_ONLY_INDEPENDENT_PROCESS"
        finally:
            os.close(fds[0])
        assert decode(bytes(raw)) == self.value.model_dump()
        return self.value


@pytest.mark.parametrize(
    "fault",
    [None, "approval", "consumer", "pg_owner", "controller", "supervisor", "absence_auditor"],
)
def test_AT79_AT82_six_process_fd_transport_and_forgery_rejection(tmp_path, fault):
    s, children, channels, sources = fixture_scope(), [], [], {}
    values = records(s)
    try:
        for domain, value in values.items():
            parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
            channels.append(parent)
            fd = os.open(tmp_path / domain, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.write(fd, b"DB_MODEL_ONLY_INDEPENDENT_PROCESS")
            os.lseek(fd, 0, 0)
            pid = os.fork()
            if pid == 0:
                parent.close()
                try:
                    child.settimeout(2)
                    prefix = child.recv(4)
                    size = struct.unpack("!I", prefix)[0]
                    request = decode(child.recv(size))
                    assert request == dict(scope_sha256=scope_hash(s), event=value.event)
                    response = canonical(value.model_dump())
                    child.sendmsg(
                        [struct.pack("!I", len(response))],
                        [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))],
                    )
                    child.sendall(response)
                    os._exit(0)
                except BaseException:
                    os._exit(1)
            children.append(pid)
            child.close()
            os.close(fd)
            parent.settimeout(3)
            sources[domain] = RemoteSource(parent, value)
        refs = {d: v.model_dump() for d, v in values.items()}
        if fault:
            refs[fault] = receipt(fault, s, values[fault].event, 2, {"forged": True}).model_dump()
            with pytest.raises(Fault, match="INDEPENDENT_RECEIPT_MISMATCH"):
                Reviewer(ReceiptSet(sources)).review(s, refs)
        else:
            result = Reviewer(ReceiptSet(sources)).review(s, refs)
            assert result["status"] == "OFFLINE_CROSS_DOMAIN_VERIFIED"
            assert result["qualifies"] is False and result["real_probe_sql_executed"] == 0
    finally:
        for channel in channels:
            channel.close()
        for pid in children:
            os.waitpid(pid, 0)


@pytest.mark.parametrize("operation", ["handler", "fsync", "stdout"])
def test_AT72_external_deadline_kills_owned_blocking_child(tmp_path, operation):
    marker = tmp_path / ".incomplete"
    marker.write_bytes(b"INCOMPLETE")

    def blocked():
        if operation == "stdout":
            os.close(1)
        time.sleep(20)

    start = time.monotonic()
    with pytest.raises(Fault, match="OUTER_DEADLINE"):
        bounded_child(blocked, timeout_ms=100)
    assert time.monotonic() - start < 2 and marker.exists()


def test_AT76_real_artifact_fsync_manifest_and_no_overwrite(tmp_path):
    os.chmod(tmp_path, 0o700)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        result = ArtifactPublisher(fd).publish(dict(model="L1_ONLY", qualifies=False))
        assert result["qualifies"] is False and not (tmp_path / ".incomplete").exists()
        before = (tmp_path / "evidence.json").read_bytes()
        with pytest.raises(Fault):
            ArtifactPublisher(fd).publish(dict(model="DO_NOT_OVERWRITE", qualifies=False))
        assert (tmp_path / ".incomplete").exists()
        assert (tmp_path / "evidence.json").read_bytes() == before
    finally:
        os.close(fd)


def test_AT76_artifact_fsync_stall_keeps_incomplete(tmp_path, monkeypatch):
    os.chmod(tmp_path, 0o700)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    monkeypatch.setattr(os, "fsync", lambda _: time.sleep(20))
    try:
        with pytest.raises(Fault, match="OUTER_DEADLINE"):
            ArtifactPublisher(fd).publish(dict(qualifies=False))
        assert (tmp_path / ".incomplete").exists()
    finally:
        os.close(fd)


def test_AT67_AT70_untrusted_scope_is_never_kernel_proof(tmp_path):
    from scripts.a42363_supervisor import CgroupScope

    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(Fault):
            CgroupScope(fd, fd, fd, fd, "a" * 64, "model")
    finally:
        os.close(fd)


def test_AT83_missing_scope_termination_blocks_even_after_rehash():
    s = fixture_scope()
    values = copy.deepcopy(records(s))
    values["supervisor"] = receipt(
        "supervisor",
        s,
        "TERMINATED",
        1,
        dict(execution_scope_terminated=False, physical_proven=False),
    )
    sources = {d: NS(read=lambda s, event, value=v: value) for d, v in values.items()}
    with pytest.raises(Fault, match="SCOPE_TERMINATION_UNPROVEN"):
        Reviewer(ReceiptSet(sources)).review(s, {d: v.model_dump() for d, v in values.items()})
    assert set(sources) == set(DOMAINS) - {"registry"}


class FileStore:
    """L1 filesystem-backed DB_MODEL_ONLY, a different directory for every domain."""

    def __init__(self, path, domain):
        self.path, self.domain = path, domain
        path.mkdir(exist_ok=True)

    def append(self, s, event, record):
        value = receipt(self.domain, s, event, len(list(self.path.iterdir())) + 1, record)
        with (self.path / (event + ".json")).open("xb") as stream:
            stream.write(canonical(value.model_dump()))
            stream.flush()
            os.fsync(stream.fileno())
        return self.read(s, event)  # Different actual open/read, not writer's buffer.

    def read(self, s, event):
        from scripts.a42363_contract import verify_receipt

        return verify_receipt(
            decode((self.path / (event + ".json")).read_bytes()), self.domain, s, event
        )

    def maybe_read(self, s, event):
        return self.read(s, event) if (self.path / (event + ".json")).exists() else None

    @contextmanager
    def lock(self, scope):
        with (self.path / ".lock").open("ab") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


class FileLedger:
    def __init__(self, path):
        self.path = path

    def scan(self, body):
        from scripts.a42361_contract import sha

        rows = decode(self.path.read_bytes()) if self.path.exists() else []
        return dict(events=rows, snapshot_sha256=sha(canonical(rows)))

    def append(self, body):
        from scripts.a42362_contract import receipt as ledger_receipt
        from scripts.a42362_contract import transition

        rows = self.scan({})["events"]
        previous = [r for r in rows if r["request"]["resource"] == body["resource"]]
        transition(previous[-1]["request"]["event"] if previous else None, body)
        value = ledger_receipt(body, len(rows) + 1, "L1_DB_MODEL_ONLY", "b" * 64)
        rows.append(value.model_dump())
        self.path.write_bytes(canonical(rows))
        return self.scan({})["events"][-1]


class FileRuntime:
    def __init__(self, path, fault=None):
        self.path, self.fault = path, fault
        path.mkdir(exist_ok=True)

    def create(self, item):
        raw = dict(id="L1_FILE_MODEL_" + item.kind, epoch=item.scope.epoch)
        (self.path / item.kind).write_bytes(canonical(raw))
        if self.fault == "create_ack":
            raise Fault("A42363_MODEL_CREATE_ACK_UNKNOWN")
        return raw

    def inspect(self, item):
        return decode((self.path / item.kind).read_bytes())

    def verify(self, item, raw):
        from scripts.a42361_contract import sha

        return sha(canonical(raw))

    def remove(self, item, raw):
        assert self.inspect(item) == raw
        (self.path / item.kind).unlink()
        if self.fault == "remove_ack":
            raise Fault("A42363_MODEL_REMOVE_ACK_UNKNOWN")

    def absent(self, item):
        return not (self.path / item.kind).exists()


def child_call(operation):
    """Real separate process for each domain call; replies cross a bounded Unix socket."""
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    pid = os.fork()
    if pid == 0:
        parent.close()
        try:
            try:
                raw = canonical(dict(result=operation(), error=None))
            except BaseException as error:
                raw = canonical(
                    dict(result=None, error=getattr(error, "code", "A42363_L1_INCOMPLETE"))
                )
            child.sendall(struct.pack("!I", len(raw)) + raw)
            os._exit(0)
        except BaseException:
            os._exit(1)
    child.close()
    parent.settimeout(3)
    try:
        prefix = parent.recv(4)
        assert len(prefix) == 4
        size = struct.unpack("!I", prefix)[0]
        assert 0 < size <= 65536
        result = bytearray()
        while len(result) < size:
            chunk = parent.recv(size - len(result))
            assert chunk
            result.extend(chunk)
        return decode(bytes(result))
    finally:
        parent.close()
        _, status = os.waitpid(pid, 0)
        assert status == 0


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "create_ack",
        "remove_ack",
        "replacement",
        "namespace",
        "observer_uid",
        "permission",
        "recreation",
        "root_scope",
        "root_ack",
        "ledger_hash",
        "forged_reference",
        "missing_identity",
    ],
)
def test_AT79_AT81_real_file_model_cross_domain_receivers_and_faults(tmp_path, monkeypatch, fault):
    """Concrete C/O/D/E algorithms, actual process boundaries, explicit fake PG/runtime.

    Method gates are replaced ONLY inside this isolated fixture's child processes.
    No PostgreSQL, Podman, real credentials or physical kernel claims can be issued.
    """
    from scripts import a42363_resources as cmod
    from scripts import a42363_supervisor as dmod
    from scripts.a42361_contract import sha
    from scripts.a42363_absence import AbsenceService, IndependentObserver
    from scripts.a42363_owner import RawOwnerBackend
    from scripts.a42363_resources import ControllerService, RecoveryEngine

    s = fixture_scope()
    stores = {d: FileStore(tmp_path / d, d) for d in set(DOMAINS) - {"registry"}}
    values = records(s)
    for domain in ("approval", "consumer"):
        result = child_call(
            lambda domain=domain: (
                stores[domain].append(s, values[domain].event, values[domain].record).model_dump()
            )
        )
        assert result["error"] is None
    ledger = FileLedger(tmp_path / "b-ledger.json")
    runtime = FileRuntime(tmp_path / "runtime", fault)
    controller = ControllerService(ledger, runtime, stores["controller"], lambda _: None)
    monkeypatch.setattr(cmod, "session_method", lambda: None)  # FILE_MODEL_ONLY, no real commands.
    result = child_call(lambda: controller.dispatch("create", dict(scope=s.model_dump())))
    if fault == "create_ack":
        assert result["error"] == "A42363_MODEL_CREATE_ACK_UNKNOWN"
        with pytest.raises(Fault, match="NO_SECOND_CREATE"):
            RecoveryEngine(ledger, runtime).create(s)
        return
    assert result["error"] is None
    row = [170001, "FILE_MODEL_PG17", *([False] * 6), [], *([False] * 4)]
    connection = NS(
        execute=lambda _: NS(fetchone=lambda: row), commit=lambda: None, close=lambda: None
    )
    raw = values["pg_owner"].record["raw"]
    runtime_owner = NS(
        verify_owner_connection=lambda c, s: None,
        inspect_owner=lambda s: {
            k: raw[k]
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
    owner = RawOwnerBackend(lambda _: connection, runtime_owner, stores["pg_owner"])
    assert child_call(lambda: owner.initialize(s))["error"] is None

    class RootModel:
        def call(self, method, value):
            if fault == "root_ack":
                raise Fault("A42363_ROOT_ACK_UNKNOWN")
            if method == "run":
                bounded_child(lambda: None)
                return dict(status="RUNNING", scope_sha256=scope_hash(s))
            return dict(
                manager_uid=0,
                execution_scope_terminated=fault != "root_scope",
                scope_sha256=scope_hash(s),
                epoch=s.epoch,
                cgroup_inode=1,
                proof_kind="FILE_MODEL_ONLY",
            )

    delegated = dmod.DelegatedExecution(RootModel(), s)
    supervisor = dmod.SupervisorService(
        delegated, None, delegated, stores["supervisor"], NS(publish=lambda _: None)
    )
    monkeypatch.setattr(dmod, "session_method", lambda: None)
    run = child_call(lambda: supervisor.dispatch("run", dict(scope=s.model_dump())))
    if fault == "root_ack":
        assert run["error"] == "A42363_ROOT_ACK_UNKNOWN"
        return
    assert run["error"] is None
    terminated = child_call(lambda: supervisor.dispatch("terminate", dict(scope=s.model_dump())))
    if fault == "root_scope":
        assert terminated["error"] == "A42363_ROOT_TERMINATION_UNPROVEN"
        return
    assert terminated["error"] is None
    if fault == "replacement":
        (runtime.path / "SECRET").write_bytes(canonical(dict(id="FOREIGN", epoch=s.epoch)))
    if fault == "missing_identity":
        rows = ledger.scan({})["events"]
        rows = [
            r
            for r in rows
            if not (
                r["request"]["resource"]["kind"] == "SECRET"
                and r["request"]["event"] == "OBSERVED_CREATED"
            )
        ]
        ledger.path.write_bytes(canonical(rows))
    reconciled = child_call(lambda: controller.dispatch("reconcile", dict(scope=s.model_dump())))
    assert reconciled["error"] is None
    if fault in ("replacement", "missing_identity", "remove_ack"):
        assert reconciled["result"]["record"]["status"] == "INCOMPLETE_QUARANTINED"
        if fault == "replacement":
            assert decode((runtime.path / "SECRET").read_bytes())["id"] == "FOREIGN"
        return
    delegation = dict(store_sha256="a" * 64, collector_sha256="b" * 64)
    proof = dict(
        **delegation,
        observer_uid=1007,
        controller_uid=s.controller_uid,
        readonly=True,
        namespace_sha256=s.namespace_sha256,
        epoch=s.epoch,
    )
    if fault == "namespace":
        proof["namespace_sha256"] = "f" * 64
    if fault == "observer_uid":
        proof["observer_uid"] = s.controller_uid
    if fault == "recreation":
        runtime.create(resources(s)[2])
    collector = NS(
        visibility=lambda _: proof,
        read_exact=lambda item: dict(
            status="UNKNOWN"
            if fault == "permission"
            else "ABSENT"
            if runtime.absent(item)
            else "PRESENT",
            code=125 if fault == "permission" else 1 if runtime.absent(item) else 0,
            identity=None if runtime.absent(item) else "RECREATED",
        ),
    )
    observer = IndependentObserver(1007, s.controller_uid, delegation, collector)
    source_ledger = ledger
    if fault == "ledger_hash":
        source_ledger = NS(
            scan=lambda _: dict(events=ledger.scan({})["events"], snapshot_sha256="f" * 64)
        )
    auditor = AbsenceService(
        observer, stores["absence_auditor"], stores["controller"], source_ledger
    )
    audited = child_call(lambda: auditor.dispatch("absent", dict(scope=s.model_dump())))
    if fault in ("namespace", "observer_uid", "permission", "recreation", "ledger_hash"):
        assert audited["error"] is not None
        assert stores["absence_auditor"].maybe_read(s, "ABSENT") is None
        return
    assert audited["error"] is None
    refs = {
        d: store.read(
            s,
            {
                "approval": "APPROVED",
                "consumer": "CONSUMED",
                "pg_owner": "OWNER_RAW",
                "controller": "RECONCILED",
                "supervisor": "TERMINATED",
                "absence_auditor": "ABSENT",
            }[d],
        ).model_dump()
        for d, store in stores.items()
    }
    if fault == "forged_reference":
        refs["controller"]["record"]["resource_ids"]["SECRET"] = sha(b"FORGED")
        with pytest.raises(Fault):
            Reviewer(ReceiptSet(stores)).review(s, refs)
        return
    result = Reviewer(ReceiptSet(stores)).review(s, refs)
    assert result["status"] == "OFFLINE_CROSS_DOMAIN_VERIFIED" and result["qualifies"] is False
    assert result["real_probe_sql_executed"] == 0


def test_AT70_platform_or_real_setsid_escape_never_becomes_scope_certificate(tmp_path, request):
    linux = sys.platform == "linux"
    request.node.user_properties.append(("linux_setsid_pidfd_executed", str(linux).lower()))
    if not linux:
        # Explicit platform result, not a fabricated execution of the Linux case.
        assert not hasattr(os, "pidfd_open")
        return
    from scripts.a42362_supervisor_service import run_fixed_offline

    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    code = (
        "import os,socket,array,time\n"
        "pid=os.fork()\n"
        "if pid: os._exit(0)\n"
        "os.setsid()\n"
        "fd=os.pidfd_open(os.getpid())\n"
        "s=socket.socket(fileno=" + str(child.fileno()) + ")\n"
        "s.sendmsg([b'OWNED'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[fd]))])\n"
        "os.close(1);os.close(2);time.sleep(20)\n"
    )
    owned_fd = None
    try:
        rc, raw = run_fixed_offline(
            sys.executable, ("-I", "-c", code), token_sha256="a" * 64, pass_fds=(child.fileno(),)
        )
        parent.settimeout(2)
        message, ancillary, _, _ = parent.recvmsg(16, socket.CMSG_SPACE(4))
        assert message == b"OWNED"
        fds = array.array("i")
        fds.frombytes(ancillary[0][2])
        assert len(fds) == 1
        owned_fd = fds[0]
        assert (rc, raw) == (0, b"")  # A command status, never scope termination.
        values, s = records(fixture_scope()), fixture_scope()
        values["supervisor"] = receipt(
            "supervisor",
            s,
            "TERMINATED",
            1,
            dict(execution_scope_terminated=False, physical_proven=False),
        )
        sources = {d: NS(read=lambda s, event, value=v: value) for d, v in values.items()}
        with pytest.raises(Fault, match="SCOPE_TERMINATION_UNPROVEN"):
            Reviewer(ReceiptSet(sources)).review(s, {d: v.model_dump() for d, v in values.items()})
    finally:
        if owned_fd is not None:
            signal.pidfd_send_signal(owned_fd, signal.SIGKILL)
            os.close(owned_fd)
        child.close()
        parent.close()


@pytest.mark.parametrize("cancel", [False, True])
def test_AT72_independent_fd_guardian_fires_while_handler_is_blocked(tmp_path, cancel):
    from scripts.a42363_supervisor import FDDeadlineGuardian

    # Private ordinary file is a model, never cgroup/physical termination evidence.
    fd = os.open(tmp_path / "held-scope-model", os.O_CREAT | os.O_RDWR | os.O_EXCL, 0o600)
    try:
        guardian = FDDeadlineGuardian(fd, 80)
        if cancel:
            assert guardian.finish() == "CANCELLED_AFTER_REAP"
            assert os.pread(fd, 1, 0) == b""
        else:
            time.sleep(0.2)  # Handler cannot service its own timeout here.
            assert os.pread(fd, 1, 0) == b"1"
            assert guardian.finish() == "DEADLINE_FIRED"
    finally:
        os.close(fd)
