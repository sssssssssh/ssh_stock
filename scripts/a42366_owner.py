"""Immutable registration of actual independently observed worker PG identity.

No SQL is added to the frozen sixteen-slot probe. The supplied observer uses the
two separately charged Owner audit connections. Installation remains blocked.
"""

from scripts.a42363_contract import require, scope_hash


class TargetSessionRegistry:
    def __init__(self, identity, authority, journal, generation):
        require(journal.domain == "pg_owner", "OWNER_SESSION_JOURNAL")
        require(type(generation) is int and generation > 0, "OWNER_SESSION_GENERATION")
        self.identity, self.authority, self.journal, self.generation = (
            identity, authority, journal, generation,
        )

    def _validate(self, raw):
        i = self.identity.verify(self.identity.scope)
        require(type(raw) is dict and set(raw) == {
            "backend_pid", "backend_start", "role", "database", "generation",
            "namespace_sha256", "scope_sha256",
        }, "OWNER_SESSION_SCHEMA")
        require(type(raw["backend_pid"]) is int and raw["backend_pid"] > 1
                and type(raw["backend_start"]) is str and bool(raw["backend_start"])
                and raw["role"] == i.probe_role and raw["database"] == i.database
                and type(raw["generation"]) is int and raw["generation"] == self.generation
                and raw["namespace_sha256"] == i.scope.namespace_sha256
                and raw["scope_sha256"] == scope_hash(i.scope), "OWNER_SESSION_DRIFT")
        return raw

    def observe(self, source, pid):
        self.authority.require("TARGET_SESSION_GUC")
        scope = self.identity.scope
        prior = self.journal.maybe_read(scope, "TARGET_SESSION_REGISTERED")
        if prior is not None:
            require(prior.record["session"]["backend_pid"] == pid, "OWNER_SESSION_DRIFT")
        # No worker-supplied backend_start/role/db/GUC data is accepted here.
        raw = self._validate(source.observe(pid))
        require(raw["backend_pid"] == pid, "OWNER_SESSION_DRIFT")
        self.authority.require("TARGET_SESSION_GUC")
        if prior is None:
            self.journal.append(scope, "TARGET_SESSION_REGISTERED", dict(
                session=raw, qualifies=False,
            ))
        else:
            require(prior.record["session"] == raw, "OWNER_SESSION_DRIFT")
        actual = self.journal.read(scope, "TARGET_SESSION_REGISTERED")
        require(actual.record["session"] == raw, "OWNER_SESSION_COMMIT_UNKNOWN")
        return raw


class RegisteredSessionSource:
    def __init__(self, registry, source):
        self.registry, self.source = registry, source

    def observe(self, pid):
        return self.registry.observe(self.source, pid)
