"""Fixed four-resource commands, committed-before-create and destroy-only recovery."""

import json
import time

from scripts.a42361_contract import canonical, checked, sha
from scripts.a42362_contract import LedgerRequest, Scope, resources, validate_receipt
from scripts.a42362_reconcile import Reconciler
from scripts.a42363_contract import Fault, lookup, require, scope_hash, session_method


class ResourceDriver:
    def __init__(self, commands, socket_directory, secret_fd, independent_observer):
        self.commands, self.socket_directory = commands, socket_directory
        self.secret_fd, self.independent_observer = secret_fd, independent_observer

    def begin_cleanup(self):
        self.commands.begin_cleanup()

    @staticmethod
    def labels(scope):
        return dict(
            a42363_scope=scope_hash(scope),
            a42363_epoch=scope.epoch,
            a42363_namespace=scope.namespace_sha256,
            a42363_owner=str(scope.controller_uid),
        )

    def creation_command(self, item):
        require(item in resources(item.scope), "RESOURCE_SCOPE")
        labels = tuple(
            v for k, value in self.labels(item.scope).items() for v in ("--label", k + "=" + value)
        )
        if item.kind == "VOLUME":
            return ("volume", "create", *labels, item.name)
        if item.kind == "SECRET":
            require(type(self.secret_fd) is int and self.secret_fd >= 0, "SECRET_FD_REQUIRED")
            return ("secret", "create", *labels, item.name, "/proc/self/fd/" + str(self.secret_fd))
        require(item.kind == "CONTAINER", "RESOURCE_KIND")
        rs = resources(item.scope)
        return (
            "create",
            "--name",
            item.name,
            *labels,
            "--network=none",
            "--read-only",
            "--cap-drop=all",
            "--security-opt=no-new-privileges",
            "--user=999:999",
            "--cpus=1",
            "--memory=512m",
            "--pids-limit=32",
            "--ipc=private",
            "--pid=private",
            "--volume",
            rs[1].name + ":/var/lib/postgresql/data:Z",
            "--secret",
            rs[2].name,
            item.scope.image_digest,
        )

    def create(self, item):
        if item.kind == "SOCKET_DIR":
            return self.socket_directory.create(item)
        self.commands.run(
            self.creation_command(item), pass_fds=(self.secret_fd,) if item.kind == "SECRET" else ()
        )
        return self.inspect(item)

    def inspect(self, item):
        require(item in resources(item.scope), "RESOURCE_SCOPE")
        if item.kind == "SOCKET_DIR":
            return self.socket_directory.inspect(item)
        code, raw = self.commands.run(
            (item.kind.lower(), "inspect", "--format", "{{json .}}", item.name)
        )
        require(code == 0 and 0 < len(raw) <= 32768, "RESOURCE_INSPECT_UNKNOWN")
        try:
            result = json.loads(raw)
        except (ValueError, TypeError):
            raise Fault("A42363_RESOURCE_INSPECT_UNKNOWN") from None
        require(type(result) is dict, "RESOURCE_INSPECT_UNKNOWN")
        return result

    def verify(self, item, raw):
        if item.kind == "SOCKET_DIR":
            require(raw == self.socket_directory.inspect(item), "SOCKET_REPLACED")
            return sha(canonical(raw))
        require(type(raw) is dict, "RESOURCE_INSPECT_UNKNOWN")
        labels = (
            raw.get("Config", {}).get("Labels", {})
            if item.kind == "CONTAINER"
            else (
                raw.get("Spec", {}).get("Labels", {})
                if item.kind == "SECRET"
                else raw.get("Labels", {})
            )
        )
        require(
            all(labels.get(k) == v for k, v in self.labels(item.scope).items()),
            "OWNERSHIP_UNKNOWN_QUARANTINE",
        )
        name = raw.get("Spec", {}).get("Name") if item.kind == "SECRET" else raw.get("Name")
        require(
            name == item.name and type(raw.get("CreatedAt", raw.get("Created"))) is str,
            "RESOURCE_EPOCH_UNPROVEN",
        )
        identity = raw.get("ID", raw.get("Id", raw.get("Mountpoint")))
        require(type(identity) is str and bool(identity), "RESOURCE_ID_UNPROVEN")
        if item.kind == "CONTAINER":
            h, c = raw.get("HostConfig", {}), raw.get("Config", {})
            require(
                raw.get("ImageDigest") == item.scope.image_digest
                and c.get("User") == "999:999"
                and h.get("NetworkMode") == "none"
                and h.get("ReadonlyRootfs") is True
                and h.get("Privileged") is False
                and h.get("PidsLimit") == 32
                and h.get("Memory") == 536870912
                and h.get("NanoCpus") == 1000000000
                and h.get("CapDrop") == ["ALL"]
                and "no-new-privileges" in h.get("SecurityOpt", [])
                and h.get("PidMode") in ("", "private")
                and h.get("IpcMode") == "private",
                "CONTAINER_ISOLATION_UNPROVEN",
            )
            mounts = raw.get("Mounts", [])
            require(
                len(mounts) == 1
                and mounts[0].get("Name") == resources(item.scope)[1].name
                and mounts[0].get("Destination") == "/var/lib/postgresql/data",
                "CONTAINER_MOUNTS",
            )
        return sha(canonical(raw))

    def remove(self, item, raw):
        self.verify(item, raw)
        if item.kind == "SOCKET_DIR":
            return self.socket_directory.remove(item, raw)
        # Exact immutable ID, never a name that could now designate another object.
        identity = raw.get("ID", raw.get("Id"))
        require(type(identity) is str and bool(identity), "REMOVE_ID_REQUIRED")
        code, _ = self.commands.run((item.kind.lower(), "rm", identity))
        require(code == 0, "REMOVE_ACK_UNKNOWN")

    def absent(self, item):
        require(self.independent_observer is not None, "INDEPENDENT_E_REQUIRED")
        return self.independent_observer.observe(item)["result"] == "ABSENT"


class ControllerService:
    def __init__(self, ledger, driver, store, consumption):
        self.ledger, self.driver, self.store, self.consumption = ledger, driver, store, consumption
        self.engine = RecoveryEngine(ledger, driver)

    def dispatch(self, method, body):
        scope = lookup(body)
        self.consumption(scope)  # Independent B committed payload, including epoch/namespace.
        if method == "receipt":
            return self.store.read(scope, "RECONCILED").model_dump()
        with self.store.lock(scope):
            return self._mutate(method, scope)

    def _mutate(self, method, scope):
        if method == "create":
            session_method()  # No partial real fixture when the session proof is unapproved.
            result = self.engine.create(scope)
            return self.store.append(scope, "CREATED", result).model_dump()
        require(method in ("destroy", "reconcile"), "CONTROLLER_METHOD")
        previous = self.store.maybe_read(scope, "RECONCILED")
        if previous is not None:
            return previous.model_dump()  # Durable ACK recovery, never another remove.
        if self.store.maybe_read(scope, "DESTROY_REQUESTED") is None:
            self.store.append(scope, "DESTROY_REQUESTED", dict(resource_ids=self.identities(scope)))
        result = self.engine.recover(scope)
        result.update(
            scope_sha256=scope_hash(scope),
            destroyed_ns=time.monotonic_ns(),
            resource_ids=self.identities(scope),
        )
        return self.store.append(scope, "RECONCILED", result).model_dump()

    def identities(self, scope):
        snapshot = self.ledger.scan(dict(scope=checked(Scope, scope).model_dump()))
        require(
            sha(canonical(snapshot["events"])) == snapshot["snapshot_sha256"], "LEDGER_SNAPSHOT"
        )
        found = {}
        for raw in snapshot["events"]:
            q = checked(LedgerRequest, raw["request"])
            validate_receipt(raw, q)
            require(q.resource.scope == scope, "LEDGER_SCOPE")
            if q.event == "OBSERVED_CREATED":
                found[q.resource.kind] = q.observed_identity_sha256
        require(found, "NO_LEDGER_QUARANTINE")
        return found


class RecoveryEngine(Reconciler):
    """Retain creation identities across UNKNOWN/REMOVE_ATTEMPTED suffixes.

    Old last-event-only recovery could lose the original identity. This layer never
    replaces it with a freshly inspected object, even when labels/name still match.
    Missing identity means quarantine; negative evidence must come from independent E.
    """

    def create(self, scope):
        require(self.ledger is not None and self.driver is not None, "CONTROLLER_NOT_CONFIGURED")
        require(
            self.ledger.scan(dict(scope=scope.model_dump()))["events"] == [], "NO_SECOND_CREATE"
        )
        started = time.monotonic_ns()
        for item in resources(scope):
            self._event(item, "RESERVED")
            self._event(item, "CREATE_ATTEMPTED")
            try:
                require(time.monotonic_ns() - started < 2_000_000_000, "INITIALIZATION_TIMEOUT")
                raw = self.driver.create(item)
                self._event(item, "OBSERVED_CREATED", observed=self.driver.verify(item, raw))
            except BaseException as error:
                # Historical B schema has its own error namespace. Preserve original
                # failure separately instead of replacing it with the journal's code.
                first = getattr(error, "code", "A42363_CREATE_ACK_UNKNOWN")
                failure = Fault(first)
                failure.first_error, failure.cleanup_codes = first, []
                try:
                    self._event(item, "UNKNOWN", error="A42362_CREATE_ACK_UNKNOWN")
                except BaseException:
                    failure.cleanup_codes.append("A42363_JOURNAL_COMMIT_UNKNOWN_NO_RETRY")
                raise failure from None
        return dict(status="CREATED_PENDING_OWNER_ATTESTATION", qualifies=False)

    def recover(self, scope):
        if isinstance(self.driver, ResourceDriver):
            self.driver.begin_cleanup()
        snapshot = self.ledger.scan(dict(scope=scope.model_dump()))
        require(
            sha(canonical(snapshot["events"])) == snapshot["snapshot_sha256"], "LEDGER_SNAPSHOT"
        )
        history, sequence = {}, 0
        for raw in snapshot["events"]:
            q = checked(LedgerRequest, raw["request"])
            r = validate_receipt(raw, q)
            require(q.resource.scope == scope and r.sequence > sequence, "LEDGER_ORDER")
            sequence = r.sequence
            history.setdefault(q.resource.kind, []).append(q)
        require(history, "NO_LEDGER_QUARANTINE")
        started, errors, removed = time.monotonic_ns(), [], []
        for item in reversed(resources(scope)):
            events = history.get(item.kind, [])
            if not events or events[-1].event == "OBSERVED_ABSENT":
                continue
            try:
                require(time.monotonic_ns() - started < 2_000_000_000, "CLEANUP_TIMEOUT")
                identities = {
                    r.observed_identity_sha256 for r in events if r.event == "OBSERVED_CREATED"
                }
                require(len(identities) == 1, "OWNERSHIP_UNKNOWN_QUARANTINE")
                # A prior remove may have succeeded despite an unknown ACK. Ask E first;
                # never infer absence from C's inspect error or replay a removal blindly.
                if events[-1].event == "REMOVE_ATTEMPTED" and self.driver.absent(item):
                    self._event(item, "OBSERVED_ABSENT")
                    removed.append(item.kind)
                    continue
                raw = self.driver.inspect(item)
                require(self.driver.verify(item, raw) in identities, "RESOURCE_REPLACED_QUARANTINE")
                if events[-1].event != "REMOVE_ATTEMPTED":
                    self._event(item, "REMOVE_ATTEMPTED")
                self.driver.remove(item, raw)
                require(self.driver.absent(item), "REMOVE_ACK_UNKNOWN")
                self._event(item, "OBSERVED_ABSENT")
                removed.append(item.kind)
            except BaseException as error:
                code = getattr(error, "code", "A42363_OWNERSHIP_UNKNOWN_QUARANTINE")
                errors.append(code)
        return dict(
            status="INCOMPLETE_QUARANTINED" if errors else "DESTROYED_PENDING_INDEPENDENT_E",
            first_error=errors[0] if errors else None,
            cleanup_codes=list(dict.fromkeys(errors)),
            removed_kinds=removed,
            independent_absent=False,
            qualifies=False,
        )
