"""E's delegated read-only view and independent, committed two-round audit."""

import json
import os
import stat
import time

from scripts.a42361_contract import canonical, sha
from scripts.a42362_contract import resources
from scripts.a42363_contract import lookup, require, scope_hash, verify_receipt


class IndependentObserver:
    """Collector is an administrator-installed readonly delegation to C's store.

    Same user namespace is insufficient: delegation pins runtime store, mount namespace,
    collector bytes, observer UID and C UID. Empty output never establishes absence.
    """

    def __init__(self, observer_uid, controller_uid, delegation, collector):
        require(observer_uid != controller_uid, "AUDITOR_UID_NOT_INDEPENDENT")
        self.uid, self.controller_uid = observer_uid, controller_uid
        self.delegation, self.collector = delegation, collector

    def observe(self, item):
        proof = self.collector.visibility(self.delegation)
        require(
            set(proof)
            == {
                "observer_uid",
                "controller_uid",
                "namespace_sha256",
                "store_sha256",
                "collector_sha256",
                "readonly",
                "epoch",
            },
            "AUDIT_VISIBILITY",
        )
        require(
            proof["observer_uid"] == self.uid
            and proof["controller_uid"] == self.controller_uid == item.scope.controller_uid
            and proof["namespace_sha256"] == item.scope.namespace_sha256
            and proof["epoch"] == item.scope.epoch
            and proof["readonly"] is True
            and proof["store_sha256"] == self.delegation["store_sha256"]
            and proof["collector_sha256"] == self.delegation["collector_sha256"],
            "AUDIT_VISIBILITY",
        )
        raw = self.collector.read_exact(item)
        require(type(raw) is dict and set(raw) == {"status", "code", "identity"}, "AUDIT_RAW")
        require(raw["status"] in ("PRESENT", "ABSENT", "UNKNOWN"), "AUDIT_RAW")
        require(
            (raw["status"] == "ABSENT") == (raw["code"] == 1 and raw["identity"] is None),
            "AUDIT_UNKNOWN",
        )
        return dict(
            resource=item.model_dump(),
            observer_uid=self.uid,
            visibility=proof,
            result=raw["status"],
            raw=raw,
            observed_ns=time.monotonic_ns(),
        )


class DelegatedReadOnlyCollector:
    """Fixed readonly runtime adapter bound to held namespace/store administrator FDs.

    Merely using a different UID's own rootless store fails the graph-root check.
    Manager must independently establish readonly filesystem/namespace delegation;
    this class neither mounts nor changes permissions or user namespaces.
    """

    def __init__(
        self, runner, namespace_fd, store_fd, expected, socket_directory, collector_fd=None
    ):
        self.runner, self.namespace_fd, self.store_fd = runner, namespace_fd, store_fd
        self.expected, self.socket_directory = expected, socket_directory
        self.collector_fd = collector_fd
        self._visibility_verified = None
        self.namespace_identity = (os.fstat(namespace_fd).st_dev, os.fstat(namespace_fd).st_ino)
        self.store_identity = (os.fstat(store_fd).st_dev, os.fstat(store_fd).st_ino)

    def visibility(self, delegation):
        self._visibility_verified = None
        require(
            os.getuid() == self.expected["observer_uid"]
            and self.expected["observer_uid"] != self.expected["controller_uid"],
            "AUDITOR_PRINCIPAL",
        )
        require(type(self.collector_fd) is int, "READONLY_DELEGATION_REQUIRED")
        meta = os.fstat(self.collector_fd)
        require(
            stat.S_ISREG(meta.st_mode)
            and meta.st_uid == 0
            and meta.st_mode & 0o022 == 0
            and sha(os.pread(self.collector_fd, 65536, 0)) == self.expected["collector_sha256"],
            "COLLECTOR_IDENTITY",
        )
        require(delegation == self.expected["delegation"], "DELEGATION_MISMATCH")
        for fd, expected in (
            (self.namespace_fd, self.namespace_identity),
            (self.store_fd, self.store_identity),
        ):
            actual = os.fstat(fd)
            require((actual.st_dev, actual.st_ino) == expected, "DELEGATION_FD_CHANGED")
        current = os.stat("/proc/self/ns/user")
        require(
            (current.st_dev, current.st_ino) == self.namespace_identity
            and sha(os.readlink("/proc/self/ns/user").encode())
            == self.expected["namespace_sha256"],
            "AUDIT_WRONG_NAMESPACE",
        )
        code, raw = self.runner.read(("info", "--format", "json"))
        require(code == 0, "AUDIT_NAMESPACE_UNAVAILABLE")
        try:
            info = json.loads(raw)
        except (ValueError, TypeError):
            require(False, "AUDIT_NAMESPACE_UNAVAILABLE")
        require(
            info["host"]["security"]["rootless"] is True
            and sha(info["store"]["graphRoot"].encode()) == self.expected["store_sha256"],
            "AUDIT_WRONG_ROOTLESS_STORE",
        )
        graph = os.stat(info["store"]["graphRoot"], follow_symlinks=False)
        require((graph.st_dev, graph.st_ino) == self.store_identity, "AUDIT_WRONG_STORE_FD")
        require(os.fstat(self.collector_fd) == meta, "COLLECTOR_CHANGED")
        self._visibility_verified = (self.namespace_identity, self.store_identity, meta)
        # Installation data are checked against held kernel objects, not C's JSON.
        return {
            k: self.expected[k]
            for k in (
                "observer_uid",
                "controller_uid",
                "namespace_sha256",
                "store_sha256",
                "collector_sha256",
                "readonly",
                "epoch",
            )
        }

    def read_exact(self, item):
        proof, self._visibility_verified = self._visibility_verified, None
        require(proof is not None, "READONLY_DELEGATION_REQUIRED")
        require(
            item.scope.controller_uid == self.expected["controller_uid"]
            and item.scope.epoch == self.expected["epoch"]
            and item.scope.namespace_sha256 == self.expected["namespace_sha256"],
            "AUDIT_VISIBILITY",
        )
        for fd, expected in ((self.namespace_fd, proof[0]), (self.store_fd, proof[1])):
            actual = os.fstat(fd)
            require((actual.st_dev, actual.st_ino) == expected, "DELEGATION_FD_CHANGED")
        require(os.fstat(self.collector_fd) == proof[2], "COLLECTOR_CHANGED")
        if item.kind == "SOCKET_DIR":
            try:
                meta = os.stat(
                    item.name, dir_fd=self.socket_directory.parent_fd, follow_symlinks=False
                )
                return dict(status="PRESENT", code=0, identity=str(meta.st_ino))
            except FileNotFoundError:
                return dict(status="ABSENT", code=1, identity=None)
        code, raw = self.runner.read((item.kind.lower(), "exists", item.name))
        # Status 125, stderr, malformed output or permission errors never mean absence.
        require(raw == b"" and code in (0, 1), "AUDIT_RAW_UNKNOWN")
        return dict(
            status="PRESENT" if code == 0 else "ABSENT",
            code=code,
            identity=item.name if code == 0 else None,
        )


class AbsenceService:
    def __init__(self, observer, store, controller_store, ledger):
        self.observer, self.store = observer, store
        self.controller_store, self.ledger = controller_store, ledger

    def dispatch(self, method, body):
        scope = lookup(body)
        require(method in ("journal", "absent", "receipt"), "AUDIT_METHOD")
        if method in ("journal", "receipt"):
            return self.store.read(scope, "ABSENT").model_dump()
        destroyed = self.controller_store.read(scope, "RECONCILED")
        verify_receipt(destroyed, "controller", scope, "RECONCILED")
        requested = self.controller_store.read(scope, "DESTROY_REQUESTED")
        require(
            requested.sequence < destroyed.sequence
            and destroyed.record["status"] == "DESTROYED_PENDING_INDEPENDENT_E",
            "DESTROY_UNPROVEN",
        )
        snapshot = self.ledger.scan(dict(scope=scope.model_dump()))
        require(sha(canonical(snapshot["events"])) == snapshot["snapshot_sha256"], "AUDIT_LEDGER")
        require(
            {r["request"]["resource"]["kind"] for r in snapshot["events"]}
            == {r.kind for r in resources(scope)},
            "AUDIT_RESOURCE_SET",
        )
        observations = []
        for _ in range(2):
            # A durable change, including a recreation invisible at the exact exists
            # instants, invalidates the first round. Never promote stale C evidence.
            current = self.ledger.scan(dict(scope=scope.model_dump()))
            require(current == snapshot, "AUDIT_LEDGER_CHANGED")
            require(
                self.controller_store.read(scope, "RECONCILED") == destroyed
                and self.controller_store.read(scope, "DESTROY_REQUESTED") == requested,
                "AUDIT_DESTRUCTION_CHANGED",
            )
            for item in resources(scope):
                raw = self.observer.observe(item)
                require(
                    raw["resource"] == item.model_dump()
                    and raw["result"] == "ABSENT"
                    and raw["observed_ns"] > destroyed.record["destroyed_ns"],
                    "ABSENCE_UNKNOWN",
                )
                observations.append(raw)
        require(
            self.ledger.scan(dict(scope=scope.model_dump())) == snapshot, "AUDIT_LEDGER_CHANGED"
        )
        require(
            self.controller_store.read(scope, "RECONCILED") == destroyed
            and self.controller_store.read(scope, "DESTROY_REQUESTED") == requested,
            "AUDIT_DESTRUCTION_CHANGED",
        )
        require(
            all(
                b["observed_ns"] > a["observed_ns"]
                for a, b in zip(observations, observations[1:], strict=False)
            ),
            "AUDIT_ORDER",
        )
        return self.store.append(
            scope,
            "ABSENT",
            dict(
                scope_sha256=scope_hash(scope),
                requested_digest=requested.digest,
                destruction_digest=destroyed.digest,
                observations=observations,
                physical_proven=False,
                qualifies=False,
            ),
        ).model_dump()


def candidate_readonly_collector(delegation, runner, socket_parent_fd):
    """Use verified readonly mounts, not the observer's unrelated rootless store."""
    from scripts.a42364_collector import FixedReadOnlyCollector

    return FixedReadOnlyCollector(delegation, runner, socket_parent_fd)
