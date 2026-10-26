"""Root-FD installed single-domain host; no CLI/env/token execution switch."""

import os
import stat
import time
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field

from scripts.a4235_calibration_adapter_contract import Hash, Strict
from scripts.a4236_g1_harness_contract import UUID
from scripts.a42361_contract import canonical, checked, decode
from scripts.a42362_contract import Fault, close_receipt, file_identity, require

Domain = Literal[
    "registry", "approval", "consumer", "pg_owner", "controller", "absence_auditor", "supervisor"
]


class ServicePolicy(Strict):
    schema_version: Literal["a42362.installation.v1"]
    domain: Domain
    uid: Annotated[int, Field(strict=True, gt=0)]
    operator_uid: Annotated[int, Field(strict=True, gt=0)]
    controller_uid: Annotated[int, Field(strict=True, gt=0)]
    read_uids: tuple[Annotated[int, Field(strict=True, gt=0)], ...]
    collector_sha256: Hash
    attestation_public_key_hex: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None
    openssl_path: str
    openssl_sha256: Hash
    openssl_version: str
    expires_at: Annotated[int, Field(strict=True, gt=0)]
    namespace_sha256: Hash | None = None
    scope_epoch: UUID | None = None
    # Missing trust remains blocked; schema cannot accept execution_enabled/g1_approved.
    platform: Literal["PLATFORM_NOT_VERIFIED"] = "PLATFORM_NOT_VERIFIED"


_INSTALLED = object()


@dataclass(frozen=True)
class InstalledPolicy:
    value: ServicePolicy
    deployment: object
    _seal: object


def installation(value):
    require(
        type(value) is InstalledPolicy and value._seal is _INSTALLED,
        "A42362_ADMINISTRATOR_FDS_REQUIRED",
    )
    require(value.value.expires_at > int(time.time()), "A42362_INSTALLATION_EXPIRED")
    return value.value


def from_administrator_fds(deployment, policy_fd, expected_digest):
    from scripts.a42361_contract import sha
    from scripts.a42361_deployment import installed

    c = installed(deployment)
    import fcntl

    before = os.fstat(policy_fd)
    require(
        stat.S_ISREG(before.st_mode)
        and before.st_uid == 0
        and before.st_mode & 0o277 == 0
        and before.st_nlink == 1
        and 0 < before.st_size <= 65536
        and fcntl.fcntl(policy_fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY,
        "A42362_INSTALLATION_FD_UNTRUSTED",
    )
    raw = os.pread(policy_fd, 65537, 0)
    require(
        sha(raw) == expected_digest and file_identity(os.fstat(policy_fd)) == file_identity(before),
        "A42362_INSTALLATION_CHANGED",
    )
    p = checked(ServicePolicy, decode(raw))
    endpoint = getattr(c, p.domain)
    readers = {
        "registry": ("consumer", "supervisor", "controller"),
        "approval": ("consumer", "supervisor", "controller"),
        "consumer": ("supervisor", "controller", "pg_owner", "absence_auditor"),
        "pg_owner": ("consumer", "controller", "supervisor"),
        "controller": ("supervisor",),
        "absence_auditor": ("consumer", "controller", "supervisor"),
        "supervisor": ("supervisor",),
    }
    require(
        set(p.read_uids) <= {getattr(c, name).peer_uid for name in readers[p.domain]},
        "A42362_INSTALLATION_ACL_MISMATCH",
    )
    if p.attestation_public_key_hex is not None:
        require(
            sha(bytes.fromhex(p.attestation_public_key_hex)) not in c.test_key_sha256,
            "A42362_TEST_ROOT_KEY_REJECTED",
        )
    require(
        p.uid == endpoint.peer_uid
        and p.uid == os.getuid()
        and p.controller_uid == c.controller_uid
        and p.operator_uid
        not in {
            getattr(c, name).peer_uid
            for name in (
                "registry",
                "approval",
                "consumer",
                "pg_owner",
                "controller",
                "absence_auditor",
                "supervisor",
            )
        }
        and p.openssl_path == c.openssl_path
        and p.openssl_sha256 == c.openssl_sha256
        and p.openssl_version == c.openssl_version,
        "A42362_INSTALLATION_DOMAIN_MISMATCH",
    )
    return InstalledPolicy(p, deployment, _INSTALLED)


class ControlRepository:
    """Concrete psycopg adapter, fixed Unix target/role and identity on every connection."""

    def __init__(self, policy=None):
        self.policy = policy

    @property
    def instance_sha256(self):
        installation(self.policy)
        from scripts.a42361_deployment import installed

        return installed(self.policy.deployment).control_instance_sha256

    def connect(self, role):
        p = installation(self.policy)
        from scripts.a42361_deployment import installed

        c = installed(self.policy.deployment)
        roles = {
            "consumer": {"consumer", "receipt_reader"},
            "approval": {"approval_writer", "receipt_reader"},
            "registry": {"approval_writer", "receipt_reader"},
            "absence_auditor": {"auditor", "receipt_reader"},
        }
        require(
            role in roles.get(p.domain, set())
            and os.getuid() == p.uid
            and c.control_database.startswith("a42361_control_")
            and not any(
                k.startswith("PG") or k in ("DATABASE_URL", "TEST_DATABASE_URL") for k in os.environ
            ),
            "A42362_CONTROL_CONNECTION_REJECTED",
        )
        try:
            import psycopg

            return psycopg.connect(
                host=c.root_directory + "/" + c.control_socket_name,
                dbname=c.control_database,
                user="g1_" + role,
                port=5432,
                password="",
                passfile="",
                connect_timeout=1,
                sslmode="disable",
                application_name="a42362-" + p.domain,
                options="-c statement_timeout=200 -c lock_timeout=100 "
                "-c search_path=pg_catalog,g1_control",
                autocommit=False,
            )
        except Exception:
            raise Fault("A42362_CONTROL_STORE_UNAVAILABLE") from None

    def verify(self, connection, role):
        installation(self.policy)
        from scripts.a42361_deployment import installed

        c = installed(self.policy.deployment)
        row = connection.execute(
            "SELECT current_database(),current_user,current_setting('server_version_num')::int,"
            "instance_sha256,purpose FROM g1_control.instance_identity WHERE singleton"
        ).fetchone()
        require(
            row is not None
            and len(row) == 5
            and type(row[2]) is int
            and 170000 <= row[2] < 180000
            and tuple(row)
            == (
                c.control_database,
                "g1_" + role,
                row[2],
                c.control_instance_sha256,
                "G1_CONTROL_PLANE_ONLY",
            ),
            "A42362_CONTROL_INSTANCE_MISMATCH",
        )

    def read(self, query, parameters):
        c = self.connect("receipt_reader")
        try:
            self.verify(c, "receipt_reader")
            return c.execute(query, parameters).fetchone()
        except Fault:
            raise
        except Exception:
            raise Fault("A42362_FRESH_RECEIPT_UNAVAILABLE") from None
        finally:
            close_receipt(c)

    def verify_scope(self, scope):
        from scripts.a42361_contract import GrantPayload, sha

        p = installation(self.policy)
        require(
            scope.controller_uid == p.controller_uid
            and scope.namespace_sha256 == p.namespace_sha256
            and scope.epoch == p.scope_epoch,
            "A42362_DEPLOYMENT_SCOPE_MISMATCH",
        )
        row = self.read(
            "SELECT payload,payload_sha256 FROM g1_control.consumed_payloads "
            "WHERE token_id=%s::uuid",
            (scope.token_id,),
        )
        require(row is not None, "A42362_CONSUMED_PAYLOAD_MISSING")
        grant = checked(GrantPayload, row[0])
        require(
            grant.token_id == scope.token_id
            and grant.binding == scope.binding
            and grant.limits == scope.limits
            and grant.image_digest == scope.image_digest
            and row[1] == scope.payload_sha256 == sha(canonical(grant.model_dump())),
            "A42362_CONSUMED_PAYLOAD_MISMATCH",
        )

    def write_import(self, kind, record, digest):
        c, sent = self.connect("approval_writer"), False
        try:
            self.verify(c, "approval_writer")
            c.execute(
                "SELECT g1_control.import_external_record(%s,%s::jsonb,%s)",
                (kind, canonical(record).decode(), digest),
            )
            sent = True
            c.commit()
        except BaseException:
            try:
                c.rollback()
            finally:
                raise Fault(
                    "A42362_IMPORT_COMMIT_UNKNOWN_NO_RETRY" if sent else "A42362_IMPORT_REJECTED"
                ) from None
        finally:
            close_receipt(c)


def service(policy=None):
    p = installation(policy)  # No imports with Linux/DB side effects until root-FD seal exists.
    from scripts.a42361_deployment import LocalReceiver

    class Receiver(LocalReceiver):
        domain = p.domain

        def allowed_uids(self, config):
            return {*p.read_uids, p.operator_uid}

        def dispatch(self, peer_uid, method, body):
            if method == "health":
                require(peer_uid in self.allowed_uids(None) and body == {}, "A42362_PEER_REJECTED")
                return dict(service_ready=True, g1_authorized=False, status="SOURCE_ONLY")
            if p.domain in ("registry", "approval"):
                from scripts.a42362_approval_registry_service import ApprovalRegistryService

                return ApprovalRegistryService(policy, ControlRepository(policy)).dispatch(
                    peer_uid, method, body
                )
            if p.domain == "consumer":
                from scripts.a42361_one_shot_store import ConsumerService

                return ConsumerService(policy.deployment, policy).dispatch(peer_uid, method, body)
            if p.domain == "pg_owner":
                from scripts.a42362_pg_owner_service import PgOwnerService

                return PgOwnerService(policy).dispatch(peer_uid, method, body)
            # These cannot be wired to fake runtime adapters by repository flags.
            raise Fault("A42362_TRUSTED_RUNTIME_BACKEND_NOT_CONFIGURED")

    return Receiver(policy.deployment)


def service_main(policy=None, listening_fd=None):
    """Manager-only FD API; bounded per-request subprocess prevents a stuck handler loop."""
    installation(policy)
    require(type(listening_fd) is int and listening_fd >= 0, "A42362_LISTENER_FD_REQUIRED")
    receiver = service(policy)
    pid = os.fork()
    if pid == 0:
        try:
            os.setsid()
            receiver.serve_once(listening_fd, timeout_ms=1000)
            os._exit(0)
        except BaseException:
            os._exit(1)
    deadline = time.monotonic_ns() + 2_000_000_000
    while time.monotonic_ns() < deadline:
        observed, status = os.waitpid(pid, os.WNOHANG)
        if observed:
            require(status == 0, "A42362_HANDLER_INCOMPLETE")
            return dict(handler_reaped=True, g1_authorized=False)
        time.sleep(0.005)
    # The unreaped direct child PID cannot be reused. Never signal external/reaped PIDs.
    import signal

    os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)
    raise Fault("A42362_HANDLER_DEADLINE")


def main(argv=None):
    # No bind/listen/install, no environment flags, no public live --execute path.
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
