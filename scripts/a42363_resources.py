"""Fixed four-resource commands, committed-before-create and destroy-only recovery."""

import json
import os
import re
import stat
import time

from scripts.a42361_contract import canonical, checked, sha
from scripts.a42362_contract import LedgerRequest, Scope, resources, validate_receipt
from scripts.a42362_reconcile import Reconciler
from scripts.a42363_contract import Fault, lookup, require, scope_hash, session_method


class ResourceDriver:
    def __init__(self, commands, socket_directory, secret_fd, independent_observer, identity=None):
        self.commands, self.socket_directory = commands, socket_directory
        self.secret_fd, self.independent_observer = secret_fd, independent_observer
        self.identity = identity

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
        fixture_options = ()
        if self.identity is not None:
            i = self.identity.verify(item.scope)
            fixture_options = (
                "--userns=keep-id:uid=999,gid=999",
                "--mount",
                "type=bind,src=" + i.socket_host + ",dst=/run/postgresql,rw",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=16m",
                "--env",
                "PGDATA=/var/lib/postgresql/data/pgdata",
                "--entrypoint=/usr/local/libexec/space-g1-pg17-bootstrap",
                "--health-cmd=pg_isready -q -h /run/postgresql -p 5432",
            )
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
            *fixture_options,
            item.scope.image_digest,
        )

    def create(self, item):
        if self.identity is not None:
            self.identity.verify(item.scope)
            require(self.independent_observer is not None, "INDEPENDENT_E_REQUIRED")
            require(
                self.independent_observer.observe(item)["result"] == "ABSENT",
                "RESOURCE_ALREADY_PRESENT_OR_UNKNOWN",
            )
        if item.kind == "SOCKET_DIR":
            return self.socket_directory.create(item)
        code, _ = self.commands.run(
            self.creation_command(item), pass_fds=(self.secret_fd,) if item.kind == "SECRET" else ()
        )
        require(code == 0, "CREATE_ACK_UNKNOWN")
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
                len(mounts) == (2 if self.identity is not None else 1)
                and mounts[0].get("Name") == resources(item.scope)[1].name
                and mounts[0].get("Destination") == "/var/lib/postgresql/data",
                "CONTAINER_MOUNTS",
            )
            if self.identity is not None:
                self.verify_socket_mount(raw, self.identity.verify(item.scope))
        # Starting/stopping PG changes State; MountCount changes while a volume is
        # mounted. These are observations, not creation identities. Every original
        # owner/label/ID/creation/mount/config field is still bound to the ledger hash.
        stable = {k: v for k, v in raw.items() if k not in ("State", "MountCount")}
        return sha(canonical(stable))

    def verify_socket_mount(self, raw, identity):
        identity.verify(identity.scope)
        mounts = raw.get("Mounts", [])
        sockets = [m for m in mounts if m.get("Destination") == "/run/postgresql"]
        require(
            len(sockets) == 1
            and sockets[0].get("Source") == identity.socket_host
            and sockets[0].get("RW") is True
            and sockets[0].get("Type") == "bind",
            "PG_SOCKET_MOUNT_UNPROVEN",
        )
        require(
            raw.get("HostConfig", {}).get("UsernsMode") == "keep-id:uid=999,gid=999",
            "PG_UID_MAPPING_UNPROVEN",
        )

    def remove(self, item, raw):
        self.verify(item, raw)
        if item.kind == "SOCKET_DIR":
            return self.socket_directory.remove(item, raw)
        # Exact immutable ID, never a name that could now designate another object.
        identity = raw.get("ID", raw.get("Id"))
        require(type(identity) is str and bool(identity), "REMOVE_ID_REQUIRED")
        # Podman volume rm accepts names, not StorageID/immutable ID. Even an ID
        # appearing in inspect JSON cannot prove the remove API's target semantics.
        require(item.kind != "VOLUME", "SAFE_DELETE_UNPROVEN")
        require(
            re.fullmatch(
                r"[0-9a-f]{64}" if item.kind == "CONTAINER" else r"(?:[0-9a-f]{25}|[0-9a-f]{64})",
                identity,
            )
            is not None,
            "REMOVE_IMMUTABLE_ID_UNPROVEN",
        )
        code, _ = self.commands.run((item.kind.lower(), "rm", identity))
        require(code == 0, "REMOVE_ACK_UNKNOWN")

    def absent(self, item):
        require(self.independent_observer is not None, "INDEPENDENT_E_REQUIRED")
        return self.independent_observer.observe(item)["result"] == "ABSENT"


class FixtureSocketDirectory:
    """Held parent and exact marker, plus only PG's socket and lock while running.

    The namespace mapping must map container999 to C and the installed shared GID.
    Creation is not permission proof; readiness additionally checks mount/UID mapping.
    No unlink of PG files, no recursive cleanup, no following socket/marker symlinks.
    """

    def __init__(self, parent_fd, identity):
        self.parent_fd, self.identity = parent_fd, identity.verify(identity.scope)
        meta = os.fstat(parent_fd)
        require(
            stat.S_ISDIR(meta.st_mode) and meta.st_uid == 0 and meta.st_mode & 0o022 == 0,
            "SOCKET_PARENT_UNTRUSTED",
        )
        require(
            os.readlink("/proc/self/fd/" + str(parent_fd)) == identity.installation.socket_parent,
            "SOCKET_PARENT_TARGET",
        )
        self.parent_identity = meta.st_dev, meta.st_ino

    def open_fixture(self):
        p = os.fstat(self.parent_fd)
        require((p.st_dev, p.st_ino) == self.parent_identity, "SOCKET_PARENT_REPLACED")
        return os.open(
            self.identity.socket_name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=self.parent_fd,
        )

    def create(self, item):
        require(item == resources(self.identity.scope)[0], "FIXTURE_IDENTITY")
        require(
            os.getuid() == self.identity.controller_uid
            and self.identity.installation.socket_gid in {os.getgid(), *os.getgroups()},
            "SOCKET_UID_MAPPING_UNPROVEN",
        )
        os.mkdir(item.name, mode=0o770, dir_fd=self.parent_fd)
        fd = self.open_fixture()
        try:
            os.fchown(fd, self.identity.controller_uid, self.identity.installation.socket_gid)
            os.fchmod(fd, 0o770)
            marker = os.open(
                ".a42363-owner",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=fd,
            )
            try:
                raw = canonical(self.identity.model_dump())
                require(os.write(marker, raw) == len(raw), "SOCKET_MARKER_WRITE")
                os.fsync(marker)
            finally:
                os.close(marker)
            os.fsync(fd)
        finally:
            os.close(fd)
        return self.inspect(item)

    def inspect(self, item):
        require(item == resources(self.identity.scope)[0], "FIXTURE_IDENTITY")
        fd = self.open_fixture()
        try:
            meta = os.fstat(fd)
            require(
                meta.st_uid == self.identity.controller_uid
                and meta.st_gid == self.identity.installation.socket_gid
                and stat.S_IMODE(meta.st_mode) == 0o770,
                "SOCKET_OWNER_UNKNOWN",
            )
            require(
                set(os.listdir(fd)) <= {".a42363-owner", ".s.PGSQL.5432", ".s.PGSQL.5432.lock"},
                "SOCKET_CONTENTS_UNKNOWN",
            )
            marker = os.open(".a42363-owner", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                m = os.fstat(marker)
                raw = os.pread(marker, 65536, 0)
                require(
                    stat.S_ISREG(m.st_mode)
                    and m.st_uid == meta.st_uid
                    and m.st_nlink == 1
                    and raw == canonical(self.identity.model_dump()),
                    "SOCKET_MARKER_UNKNOWN",
                )
            finally:
                os.close(marker)
            for name in set(os.listdir(fd)) - {".a42363-owner"}:
                f = os.stat(name, dir_fd=fd, follow_symlinks=False)
                require(
                    f.st_uid == meta.st_uid
                    and (
                        stat.S_ISSOCK(f.st_mode)
                        if name == ".s.PGSQL.5432"
                        else stat.S_ISREG(f.st_mode) and f.st_nlink == 1
                    ),
                    "SOCKET_CONTENTS_UNKNOWN",
                )
            linked = os.stat(item.name, dir_fd=self.parent_fd, follow_symlinks=False)
            require((linked.st_dev, linked.st_ino) == (meta.st_dev, meta.st_ino), "SOCKET_REPLACED")
            return dict(
                device=meta.st_dev,
                inode=meta.st_ino,
                uid=meta.st_uid,
                gid=meta.st_gid,
                binding_sha256=sha(raw),
            )
        finally:
            os.close(fd)

    def remove(self, item, raw):
        require(self.inspect(item) == raw, "SOCKET_REPLACED")
        fd = self.open_fixture()
        try:
            require(set(os.listdir(fd)) == {".a42363-owner"}, "SOCKET_CONTENTS_UNKNOWN")
            os.unlink(".a42363-owner", dir_fd=fd)
            os.rmdir(item.name, dir_fd=self.parent_fd)
        finally:
            os.close(fd)


class ControllerService:
    def __init__(self, ledger, driver, store, consumption, fixture=None):
        self.ledger, self.driver, self.store, self.consumption = ledger, driver, store, consumption
        self.engine = RecoveryEngine(ledger, driver)
        self.fixture = fixture
        if fixture is not None:
            require(fixture.driver is driver, "FIXTURE_DRIVER_BINDING")
            fixture.engine = self.engine

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
            if type(self.driver) is ResourceDriver and self.driver.identity is not None:
                require(self.fixture is not None, "PG_FIXTURE_REQUIRED")
                self.driver.identity.verify(scope)
                self.fixture.prepare()
                self.fixture.start()
                result = self.fixture.readiness()
            else:
                result = self.engine.create(scope)
            return self.store.append(scope, "CREATED", result).model_dump()
        require(method in ("destroy", "reconcile"), "CONTROLLER_METHOD")
        previous = self.store.maybe_read(scope, "RECONCILED")
        if previous is not None:
            return previous.model_dump()  # Durable ACK recovery, never another remove.
        if self.store.maybe_read(scope, "DESTROY_REQUESTED") is None:
            self.store.append(scope, "DESTROY_REQUESTED", dict(resource_ids=self.identities(scope)))
        stop_error = None
        if self.fixture is not None:
            try:
                if self.fixture.container_id is None:
                    self.fixture.restore()
                self.fixture.stop()
            except BaseException as error:
                stop_error = getattr(error, "code", "A42363_PG_STOP_ACK_UNKNOWN")
        result = self.engine.recover(scope)
        if stop_error:
            result.update(
                status="INCOMPLETE_QUARANTINED",
                first_error=stop_error,
                cleanup_codes=list(dict.fromkeys([stop_error, *result["cleanup_codes"]])),
            )
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
                if events[-1].event == "REMOVE_ATTEMPTED":
                    require(self.driver.absent(item), "REMOVE_ACK_UNKNOWN")
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
