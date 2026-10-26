"""One installed host per trust domain; strict shared client/server method matrix."""

import os
import stat
import time

from scripts.a42361_contract import Approval, canonical, checked, sha
from scripts.a42361_deployment import LocalReceiver, LocalService, installed
from scripts.a42362_service_host import ControlRepository, installation
from scripts.a42363_contract import lookup, receipt, require
from scripts.a42363_supervisor import bounded_child, run_installed_command

METHODS = {
    "registry": ("key-status", "import", "receipt"),
    "approval": ("approval", "receipt", "import", "revoke"),
    "consumer": (
        "consume",
        "receipt",
        "journal",
        "resource-append",
        "resource-scan",
        "committed-receipt",
    ),
    "pg_owner": ("create", "receipt", "run"),
    "controller": ("create", "destroy", "receipt", "reconcile"),
    "absence_auditor": ("journal", "absent", "receipt"),
    "supervisor": ("run", "terminate", "receipt"),
}


class FixedCommandRunner:
    """Administrator-pinned executable and namespace; no shell or caller argv RPC."""

    def __init__(self, executable, digest, namespace_fd, command_scope=None):
        from scripts.a42361_deployment import checked_executable

        self.executable = checked_executable(executable, digest)
        self.digest, self.namespace_fd, self.count = digest, namespace_fd, 0
        self.command_scope = command_scope
        self.cleanup_count, self.read_count, self.cleaning = 0, 0, False
        self.namespace_identity = (os.fstat(namespace_fd).st_dev, os.fstat(namespace_fd).st_ino)
        self.namespace_sha256 = sha(os.readlink("/proc/self/ns/user").encode())

    def run(self, arguments, pass_fds=()):
        if self.cleaning:
            require(self.cleanup_count < 12, "CLEANUP_COMMAND_BUDGET")
            self.cleanup_count += 1
        else:
            require(self.count < 12, "INITIALIZATION_COMMAND_BUDGET")
            self.count += 1
        return self._run(arguments, pass_fds)

    def begin_cleanup(self):
        self.cleaning = True  # Monotonic phase; never reset initialization counts.

    def read(self, arguments):
        require(
            arguments == ("info", "--format", "json")
            or (
                len(arguments) == 3
                and arguments[0] in ("volume", "secret", "container")
                and arguments[1] == "exists"
            ),
            "AUDITOR_READ_ONLY",
        )
        # Count all E reads separately. They cannot spend or reset the initialization
        # budget; the receiver's external deadline bounds each fixed audit sequence.
        self.read_count += 1
        return self._run(arguments)

    def _run(self, arguments, pass_fds=()):
        from scripts.a42361_deployment import checked_executable

        require(
            type(arguments) is tuple and arguments and len(arguments) <= 64,
            "FIXED_COMMAND_REQUIRED",
        )
        require(
            arguments[0] in ("volume", "secret", "container", "create", "info"),
            "FIXED_COMMAND_REQUIRED",
        )
        require(
            checked_executable(self.executable, self.digest) == self.executable,
            "EXECUTABLE_CHANGED",
        )
        meta = os.fstat(self.namespace_fd)
        require((meta.st_dev, meta.st_ino) == self.namespace_identity, "NAMESPACE_CHANGED")
        current = os.stat("/proc/self/ns/user")
        require(
            (current.st_dev, current.st_ino) == self.namespace_identity, "WRONG_RUNTIME_NAMESPACE"
        )
        # Short commands also need descendant confinement. Never route them through
        # the legacy direct-child-only helper just because their argv is short.
        return run_installed_command(
            self.executable, arguments, pass_fds=pass_fds, command_scope=self.command_scope
        )


class ManagerFDs:
    """Validate lifetime and original listener identity; never bind/install from CLI."""

    def __init__(self, policy=None, listener_fd=None, root_fd=None):
        import socket

        p = installation(policy)
        require(type(listener_fd) is int and type(root_fd) is int, "ADMINISTRATOR_FDS_REQUIRED")
        root = os.fstat(root_fd)
        require(
            stat.S_ISDIR(root.st_mode) and root.st_uid == 0 and root.st_mode & 0o022 == 0,
            "ROOT_FD_UNTRUSTED",
        )
        with socket.fromfd(listener_fd, socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            require(
                listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1,
                "LISTENER_REQUIRED",
            )
        self.policy, self.listener_fd, self.root_fd = policy, listener_fd, root_fd
        self.root_identity, self.listener_identity = os.fstat(root_fd), os.fstat(listener_fd)
        self.expires_at = p.expires_at

    def serve(self, capabilities):
        require(int(time.time()) < self.expires_at, "MANAGER_EXPIRED")
        require(
            os.fstat(self.root_fd) == self.root_identity
            and os.fstat(self.listener_fd) == self.listener_identity,
            "MANAGER_FD_CHANGED",
        )
        compose(self.policy, capabilities).serve_supervised(self.listener_fd)


class Repository(ControlRepository):
    """Fixed role per service, admin-installed Unix target, no environment DSN."""

    def connect(self, role):
        p = installation(self.policy)
        require(
            role in {p.domain, "receipt_reader"}
            or p.domain in ("registry", "approval")
            and role == "approval_writer",
            "ROLE_ACL",
        )
        c = installed(self.policy.deployment)
        require(
            not any(
                k.startswith("PG") or k in ("DATABASE_URL", "TEST_DATABASE_URL") for k in os.environ
            ),
            "ENVIRONMENT_DATABASE_REJECTED",
        )
        require(c.schema_version == "a42363.deployment.v2", "DEPLOYMENT_V2_REQUIRED")
        import psycopg

        return psycopg.connect(
            host=c.root_directory + "/" + c.control_socket_name,
            dbname=c.control_database,
            user=self.database_role(role),
            port=5432,
            password="",
            passfile="",
            sslmode="disable",
            connect_timeout=1,
            options="-c statement_timeout=200 -c lock_timeout=100 "
            "-c search_path=pg_catalog,g1_control",
            autocommit=False,
        )

    def verify(self, connection, role):
        return super().verify(connection, self.database_role(role).removeprefix("g1_"))

    def database_role(self, role):
        p = installation(self.policy)
        if role == "receipt_reader":
            return "g1_receipt_reader"
        if role == "consumer" and p.domain == "consumer":
            return "g1_consumer"
        return "g1_" + p.domain + "_writer"


class ServiceHost(LocalReceiver):
    def __init__(self, policy=None, backends=None):
        p = installation(policy)
        c = installed(policy.deployment)
        require(c.schema_version == "a42363.deployment.v2", "DEPLOYMENT_V2_REQUIRED")
        require(backends is not None, "ADMINISTRATOR_BACKENDS_REQUIRED")
        self.policy, self.backends, self.domain = policy, backends, p.domain
        super().__init__(policy.deployment)

    def allowed_uids(self, config):
        p = installation(self.policy)
        return {*p.read_uids, p.operator_uid}

    def dispatch(self, peer_uid, method, body):
        p = installation(self.policy)
        require(
            os.getuid() == p.uid and method in METHODS[self.domain], "METHOD_OR_SERVICE_IDENTITY"
        )
        operator = method in ("import", "revoke")
        require(peer_uid == p.operator_uid if operator else peer_uid in p.read_uids, "PEER_ACL")
        require(type(body) is dict and len(canonical(body)) <= 65536, "BODY_SCHEMA")
        from scripts.a42363_rpc import request_contract

        request_contract(self.domain, method).validate(body)
        if self.domain in ("registry", "approval"):
            from scripts.a42362_approval_registry_service import ApprovalRegistryService

            if method == "revoke":
                require(body.get("kind") == "REVOCATION", "REVOCATION_ONLY")
                method = "import"
            if method == "import":
                require(
                    body.get("kind") == "KEY_STATUS"
                    if self.domain == "registry"
                    else body.get("kind") in ("APPROVAL", "REVOCATION"),
                    "IMPORT_DOMAIN",
                )
            if self.domain == "approval" and method == "receipt" and set(body) == {"scope"}:
                scope = lookup(body)
                repository = self.backends["repository"]
                repository.verify_scope(scope)
                row = repository.read(
                    "SELECT a.canonical_record,a.registry_epoch FROM g1_control.approval_records a "
                    "JOIN g1_control.g1_consumptions b ON b.approval_id=a.approval_id "
                    "WHERE b.token_id=%s::uuid AND NOT EXISTS(SELECT 1 FROM "
                    "g1_control.approval_revocations r WHERE r.approval_id=a.approval_id)",
                    (scope.token_id,),
                )
                require(row is not None, "APPROVAL_REVOKED_OR_MISSING")
                approval = checked(Approval, row[0])
                require(
                    approval.binding == scope.binding
                    and approval.payload_sha256 == scope.payload_sha256
                    and approval.status == "APPROVED"
                    and approval.expires_at > int(time.time())
                    and len(set(approval.approver_sha256)) == 2,
                    "APPROVAL_BINDING",
                )
                return receipt(
                    "approval", scope, "APPROVED", row[1], approval.model_dump()
                ).model_dump()
            return ApprovalRegistryService(self.policy, self.backends["repository"]).dispatch(
                peer_uid, method, body
            )
        if self.domain == "consumer":
            from scripts.a42361_one_shot_store import ConsumerService

            if method == "committed-receipt":
                scope = lookup(body)
                self.backends["repository"].verify_scope(scope)
                method, body = (
                    "receipt",
                    dict(token_id=scope.token_id, payload_sha256=scope.payload_sha256),
                )
                raw = ConsumerService(self.policy.deployment, self.policy).dispatch(
                    peer_uid, method, body
                )
                require(raw.get("committed") is True, "CONSUMPTION_UNPROVEN")
                return receipt("consumer", scope, "CONSUMED", 1, raw).model_dump()
            return ConsumerService(self.policy.deployment, self.policy).dispatch(
                peer_uid, method, body
            )
        if self.domain == "pg_owner":
            if method == "receipt" and set(body) == {"purpose", "instance_sha256"}:
                require(body["purpose"] == "CONTROL_PLANE_ISOLATION", "CONTROL_PURPOSE")
                raw = self.backends["owner"].runtime.inspect_control()
                require(raw["instance_sha256"] == body["instance_sha256"], "CONTROL_IDENTITY")
                return raw
            scope = lookup(body)
            backend = self.backends["owner"]
            if method == "create":
                require(peer_uid == self.policy.deployment.controller.peer_uid, "OWNER_CREATE_ACL")
                from scripts.a42363_owner import OwnerRuntime

                require(type(backend.runtime) is OwnerRuntime, "OWNER_RUNTIME_REQUIRED")
            if method == "run":
                from scripts.a42363_contract import session_method

                session_method()
            return backend.initialize(scope) if method == "create" else backend.inspect(scope)
        # C/E/D use concrete receivers, not an unconditional NOT_CONFIGURED branch.
        return self.backends[self.domain].dispatch(method, body)

    def serve_supervised(self, listening_fd):
        bounded_child(lambda: self.serve_once(listening_fd, timeout_ms=1000))


def compose(policy=None, capabilities=None):
    """Only trusted manager code supplies capabilities; no CLI/env/config activation.

    Each process receives only its domain's dependencies. Store reader and writer are
    different connections; E receives its own writer, not C's response as audit authority.
    """
    p = installation(policy)
    require(capabilities is not None, "ADMINISTRATOR_BACKENDS_REQUIRED")
    from scripts.a42363_absence import AbsenceService
    from scripts.a42363_owner import RawOwnerBackend
    from scripts.a42363_resources import ControllerService
    from scripts.a42363_stores import DomainStore
    from scripts.a42363_supervisor import DelegatedExecution, SupervisorService

    repository = Repository(policy)
    store = DomainStore(p.domain, repository)
    backend = {"repository": repository}
    from scripts.a42363_installation import CAPABILITIES

    required = CAPABILITIES[p.domain]
    require(set(capabilities) == required, "CAPABILITY_SET")
    if p.domain == "pg_owner":
        backend["owner"] = RawOwnerBackend(
            capabilities["owner_connection"], capabilities["owner_runtime"], store
        )
    elif p.domain == "controller":
        backend[p.domain] = ControllerService(
            capabilities["ledger"],
            capabilities["resource_driver"],
            store,
            capabilities["consumption"],
            capabilities["fixture"],
        )
    elif p.domain == "absence_auditor":
        backend[p.domain] = AbsenceService(
            capabilities["observer"],
            store,
            capabilities["controller_store"],
            capabilities["ledger"],
        )
    elif p.domain == "supervisor":
        delegated = DelegatedExecution(capabilities["root_manager"], capabilities["scope"])
        backend[p.domain] = SupervisorService(
            delegated,
            None,
            delegated,
            store,
            capabilities["publisher"],
        )
    return ServiceHost(policy, backend)


def compose_installed(policy, document, scope, capabilities, code_fds):
    """Manager-only FD-bound factory. Creates no sockets, processes or SQL connections."""
    from scripts.a42363_installation import InstalledFDDocument

    p = installation(policy)
    require(
        type(document) is InstalledFDDocument
        and document.domain == p.domain
        and document.uid == p.uid
        and os.getuid() == p.uid,
        "INSTALLATION_PRINCIPAL",
    )
    document.verify_scope(scope, int(time.time())).verify_code_fds(code_fds)
    require(set(capabilities) == set(code_fds), "INSTALLATION_CAPABILITIES")
    if p.domain == "controller":
        require(
            capabilities["resource_driver"].identity == capabilities["fixture"].identity,
            "FIXTURE_IDENTITY",
        )
        capabilities["fixture"].identity.verify(scope)
    elif p.domain == "pg_owner":
        capabilities["owner_runtime"].identity.verify(scope)
    elif p.domain == "supervisor":
        require(capabilities["scope"] == scope, "WORKER_SCOPE_BINDING")
    return compose(policy, capabilities)


class Orchestrator:
    def __init__(self, clients, reviewer):
        require(set(clients) == set(METHODS), "CLIENT_DOMAINS")
        self.clients, self.reviewer, self.stopped = clients, reviewer, False

    def stop(self, scope):
        self.stopped = True  # Stop new consumption/creation/run before cleanup.
        body = dict(scope=scope.model_dump())
        self.clients["controller"].call("reconcile", body)
        return self.clients["absence_auditor"].call("absent", body)

    def recover(self, scope):
        body = dict(scope=scope.model_dump())
        # Actual C receiver handles recovery. ACK uncertainty cannot trigger create again.
        return self.clients["controller"].call("reconcile", body)

    def run(self, scope):
        require(not self.stopped, "STOPPED")
        # Current method approval cannot be supplied in a request or synthetic bundle.
        from scripts.a42363_contract import session_method

        session_method()

    def execute(self, scope, consume_request, approval_id):
        require(not self.stopped, "STOPPED")
        body = dict(scope=scope.model_dump())
        from scripts.a42363_contract import session_method

        session_method()  # Before consuming, issuing credentials or creating resources.
        self.clients["approval"].call("approval", dict(approval_id=approval_id))
        self.clients["consumer"].call("consume", consume_request)
        self.clients["consumer"].call("committed-receipt", body)
        first, cleanup = None, []
        try:
            self.clients["controller"].call("create", body)
            self.clients["pg_owner"].call("create", body)
            self.clients["supervisor"].call("run", body)
        except BaseException as error:
            first = getattr(error, "code", "A42363_EXECUTION_UNKNOWN")
        finally:
            for domain, method in (
                ("supervisor", "terminate"),
                ("controller", "reconcile"),
                ("absence_auditor", "absent"),
            ):
                try:
                    self.clients[domain].call(method, body)
                except BaseException as error:
                    cleanup.append(getattr(error, "code", "A42363_CLEANUP_UNKNOWN"))
        if first or cleanup:
            return dict(
                first_error=first or cleanup[0],
                cleanup_codes=cleanup,
                qualifies=False,
                status="INCOMPLETE_QUARANTINED",
            )
        refs = {
            d: self.clients[d].call("committed-receipt" if d == "consumer" else "receipt", body)
            for d in (
                "approval",
                "consumer",
                "pg_owner",
                "controller",
                "supervisor",
                "absence_auditor",
            )
        }
        return self.reviewer.review(scope, refs)


def main(argv=None):
    return 2


__all__ = ["LocalService", "METHODS", "ServiceHost", "compose"]
