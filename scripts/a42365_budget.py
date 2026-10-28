"""B-owned persistent, pre-effect accounting. No runtime selection from RPC."""

import time

from scripts.a42361_contract import canonical, sha
from scripts.a42363_contract import require
from scripts.a42364_costs import ACTIVE, CANDIDATE, cost_plan
from scripts.a42365_protocol import runtime_budget_plan


class BudgetService:
    def __init__(self, identity, authority, journal, boot_identity):
        require(journal.domain == "consumer", "BUDGET_WRITER_DOMAIN")
        self.identity, self.authority, self.journal = identity, authority, journal
        self.boot_identity = boot_identity
        self.plan = cost_plan(identity)
        self.digest = sha(canonical(runtime_budget_plan(identity)))
        self.operations = {op["name"]: op for op in self.plan["operations"]}

    def start(self):
        self.authority.require("BOOTSTRAP_AND_BUDGET")
        self.authority.require("TARGET_SESSION_GUC")
        return self.journal.append(
            self.identity.scope,
            "BUDGET_STARTED",
            dict(
                plan_sha256=self.digest,
                boot_identity=self.boot_identity,
                monotonic_ns=time.monotonic_ns(),
                wall_ns=time.time_ns(),
                qualifies=False,
            ),
        )

    def _check(self):
        self.authority.require("BOOTSTRAP_AND_BUDGET")
        require(
            self.journal.maybe_read(self.identity.scope, "BUDGET_STOPPED") is None,
            "CANDIDATE_BOOTSTRAP_DEADLINE",
        )
        start = self.journal.read(self.identity.scope, "BUDGET_STARTED").record
        require(
            start["plan_sha256"] == self.digest and start["boot_identity"] == self.boot_identity,
            "BUDGET_RESTART_IDENTITY",
        )
        valid = (
            0 <= time.monotonic_ns() - start["monotonic_ns"] < CANDIDATE["window_ms"] * 1000000
            and 0 <= time.time_ns() - start["wall_ns"] < CANDIDATE["window_ms"] * 1000000
        )
        if not valid:
            if self.journal.maybe_read(self.identity.scope, "BUDGET_STOPPED") is None:
                self.journal.append(self.identity.scope, "BUDGET_STOPPED", dict(qualifies=False))
            require(False, "CANDIDATE_BOOTSTRAP_DEADLINE")

    def reserve_named(self, name, now_ns=None, wall_ms=None):
        # Clocks supplied by legacy adapters are not trusted; read B's own clock.
        self._check()
        require(name in self.operations, "UNACCOUNTED_BOOTSTRAP_OPERATION")
        op = self.operations[name]
        return self._reserve(
            name, dict(sql=op["sql"], commands=op["commands"], audit_sql=0, audit_auth=0)
        )

    def reserve_audit(self, index, kind):
        self.authority.require("TARGET_SESSION_GUC")
        self._check()
        require(
            type(index) is int and index in (1, 2) and kind in ("SQL", "AUTH"), "AUDIT_BUDGET_SLOT"
        )
        return self._reserve(
            "TARGET_AUDIT_" + str(index) + "_" + kind,
            dict(sql=0, commands=0, audit_sql=int(kind == "SQL"), audit_auth=int(kind == "AUTH")),
        )

    def _reserve(self, name, costs):
        return self.journal.reserve(
            self.identity.scope,
            "RESERVE_" + sha(name.encode())[:40],
            dict(
                operation=name,
                costs=costs,
                plan_sha256=self.digest,
                attempted_ns=time.monotonic_ns(),
                qualifies=False,
            ),
            dict(sql=12, commands=32, audit_sql=2, audit_auth=2),
        )

    def reserve_filesystem(self, step):
        self._check()
        require(
            type(step) is int and 0 <= step < len(self.plan["filesystem_operations"]),
            "UNACCOUNTED_FILESYSTEM_OPERATION",
        )
        return self.journal.append(
            self.identity.scope,
            "FILESYSTEM_" + str(step),
            dict(
                operation=self.plan["filesystem_operations"][step],
                plan_sha256=self.digest,
                attempted_ns=time.monotonic_ns(),
                qualifies=False,
            ),
        )

    def native_exec(self, ordinal):
        # A reservation-only endpoint must not be mistaken for exec admission.
        self.authority.require("BOOTSTRAP_AND_BUDGET")
        require(type(ordinal) is int and 1 <= ordinal <= 5, "UNACCOUNTED_INITDB_EXEC")
        require(False, "NATIVE_TRANSITIVE_CENSUS_UNPROVEN")

    def require_active_plan(self):
        require(
            self.plan["total"]["sql"] <= ACTIVE["sql"]
            and self.plan["total"]["commands"] <= ACTIVE["commands"]
            and self.plan["total"]["allocated_ms"] <= ACTIVE["window_ms"],
            "ACTIVE_BOOTSTRAP_LIMIT_EXCEEDED",
        )

    def report(self):
        return dict(
            plan_sha256=self.digest,
            events=[r.model_dump() for r in self.journal.events(self.identity.scope)],
            measured=False,
            native_exec_census="NOT_IMPLEMENTED",
            qualifies=False,
        )
