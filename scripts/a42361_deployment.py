"""Independent administrator FD bootstrap and authenticated, bounded local service RPC.

No loader runs on import. No env/path CLI is a source of trust. This module installs nothing.
"""

import fcntl
import os
import socket
import stat
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from scripts.a4235_calibration_adapter_contract import Hash, Strict
from scripts.a42361_contract import (
    Fault,
    Name,
    Positive,
    canonical,
    checked,
    decode,
    require,
    sha,
)


class Endpoint(Strict):
    socket_name: Name
    peer_uid: Positive


class Key(Strict):
    issuer: Name
    kid: Name
    public_key_hex: str
    usage: Literal["PRODUCTION_G1", "TEST_ONLY"]
    valid_from: Positive
    valid_until: Positive
    revoked: bool
    custody_review_sha256: Hash


class Deployment(Strict):
    schema_version: Literal["a42361.deployment.v1"] = "a42361.deployment.v1"
    root_directory: str
    control_database: Name
    control_role: Name
    control_socket_name: Name
    control_instance_sha256: Hash
    openssl_path: str
    openssl_sha256: Hash
    openssl_version: str
    podman_path: str
    podman_sha256: Hash
    python_path: str
    python_sha256: Hash
    image: str
    worker_uid: Positive
    controller_uid: Positive
    socket_gid: Positive
    registry: Endpoint
    approval: Endpoint
    consumer: Endpoint
    pg_owner: Endpoint
    controller: Endpoint
    absence_auditor: Endpoint
    supervisor: Endpoint
    keys: tuple[Key, ...]
    test_key_sha256: tuple[Hash, ...]
    deployment_review_sha256: Hash
    expires_at: Positive
    network: Literal["none"] = "none"
    public_ports: Literal[False] = False
    host_pid: Literal[False] = False
    host_proc: Literal[False] = False
    sensitive_mounts: Literal[False] = False
    privileged: Literal[False] = False
    fixture_count: Literal[1] = 1


_SEAL = object()


@dataclass(frozen=True)
class InstalledDeployment:
    value: Deployment
    digest: str
    _seal: object


def installed(value):
    require(
        type(value) is InstalledDeployment and value._seal is _SEAL,
        "A42361_DEPLOYMENT_NOT_CONFIGURED",
    )
    return value.value


def validate_deployment(value, now):
    value = checked(Deployment, value)
    root = Path(value.root_directory)
    require(
        root.is_absolute()
        and ".." not in root.parts
        and str(root).startswith("/run/a42361-")
        and len(root.parts) == 3,
        "A42361_DEPLOYMENT_PATH_INVALID",
    )
    require(
        value.control_database.startswith("a42361_control_")
        and value.control_role == "g1_consumer"
        and value.expires_at > now,
        "A42361_CONTROL_DATABASE_REJECTED",
    )
    endpoints = [
        getattr(value, k)
        for k in (
            "registry",
            "approval",
            "consumer",
            "pg_owner",
            "controller",
            "absence_auditor",
            "supervisor",
        )
    ]
    require(
        len({e.socket_name for e in endpoints}) == 7
        and len({e.peer_uid for e in endpoints}) == 7
        and value.worker_uid == value.supervisor.peer_uid
        and value.controller_uid == value.controller.peer_uid,
        "A42361_TRUST_DOMAINS_NOT_INDEPENDENT",
    )
    require(
        value.image.startswith("docker.io/library/postgres@sha256:")
        and len(value.image.rsplit(":", 1)[-1]) == 64
        and all(c in "0123456789abcdef" for c in value.image.rsplit(":", 1)[-1]),
        "A42361_IMAGE_NOT_PINNED",
    )
    require(
        bool(value.keys) and len({(k.issuer, k.kid) for k in value.keys}) == len(value.keys),
        "A42361_ISSUER_NOT_CONFIGURED",
    )
    for key in value.keys:
        require(
            key.usage == "PRODUCTION_G1"
            and len(bytes.fromhex(key.public_key_hex)) == 32
            and sha(bytes.fromhex(key.public_key_hex)) not in value.test_key_sha256,
            "A42361_TEST_KEY_FORBIDDEN",
        )
    return value


def load_from_administrator_fd(fd, expected_digest, now):
    """Called by an independently installed service manager, never from a public CLI.

    The manager supplies both the read-only root-owned FD and independently pinned digest.
    Repo JSON, env flags and callers' self-reported approved fields cannot mint this seal.
    """
    try:
        meta = os.fstat(fd)
        require(
            stat.S_ISREG(meta.st_mode)
            and fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
            and meta.st_uid == 0
            and meta.st_mode & 0o277 == 0
            and meta.st_nlink == 1
            and 0 < meta.st_size <= 65536,
            "A42361_BOOTSTRAP_NOT_TRUSTED",
        )
        raw = os.pread(fd, 65537, 0)
        require(sha(raw) == expected_digest, "A42361_BOOTSTRAP_NOT_TRUSTED")
        value = checked(Deployment, decode(raw))
        validate_deployment(value, now)
        require(os.fstat(fd) == meta, "A42361_BOOTSTRAP_CHANGED")
        return InstalledDeployment(value, sha(raw), _SEAL)
    except Fault:
        raise
    except Exception:
        raise Fault("A42361_BOOTSTRAP_NOT_TRUSTED") from None


def checked_executable(path, expected):
    try:
        path = Path(path)
        require(
            path.is_absolute() and not any(p.is_symlink() for p in (path, *path.parents)),
            "A42361_EXECUTABLE_UNTRUSTED",
        )
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            require(
                stat.S_ISREG(before.st_mode)
                and before.st_uid == 0
                and before.st_mode & 0o022 == 0
                and before.st_size <= 64_000_000,
                "A42361_EXECUTABLE_UNTRUSTED",
            )
            raw = os.read(fd, before.st_size + 1)
            require(sha(raw) == expected and os.fstat(fd) == before, "A42361_EXECUTABLE_UNTRUSTED")
        finally:
            os.close(fd)
        return str(path)
    except Fault:
        raise
    except Exception:
        raise Fault("A42361_EXECUTABLE_UNTRUSTED") from None


class LocalService:
    """Concrete framed Unix RPC client. Peer identity is obtained from the OS, not JSON."""

    def __init__(self, deployment=None, domain=None):
        self.deployment, self.domain = deployment, domain

    def call(self, method, body, timeout_ms=200):
        config = installed(self.deployment)  # No socket, DNS or env access before this gate.
        require(
            self.domain
            in (
                "registry",
                "approval",
                "consumer",
                "pg_owner",
                "controller",
                "absence_auditor",
                "supervisor",
            )
            and method
            in {
                "registry": ("key-status",),
                "approval": ("approval", "receipt"),
                "consumer": ("consume", "receipt", "journal", "resource-append", "resource-scan"),
                "pg_owner": ("create", "receipt", "run"),
                "controller": ("create", "destroy", "receipt", "reconcile"),
                "absence_auditor": ("journal", "absent", "receipt"),
                "supervisor": ("run", "terminate", "receipt"),
            }.get(self.domain, ()),
            "A42361_RPC_METHOD_REJECTED",
        )
        endpoint = getattr(config, self.domain)
        require(type(timeout_ms) is int and 0 < timeout_ms <= 2000, "A42361_RPC_BUDGET_INVALID")
        deadline = time.monotonic_ns() + timeout_ms * 1_000_000
        raw = canonical(dict(schema_version="a42361.rpc.v1", method=method, body=body))
        path = Path(config.root_directory) / (endpoint.socket_name + ".sock")
        try:
            require(hasattr(socket, "SO_PEERCRED"), "A42361_PEER_IDENTITY_UNAVAILABLE")
            require(not any(p.is_symlink() for p in (path, *path.parents)), "A42361_UNSAFE_SOCKET")
            meta = path.stat()
            require(
                stat.S_ISSOCK(meta.st_mode)
                and meta.st_uid == endpoint.peer_uid
                and meta.st_mode & 0o007 == 0,
                "A42361_UNSAFE_SOCKET",
            )
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:

                def remaining():
                    value = deadline - time.monotonic_ns()
                    require(value > 0, "A42361_RPC_TIMEOUT")
                    connection.settimeout(value / 1_000_000_000)

                remaining()
                connection.connect(str(path))
                _, uid, _ = struct.unpack(
                    "3i",
                    connection.getsockopt(
                        socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
                    ),
                )
                require(uid == endpoint.peer_uid, "A42361_PEER_IDENTITY_MISMATCH")
                remaining()
                connection.sendall(struct.pack("!I", len(raw)) + raw)

                def read_exact(n):
                    result = b""
                    while len(result) < n:
                        remaining()
                        chunk = connection.recv(n - len(result))
                        require(bool(chunk), "A42361_RPC_INCOMPLETE")
                        result += chunk
                    return result

                size = struct.unpack("!I", read_exact(4))[0]
                require(0 < size <= 65536, "A42361_RPC_TOO_LARGE")
                result = decode(read_exact(size))
                remaining()
                require(path.stat() == meta, "A42361_SOCKET_CHANGED")
                if type(result) is dict and result.get("schema_version") == "a42361.rpc-error.v1":
                    require(set(result) == {"schema_version", "code"}, "A42361_RPC_INCOMPLETE")
                    if str(result["code"]).startswith("A42362_"):
                        from scripts.a42362_contract import Fault as ServiceFault

                        raise ServiceFault(result["code"])
                    raise Fault(result["code"])
                return result
        except Fault:
            raise
        except Exception:
            raise Fault("A42361_SERVICE_UNAVAILABLE") from None


class LocalReceiver:
    """One request on an administrator-installed listening FD; never binds/listens.

    An independent service manager owns the loop, process lifetime and FD delivery.
    Network framing has one absolute deadline. It cannot interrupt a blocked handler:
    process-level supervision is still required before deployment (not proven here).
    """

    domain = None

    def __init__(self, deployment=None):
        self.deployment = deployment

    def allowed_uids(self, config):
        raise Fault("A42361_SERVICE_NOT_CONFIGURED")

    def dispatch(self, peer_uid, method, body):
        raise Fault("A42361_SERVICE_NOT_CONFIGURED")

    def serve_once(self, listening_fd, timeout_ms=1000):
        config = installed(self.deployment)  # Before FD inspection, socket I/O or dispatch.
        require(self.domain in ("registry", "approval", "consumer", "pg_owner", "controller",
                                "absence_auditor", "supervisor"), "A42361_SERVICE_NOT_CONFIGURED")
        endpoint = getattr(config, self.domain)
        require(os.getuid() == endpoint.peer_uid, "A42361_SERVICE_PRINCIPAL_MISMATCH")
        require(
            type(listening_fd) is int
            and listening_fd >= 0
            and type(timeout_ms) is int
            and 0 < timeout_ms <= 2000,
            "A42361_RPC_BUDGET_INVALID",
        )
        deadline = time.monotonic_ns() + timeout_ms * 1_000_000
        path = Path(config.root_directory) / (endpoint.socket_name + ".sock")
        try:
            require(hasattr(socket, "SO_PEERCRED"), "A42361_PEER_IDENTITY_UNAVAILABLE")
            require(not any(p.is_symlink() for p in (path, *path.parents)), "A42361_UNSAFE_SOCKET")
            meta = path.stat()
            require(
                stat.S_ISSOCK(meta.st_mode)
                and meta.st_uid == endpoint.peer_uid
                and meta.st_mode & 0o007 == 0,
                "A42361_UNSAFE_SOCKET",
            )
            with socket.fromfd(listening_fd, socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                require(
                    listener.family == socket.AF_UNIX
                    and listener.type == socket.SOCK_STREAM
                    and listener.getsockname() == str(path)
                    and listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1,
                    "A42361_LISTENER_UNTRUSTED",
                )

                def remaining(connection):
                    value = deadline - time.monotonic_ns()
                    require(value > 0, "A42361_RPC_TIMEOUT")
                    connection.settimeout(value / 1_000_000_000)

                remaining(listener)
                connection, _ = listener.accept()
                with connection:
                    _, uid, _ = struct.unpack(
                        "3i",
                        connection.getsockopt(
                            socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
                        ),
                    )
                    require(uid in self.allowed_uids(config), "A42361_PEER_IDENTITY_MISMATCH")

                    def read_exact(n):
                        result = b""
                        while len(result) < n:
                            remaining(connection)
                            chunk = connection.recv(n - len(result))
                            require(bool(chunk), "A42361_RPC_INCOMPLETE")
                            result += chunk
                        return result

                    try:
                        size = struct.unpack("!I", read_exact(4))[0]
                        require(0 < size <= 65536, "A42361_RPC_TOO_LARGE")
                        request = decode(read_exact(size))
                        require(
                            type(request) is dict
                            and set(request) == {"schema_version", "method", "body"}
                            and request["schema_version"] == "a42361.rpc.v1"
                            and type(request["method"]) is str
                            and type(request["body"]) is dict,
                            "A42361_RPC_METHOD_REJECTED",
                        )
                        require(path.stat() == meta, "A42361_SOCKET_CHANGED")
                        remaining(connection)
                        response = self.dispatch(uid, request["method"], request["body"])
                    except Exception as error:
                        response = dict(
                            schema_version="a42361.rpc-error.v1",
                            code=error.code
                            if isinstance(error, Fault)
                            else "A42361_SERVICE_UNAVAILABLE",
                        )
                    raw = canonical(response)
                    remaining(connection)
                    require(path.stat() == meta, "A42361_SOCKET_CHANGED")
                    connection.sendall(struct.pack("!I", len(raw)) + raw)
        except Fault:
            raise
        except Exception:
            raise Fault("A42361_SERVICE_UNAVAILABLE") from None
