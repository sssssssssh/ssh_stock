"""L1 Linux processes/Unix IPC only. Never PG/Podman/G1, credentials or cloud.

These tests intentionally need Linux; Windows runs only portable L0 tests locally.
No skip/xfail is used to count a missing Linux primitive as an acceptance result.
"""

import os
import signal
import socket
import struct
import sys
import time
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from scripts.a42361_contract import Fault, canonical, decode
from scripts.a42362_supervisor_service import manifest_allowed, run_fixed_offline


@pytest.mark.parametrize("allowed", [True, False])
def test_AT11_AT64_AT68_kernel_peer_uid_checked_before_dispatch(tmp_path, monkeypatch, allowed):
    from scripts import a42361_deployment as d

    path = tmp_path / "consumer.sock"
    config = NS(
        root_directory=str(tmp_path), consumer=NS(socket_name="consumer", peer_uid=os.getuid())
    )
    monkeypatch.setattr(d, "installed", lambda _: config)
    read_fd, write_fd = os.pipe()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    os.chmod(path, 0o600)
    listener.listen(1)

    class Receiver(d.LocalReceiver):
        domain = "consumer"

        def allowed_uids(self, value):
            return {os.getuid()} if allowed else set()

        def dispatch(self, uid, method, body):
            os.write(write_fd, b"D")
            return dict(status="OFFLINE_CONTROLLED_RESPONSE", qualifies=False)

    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        try:
            Receiver(object()).serve_once(listener.fileno(), 1000)
            os._exit(0)
        except BaseException:
            os._exit(1)
    os.close(write_fd)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(2)
            peer.connect(str(path))
            request = canonical(dict(schema_version="a42361.rpc.v1", method="receipt", body={}))
            peer.sendall(struct.pack("!I", len(request)) + request)
            if allowed:
                size = struct.unpack("!I", peer.recv(4))[0]
                result = decode(peer.recv(size))
                assert result["qualifies"] is False
            else:
                try:
                    assert peer.recv(4) == b""
                except ConnectionResetError:
                    pass
        _, status = os.waitpid(pid, 0)
        assert (status == 0) is allowed
        assert os.read(read_fd, 2) == (b"D" if allowed else b"")
    finally:
        listener.close()
        os.close(read_fd)


@pytest.mark.parametrize("operation", ["ipc", "fsync", "stdout"])
def test_AT52_AT55_blocking_child_is_killed_outside_handler(tmp_path, operation):
    marker = tmp_path / ".incomplete"
    marker.write_bytes(b"OFFLINE_INCOMPLETE")
    code = {
        "ipc": "import time;time.sleep(60)",
        "fsync": "import os,time;os.fsync=lambda fd:time.sleep(60);os.fsync(1)",
        "stdout": "import os,time;os.close(1);time.sleep(60)",
    }[operation]
    started = time.monotonic()
    with pytest.raises(Fault):
        run_fixed_offline(sys.executable, ("-I", "-c", code), token_sha256="a" * 64, timeout_ms=150)
    assert time.monotonic() - started < 3
    assert marker.exists() and not manifest_allowed(tmp_path)


def test_AT49_normal_controlled_child_is_reaped():
    status, raw = run_fixed_offline(
        sys.executable, ("-I", "-c", "print('OFFLINE_ONLY')"), token_sha256="a" * 64
    )
    assert status == 0 and raw.strip() == b"OFFLINE_ONLY"


def test_AT50_parent_exit_with_live_grandchild_is_not_scope_success(tmp_path):
    path = tmp_path / "grandchild.pid"
    # The child exits; its same-group descendant retains stdout. The production
    # helper must reject, NOT kill a possibly reused group after reaping the leader.
    code = (
        "import os,time;pid=os.fork();"
        "\nif pid==0:\n open(" + repr(str(path)) + ",'w').write(str(os.getpid()));time.sleep(60)"
        "\nelse: os._exit(0)"
    )
    try:
        with pytest.raises(Fault) as caught:
            run_fixed_offline(
                sys.executable, ("-I", "-c", code), token_sha256="a" * 64, timeout_ms=300
            )
        assert caught.value.first_error == "A42362_OUTER_IO_DEADLINE"
        assert caught.value.cleanup_codes == ["A42362_TERMINATION_NOT_PROVEN"]
    finally:
        # Test-only cleanup: kernel pidfd pins this exact fixture process, no PID/group scan kill.
        if path.exists():
            pid = int(path.read_text())
            try:
                fd = os.pidfd_open(pid)
            except ProcessLookupError:
                fd = None
            if fd is not None:
                try:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                finally:
                    os.close(fd)


def test_AT36_actual_socket_directory_rejects_replacement_and_never_recurses(tmp_path):
    from scripts.a42361_offline_cases import binding
    from scripts.a42362_contract import Scope, resources
    from scripts.a42362_reconcile import ExactSocketDirectory

    s = Scope(
        token_id="32345678-1234-4234-8234-123456789012",
        binding=binding(),
        payload_sha256="1" * 64,
        image_digest="sha256:" + "2" * 64,
        controller_uid=os.getuid(),
        namespace_sha256="3" * 64,
        epoch="42345678-1234-4234-8234-123456789012",
    )
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        directory = ExactSocketDirectory(fd, os.getuid(), os.getgid())
        item = resources(s)[0]
        original = directory.create(item)
        (Path(tmp_path) / item.name / "unrelated.txt").write_text("DO_NOT_DELETE")
        with pytest.raises(Fault):
            directory.remove(item, original)
        assert (Path(tmp_path) / item.name / "unrelated.txt").read_text() == "DO_NOT_DELETE"
    finally:
        os.close(fd)
