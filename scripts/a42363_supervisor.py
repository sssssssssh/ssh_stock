"""Installed FD capabilities and external deadlines. No public launch switches."""

import ctypes
import hashlib
import os
import select
import selectors
import signal
import stat
import time

from scripts.a42361_contract import canonical, decode, sha
from scripts.a42362_contract import file_identity
from scripts.a42363_contract import Fault, lookup, require, scope_hash, session_method


def run_installed_command(executable, arguments, pass_fds=(), command_scope=None):
    # Direct-child exit alone cannot certify all runtime subprocesses. Real callers
    # need a manager-installed nondelegated kernel scope; never fallback to PGID.
    require(type(command_scope) is CgroupScope, "COMMAND_SCOPE_REQUIRED")
    return command_scope.run_command(executable, arguments, pass_fds)


def _collect_command(child, stdout_fd, deadline):
    result = bytearray()
    os.set_blocking(stdout_fd, False)
    with selectors.DefaultSelector() as selector:
        selector.register(stdout_fd, selectors.EVENT_READ)
        while selector.get_map():
            remaining = (deadline - time.monotonic_ns()) / 1e9
            require(remaining > 0, "COMMAND_DEADLINE")
            for key, _ in selector.select(remaining):
                chunk = os.read(key.fd, 4096)
                result.extend(chunk)
                require(len(result) <= 65536, "COMMAND_OUTPUT_LIMIT")
                if not chunk:
                    selector.unregister(key.fd)
    child.reap(max(1, (deadline - time.monotonic_ns()) // 1_000_000), close_fd=False)
    return os.waitstatus_to_exitcode(child.status), bytes(result)


def bounded_child(operation, *, timeout_ms=2000):
    """Direct unreaped child only. Never signal a request PID or recycled process group."""
    require(type(timeout_ms) is int and 0 < timeout_ms <= 2000, "DEADLINE_BUDGET")
    rfd, wfd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(rfd)
        try:
            operation()
            os.write(wfd, b"OK")
            os._exit(0)
        except BaseException:
            os._exit(1)
    os.close(wfd)
    deadline = time.monotonic_ns() + timeout_ms * 1_000_000
    reaped = False
    try:
        ready, _, _ = select.select([rfd], [], [], max(0, (deadline - time.monotonic_ns()) / 1e9))
        if not ready:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            reaped = True
            raise Fault("A42363_OUTER_DEADLINE")
        raw = os.read(rfd, 3)
        _, status = os.waitpid(pid, 0)
        reaped = True
        require(raw == b"OK" and status == 0, "CHILD_INCOMPLETE")
    finally:
        if not reaped:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        os.close(rfd)


class CgroupScope:
    """Pinned administrator-owned cgroup v2 directory and kill/events/procs FDs.

    No user-selected path/PID. Physical use needs root-manager provisioning and immutable
    nondelegated ownership. Ordinary L1 files cannot be accepted as kernel cgroup proof.
    """

    def __init__(self, directory_fd, kill_fd, events_fd, procs_fd, scope_sha256, epoch):
        self.directory_fd, self.kill_fd, self.events_fd, self.procs_fd = (
            directory_fd,
            kill_fd,
            events_fd,
            procs_fd,
        )
        self.scope_sha256, self.epoch = scope_sha256, epoch
        meta = os.fstat(directory_fd)
        require(
            stat.S_ISDIR(meta.st_mode) and meta.st_uid == 0 and meta.st_mode & 0o022 == 0,
            "CGROUP_OWNER",
        )
        # fstatfs magic protects against ordinary files masquerading as a cgroup FD.
        buf = ctypes.create_string_buffer(256)
        libc = ctypes.CDLL(None, use_errno=True)
        require(
            libc.fstatfs(directory_fd, buf) == 0
            and ctypes.c_long.from_buffer(buf).value == 0x63677270,
            "CGROUP_KERNEL_REQUIRED",
        )
        self.identity = file_identity(meta)[:6]
        for name, fd in (
            ("cgroup.kill", kill_fd),
            ("cgroup.events", events_fd),
            ("cgroup.procs", procs_fd),
        ):
            expected = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            actual = os.fstat(fd)
            require(
                (expected.st_dev, expected.st_ino) == (actual.st_dev, actual.st_ino)
                and actual.st_uid == 0,
                "CGROUP_FD_BINDING",
            )

    def attach(self, pid):
        require(type(pid) is int and pid > 1, "OWNED_CHILD_REQUIRED")
        os.write(self.procs_fd, str(pid).encode())

    def run_command(self, executable, arguments, pass_fds):
        """Blocked fork -> attach -> exec FD, guardian -> all descendants -> reap.

        This internal manager capability is never an RPC argv interface. Ordinary
        private files cannot instantiate this class, including in L1 tests.
        """
        require(type(arguments) is tuple and 0 < len(arguments) <= 64, "COMMAND_ARGUMENTS")
        executable_fd = os.open(executable, os.O_RDONLY | os.O_NOFOLLOW)
        meta = os.fstat(executable_fd)
        require(
            stat.S_ISREG(meta.st_mode) and meta.st_uid == 0 and meta.st_mode & 0o022 == 0,
            "COMMAND_EXECUTABLE",
        )
        guardian = FDDeadlineGuardian(self.kill_fd, 1000)
        read_fd, write_fd = os.pipe()
        gate_r, gate_w = os.pipe()
        child = None
        first = None
        try:
            pid = os.fork()
            if pid == 0:
                try:
                    os.close(read_fd)
                    os.close(gate_w)
                    os.close(guardian.write_fd)  # Child may not keep parent-death pipe alive.
                    require(os.read(gate_r, 1) == b"G", "COMMAND_GATE")
                    os.dup2(write_fd, 1)
                    null = os.open(os.devnull, os.O_RDWR)
                    os.dup2(null, 0)
                    os.dup2(null, 2)
                    keep = {0, 1, 2, executable_fd, *pass_fds}
                    for name in os.listdir("/proc/self/fd"):
                        fd = int(name)
                        if fd not in keep:
                            try:
                                os.close(fd)
                            except OSError:
                                pass
                    for fd in keep:
                        os.set_inheritable(fd, True)
                    os.execve(executable_fd, [executable, *arguments], {})
                except BaseException:
                    os._exit(126)
            child = _adopt_forked_child(pid)
            os.close(write_fd)
            write_fd = None
            self.attach(pid)
            os.write(gate_w, b"G")
            result = _collect_command(child, read_fd, time.monotonic_ns() + 1_000_000_000)
            return result
        except BaseException as error:
            first = error
            raise
        finally:
            cleanup = []
            if child is not None:
                try:
                    self.terminate(child)  # Also when leader exited and closed stdout.
                    guardian.finish()
                except BaseException:
                    cleanup.append("A42363_COMMAND_SCOPE_TERMINATION_UNKNOWN")
            for fd in (read_fd, write_fd, gate_r, gate_w, executable_fd):
                if fd is not None:
                    os.close(fd)
            if cleanup:
                if first is None:
                    raise Fault(cleanup[0]) from None
                first.cleanup_codes = list(getattr(first, "cleanup_codes", [])) + cleanup

    def terminate(self, child):
        require(file_identity(os.fstat(self.directory_fd))[:6] == self.identity, "CGROUP_REPLACED")
        # A pinned pidfd identifies the exact leader; descendants, including setsid, stay
        # in a nondelegated cgroup. kill_fd targets that scope, never a recycled PID/PGID.
        if child.poll() is None:
            signal.pidfd_send_signal(child.pidfd, signal.SIGTERM)
        os.write(self.kill_fd, b"1")
        deadline = time.monotonic_ns() + 2_000_000_000
        while time.monotonic_ns() < deadline:
            raw = os.pread(self.events_fd, 4096, 0)
            if b"populated 0\n" in raw:
                child.reap(max(1, (deadline - time.monotonic_ns()) // 1_000_000))
                return dict(
                    execution_scope_terminated=True,
                    epoch=self.epoch,
                    scope_sha256=self.scope_sha256,
                    cgroup_inode=self.identity[1],
                )
            time.sleep(0.005)
        raise Fault("A42363_TERMINATION_NOT_PROVEN")


class OwnedChild:
    def __init__(self, pid):
        self.pid, self.pidfd, self.status = pid, os.pidfd_open(pid), None

    def poll(self):
        if self.status is None:
            observed, status = os.waitpid(self.pid, os.WNOHANG)
            if observed:
                self.status = status
        return self.status

    def reap(self, timeout_ms, *, close_fd=True):
        deadline = time.monotonic_ns() + timeout_ms * 1_000_000
        while self.poll() is None and time.monotonic_ns() < deadline:
            time.sleep(0.005)
        require(self.status is not None, "WORKER_NOT_REAPED")
        if close_fd and self.pidfd is not None:
            os.close(self.pidfd)
            self.pidfd = None


def _adopt_forked_child(pid):
    """If pidfd acquisition fails, only our still-unreaped fork may be signalled."""
    try:
        return OwnedChild(pid)
    except BaseException:
        observed, _ = os.waitpid(pid, os.WNOHANG)
        if not observed:
            os.kill(pid, signal.SIGKILL)
            deadline = time.monotonic_ns() + 2_000_000_000
            while True:
                observed, _ = os.waitpid(pid, os.WNOHANG)
                if observed:
                    break
                require(time.monotonic_ns() < deadline, "OWNED_CHILD_REAP_UNPROVEN")
                time.sleep(0.005)
        raise


class InstalledWorkerLauncher:
    """Root-manager-only constructor; worker source and credentials arrive as trusted FDs."""

    def __init__(
        self,
        python_fd,
        worker_fd,
        worker_sha256,
        worker_uid,
        worker_gid,
        supervisor_uid,
        python_sha256=None,
    ):
        require(
            os.getuid() == 0 and worker_uid > 0 and worker_uid != supervisor_uid,
            "DISTINCT_INSTALLED_WORKER_UID",
        )
        from scripts.a42362_supervisor_service import verify_worker_fd

        verify_worker_fd(worker_fd, worker_sha256)
        meta = os.fstat(python_fd)
        require(
            stat.S_ISREG(meta.st_mode) and meta.st_uid == 0 and meta.st_mode & 0o022 == 0,
            "PYTHON_FD_UNTRUSTED",
        )
        require(
            type(python_sha256) is str
            and len(python_sha256) == 64
            and 0 < meta.st_size <= 64_000_000,
            "PYTHON_DIGEST_REQUIRED",
        )
        digest, offset = hashlib.sha256(), 0
        while offset < meta.st_size:
            raw = os.pread(python_fd, min(65536, meta.st_size - offset), offset)
            require(raw, "PYTHON_FD_CHANGED")
            digest.update(raw)
            offset += len(raw)
        require(
            digest.hexdigest() == python_sha256 and os.fstat(python_fd) == meta, "PYTHON_FD_CHANGED"
        )
        self.python_fd, self.worker_fd = python_fd, worker_fd
        self.python_identity, self.worker_sha256 = file_identity(meta), worker_sha256
        require(python_fd > 3 and worker_fd > 3 and python_fd != worker_fd, "RESERVED_WORKER_FDS")
        self.uid, self.gid = worker_uid, worker_gid

    def launch(self, cgroup, credential_source):
        # This method is an internal manager capability, never an RPC argument surface.
        import array
        import socket

        require(type(cgroup) is CgroupScope and callable(credential_source), "INSTALLED_LAUNCHER")
        require(
            file_identity(os.fstat(self.python_fd)) == self.python_identity, "PYTHON_FD_CHANGED"
        )
        from scripts.a42362_supervisor_service import verify_worker_fd

        verify_worker_fd(self.worker_fd, self.worker_sha256)
        parent, gate = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        pid = os.fork()
        if pid == 0:
            try:
                parent.close()
                raw, ancillary, flags, _ = gate.recvmsg(1, socket.CMSG_SPACE(4))
                fds = array.array("i")
                for level, kind, data in ancillary:
                    require(
                        level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS, "CREDENTIAL_FD"
                    )
                    fds.frombytes(data)
                require(raw == b"G" and flags == 0 and len(fds) == 1, "LAUNCH_GATE")
                credential_fd = fds[0]
                gate.close()
                # Fixed descriptor3, never argv/env credential discovery. Preserve worker
                # source and Python FDs; close all other inherited privileged descriptors.
                if credential_fd != 3:
                    os.dup2(credential_fd, 3)
                allowed = {0, 1, 2, 3, self.python_fd, self.worker_fd}
                for entry in os.listdir("/proc/self/fd"):
                    fd = int(entry)
                    if fd not in allowed:
                        try:
                            os.close(fd)
                        except OSError:
                            pass
                os.setgroups([])
                os.setgid(self.gid)
                os.setuid(self.uid)
                require(ctypes.CDLL(None).prctl(38, 1, 0, 0, 0) == 0, "NO_NEW_PRIVILEGES")
                for fd in (self.python_fd, self.worker_fd, 3):
                    os.set_inheritable(fd, True)
                os.execve(
                    self.python_fd, ["python", "-I", "/proc/self/fd/" + str(self.worker_fd)], {}
                )
            except BaseException:
                os._exit(1)
        gate.close()
        try:
            child = _adopt_forked_child(pid)
        except BaseException:
            parent.close()
            raise
        credential_fd = None
        try:
            cgroup.attach(pid)  # Child is blocked until moved to nondelegated scope.
            credential_fd = credential_source(pid)
            parent.sendmsg(
                [b"G"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [credential_fd]))]
            )
        except BaseException:
            signal.pidfd_send_signal(child.pidfd, signal.SIGKILL)
            child.reap(2000)
            raise
        finally:
            parent.close()
            if credential_fd is not None:
                os.close(credential_fd)
        return child


class ArtifactPublisher:
    def __init__(self, directory_fd):
        self.fd = directory_fd

    def publish(self, record):
        raw = canonical(record)

        def write():
            self._publish_inside(raw)

        try:
            bounded_child(write)
        except BaseException as first:
            # All filesystem mutations, including the marker, are in independently
            # bounded children. If the filesystem cannot even restore a marker, the
            # missing final D receipt remains an independent rejection condition.
            def restore():
                fd = os.open(
                    ".incomplete", os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=self.fd
                )
                os.close(fd)
                os.fsync(self.fd)

            try:
                bounded_child(restore)
            except BaseException:
                first.cleanup_codes = ["A42363_ARTIFACT_MARKER_RESTORE_UNPROVEN"]
            raise
        return dict(qualifies=False, artifact_sha256=sha(raw))

    def _publish_inside(self, raw):
        meta = os.fstat(self.fd)
        require(
            stat.S_ISDIR(meta.st_mode)
            and meta.st_uid == os.getuid()
            and stat.S_IMODE(meta.st_mode) == 0o700,
            "ARTIFACT_OWNER",
        )
        # The outer guardian supervises this entire fixed operation.
        marker = os.open(
            ".incomplete",
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o600,
            dir_fd=self.fd,
        )
        os.close(marker)

        def write():
            for name, data in (
                ("evidence.json", raw),
                (
                    "manifest.json",
                    canonical(
                        dict(
                            files={"evidence.json": dict(bytes=len(raw), sha256=sha(raw))},
                            qualifies=False,
                        )
                    ),
                ),
            ):
                fd = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=self.fd,
                )
                try:
                    view = memoryview(data)
                    while view:
                        n = os.write(fd, view)
                        require(n > 0, "ARTIFACT_SHORT_WRITE")
                        view = view[n:]
                    os.fsync(fd)
                finally:
                    os.close(fd)
            os.fsync(self.fd)

        write()
        os.unlink(".incomplete", dir_fd=self.fd)
        os.fsync(self.fd)


class SupervisorService:
    def __init__(self, launcher, owner, cgroup, store, publisher):
        self.launcher, self.owner, self.cgroup = launcher, owner, cgroup
        self.store, self.publisher, self.child = store, publisher, None

    def dispatch(self, method, body):
        scope = lookup(body)
        if method == "receipt":
            return self.store.read(scope, "TERMINATED").model_dump()
        if method == "run":
            session_method()  # No credentials or launch before independent protocol approval.
            require(self.store.maybe_read(scope, "RUN_ATTEMPTED") is None, "NO_SECOND_WORKER")
            self.store.append(scope, "RUN_ATTEMPTED", dict(qualifies=False))
            self.child = self.launcher.launch(self.cgroup, lambda pid: self.owner.lease(scope, pid))
            return self.store.append(scope, "RUNNING", dict(qualifies=False)).model_dump()
        previous = self.store.maybe_read(scope, "TERMINATED")
        if previous is not None:
            return previous.model_dump()
        require(method == "terminate", "SUPERVISOR_METHOD")
        running = self.store.read(scope, "RUN_ATTEMPTED")
        require(running.scope_sha256 == scope_hash(scope), "NO_OWNED_EXECUTION_SCOPE")
        require(
            self.cgroup.scope_sha256 == scope_hash(scope) and self.cgroup.epoch == scope.epoch,
            "WORKER_SCOPE_BINDING",
        )
        result = self.cgroup.terminate(self.child)
        # D's L1 receipt never upgrades to physical G1 even if kernel proof is configured.
        result.update(qualifies=False, physical_proven=False, terminated_ns=time.monotonic_ns())
        proved = self.store.maybe_read(scope, "TERMINATION_PROVEN")
        if proved is None:
            proved = self.store.append(scope, "TERMINATION_PROVEN", result)
        published = self.publisher.publish(proved.model_dump())
        # A final committed success must never precede artifact publication. Unknown
        # publication ACK stops this attempt; no automatically valid half-evidence.
        result["publication"] = published
        committed = self.store.append(scope, "TERMINATED", result)
        return committed.model_dump()


class RootManager:
    """Privileged installed manager receiver; separate from D and Worker identities.

    Manager receives only its independently installed single scope, cgroup and source
    capabilities. It never accepts a request PID, argv, environment, DSN or path.
    Transport supplies the kernel peer UID, not a JSON principal.
    """

    def __init__(self, supervisor_uid, scope, cgroup, launcher, owner):
        require(os.getuid() == 0 and supervisor_uid > 0, "ROOT_MANAGER_REQUIRED")
        require(
            cgroup.scope_sha256 == scope_hash(scope) and cgroup.epoch == scope.epoch,
            "ROOT_SCOPE_BINDING",
        )
        self.uid, self.scope, self.cgroup = supervisor_uid, scope, cgroup
        self.launcher, self.owner, self.child, self.result = launcher, owner, None, None
        self.attempted, self.guardian = False, None
        self.failure = None

    def dispatch(self, peer_uid, method, body):
        require(
            os.getuid() == 0 and peer_uid == self.uid and lookup(body) == self.scope,
            "ROOT_MANAGER_PEER_OR_SCOPE",
        )
        require(method in ("run", "terminate", "receipt"), "ROOT_METHOD")
        require(self.failure is None, "ROOT_EXECUTION_QUARANTINED")
        if method == "run":
            session_method()
            require(not self.attempted, "NO_SECOND_WORKER")
            self.attempted = True  # Sticky even when lease, fork, attach or ACK fails.
            try:
                self.guardian = FDDeadlineGuardian(self.cgroup.kill_fd, 3000)
                self.child = self.launcher.launch(
                    self.cgroup, lambda pid: self.owner.lease(self.scope, pid)
                )
            except BaseException:
                self.failure = "GUARDIAN_ARM_FAILED" if self.guardian is None else "LAUNCH_UNKNOWN"
                # No worker can start before the guardian. If launch ACK is unknown,
                # keep the guardian armed; do not cancel an unknown live scope.
                if self.child is not None:
                    try:
                        self.cgroup.terminate(self.child)
                    except BaseException:
                        self.failure = "GUARDIAN_ARM_AND_CLEANUP_FAILED"
                raise Fault("A42363_" + self.failure) from None
            return dict(status="RUNNING", qualifies=False, scope_sha256=scope_hash(self.scope))
        if self.result is not None:
            return self.result
        require(method == "terminate" and self.child is not None, "TERMINATION_NOT_PROVEN")
        try:
            result = dict(
                self.cgroup.terminate(self.child),
                manager_uid=0,
                supervisor_uid=self.uid,
                qualifies=False,
            )
            if self.guardian is not None:
                result["guardian_status"] = self.guardian.finish()
        except BaseException:
            self.failure = "TERMINATION_NOT_PROVEN"
            raise
        self.result = result  # Cache only after the guardian has also been reaped.
        return self.result


class FDDeadlineGuardian:
    """Out-of-process hard wall: authorization1s + SQL2s, not an elapsed post-check.

    Production caller passes only its verified nondelegated cgroup.kill FD. L1 tests
    pass private ordinary files and make no physical kernel claims. No PID signalling.
    Parent death/EOF also fires the exact held FD; cancellation follows proven reaping.
    """

    def __init__(self, kill_fd, timeout_ms):
        require(type(timeout_ms) is int and 0 < timeout_ms <= 3000, "GUARDIAN_BUDGET")
        read_fd, write_fd = os.pipe()
        ack_r, ack_w = os.pipe()
        try:
            pid = os.fork()
        except BaseException:
            for fd in (read_fd, write_fd, ack_r, ack_w):
                os.close(fd)
            raise
        if pid == 0:
            os.close(write_fd)
            os.close(ack_r)
            try:
                os.write(ack_w, b"ARMED")
                os.close(ack_w)
                ready, _, _ = select.select([read_fd], [], [], timeout_ms / 1000)
                if ready and os.read(read_fd, 1) == b"D":
                    os._exit(0)
                os.write(kill_fd, b"1")
                os._exit(2)
            except BaseException:
                os._exit(3)
        os.close(read_fd)
        os.close(ack_w)
        try:
            armed, _, _ = select.select([ack_r], [], [], 0.2)
            require(armed and os.read(ack_r, 6) == b"ARMED", "GUARDIAN_ARM_FAILED")
        except BaseException:
            os.close(write_fd)
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            raise
        finally:
            os.close(ack_r)
        self.pid, self.write_fd, self.status = pid, write_fd, None

    def finish(self):
        require(self.status is None, "GUARDIAN_ALREADY_REAPED")
        try:
            os.write(self.write_fd, b"D")
        except BrokenPipeError:
            pass  # The independent deadline may already have fired.
        finally:
            os.close(self.write_fd)
        deadline = time.monotonic_ns() + 2_000_000_000
        while True:
            observed, status = os.waitpid(self.pid, os.WNOHANG)
            if observed:
                break
            require(time.monotonic_ns() < deadline, "GUARDIAN_REAP_NOT_PROVEN")
            time.sleep(0.005)
        self.status = status
        require(os.WIFEXITED(status) and os.WEXITSTATUS(status) in (0, 2), "GUARDIAN_INCOMPLETE")
        return "CANCELLED_AFTER_REAP" if os.WEXITSTATUS(status) == 0 else "DEADLINE_FIRED"


class RootManagerClient:
    """Held connected private Unix channel, pinned kernel-root peer, no path lookup."""

    def __init__(self, channel):
        import socket
        import struct

        require(channel.family == socket.AF_UNIX and hasattr(socket, "SO_PEERCRED"), "ROOT_CHANNEL")
        _, uid, _ = struct.unpack(
            "3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        )
        require(uid == 0, "ROOT_CHANNEL_PEER")
        self.channel = channel

    def call(self, method, scope):
        import struct

        require(method in ("run", "terminate", "receipt"), "ROOT_METHOD")
        raw = canonical(dict(method=method, body=dict(scope=scope.model_dump())))
        self.channel.settimeout(2)
        deadline = time.monotonic_ns() + 2_000_000_000
        self.channel.sendall(struct.pack("!I", len(raw)) + raw)

        def read_exact(n):
            result = bytearray()
            while len(result) < n:
                remaining = (deadline - time.monotonic_ns()) / 1e9
                require(remaining > 0, "ROOT_ACK_UNKNOWN")
                self.channel.settimeout(remaining)
                chunk = self.channel.recv(n - len(result))
                require(chunk, "ROOT_ACK_UNKNOWN")
                result.extend(chunk)
            return bytes(result)

        size = struct.unpack("!I", read_exact(4))[0]
        require(0 < size <= 65536, "ROOT_ACK_UNKNOWN")
        result = decode(read_exact(size))
        require(result.get("scope_sha256") == scope_hash(scope), "ROOT_RECEIPT_BINDING")
        return result


class DelegatedExecution:
    """D never setuids a child itself: root-manager RPC owns creation and reaping."""

    def __init__(self, client, scope):
        self.client, self.scope = client, scope
        self.scope_sha256, self.epoch = scope_hash(scope), scope.epoch

    def launch(self, cgroup, credential_source):
        require(cgroup is self, "ROOT_SCOPE_BINDING")
        result = self.client.call("run", self.scope)
        require(result["status"] == "RUNNING", "ROOT_LAUNCH_UNKNOWN")
        return result

    def terminate(self, child):
        result = self.client.call("terminate", self.scope)
        require(
            result.get("manager_uid") == 0
            and result.get("execution_scope_terminated") is True
            and result.get("scope_sha256") == self.scope_sha256
            and result.get("epoch") == self.epoch,
            "ROOT_TERMINATION_UNPROVEN",
        )
        return result


def serve_root_channel(manager, channel):
    """Installed manager's per-request receiver; caller must externally supervise it."""
    import socket
    import struct

    require(os.getuid() == 0 and hasattr(socket, "SO_PEERCRED"), "ROOT_MANAGER_REQUIRED")
    _, uid, _ = struct.unpack("3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    channel.settimeout(1)
    deadline = time.monotonic_ns() + 1_000_000_000

    def read_exact(n):
        result = bytearray()
        while len(result) < n:
            remaining = (deadline - time.monotonic_ns()) / 1e9
            require(remaining > 0, "ROOT_REQUEST_DEADLINE")
            channel.settimeout(remaining)
            chunk = channel.recv(n - len(result))
            require(chunk, "ROOT_REQUEST_INCOMPLETE")
            result.extend(chunk)
        return bytes(result)

    size = struct.unpack("!I", read_exact(4))[0]
    require(0 < size <= 65536, "ROOT_REQUEST_SCHEMA")
    request = decode(read_exact(size))
    require(type(request) is dict and set(request) == {"method", "body"}, "ROOT_REQUEST_SCHEMA")
    result = canonical(manager.dispatch(uid, request["method"], request["body"]))
    channel.sendall(struct.pack("!I", len(result)) + result)
