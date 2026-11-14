"""Read-only E03 plan inspection. No live authority or resource operations exist.

All observations and receipts here are OFFLINE fixtures. Matching declarations
is insufficient: injected ports must attest the canonical whole-plan digest.
Their result is still only an offline proof, never an execution permit. The
in-memory UUID journal has session scope and makes no durable/live lease claim.
"""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Protocol

from scripts import biz_perf_p1_04_diagnostic as d

SCHEMA = "biz-perf-p1-04.e03.offline-plan.v1"
MAX_PLAN_BYTES = 64 * 1024
GATES = dict(root_attempts=0, hotspot="NONE_PROVEN", b_gate="NOT_APPROVED",
             targeted_pg17_gate="NOT_APPROVED", authorization="AUTHORIZATION_PENDING")
LIMITS = dict(worker_bytes=3 * 1024**3, pg_bytes=4 * 1024**3,
              volume_bytes=10 * 1024**3, output_bytes=10 * 1024**2,
              total_ms=1_200_000, cleanup_reserve_ms=300_000)
CODES = frozenset({
    "PLAN_REJECTED", "SOURCE_MISMATCH", "CI_REJECTED", "REVIEW_REJECTED",
    "SCOPE_REJECTED", "RESOURCE_REJECTED", "BUDGET_REJECTED", "EVIDENCE_CLASS_REFUSED",
    "INSPECTION_REFUSED", "IDENTITY_REFUSED", "APPROVAL_REFUSED", "BUDGET_REFUSED",
    "EXECUTION_NOT_AVAILABLE", "PORT_REJECTED", "RUN_UUID_REUSED", "JOURNAL_REFUSED",
    "AUTHORIZATION_PENDING", "INPUT_REJECTED",
})


class Refused(ValueError):
    def __init__(self, code):
        self.code = code if type(code) is str and code in CODES else "PLAN_REJECTED"
        super().__init__(self.code)


def require(value, code="PLAN_REJECTED"):
    if not value:
        raise Refused(code)


def fields(value, keys, code="PLAN_REJECTED"):
    require(type(value) is dict and set(value) == set(keys), code)


def seed_rows(benchmark_count):
    """Static expected Seed rows per table, not generated or observed facts.

    The historical harness spans start-900 through Jan 31 inclusive (931 days),
    using weekdays (665) as its SYNTHETIC calendar, not an exchange calendar.
    Quality rows below are the seed input only, not a post-root output budget.
    """
    return dict(trade_calendar=931, stock_basic=8, sector=1, sector_member=8,
                stock_daily=5320, stock_adj_factor=5320, stock_daily_basic=5320,
                stock_limit_daily=5320, index_daily=665 * benchmark_count,
                stock_st_daily=0, stock_suspend_daily=0, data_quality_daily=1330)


def decode_plan(raw):
    try:
        require(type(raw) is bytes and len(raw) <= MAX_PLAN_BYTES)
        return d.decode(raw)
    except (d.Rejected, ValueError, TypeError, RecursionError):
        raise Refused("INPUT_REJECTED") from None


def _scope(scope):
    fields(scope, {"start", "end", "roots", "seed_history_days", "seed_open_days",
                   "stock_day_rows", "benchmark_count", "row_budgets"}, "SCOPE_REJECTED")
    require(scope["start"] == "2025-01-01" and scope["end"] == "2025-01-31",
            "SCOPE_REJECTED")
    for key, expected in dict(roots=1, seed_history_days=900, seed_open_days=665,
                              stock_day_rows=5320).items():
        require(type(scope[key]) is int and scope[key] == expected, "SCOPE_REJECTED")
    n = scope["benchmark_count"]
    require(type(n) is int and 1 <= n <= 16, "SCOPE_REJECTED")
    expected_rows = seed_rows(n)
    fields(scope["row_budgets"], expected_rows, "SCOPE_REJECTED")
    for table, rows in expected_rows.items():
        value = scope["row_budgets"][table]
        fields(value, {"max_rows", "content_sha256"}, "SCOPE_REJECTED")
        require(type(value["max_rows"]) is int and value["max_rows"] == rows
                and d.hex_value(value["content_sha256"], 64), "SCOPE_REJECTED")


def _resources(value, preflight):
    fields(value, {"platform", "architecture", "instance", "pgdata_new", "pgdata_exclusive",
                   "database_new", "database_owner_sha256", "volume_sha256", "lease_uuid",
                   "lease_exclusive", "offline_system_identifier", "online_system_identifier",
                   "limits"}, "RESOURCE_REJECTED")
    require(value["platform"] == "Linux" and value["architecture"] == "x86_64",
            "RESOURCE_REJECTED")
    require(all(value[key] is True for key in (
        "pgdata_new", "pgdata_exclusive", "database_new", "lease_exclusive")),
        "RESOURCE_REJECTED")
    require(value["instance"] == preflight["expected_instance"], "RESOURCE_REJECTED")
    instance = value["instance"]
    require(value["offline_system_identifier"] == value["online_system_identifier"]
            == instance["system_identifier"], "RESOURCE_REJECTED")
    require(value["database_owner_sha256"] == instance["owner_sha256"]
            and d.hex_value(value["volume_sha256"], 64)
            and value["lease_uuid"] == preflight["run_uuid"], "RESOURCE_REJECTED")
    limits = value["limits"]
    fields(limits, {*LIMITS, "cpu_millis"}, "BUDGET_REJECTED")
    require(all(type(limits[key]) is int and limits[key] == expected
                for key, expected in LIMITS.items()), "BUDGET_REJECTED")
    # CPU is deliberately a bounded draft field to be reviewed, not a grant.
    require(type(limits["cpu_millis"]) is int and 1 <= limits["cpu_millis"] <= 64_000,
            "BUDGET_REJECTED")


def validate_plan(plan, expected_sha):
    """Validate declarations only; return a binding digest, never a permit."""
    try:
        fields(plan, {"schema", "evidence_kind", "preflight", "ci", "review", "scope",
                      "expected", "observed", "budget_status"})
        require(plan["schema"] == SCHEMA)
        require(plan["evidence_kind"] == "OFFLINE_FIXTURE", "EVIDENCE_CLASS_REFUSED")
        require(d.hex_value(expected_sha, 40), "SOURCE_MISMATCH")
        d.preflight(plan["preflight"], expected_sha)
        fields(plan["ci"], {"sha", "status", "receipt_sha256"}, "CI_REJECTED")
        ci = plan["ci"]
        require(ci["sha"] == expected_sha and ci["status"] == "SUCCESS"
                and d.hex_value(ci["receipt_sha256"], 64), "CI_REJECTED")
        review = plan["review"]
        fields(review, {"sha", "status", "receipt_sha256", "reviewer_sha256",
                        "implementer_sha256"}, "REVIEW_REJECTED")
        require(review["sha"] == expected_sha and review["status"] == "APPROVED"
                and all(d.hex_value(review[key], 64) for key in (
                    "receipt_sha256", "reviewer_sha256", "implementer_sha256"))
                and review["reviewer_sha256"] != review["implementer_sha256"], "REVIEW_REJECTED")
        _scope(plan["scope"])
        require(plan["budget_status"] == "DRAFT_NOT_APPROVED", "BUDGET_REJECTED")
        for key, kind in (("expected", "EXPECTED"), ("observed", "OBSERVED_OFFLINE")):
            fields(plan[key], {"kind", "resources"}, "RESOURCE_REJECTED")
            require(plan[key]["kind"] == kind, "EVIDENCE_CLASS_REFUSED")
            _resources(plan[key]["resources"], plan["preflight"])
        require(plan["expected"]["resources"] == plan["observed"]["resources"],
                "RESOURCE_REJECTED")
        raw = d.encode(plan)
        require(len(raw) <= MAX_PLAN_BYTES)
        return d.preflight_digest(plan)
    except Refused:
        raise
    except d.Rejected as exc:
        # The frozen validator owns its field semantics; never echo its input.
        code = "SOURCE_MISMATCH" if str(exc) == "SOURCE_MISMATCH" else "PLAN_REJECTED"
        raise Refused(code) from None
    except (TypeError, ValueError, KeyError, RecursionError, OverflowError):
        raise Refused("PLAN_REJECTED") from None


class Inspector(Protocol):
    def inspect(self, plan: dict, binding: str) -> dict: ...


class IdentityAttestor(Protocol):
    def attest(self, plan: dict, binding: str) -> dict: ...


class ApprovalVerifier(Protocol):
    def verify(self, plan: dict, binding: str) -> dict: ...


class BudgetGuard(Protocol):
    def check(self, plan: dict, binding: str) -> dict: ...


class ExecutorPort(Protocol):
    def create_and_claim(self, identity: dict) -> str: ...
    def execute_claimed_job(self, root_job_id: str) -> dict: ...


class RefusedInspector:
    def inspect(self, plan, binding):
        raise Refused("INSPECTION_REFUSED")


class RefusedIdentityAttestor:
    def attest(self, plan, binding):
        raise Refused("IDENTITY_REFUSED")


class RefusedApprovalVerifier:
    def verify(self, plan, binding):
        raise Refused("APPROVAL_REFUSED")


class RefusedBudgetGuard:
    def check(self, plan, binding):
        raise Refused("BUDGET_REFUSED")


class RefusedExecutor:
    def create_and_claim(self, identity):
        raise Refused("EXECUTION_NOT_AVAILABLE")

    def execute_claimed_job(self, root_job_id):
        raise Refused("EXECUTION_NOT_AVAILABLE")


class OfflineJournal:
    """Session-local replay protection for fixture proofs only; no live storage."""

    def __init__(self):
        self._used = set()

    def claim(self, run_uuid):
        require(d.uuid_value(run_uuid), "JOURNAL_REFUSED")
        require(run_uuid not in self._used, "RUN_UUID_REUSED")
        self._used.add(run_uuid)


class OfflineGuard:
    def __init__(self, *, inspector: Inspector | None = None,
                 attestor: IdentityAttestor | None = None,
                 approvals: ApprovalVerifier | None = None,
                 budgets: BudgetGuard | None = None, journal=None):
        self.inspector = inspector or RefusedInspector()
        self.attestor = attestor or RefusedIdentityAttestor()
        self.approvals = approvals or RefusedApprovalVerifier()
        self.budgets = budgets or RefusedBudgetGuard()
        self.journal = journal  # Explicit session scope, never a hidden fresh journal.

    def inspect(self, plan, expected_sha):
        plan = copy.deepcopy(plan)
        binding = validate_plan(plan, expected_sha)
        for port, method in ((self.inspector, "inspect"), (self.attestor, "attest"),
                             (self.approvals, "verify"), (self.budgets, "check")):
            try:
                # Ports get their own snapshot. A mutated argument cannot change
                # subsequent checks or the digest accepted by another verifier.
                receipt = getattr(port, method)(copy.deepcopy(plan), binding)
            except Refused:
                raise
            except Exception:
                raise Refused("PORT_REJECTED") from None
            fields(receipt, {"kind", "binding_sha256", "status"}, "PORT_REJECTED")
            require(receipt == dict(kind="OBSERVED_OFFLINE", binding_sha256=binding,
                                    status="OFFLINE_CHECKED"), "PORT_REJECTED")
        require(type(self.journal) is OfflineJournal, "JOURNAL_REFUSED")
        self.journal.claim(plan["preflight"]["run_uuid"])
        return dict(schema=SCHEMA, kind="OBSERVED_OFFLINE", status="OFFLINE_PROOF_ONLY",
                    binding_sha256=binding, budget_status="DRAFT_NOT_APPROVED", **GATES)


def cleanup_status(expected, observed):
    """Classification only. Even a match here grants no cleanup capability."""
    try:
        fields(expected, {"kind", "resources"}, "RESOURCE_REJECTED")
        fields(observed, {"kind", "resources"}, "RESOURCE_REJECTED")
        require(expected["kind"] == "EXPECTED" and observed["kind"] == "OBSERVED_OFFLINE")
        resources = expected["resources"]
        d.instance_identity(resources["instance"])
        _resources(resources, dict(expected_instance=resources["instance"],
                                  run_uuid=resources["lease_uuid"]))
        require(d.uuid_value(resources["lease_uuid"]))
        require(resources == observed["resources"])
        return "OFFLINE_OWNERSHIP_MATCH_ONLY"
    except (Refused, d.Rejected, TypeError, KeyError):
        return "CLEANUP_BLOCKED"


def check_offline_usage(limits, usage, *, phase):
    """Pure mock budget checkpoint; no process enforcement or approved budget.

    Root work stops at the cleanup reserve, cleanup at the overall deadline.
    No timeout extends a lease. CPU here is allocation in milli-CPUs; cumulative
    CPU time is a separate collector metric, not interchangeable with this cap.
    """
    fields(limits, {*LIMITS, "cpu_millis"}, "BUDGET_REJECTED")
    fields(usage, {"cpu_millis", "worker_bytes", "pg_bytes", "volume_bytes",
                   "output_bytes", "elapsed_ms"}, "BUDGET_REJECTED")
    require(phase in {"root", "cleanup"}, "BUDGET_REJECTED")
    require(all(type(v) is int and v >= 0 for v in usage.values()), "BUDGET_REJECTED")
    require(all(type(v) is int and v > 0 for v in limits.values()), "BUDGET_REJECTED")
    require(limits["cleanup_reserve_ms"] < limits["total_ms"], "BUDGET_REJECTED")
    for key in ("cpu_millis", "worker_bytes", "pg_bytes", "volume_bytes", "output_bytes"):
        require(usage[key] <= limits[key], "BUDGET_REJECTED")
    deadline = limits["total_ms"] - (limits["cleanup_reserve_ms"] if phase == "root" else 0)
    require(usage["elapsed_ms"] < deadline, "BUDGET_REJECTED")
    return "OFFLINE_BUDGET_CHECK_ONLY"


def execute():
    print("AUTHORIZATION_PENDING")
    return 2


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused("INPUT_REJECTED")


def main(argv=None):
    parser = _Parser(description=__doc__)
    parser.add_argument("command", choices=("plan", "inspect", "validate-offline", "execute"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--expected-implementation-sha")
    try:
        args = parser.parse_args(argv)
        if args.command == "execute":
            return execute()
        require(args.input is not None, "INPUT_REJECTED")
        parent = d.directory(args.input.parent)
        plan = decode_plan(d.read_file(parent / args.input.name, MAX_PLAN_BYTES))
        binding = validate_plan(plan, args.expected_implementation_sha)
        if args.command == "inspect":
            OfflineGuard().inspect(plan, args.expected_implementation_sha)
        # No user text or receipt content is exported, even on valid input.
        print(d.encode(dict(status="OFFLINE_DECLARATIONS_ONLY", kind="OBSERVED_OFFLINE",
                            binding_sha256=binding, **GATES)).decode().strip())
        return 0
    except Refused as exc:
        print(exc.code)
        return 2
    except (d.Rejected, OSError, ValueError, RecursionError):
        print("INPUT_REJECTED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
