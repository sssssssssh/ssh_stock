"""Installed FD capabilities and external deadlines. No public launch switches."""

import ctypes
import os
import select
import selectors
import signal
import stat
import subprocess
import time

from scripts.a42361_contract import canonical, sha
from scripts.a42362_contract import file_identity
from scripts.a42363_contract import Fault, lookup, require, session_method


def run_installed_command(executable, arguments, pass_fds=()):
    child = subprocess.Popen(
        (executable, *arguments),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={},
        close_fds=True,
        pass_fds=pass_fds,
        start_new_session=True,
    )
    deadline, result = time.monotonic_ns() + 1_000_000_000, bytearray()
    try:
        os.set_blocking(child.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = (deadline - time.monotonic_ns()) / 1e9
                require(remaining > 0, "COMMAND_DEADLINE")
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fd, 4096)
                    result.extend(chunk)
                    require(len(result) <= 65536, "COMMAND_OUTPUT_LIMIT")
                    if not chunk:
                        selector.unregister(key.fd)
        remaining = (deadline - time.monotonic_ns()) / 1e9
        require(remaining > 0, "COMMAND_DEADLINE")
        child.wait(timeout=remaining)
        return child.returncode, bytes(result)
    finally:
        # Only our unreaped direct child can be signalled. No PGID success claim.
        if child.poll() is None:
            child.kill()
            child.wait(timeout=1)
        child.stdout.close()


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
    try:
        ready, _, _ = select.select([rfd], [], [], max(0, (deadline - time.monotonic_ns()) / 1e9))
        if not ready:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            raise Fault("A42363_OUTER_DEADLINE")
        raw = os.read(rfd, 3)
        _, status = os.waitpid(pid, 0)
        require(raw == b"OK" and status == 0, "CHILD_INCOMPLETE")
    finally:
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

    def reap(self, timeout_ms):
        deadline = time.monotonic_ns() + timeout_ms * 1_000_000
        while self.poll() is None and time.monotonic_ns() < deadline:
            time.sleep(0.005)
        require(self.status is not None, "WORKER_NOT_REAPED")
        os.close(self.pidfd)


class InstalledWorkerLauncher:
    """Root-manager-only constructor; worker source and credentials arrive as trusted FDs."""

    def __init__(self, python_fd, worker_fd, worker_sha256, worker_uid, worker_gid, supervisor_uid):
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
        self.python_fd, self.worker_fd = python_fd, worker_fd
        self.uid, self.gid = worker_uid, worker_gid

    def launch(self, cgroup, credential_fd):
        # This method is an internal manager capability, never an RPC argument surface.
        require(type(cgroup) is CgroupScope and type(credential_fd) is int, "INSTALLED_LAUNCHER")
        gate_r, gate_w = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                os.close(gate_w)
                require(os.read(gate_r, 1) == b"G", "LAUNCH_GATE")
                os.close(gate_r)
                os.setgroups([])
                os.setgid(self.gid)
                os.setuid(self.uid)
                require(ctypes.CDLL(None).prctl(38, 1, 0, 0, 0) == 0, "NO_NEW_PRIVILEGES")
                for fd in (self.python_fd, self.worker_fd, credential_fd):
                    os.set_inheritable(fd, True)
                os.execve(
                    self.python_fd, ["python", "-I", "/proc/self/fd/" + str(self.worker_fd)], {}
                )
            except BaseException:
                os._exit(1)
        os.close(gate_r)
        child = OwnedChild(pid)
        try:
            cgroup.attach(pid)  # Child is blocked until moved to nondelegated scope.
            os.write(gate_w, b"G")
        except BaseException:
            signal.pidfd_send_signal(child.pidfd, signal.SIGKILL)
            child.reap(2000)
            raise
        finally:
            os.close(gate_w)
        return child


class ArtifactPublisher:
    def __init__(self, directory_fd):
        self.fd = directory_fd

    def publish(self, record):
        meta = os.fstat(self.fd)
        require(
            stat.S_ISDIR(meta.st_mode)
            and meta.st_uid == os.getuid()
            and stat.S_IMODE(meta.st_mode) == 0o700,
            "ARTIFACT_OWNER",
        )
        raw = canonical(record)
        # Marker exists before launching a child that could block in fsync.
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

        bounded_child(write)
        # Only a second supervised operation removes the marker, after durable manifest.
        # If it stalls/fails, parent restores marker; success never inferred from JSON alone.
        try:
            bounded_child(lambda: (os.unlink(".incomplete", dir_fd=self.fd), os.fsync(self.fd)))
        except BaseException:
            fd = os.open(
                ".incomplete", os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=self.fd
            )
            os.close(fd)
            raise
        return dict(qualifies=False, artifact_sha256=sha(raw))


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
        require(method == "terminate" and self.child is not None, "NO_OWNED_EXECUTION_SCOPE")
        result = self.cgroup.terminate(self.child)
        # D's L1 receipt never upgrades to physical G1 even if kernel proof is configured.
        result.update(qualifies=False, physical_proven=False)
        committed = self.store.append(scope, "TERMINATED", result)
        self.publisher.publish(committed.model_dump())
        return committed.model_dump()
