"""Small documentary completeness check. Declarations never grant authority.

assess is pure. Only review-offline reads one explicit local file, using the
existing trusted/stable ancestor reader; it neither opens evidence references
nor authenticates CI, signatures, approvals, resources or filesystem owners.
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from scripts import biz_perf_p1_04_diagnostic as d

SCHEMA = "biz-perf-p1-04.w05.documentary.v1"
MAX_BYTES = 64 * 1024
PHASES = ("create", "seed", "migrate_warmup", "root", "post", "cleanup")
LIMITS = dict(total_seconds=1200, cleanup_reserve_seconds=300,
              worker_bytes=3 * 1024**3, pg_bytes=4 * 1024**3,
              volume_bytes=10 * 1024**3, output_bytes=10 * 1024**2)
UNVERIFIED = ["CI_SOURCE_AND_RESULT", "INDEPENDENT_REVIEW", "RESOURCE_AND_OWNERSHIP",
              "FINGERPRINT_CONTENT", "OPERATOR_AND_WINDOW", "BUDGET_ENFORCEMENT",
              "EXECUTION_WIRING_AND_EVIDENCE", "CLEANUP_AUTHORITY"]
DECISIONS = ["NEW_ISOLATED_RESOURCE", "INDEPENDENT_SOURCE_REVIEW", "TIME_BOUNDARY_SIGNOFF",
             "RESOURCE_COST_AND_STOP_LIMITS", "SEPARATE_EXPLICIT_AUTHORIZATION"]


def result(blockers=(), excluded=()):
    return dict(schema=SCHEMA, mode="DOCUMENTARY_READINESS_REVIEW",
                status="BLOCKED" if blockers else "REVIEWABLE_ONLY",
                unverified_claims=list(UNVERIFIED), blockers=list(blockers),
                owner_decisions=list(DECISIONS) + (
                    ["SEPARATE_PREPARATION_BUDGET"] if excluded else []),
                excluded_steps=list(excluded), approved=False, execution_available=False,
                root_attempts=0, hotspot="NONE_PROVEN", b_gate="NOT_APPROVED",
                targeted_pg17_gate="NOT_APPROVED", authorization="AUTHORIZATION_PENDING",
                budget="DRAFT_NOT_APPROVED", next_action="HOLD_FOR_OWNER_REVIEW")


def need(condition, code="REQUEST_INVALID"):
    if not condition:
        raise ValueError(code)


def keys(value, names):
    need(type(value) is dict and set(value) == set(names))


def uint(value, maximum=2**63 - 1):
    return type(value) is int and 0 <= value <= maximum


def label(value):
    return (type(value) is str and 1 <= len(value) <= 160 and value == value.strip()
            and all(c.isprintable() for c in value))


def decode_request(raw):
    """Strict bounded JSON, including duplicate/nonfinite rejection, no IO."""
    need(type(raw) is bytes and len(raw) <= MAX_BYTES)
    try:
        return d.decode(raw)
    except (d.Rejected, ValueError, TypeError, RecursionError, OverflowError):
        raise ValueError("REQUEST_INVALID") from None


def assess(request, expected_sha):
    """Check presence/types and internal consistency, never declaration truth.

    A complete forged request is REVIEWABLE_ONLY with every trust claim still
    unverified. No signature, permit, approval flag, path lookup or live port.
    """
    try:
        need(len(d.encode(request)) <= MAX_BYTES)
        keys(request, {"schema", "implementation_sha", "run_uuid", "scope", "flags",
                       "resources", "budget", "timing", "people", "evidence",
                       "fingerprints", "ack"})
        need(request["schema"] == SCHEMA)
        need(d.hex_value(expected_sha, 40)
             and request["implementation_sha"] == expected_sha, "SHA_MISMATCH")
        run = request["run_uuid"]
        need(type(run) is str and d.uuid_value(run), "RUN_INVALID")
        scope = request["scope"]
        expected = dict(stocks=8, start="2025-01-01", end="2025-01-31",
                        roots=1, seed_history_days=900)
        keys(scope, expected)
        need(all(type(scope[k]) is type(v) and scope[k] == v
                 for k, v in expected.items()), "SCOPE_MISMATCH")
        keys(request["flags"], d.FLAGS)
        need(all(v is False for v in request["flags"].values()), "FLAGS_MISMATCH")
        resources = request["resources"]
        keys(resources, {"platform", "architecture", "pg_major", "new_instance", "exclusive",
                         "version_ref", "image_digest", "marker", "offline_system_identifier",
                         "online_system_identifier", "pgdata_ref", "volume_ref", "network_ref",
                         "cgroup_ref", "owner", "lease_uuid"})
        need(resources["platform"] == "Linux" and resources["architecture"] == "x86_64"
             and type(resources["pg_major"]) is int and resources["pg_major"] == 17
             and resources["new_instance"] is True and resources["exclusive"] is True,
             "RESOURCE_INVALID")
        need(resources["lease_uuid"] == run and d.uuid_value(resources["marker"]),
             "RUN_MISMATCH")
        physical = resources["offline_system_identifier"]
        need(type(physical) is str and re.fullmatch(r"[1-9][0-9]{0,19}", physical)
             and int(physical) < 2**64 and physical == resources["online_system_identifier"],
             "RESOURCE_INVALID")
        need(d.hex_value(resources["image_digest"], 64), "RESOURCE_INVALID")
        need(all(label(resources[k]) for k in ("version_ref", "pgdata_ref", "volume_ref",
                 "network_ref", "cgroup_ref", "owner")), "RESOURCE_INVALID")
        fingerprints = request["fingerprints"]
        keys(fingerprints, {"business", "config", "strategy", "dataset", "table_manifest"})
        need(all(d.hex_value(v, 64) for v in fingerprints.values()), "FINGERPRINT_INVALID")
        budget = request["budget"]
        keys(budget, {*LIMITS, "status", "cpu_millis", "disk_io_ref", "cost_limit_minor",
                      "cost_currency"})
        need(budget["status"] == "DRAFT_NOT_APPROVED"
             and all(type(budget[k]) is int and budget[k] == v for k, v in LIMITS.items())
             and uint(budget["cpu_millis"], 64000) and budget["cpu_millis"] > 0
             and uint(budget["cost_limit_minor"]) and label(budget["disk_io_ref"])
             and type(budget["cost_currency"]) is str
             and re.fullmatch(r"[A-Z]{3}", budget["cost_currency"]), "BUDGET_INVALID")
        timing = request["timing"]
        keys(timing, PHASES)
        excluded, before_cleanup = [], 0
        for phase in PHASES:
            row = timing[phase]
            keys(row, {"seconds", "in_total", "separate_limit_seconds"})
            need(uint(row["seconds"], 1200) and row["seconds"] > 0
                 and type(row["in_total"]) is bool
                 and uint(row["separate_limit_seconds"]), "TIMING_INVALID")
            if row["in_total"]:
                need(row["separate_limit_seconds"] == 0, "TIMING_INVALID")
                if phase != "cleanup":
                    before_cleanup += row["seconds"]
            else:
                need(phase in PHASES[:3]
                     and row["separate_limit_seconds"] >= row["seconds"], "TIMING_INVALID")
                excluded.append(phase)
        need(timing["root"]["seconds"] < 900 and before_cleanup < 900
             and timing["cleanup"]["seconds"] <= 300
             and before_cleanup + timing["cleanup"]["seconds"] <= 1200, "TIMING_INVALID")
        people = request["people"]
        keys(people, {"owner", "operator", "reviewer", "cleanup_owner", "cost_owner",
                      "window_start", "window_end", "stop_ref", "retention_ref"})
        need(all(label(v) for v in people.values()), "PEOPLE_INCOMPLETE")
        times = [datetime.fromisoformat(people[k]) for k in ("window_start", "window_end")]
        need(all(t.tzinfo is not None for t in times) and times[0] < times[1],
             "WINDOW_INVALID")
        need((times[1] - times[0]).total_seconds() >=
             1200 + sum(timing[p]["separate_limit_seconds"] for p in excluded),
             "WINDOW_INVALID")
        evidence = request["evidence"]
        keys(evidence, {"ci", "review", "resource"})
        for row in evidence.values():
            keys(row, {"source", "sha", "run_uuid", "reference"})
            need(label(row["source"]) and label(row["reference"]), "EVIDENCE_INCOMPLETE")
            need(row["sha"] == expected_sha, "SHA_MISMATCH")
            need(row["run_uuid"] == run, "RUN_MISMATCH")
        need(evidence["ci"]["source"] == "GITHUB_ACTIONS", "CI_SOURCE_UNKNOWN")
        need(type(request["ack"]) is str and request["ack"] == "NOT_STARTED",
             "MANUAL_STOP_REQUIRED")
        return result(excluded=excluded)
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as exc:
        code = str(exc) if type(exc) is ValueError else "REQUEST_INVALID"
        allowed = {"REQUEST_INVALID", "SHA_MISMATCH", "RUN_INVALID", "RUN_MISMATCH",
                   "SCOPE_MISMATCH", "FLAGS_MISMATCH", "RESOURCE_INVALID",
                   "FINGERPRINT_INVALID", "BUDGET_INVALID", "TIMING_INVALID",
                   "PEOPLE_INCOMPLETE", "WINDOW_INVALID", "EVIDENCE_INCOMPLETE",
                   "CI_SOURCE_UNKNOWN", "MANUAL_STOP_REQUIRED"}
        return result([code if code in allowed else "REQUEST_INVALID"])


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("ARGUMENTS_REJECTED")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if any(a == "execute" or a.split("=", 1)[0] in {"--allow", "--force", "--permit"}
           for a in argv):
        report = result(["AUTHORIZATION_PENDING"])
    else:
        try:
            parser = Parser(add_help=False, allow_abbrev=False)
            parser.add_argument("command", choices=["review-offline"])
            parser.add_argument("--input", required=True)
            parser.add_argument("--expected-sha", required=True)
            args = parser.parse_args(argv)
            path = Path(args.input)
            need(not args.input.startswith(("\\\\", "//")) and ".." not in path.parts
                 and path.name != ".env" and ":" not in path.name, "PATH_REJECTED")
            path = d.directory(path.parent) / path.name
            request = decode_request(d.read_file(path, MAX_BYTES))
            report = assess(request, args.expected_sha)
        except (ValueError, TypeError, OSError, d.Rejected):
            report = result(["INPUT_OR_ARGUMENTS_REJECTED"])
    sys.stdout.write(d.encode(report).decode("ascii"))
    return 0 if report["status"] == "REVIEWABLE_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
