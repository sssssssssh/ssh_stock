"""Committed-before-side-effect creation and exact, destroy-only recovery."""

import os
import stat
import time
import uuid
from pathlib import Path

from scripts.a42361_contract import canonical, checked, sha
from scripts.a42362_contract import (
    FailureLedger,
    Fault,
    LedgerRequest,
    Scope,
    file_identity,
    require,
    resource,
    resources,
    validate_receipt,
)


class RpcLedger:
    def __init__(self, deployment):
        from scripts.a42361_deployment import LocalService, installed

        installed(deployment)
        self.client = LocalService(deployment, "consumer")

    def append(self, body):
        return self.client.call("resource-append", body)

    def scan(self, body):
        return self.client.call("resource-scan", body)


class Reconciler:
    """Driver observes/removes only exact Resource values, never caller paths/prefixes."""

    def __init__(self, ledger=None, driver=None):
        self.ledger, self.driver = ledger, driver

    def _event(self, item, event, observed=None, error=None):
        require(self.ledger is not None, "A42362_LEDGER_NOT_CONFIGURED")
        q = LedgerRequest(
            resource=item,
            event=event,
            event_id=str(uuid.uuid4()),
            observed_identity_sha256=observed,
            error_code=error,
        )
        result = self.ledger.append(q.model_dump())
        return validate_receipt(result, q)

    def create(self, scope):
        scope = checked(Scope, scope)
        require(
            self.driver is not None and self.ledger is not None, "A42362_CONTROLLER_NOT_CONFIGURED"
        )
        require(
            self.ledger.scan(dict(scope=scope.model_dump()))["events"] == [],
            "A42362_NO_SECOND_CREATE",
        )
        started = time.monotonic_ns()
        for item in resources(scope):
            # Fresh committed ACK before mkdir/volume/secret/container, including crash paths.
            self._event(item, "RESERVED")
            self._event(item, "CREATE_ATTEMPTED")
            try:
                require(
                    time.monotonic_ns() - started < 2_000_000_000, "A42362_INITIALIZATION_TIMEOUT"
                )
                observation = self.driver.create(item)
                digest = self.driver.verify(item, observation)
                self._event(item, "OBSERVED_CREATED", observed=digest)
            except BaseException as error:
                code = error.code if isinstance(error, Fault) else "A42362_CREATE_ACK_UNKNOWN"
                try:
                    self._event(item, "UNKNOWN", error=code)
                except BaseException:
                    # Failed persistence does not authorize a second create or broad cleanup.
                    raise Fault("A42362_CREATE_AND_JOURNAL_UNKNOWN") from None
                raise Fault(code) from None
        return dict(status="CREATED_PENDING_OWNER_ATTESTATION", qualifies=False)

    def recover(self, scope):
        """Fresh ledger only; no create continuation, filesystem scans or name-prefix deletion."""
        scope = checked(Scope, scope)
        require(
            self.driver is not None and self.ledger is not None, "A42362_CONTROLLER_NOT_CONFIGURED"
        )
        snapshot = self.ledger.scan(dict(scope=scope.model_dump()))
        require(
            set(snapshot) == {"events", "snapshot_sha256"}
            and sha(canonical(snapshot["events"])) == snapshot["snapshot_sha256"],
            "A42362_LEDGER_SNAPSHOT_UNTRUSTED",
        )
        known, previous_sequence = {}, 0
        for raw in snapshot["events"]:
            q = checked(LedgerRequest, raw["request"])
            r = validate_receipt(raw, q)
            require(
                q.resource.scope == scope and r.sequence > previous_sequence,
                "A42362_LEDGER_SCOPE_MISMATCH",
            )
            previous_sequence = r.sequence
            known[q.resource.kind] = r
        require(bool(known), "A42362_MANUAL_QUARANTINE_NO_LEDGER")
        started, failures = time.monotonic_ns(), FailureLedger()
        for item in reversed(resources(scope)):
            last = known.get(item.kind)
            if last is None:
                continue  # Never created by this ledger; NOT an independent absent proof.
            if last.request.event == "OBSERVED_ABSENT":
                continue
            try:
                require(
                    time.monotonic_ns() - started < 2_000_000_000,
                    "A42362_CLEANUP_TIMEOUT_QUARANTINE",
                )
                raw = self.driver.inspect(item)
                actual = self.driver.verify(item, raw)
                if last.request.observed_identity_sha256 is not None:
                    require(
                        actual == last.request.observed_identity_sha256,
                        "A42362_RESOURCE_REPLACED_QUARANTINE",
                    )
                if last.request.event != "REMOVE_ATTEMPTED":
                    self._event(item, "REMOVE_ATTEMPTED")
                self.driver.remove(item, raw)
                require(self.driver.absent(item) is True, "A42362_REMOVE_ACK_UNKNOWN")
                self._event(item, "OBSERVED_ABSENT")
            except BaseException as error:
                failures.fail(
                    error.code
                    if isinstance(error, Fault)
                    else "A42362_OWNERSHIP_UNKNOWN_QUARANTINE",
                    cleanup=True,
                )
        return dict(
            status="INCOMPLETE_QUARANTINED"
            if failures.first_error
            else "DESTROYED_PENDING_INDEPENDENT_E",
            first_error=failures.first_error,
            cleanup_codes=failures.cleanup_codes,
            qualifies=False,
            independent_absent=False,
        )


class ExactSocketDirectory:
    """No recursive remove. Held parent FD, owner/inode and immutable marker must match."""

    def __init__(self, parent_fd, uid, gid):
        self.parent_fd, self.uid, self.gid = parent_fd, uid, gid

    def create(self, item):
        item = resource(item)
        require(item.kind == "SOCKET_DIR", "A42362_RESOURCE_OUTSIDE_SCOPE")
        os.mkdir(item.name, mode=0o700, dir_fd=self.parent_fd)
        fd = os.open(item.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.parent_fd)
        try:
            os.fchown(fd, self.uid, self.gid)
            marker = os.open(
                ".a42362-owner",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=fd,
            )
            with os.fdopen(marker, "wb") as stream:
                stream.write(canonical(item.model_dump()))
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(fd)
        finally:
            os.close(fd)
        return self.inspect(item)

    def inspect(self, item):
        item = resource(item)
        require(item.kind == "SOCKET_DIR", "A42362_RESOURCE_OUTSIDE_SCOPE")
        fd = os.open(item.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.parent_fd)
        try:
            meta = os.fstat(fd)
            require(
                meta.st_uid == self.uid
                and meta.st_gid == self.gid
                and stat.S_IMODE(meta.st_mode) == 0o700,
                "A42362_SOCKET_OWNER_UNKNOWN",
            )
            require(set(os.listdir(fd)) == {".a42362-owner"}, "A42362_SOCKET_CONTENTS_UNKNOWN")
            marker = os.open(".a42362-owner", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                m = os.fstat(marker)
                raw = os.read(marker, 65537)
                require(
                    stat.S_ISREG(m.st_mode)
                    and m.st_nlink == 1
                    and m.st_uid == self.uid
                    and raw == canonical(item.model_dump())
                    and file_identity(os.fstat(marker)) == file_identity(m),
                    "A42362_SOCKET_MARKER_UNKNOWN",
                )
            finally:
                os.close(marker)
            require(
                file_identity(os.stat(item.name, dir_fd=self.parent_fd, follow_symlinks=False))
                == file_identity(meta),
                "A42362_SOCKET_REPLACED",
            )
            return dict(
                device=meta.st_dev,
                inode=meta.st_ino,
                uid=meta.st_uid,
                gid=meta.st_gid,
                binding_sha256=sha(raw),
            )
        finally:
            os.close(fd)

    def remove(self, item, expected):
        require(self.inspect(item) == expected, "A42362_SOCKET_REPLACED")
        fd = os.open(item.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.parent_fd)
        try:
            require(
                (os.fstat(fd).st_dev, os.fstat(fd).st_ino)
                == (expected["device"], expected["inode"]),
                "A42362_SOCKET_REPLACED",
            )
            os.unlink(".a42362-owner", dir_fd=fd)
            os.rmdir(item.name, dir_fd=self.parent_fd)
        finally:
            os.close(fd)


class PodmanResourceDriver:
    """Exact fixed command adapter. Missing installed namespace/owner methods fail closed."""

    def __init__(self, controller, socket_directory, owner=None):
        self.controller, self.socket_directory, self.owner = controller, socket_directory, owner

    def inspect(self, item):
        import json

        item = resource(item)
        if item.kind == "SOCKET_DIR":
            return self.socket_directory.inspect(item)
        return json.loads(
            self.controller._command(
                (item.kind.lower(), "inspect", "--format", "{{json .}}", item.name), cleanup=True
            )
        )

    def verify(self, item, raw):
        item = resource(item)
        if item.kind == "SOCKET_DIR":
            require(raw == self.socket_directory.inspect(item), "A42362_SOCKET_REPLACED")
        else:
            s = item.scope
            labels = (
                raw.get("Config", {}).get("Labels", {})
                if item.kind == "CONTAINER"
                else raw.get("Spec", {}).get("Labels", {})
                if item.kind == "SECRET"
                else raw.get("Labels", {})
            )
            expected = dict(
                a42361_owner=str(s.controller_uid),
                a42361_fixture=s.binding.fixture_uuid,
                a42361_nonce=s.binding.nonce,
                a42361_payload=s.payload_sha256,
            )
            require(
                all(labels.get(k) == v for k, v in expected.items()),
                "A42362_OWNERSHIP_UNKNOWN_QUARANTINE",
            )
            name = raw.get("Spec", {}).get("Name") if item.kind == "SECRET" else raw.get("Name")
            require(name == item.name, "A42362_RESOURCE_REPLACED_QUARANTINE")
            require(
                raw.get("ID") or raw.get("Id") or raw.get("Mountpoint"),
                "A42362_RAW_RESOURCE_ID_REQUIRED",
            )
            if item.kind == "CONTAINER":
                self.controller._validate_inspection(
                    raw, self.controller._authorization, item.name, resources(s)[1].name
                )
        return sha(canonical(raw))

    def create(self, item):
        item = resource(item)
        if item.kind == "SOCKET_DIR":
            return self.socket_directory.create(item)
        labels = tuple(
            x
            for k, v in dict(
                a42361_owner=str(item.scope.controller_uid),
                a42361_fixture=item.scope.binding.fixture_uuid,
                a42361_nonce=item.scope.binding.nonce,
                a42361_payload=item.scope.payload_sha256,
            ).items()
            for x in ("--label", k + "=" + v)
        )
        if item.kind == "VOLUME":
            self.controller._command(("volume", "create", *labels, item.name))
        else:
            # Owner initialization/secret/container launch cannot proceed while its
            # actual GUC/ACL method and rootless namespace deployment are unapproved.
            from scripts.a42362_pg_owner_service import require_session_method

            require_session_method()
        return self.inspect(item)

    def remove(self, item, raw):
        self.verify(item, raw)
        if item.kind == "SOCKET_DIR":
            return self.socket_directory.remove(item, raw)
        self.controller._command((item.kind.lower(), "rm", item.name), cleanup=True)

    def absent(self, item):
        if item.kind == "SOCKET_DIR":
            try:
                os.stat(item.name, dir_fd=self.socket_directory.parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return True
            return False
        # A command failure is not a negative observation. E must independently check.
        raise Fault("A42362_ABSENCE_REQUIRES_INDEPENDENT_E")


def legacy_create(deployment, consumption):
    from scripts.a42361_deployment import installed
    from scripts.a42361_one_shot_store import committed
    from scripts.a42362_pg_owner_service import require_session_method

    installed(deployment)
    committed(consumption)
    require_session_method()  # No partial real fixture just to hit an already-known method block.


def safe_parent(path, uid):
    path = Path(path)
    require(
        path.is_absolute() and not any(p.is_symlink() for p in (path, *path.parents)),
        "A42362_PARENT_NOT_TRUSTED",
    )
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        meta = os.fstat(fd)
        require(
            meta.st_uid == uid and stat.S_IMODE(meta.st_mode) == 0o700, "A42362_PARENT_NOT_TRUSTED"
        )
        return fd
    except BaseException:
        os.close(fd)
        raise
