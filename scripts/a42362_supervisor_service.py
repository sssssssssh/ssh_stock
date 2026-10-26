"""External bounded process/IO supervision. No public worker-launch command."""

import os
import selectors
import signal
import stat
import subprocess
import time
from dataclasses import dataclass

from scripts.a42361_contract import checked, sha
from scripts.a42362_contract import Fault, Lookup, file_identity, require

_OWNED = object()


@dataclass(frozen=True)
class ProcessScope:
    process: object
    pid: int
    start_ticks: int
    token_sha256: str
    _seal: object


def start_ticks(pid):
    # Linux comm can contain spaces/parentheses; split only after its final ')'.
    with open(f"/proc/{pid}/stat", encoding="ascii") as stream:
        raw = stream.read(8192)
    return int(raw.rsplit(")", 1)[1].split()[19])


def scope_empty(pgid):
    for name in os.listdir("/proc"):
        if name.isdigit():
            try:
                with open(f"/proc/{name}/stat", encoding="ascii") as stream:
                    fields = stream.read(8192).rsplit(")", 1)[1].split()
                if int(fields[2]) == pgid and fields[0] != "Z":
                    return False
            except FileNotFoundError:
                continue
    return True


def terminate_scope(scope, timeout_ms=2000):
    """Never signal a received PID or a reused group after its direct child is reaped.

    A process group cannot prove that descendants did not setsid(). Consequently this
    routine never claims cgroup-level termination, even after the visible group empties.
    A future installed cgroup capability is a separate, currently unresolved method.
    """
    require(
        type(scope) is ProcessScope
        and scope._seal is _OWNED
        and timeout_ms == 2000
        and scope.pid == scope.process.pid
        and scope.pid > 1
        and scope.pid != os.getpid(),
        "A42362_FOREIGN_SCOPE_REJECTED",
    )
    deadline = time.monotonic_ns() + timeout_ms * 1_000_000
    if scope.process.poll() is None:
        require(
            start_ticks(scope.pid) == scope.start_ticks and os.getpgid(scope.pid) == scope.pid,
            "A42362_SCOPE_REUSED",
        )
        os.killpg(scope.pid, signal.SIGTERM)
        try:
            scope.process.wait(timeout=0.25)
        except subprocess.TimeoutExpired:
            require(
                start_ticks(scope.pid) == scope.start_ticks and os.getpgid(scope.pid) == scope.pid,
                "A42362_SCOPE_REUSED",
            )
            os.killpg(scope.pid, signal.SIGKILL)
            remaining = (deadline - time.monotonic_ns()) / 1e9
            require(remaining > 0, "A42362_TERMINATION_NOT_PROVEN")
            scope.process.wait(timeout=remaining)
    require(
        time.monotonic_ns() <= deadline and scope_empty(scope.pid), "A42362_TERMINATION_NOT_PROVEN"
    )
    return dict(
        direct_child_reaped=True,
        visible_group_empty=True,
        execution_scope_terminated=False,
        status="TERMINATION_NOT_PROVEN",
    )


def run_fixed_offline(executable, arguments, *, token_sha256, timeout_ms=1000, pass_fds=()):
    """Private bounded primitive; never exposed by RPC or accepted as caller argv.

    Used for pre-reviewed installed helpers and controlled L1 fixtures, NOT G1 workers.
    Caps stdout while it is read, and can terminate a helper stuck inside fsync or IPC.
    """
    require(
        0 < timeout_ms <= 2000 and type(arguments) is tuple and len(arguments) <= 8,
        "A42362_HELPER_BUDGET_REJECTED",
    )
    child = subprocess.Popen(
        [executable, *arguments],
        env={},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
        pass_fds=pass_fds,
    )
    scope = ProcessScope(child, child.pid, start_ticks(child.pid), token_sha256, _OWNED)
    deadline, result = time.monotonic_ns() + timeout_ms * 1_000_000, bytearray()
    try:
        os.set_blocking(child.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = (deadline - time.monotonic_ns()) / 1e9
                require(remaining > 0, "A42362_OUTER_IO_DEADLINE")
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fd, 4096)
                    result.extend(chunk)
                    require(len(result) <= 65536, "A42362_HELPER_OUTPUT_LIMIT")
                    if not chunk:
                        selector.unregister(key.fd)
            remaining = (deadline - time.monotonic_ns()) / 1e9
            require(remaining > 0, "A42362_OUTER_IO_DEADLINE")
            child.wait(timeout=remaining)
        require(scope_empty(child.pid), "A42362_DESCENDANT_REMAINS")
        return child.returncode, bytes(result)
    except BaseException as error:
        first = error.code if isinstance(error, Fault) else "A42362_HELPER_INCOMPLETE"
        failure = Fault(first)
        failure.first_error = first
        failure.cleanup_codes = []
        try:
            terminate_scope(scope)
        except BaseException:
            failure.cleanup_codes.append("A42362_TERMINATION_NOT_PROVEN")
        raise failure from None
    finally:
        child.stdout.close()


def verify_worker_fd(fd, expected_sha256):
    meta = os.fstat(fd)
    require(
        stat.S_ISREG(meta.st_mode)
        and meta.st_uid == 0
        and meta.st_nlink == 1
        and meta.st_mode & 0o022 == 0
        and meta.st_size <= 1_000_000,
        "A42362_INSTALLED_WORKER_UNTRUSTED",
    )
    raw = os.pread(fd, 1_000_001, 0)
    require(
        sha(raw) == expected_sha256 and file_identity(os.fstat(fd)) == file_identity(meta),
        "A42362_INSTALLED_WORKER_UNTRUSTED",
    )


class SupervisorService:
    def __init__(self, installation=None, receipt_store=None):
        self.installation, self.receipt_store = installation, receipt_store

    def dispatch(self, peer_uid, method, body):
        from scripts.a42362_service_host import installation

        c = installation(self.installation)
        require(
            c.domain == "supervisor" and os.getuid() == c.uid and peer_uid in c.read_uids,
            "A42362_SUPERVISOR_PEER_REJECTED",
        )
        require(method in ("run", "terminate", "receipt"), "A42362_METHOD_REJECTED")
        q = checked(Lookup, body)
        require(self.receipt_store is not None, "A42362_SUPERVISOR_NOT_CONFIGURED")
        if method == "receipt":
            return self.receipt_store.read_supervisor(q.scope)
        if method == "terminate":
            # No unsealed process object/PID from the network. The supervisor must own it.
            raise Fault("A42362_NO_OWNED_EXECUTION_SCOPE")
        self.receipt_store.require_preconditions(q.scope)
        from scripts.a42362_pg_owner_service import require_session_method

        require_session_method()  # Before launch, socket/DB or G1 credential access.


def manifest_allowed(directory):
    return not (directory / ".incomplete").exists() and (directory / "manifest.json").is_file()
