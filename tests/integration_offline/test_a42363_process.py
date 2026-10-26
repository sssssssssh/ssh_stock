"""L1 fork/Unix FD/files only. No PG17/Podman/cgroup/systemd or G1.

Immutable fixture stores are DB_MODEL_ONLY. Separate processes prove transport,
not multi-UID deployment. Physical kernel containment is not claimed by this test.
"""

import array
import copy
import os
import socket
import time
from types import SimpleNamespace as NS

import pytest

from scripts.a42361_contract import canonical, decode
from scripts.a42361_offline_cases import binding
from scripts.a42362_contract import Scope
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
        ),
    )
    return {
        "approval": receipt("approval", s, "APPROVED", 1, dict(model="DB_MODEL_ONLY")),
        "consumer": receipt("consumer", s, "CONSUMED", 1, dict(model="DB_MODEL_ONLY")),
        "pg_owner": receipt("pg_owner", s, "OWNER_RAW", 1, dict(model="DB_MODEL_ONLY")),
        "controller": c,
        "supervisor": receipt(
            "supervisor",
            s,
            "TERMINATED",
            1,
            dict(execution_scope_terminated=True, physical_proven=False, model="DB_MODEL_ONLY"),
        ),
        "absence_auditor": receipt(
            "absence_auditor",
            s,
            "ABSENT",
            1,
            dict(destruction_digest=c.digest, observations=[dict(model="DB_MODEL_ONLY")] * 8),
        ),
    }


class RemoteSource:
    def __init__(self, channel, value):
        self.channel, self.value = channel, value

    def read(self, s, event):
        self.channel.send(canonical(dict(scope_sha256=scope_hash(s), event=event)))
        raw, ancillary, _, _ = self.channel.recvmsg(65536, socket.CMSG_SPACE(4))
        fds = array.array("i")
        for level, kind, data in ancillary:
            assert (level, kind) == (socket.SOL_SOCKET, socket.SCM_RIGHTS)
            fds.frombytes(data[: len(data) - len(data) % fds.itemsize])
        assert len(fds) == 1
        try:
            assert os.read(fds[0], 64) == b"DB_MODEL_ONLY_INDEPENDENT_PROCESS"
        finally:
            os.close(fds[0])
        assert decode(raw) == self.value.model_dump()
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
            parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
            channels.append(parent)
            fd = os.open(tmp_path / domain, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.write(fd, b"DB_MODEL_ONLY_INDEPENDENT_PROCESS")
            os.lseek(fd, 0, 0)
            pid = os.fork()
            if pid == 0:
                parent.close()
                try:
                    child.settimeout(2)
                    request = decode(child.recv(65536))
                    assert request == dict(scope_sha256=scope_hash(s), event=value.event)
                    child.sendmsg(
                        [canonical(value.model_dump())],
                        [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))],
                    )
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
