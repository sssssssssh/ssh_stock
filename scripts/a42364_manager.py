"""Trusted package/worker entrypoints; no environment or CLI execution authorization."""

import array
import os
import socket
import stat
import struct
import time

from scripts.a42361_contract import canonical, checked, decode, sha
from scripts.a42362_contract import Scope, file_identity
from scripts.a42363_contract import require, scope_hash
from scripts.a42364_installation_verify import installed_package


def sealed_capsule(raw):
    import fcntl

    require(os.getuid() == 0 and type(raw) is bytes and len(raw) <= 65536, "ROOT_CAPSULE_REQUIRED")
    fd = os.memfd_create("space-g1-worker", os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC)
    try:
        require(os.write(fd, raw) == len(raw), "CAPSULE_SHORT_WRITE")
        os.fchmod(fd, 0o400)
        seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_worker_capsule(fd):
    import fcntl

    m = os.fstat(fd)
    require(
        stat.S_ISREG(m.st_mode)
        and m.st_uid == 0
        and stat.S_IMODE(m.st_mode) == 0o400
        and 0 < m.st_size <= 65536,
        "WORKER_CAPSULE_FD",
    )
    seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
    require(fcntl.fcntl(fd, fcntl.F_GET_SEALS) & seals == seals, "WORKER_CAPSULE_NOT_SEALED")
    raw = os.pread(fd, 65537, 0)
    require(
        len(raw) == m.st_size and file_identity(os.fstat(fd)) == file_identity(m),
        "WORKER_CAPSULE_CHANGED",
    )
    body = decode(raw)
    require(
        type(body) is dict
        and set(body)
        == {
            "version",
            "scope",
            "fixture_identity",
            "worker_pid",
            "worker_uid",
            "owner_uid",
            "owner_socket",
            "lease_not_after",
            "run_not_after",
            "decision_digests",
            "source_archive_sha256",
            "credentials",
        }
        and body["version"] == "a42364.worker-capsule.v3",
        "WORKER_CAPSULE_SCHEMA",
    )
    require(
        body["worker_pid"] == os.getpid()
        and body["worker_uid"] == os.getuid()
        and int(time.time()) < body["lease_not_after"] <= int(time.time()) + 1,
        "WORKER_CAPSULE_LEASE",
    )
    require(
        set(body["decision_digests"])
        == {
            "BOOTSTRAP_AND_BUDGET",
            "SAFE_VOLUME_DISPOSAL",
            "TARGET_SESSION_GUC",
            "G1_L2_EXECUTION",
        },
        "WORKER_CAPSULE_DECISIONS",
    )
    scope = checked(Scope, body["scope"])
    require(
        body["owner_socket"] == "/run/space-g1/" + scope.binding.fixture_uuid + "/owner.sock",
        "WORKER_OWNER_SOCKET",
    )
    return body


class SealedWorkerAuthority:
    def __init__(self, fd, body):
        self.fd, self.body = fd, body

    def require(self, kind):
        require(
            kind in self.body["decision_digests"] and int(time.time()) < self.body["run_not_after"],
            "WORKER_RUN_AUTHORIZATION",
        )
        import fcntl

        require(
            os.fstat(self.fd).st_uid == 0
            and fcntl.fcntl(self.fd, fcntl.F_GET_SEALS) & fcntl.F_SEAL_WRITE,
            "WORKER_CAPSULE_CHANGED",
        )


def peer_uid(channel):
    require(
        channel.family == socket.AF_UNIX and hasattr(socket, "SO_PEERCRED"), "PRIVATE_UNIX_CHANNEL"
    )
    return struct.unpack("3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]


def read_frame(channel, deadline):
    def exact(n):
        result = bytearray()
        while len(result) < n:
            remaining = (deadline - time.monotonic_ns()) / 1e9
            require(remaining > 0, "MANAGER_RPC_DEADLINE")
            channel.settimeout(remaining)
            chunk = channel.recv(n - len(result))
            require(chunk, "MANAGER_RPC_ACK_UNKNOWN")
            result.extend(chunk)
        return bytes(result)

    size = struct.unpack("!I", exact(4))[0]
    require(0 < size <= 65536, "MANAGER_RPC_SIZE")
    return decode(exact(size))


def send_frame(channel, record):
    raw = canonical(record)
    require(len(raw) <= 65536, "MANAGER_RPC_SIZE")
    channel.sendall(struct.pack("!I", len(raw)) + raw)


class OwnerSessionClient:
    def __init__(self, scope, path, uid):
        self.scope, self.path, self.uid = scope, path, uid

    def observe(self, pid):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.settimeout(0.1)
            channel.connect(self.path)
            require(peer_uid(channel) == self.uid, "OWNER_SESSION_PEER")
            send_frame(
                channel,
                dict(method="candidate-session-v3", scope=self.scope.model_dump(), backend_pid=pid),
            )
            raw = read_frame(channel, time.monotonic_ns() + 100_000_000)
            require(
                raw.get("scope_sha256") == scope_hash(self.scope)
                and raw.get("backend_pid") == pid
                and raw.get("namespace_sha256") == self.scope.namespace_sha256,
                "OWNER_SESSION_BINDING",
            )
            return raw


def serve_owner_session(channel, package, session_source):
    p = installed_package(package)
    require(
        os.getuid() == p.document.principals["pg_owner"]
        and peer_uid(channel) == p.document.principals["worker"],
        "OWNER_SESSION_PEER",
    )
    request = read_frame(channel, time.monotonic_ns() + 100_000_000)
    require(
        set(request) == {"method", "scope", "backend_pid"}
        and request["method"] == "candidate-session-v3"
        and checked(Scope, request["scope"]) == p.document.scope,
        "OWNER_SESSION_REQUEST",
    )
    send_frame(channel, session_source.observe(request["backend_pid"]))


def run_worker_capsule(fd=3):
    body = read_worker_capsule(fd)
    from scripts.a42363_identity import FixtureIdentity
    from scripts.a42364_session import CandidateSessionExecutor

    identity = checked(FixtureIdentity, body["fixture_identity"])
    scope = checked(Scope, body["scope"])
    identity.verify(scope).verify_credentials(body["credentials"])
    authority = SealedWorkerAuthority(fd, body)
    authority.require("TARGET_SESSION_GUC")
    require(
        not any(
            k.startswith("PG") or k in ("DATABASE_URL", "TEST_DATABASE_URL") for k in os.environ
        ),
        "WORKER_AMBIENT_CONNECTION",
    )
    import psycopg

    secret = body["credentials"]
    c = psycopg.connect(
        host=secret["host"],
        dbname=secret["database"],
        user=secret["user"],
        password=secret["password"],
        port=5432,
        sslmode="disable",
        passfile="",
        connect_timeout=1,
        autocommit=True,
        prepare_threshold=5,
        options="-c statement_timeout=100 "
        "-c default_transaction_read_only=on -c search_path=pg_catalog",
    )
    try:
        source = OwnerSessionClient(scope, body["owner_socket"], body["owner_uid"])
        return CandidateSessionExecutor(identity, authority, source).execute(c)
    finally:
        c.close()


class CandidateRootManager:
    """Single scope; own journal, cgroup, Guardian, pinned worker and separate live grant."""

    def __init__(
        self, package, authority, cgroup, launcher, credential_source, journal, store_capability
    ):
        self.package = installed_package(package)
        require(os.getuid() == 0, "ROOT_MANAGER_REQUIRED")
        from scripts.a42363_supervisor import CgroupScope, InstalledWorkerLauncher

        require(
            type(cgroup) is CgroupScope and type(launcher) is InstalledWorkerLauncher,
            "INSTALLED_KERNEL_LAUNCHER_REQUIRED",
        )
        self.scope = self.package.document.scope
        require(
            cgroup.scope_sha256 == scope_hash(self.scope) and cgroup.epoch == self.scope.epoch,
            "ROOT_SCOPE_BINDING",
        )
        self.authority, self.cgroup, self.launcher = authority, cgroup, launcher
        self.credential_source, self.journal, self.store_capability = (
            credential_source,
            journal,
            store_capability,
        )
        self.child, self.guardian = None, None

    def dispatch(self, uid, method, body):
        self.package.revalidate()
        require(
            uid == self.package.document.principals["supervisor"]
            and type(body) is dict
            and set(body) == {"scope"}
            and checked(Scope, body["scope"]) == self.scope,
            "ROOT_MANAGER_PEER_OR_SCOPE",
        )
        require(method in ("run", "terminate", "receipt"), "ROOT_MANAGER_METHOD")
        if method == "receipt":
            return self.journal.read(self.scope, "ROOT_V3_TERMINATED").model_dump()
        if method == "run":
            require(self.authority is not None, "SEPARATE_LIVE_AUTHORIZATION_REQUIRED")
            for kind in ("BOOTSTRAP_AND_BUDGET", "SAFE_VOLUME_DISPOSAL", "TARGET_SESSION_GUC"):
                self.authority.require(kind)
            self.store_capability.verify(self.scope)  # Global-writer gap blocks BEFORE claim/spawn.
            self.authority.claim()
            require(
                self.journal.maybe_read(self.scope, "ROOT_V3_ATTEMPTED") is None, "NO_SECOND_WORKER"
            )
            self.journal.append(self.scope, "ROOT_V3_ATTEMPTED", dict(qualifies=False))
            from scripts.a42363_supervisor import FDDeadlineGuardian

            try:
                self.guardian = FDDeadlineGuardian(
                    self.cgroup.kill_fd, 3000
                )  # ARMED before child release.
                self.child = self.launcher.launch(self.cgroup, self.credential_source)
            except BaseException as first:
                if self.guardian is not None:
                    try:
                        self.guardian.abandon()
                    except BaseException:
                        first.cleanup_codes = ["A42363_GUARDIAN_REAP_NOT_PROVEN"]
                raise
            return dict(status="RUNNING", qualifies=False, scope_sha256=scope_hash(self.scope))
        require(self.child is not None, "NO_OWNED_EXECUTION_SCOPE")
        result = self.cgroup.terminate(self.child)
        self.guardian.finish()
        return self.journal.append(
            self.scope, "ROOT_V3_TERMINATED", dict(result, qualifies=False)
        ).model_dump()


def receive_fds(channel, count):
    """Fixed-size SCM_RIGHTS installation handoff, never caller descriptor numbers."""
    require(type(count) is int and 0 < count <= 16, "FD_TRANSFER_COUNT")
    raw, ancillary, flags, _ = channel.recvmsg(
        1, socket.CMSG_SPACE(count * array.array("i").itemsize)
    )
    fds = array.array("i")
    try:
        valid = True
        for level, kind, data in ancillary:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                fds.frombytes(data)
            else:
                valid = False
        require(valid, "FD_TRANSFER_KIND")
        require(raw == b"F" and flags == 0 and len(fds) == count, "FD_TRANSFER_INCOMPLETE")
        for fd in fds:
            os.set_inheritable(fd, False)
        return tuple(fds)
    except BaseException:
        for fd in fds:
            os.close(fd)
        raise


class InstalledServiceHost:
    """Kernel peer checked before decoding; no factory/class/argv/path accepted in RPC.

    The root provisioner can supply a fully constructed backend, never an RPC client.
    Without its kernel capabilities the installed service offers only status, not a
    fictitious ready backend. Units alone cannot manufacture those capabilities.
    """

    def __init__(self, package, backend=None):
        self.package, self.backend = installed_package(package), backend

    def serve_once(self, listener_fd):
        p = self.package.revalidate()
        root = p.document.service_domain == "root_manager"
        require(
            os.getuid() == (0 if root else p.document.principals["absence_auditor"]),
            "INSTALLED_SERVICE_PRINCIPAL",
        )
        with socket.fromfd(listener_fd, socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            require(
                listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1,
                "INSTALLED_LISTENER_REQUIRED",
            )
            listener.settimeout(1)
            channel, _ = listener.accept()
        with channel:
            uid = peer_uid(channel)
            allowed = {p.document.principals["supervisor"]}
            if not root:
                allowed.add(p.document.principals["controller"])
            require(uid in allowed, "INSTALLED_SERVICE_PEER")
            request = read_frame(channel, time.monotonic_ns() + 1_000_000_000)
            require(
                type(request) is dict
                and set(request) == {"method", "body"}
                and request["body"] == dict(scope=p.document.scope.model_dump()),
                "INSTALLED_SERVICE_REQUEST",
            )
            method = request["method"]
            if method == "installation-status":
                result = (
                    self.backend.status()
                    if self.backend is not None and hasattr(self.backend, "status")
                    else dict(
                        source="INSTALLED_FD_BOUND_HOST",
                        active_live_gate="DENY",
                        runtime_backend="PRESENT"
                        if self.backend is not None
                        else "ENGINEERING_BLOCKED",
                        qualifies=False,
                    )
                )
            else:
                require(self.backend is not None, "INSTALLED_RUNTIME_CAPABILITIES_REQUIRED")
                require(
                    method in (("run", "terminate", "receipt") if root else ("absent", "receipt")),
                    "INSTALLED_SERVICE_METHOD",
                )
                result = (
                    self.backend.dispatch(uid, method, request["body"])
                    if root
                    else self.backend.dispatch(method, request["body"])
                )
            send_frame(channel, result)


def serve_installed(document_fd=3, listener_fd=5):
    from scripts.a42364_installation_verify import InstalledPackage

    raw = os.pread(document_fd, 65537, 0)
    package = InstalledPackage.read(document_fd, sha(raw))
    if package.document.version == "a42366.installation.v5":
        from scripts.a42366_installation import serve_installed_domain

        return serve_installed_domain(package, listener_fd)
    from scripts.a42365_runtime_factory import build_installed_runtime

    backend = build_installed_runtime(package)
    InstalledServiceHost(package, backend).serve_once(listener_fd)
