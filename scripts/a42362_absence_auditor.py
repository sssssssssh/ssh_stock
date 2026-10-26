"""E-domain exact negative observations, never a mirror of Controller JSON."""

import os
import time
from typing import Literal

from scripts.a4235_calibration_adapter_contract import Hash, Strict
from scripts.a42361_contract import canonical, checked, sha
from scripts.a42362_contract import Lookup, Resource, Scope, require, resources


class Observation(Strict):
    resource: Resource
    observer_uid: int
    namespace_sha256: Hash
    collector_sha256: Hash
    observed_ns: int
    result: Literal["PRESENT", "ABSENT", "ABSENCE_UNKNOWN"]
    exit_code: int


class ReadOnlyObserver:
    def __init__(self, installation=None, runner=None, parent_fd=None):
        self.installation, self.runner, self.parent_fd = installation, runner, parent_fd

    def observe(self, item):
        from scripts.a42362_service_host import installation

        c = installation(self.installation)
        require(
            c.domain == "absence_auditor"
            and os.getuid() == c.uid
            and c.uid != item.scope.controller_uid,
            "A42362_AUDITOR_NOT_INDEPENDENT",
        )
        namespace = sha(os.readlink("/proc/self/ns/user").encode())
        require(namespace == item.scope.namespace_sha256, "A42362_AUDIT_NAMESPACE_UNPROVEN")
        if item.kind == "SOCKET_DIR":
            require(self.parent_fd is not None, "A42362_AUDIT_PARENT_UNAVAILABLE")
            try:
                os.stat(item.name, dir_fd=self.parent_fd, follow_symlinks=False)
                code, result = 0, "PRESENT"
            except FileNotFoundError:
                code, result = 1, "ABSENT"
        else:
            require(self.runner is not None, "A42362_READONLY_COLLECTOR_NOT_CONFIGURED")
            # Only exists, not list/inspect --showsecret, remove, prune, exec or arbitrary args.
            code, _ = self.runner.run_readonly((item.kind.lower(), "exists", item.name))
            result = {0: "PRESENT", 1: "ABSENT"}.get(code, "ABSENCE_UNKNOWN")
        return Observation(
            resource=item,
            observer_uid=c.uid,
            namespace_sha256=namespace,
            collector_sha256=c.collector_sha256,
            observed_ns=time.monotonic_ns(),
            result=result,
            exit_code=code,
        )


class AbsenceAuditor:
    def __init__(self, installation=None, ledger=None, store=None, observer=None):
        self.installation, self.ledger, self.store, self.observer = (
            installation,
            ledger,
            store,
            observer,
        )

    def dispatch(self, peer_uid, method, body):
        from scripts.a42362_service_host import installation

        c = installation(self.installation)
        require(
            c.domain == "absence_auditor"
            and os.getuid() == c.uid
            and peer_uid in c.read_uids
            and c.uid != c.controller_uid,
            "A42362_AUDITOR_NOT_INDEPENDENT",
        )
        q = checked(Lookup, body)
        require(method in ("absent", "receipt"), "A42362_METHOD_REJECTED")
        require(self.store is not None, "A42362_AUDIT_STORE_NOT_CONFIGURED")
        if method == "receipt":
            return self.store.read_absence(q.scope)
        return self.audit(q.scope)

    def audit(self, scope):
        from scripts.a42362_service_host import installation

        c = installation(self.installation)
        scope = checked(Scope, scope)
        require(
            c.domain == "absence_auditor" and c.uid != scope.controller_uid,
            "A42362_AUDITOR_NOT_INDEPENDENT",
        )
        require(
            self.store is not None and self.ledger is not None and self.observer is not None,
            "A42362_AUDITOR_NOT_CONFIGURED",
        )
        snapshot = self.ledger.scan(dict(scope=scope.model_dump()))
        require(
            sha(canonical(snapshot["events"])) == snapshot["snapshot_sha256"],
            "A42362_AUDIT_LEDGER_UNTRUSTED",
        )
        require(
            {e["request"]["resource"]["kind"] for e in snapshot["events"]}
            == {r.kind for r in resources(scope)},
            "A42362_AUDIT_RESOURCE_SET_INCOMPLETE",
        )
        # Independent committed store, not a destroy response forwarded by C.
        destroy = self.store.read_destruction(scope)
        require(
            set(destroy)
            == {
                "requested_sequence",
                "destroyed_sequence",
                "destroyed_ns",
                "domain",
                "scope_sha256",
            }
            and destroy["domain"] == "CONTROLLER"
            and destroy["scope_sha256"] == sha(canonical(scope.model_dump()))
            and 0 < destroy["requested_sequence"] < destroy["destroyed_sequence"],
            "A42362_DESTROY_ORDER_UNPROVEN",
        )
        raw = []
        for _ in range(2):
            for item in resources(scope):
                o = checked(Observation, self.observer.observe(item))
                require(
                    o.resource == item
                    and o.observer_uid == c.uid
                    and o.observer_uid != scope.controller_uid
                    and o.namespace_sha256 == scope.namespace_sha256
                    and o.collector_sha256 == c.collector_sha256
                    and o.observed_ns > destroy["destroyed_ns"]
                    and o.result == "ABSENT"
                    and o.exit_code == 1,
                    "A42362_ABSENCE_UNKNOWN",
                )
                raw.append(o.model_dump())
        require(
            all(b["observed_ns"] > a["observed_ns"] for a, b in zip(raw, raw[1:], strict=False)),
            "A42362_AUDIT_CLOCK_UNPROVEN",
        )
        record = dict(
            domain="ABSENCE_AUDITOR",
            event="ABSENT",
            scope=scope.model_dump(),
            observations=raw,
            destruction=destroy,
            qualifies=False,
        )
        digest = self.store.append_absence(record)
        fresh = self.store.read_absence(scope)
        require(
            fresh == dict(record=record, raw_receipt_sha256=sha(canonical(record)), committed=True)
            and digest == fresh["raw_receipt_sha256"],
            "A42362_AUDIT_COMMIT_UNKNOWN",
        )
        return fresh
