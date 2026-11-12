"""Validate P1-04 fixture evidence offline. This module cannot start a root."""

import argparse
import hashlib
import json
import math
import os
import re
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from scripts.business_sql_snapshot import build
from scripts.perf03_lnx_w04a_offline_contract import Refused, parse_json

BASELINE = "391dca85cf9cc5b2e1858f4ea7fa19f98f52f079"
BUSINESS_SOURCE_SHA256 = "529d933c6997a6a5fb133c5ec2a59c5c06d4e78a087cfd06032011c2d806095a"
SCHEMA = "biz-perf-p1-04.root.v1"
FIXTURE = "OFFLINE_FIXTURE"
BOUNDARY = "create_claim_execute_then_independent_validation"
LEGACY_SCHEMA = "biz-perf-03-b.actions-once.v1"
MAX_RAW_BYTES = 8 * 1024**2
MAX_BUNDLE_BYTES = 10 * 1024**2
MAX_LINE_BYTES = 64 * 1024
MAX_EVENTS = 4096
MAX_ELAPSED_MS = 1_200_000
UNKNOWN = "UNKNOWN"
FLAGS = frozenset({
    "factor_input_reuse_enabled", "raw_preflight_batch_enabled",
    "factor_cpu_optimization_enabled", "ab_merge_read_enabled", "perf_diagnostics_enabled",
})
STAGES = frozenset({
    "recalculation.raw_prerequisites", "factors.stock_daily", "factors.adj_factor",
    "factors.stock_basic", "factors.trade_status", "factors.index_daily", "factors.compute",
    "candidate_lookup_batch", "candidate_store_batch", "publication.verify", "publish_inclusive",
})
TABLES = frozenset({
    "stock_trade_status_daily", "stock_factor_daily", "market_daily", "sector_factor_daily",
    "theme_factor_daily", "stock_state_daily", "stock_opportunity_daily", "strategy_signal",
    "signal_forward_eval", "data_quality_daily",
})
SQL_OPERATIONS = frozenset({
    "SELECT", "INSERT", "UPDATE", "DELETE", "WITH", "SET", "CREATE", "DROP", "LOCK", "SHOW",
    "SAVEPOINT", "RELEASE", "ROLLBACK", "COMMIT",
})
ROOT_STATES = {
    "SUCCESS": None, "FAILED": "ROOT_FAILED", "CANCELLED": "ROOT_CANCELLED",
    "UNKNOWN": "ROOT_UNKNOWN",
}
FAILURE_CODES = frozenset({"ROOT_FAILED", "ROOT_CANCELLED", "ROOT_UNKNOWN", "TIMEOUT", "OOM"})
PUBLICATION_STATES = frozenset({"PUBLISHED", "PREPARING", "ABORTED", "UNKNOWN"})


class Rejected(ValueError):
    """Only fixed diagnostic codes may cross the CLI boundary."""


def require(condition, code):
    if not condition:
        raise Rejected(code)


def fields(value, expected, code="EVIDENCE_INVALID"):
    require(type(value) is dict and value.keys() == expected, code)


def hex_value(value, length):
    return type(value) is str and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def uuid_value(value):
    try:
        identity = UUID(value)
        return str(identity) == value and identity.int != 0
    except (ValueError, TypeError, AttributeError):
        return False


def uint(value, upper=2**63 - 1):
    return type(value) is int and 0 <= value <= upper


def duration(value):
    return type(value) in (int, float) and 0 <= value <= MAX_ELAPSED_MS


def instance_identity(value):
    fields(value, {
        "scope", "host", "database", "pg_major", "marker", "system_identifier",
        "pgdata_sha256", "network_sha256", "owner_sha256",
    }, "INSTANCE_REJECTED")
    require(
        value["scope"] == "ISOLATED_SYNTHETIC"
        and value["host"] in ("127.0.0.1", "::1")
        and type(value["database"]) is str
        and re.fullmatch(r"v14_[0-9a-f]{32}_test", value["database"]) is not None
        and type(value["pg_major"]) is int and value["pg_major"] == 17
        and uuid_value(value["marker"])
        and type(value["system_identifier"]) is str
        and re.fullmatch(r"[1-9][0-9]{0,19}", value["system_identifier"]) is not None
        and int(value["system_identifier"]) < 2**64
        and all(hex_value(value[k], 64) for k in (
            "pgdata_sha256", "network_sha256", "owner_sha256",
        )), "INSTANCE_REJECTED",
    )


def preflight(value, expected_sha):
    if type(value) is dict and value.get("schema") == LEGACY_SCHEMA:
        raise Rejected("LEGACY_PROTOCOL_REFUSED")
    fields(value, {
        "schema_version", "evidence_kind", "design_baseline_sha",
        "measurement_implementation_sha", "business_source_sha256", "worktree", "run_uuid",
        "run_attempt", "stocks", "months", "dataset_sha256", "strategy_sha256",
        "env_identity_digest", "resource_budget_id", "flags", "expected_instance",
        "observed_instance",
    }, "PREFLIGHT_REJECTED")
    require(value["schema_version"] == SCHEMA and value["evidence_kind"] == FIXTURE,
            "EVIDENCE_CLASS_REFUSED")
    require(
        value["design_baseline_sha"] == BASELINE and hex_value(expected_sha, 40)
        and value["measurement_implementation_sha"] == expected_sha
        and value["worktree"] == "CLEAN"
        and value["business_source_sha256"] == BUSINESS_SOURCE_SHA256, "SOURCE_MISMATCH",
    )
    require(uuid_value(value["run_uuid"]) and all(hex_value(value[k], 64) for k in (
        "dataset_sha256", "strategy_sha256", "env_identity_digest", "resource_budget_id",
    )), "IDENTITY_REJECTED")
    require(type(value["run_attempt"]) is int and value["run_attempt"] == 1,
            "ONE_ATTEMPT_CONSUMED")
    require(type(value["stocks"]) is int and value["stocks"] == 8
            and type(value["months"]) is int and value["months"] == 1, "PROTOCOL_REFUSED")
    fields(value["flags"], FLAGS, "FLAG_MISMATCH")
    require(all(flag is False for flag in value["flags"].values()), "FLAG_MISMATCH")
    instance_identity(value["expected_instance"])
    instance_identity(value["observed_instance"])
    require(value["expected_instance"] == value["observed_instance"], "INSTANCE_REJECTED")
    return value


def directory(path):
    path = Path(path)
    require(".." not in path.parts, "PATH_REJECTED")
    path = path.absolute()
    for part in (path, *path.parents):
        info = part.lstat()
        require(stat.S_ISDIR(info.st_mode) and not part.is_junction(), "PATH_REJECTED")
    return path


def read_file(path, limit):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not path.is_junction()
            and before.st_nlink == 1, "PATH_REJECTED")
    require(before.st_size <= limit, "SIZE_LIMIT")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        require(os.path.samestat(before, opened) and stat.S_ISREG(opened.st_mode),
                "PATH_REJECTED")
        raw = stream.read(limit + 1)
    after = path.lstat()
    require(len(raw) <= limit, "SIZE_LIMIT")
    require(os.path.samestat(opened, after) and after.st_nlink == 1
            and before.st_size == len(raw) == after.st_size
            and before.st_mtime_ns == after.st_mtime_ns, "PATH_REJECTED")
    return raw


def decode(raw):
    try:
        return parse_json(raw)
    except Refused:
        raise Rejected("EVIDENCE_INVALID") from None


def encode(value):
    return (json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode("ascii")


def preflight_digest(contract):
    return hashlib.sha256(encode(contract)).hexdigest()


def sync_write(stream, raw):
    if stream.write(raw) != len(raw):
        raise OSError("short write")
    stream.flush()
    os.fsync(stream.fileno())


def sync_directory(path):
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def publish(path, value):
    raw = encode(value)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".pending-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            sync_write(stream, raw)
        except BaseException:
            stream.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.link(temporary, path)  # Atomic publication without replacing a prior receipt.
    finally:
        temporary.unlink(missing_ok=True)
    sync_directory(path.parent)
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def publish_member(destination, manifest, name, value, *, raw_bytes=0):
    other_bytes = sum(item["bytes"] for item in manifest.values())
    require(other_bytes + raw_bytes + len(encode(value)) <= MAX_BUNDLE_BYTES, "SIZE_LIMIT")
    manifest[name] = publish(destination / name, value)


COMMON = {"seq", "event_kind", "run_uuid", "root_job_id", "utc", "elapsed_ms"}
EVENT_FIELDS = {
    "root_started": {"preflight_sha256"},
    "worker_started": set(),
    "stage": {"stage_name", "started_ms", "instrumented", "coverage_reason",
              "sql_execute_ms", "sql_calls", "fetch_observed_ms", "fetched_rows"},
    "root_frozen": {"sql_counts", "process_cpu_ms", "rss_peak_bytes",
                    "fetch_observed_ms", "fetched_rows"},
    "post_root_validation": {"job_status", "publication_state", "quality_verified",
                             "no_candidate_leak", "atomic_publication_verified", "tables_sha256",
                             "source_mismatches"},
    "cleanup": {"cleanup_status", "instance"},
    "failure": {"failure_code"},
}
NEXT_EVENT = {
    "INITIAL": {"root_started"},
    "root_started": {"worker_started", "failure"},
    "worker_started": {"stage", "root_frozen", "failure"},
    "stage": {"stage", "root_frozen", "failure"},
    "root_frozen": {"post_root_validation", "failure"},
    "post_root_validation": {"cleanup", "failure"},
    "cleanup": set(),
    "failure": set(),
}


def observation(event, time_keys, count_keys):
    require(all(event[k] == UNKNOWN or duration(event[k]) for k in time_keys)
            and all(event[k] == UNKNOWN or uint(event[k]) for k in count_keys),
            "EVIDENCE_INVALID")


class Replay:
    def __init__(self, contract):
        self.contract = contract
        self.seq = 0
        self.phase = "INITIAL"
        self.root_id = None
        self.started = self.worker_started = self.elapsed = 0
        self.utc = None
        self.stages = []
        self.snapshot = self.post = None
        self.failure = None

    def binding(self):
        return {
            **{key: self.contract[key] for key in (
                "schema_version", "evidence_kind", "design_baseline_sha",
                "measurement_implementation_sha", "business_source_sha256", "worktree",
                "run_uuid", "run_attempt", "dataset_sha256", "strategy_sha256",
                "env_identity_digest", "resource_budget_id", "flags",
            )},
            "root_job_id": self.root_id,
            "measurement_boundary": BOUNDARY,
        }

    def accept(self, event):
        require(type(event) is dict, "EVIDENCE_INVALID")
        kind = event.get("event_kind")
        require(type(kind) is str and kind in EVENT_FIELDS, "EVIDENCE_INVALID")
        fields(event, COMMON | EVENT_FIELDS[kind])
        if self.root_id is not None:
            require(kind != "root_started" and event["root_job_id"] == self.root_id,
                    "ONE_ATTEMPT_CONSUMED")
        require(kind in NEXT_EVENT[self.phase], "EVIDENCE_INVALID")
        require(type(event["seq"]) is int and event["seq"] == self.seq + 1
                and self.seq < MAX_EVENTS and event["run_uuid"] == self.contract["run_uuid"]
                and uuid_value(event["root_job_id"]), "EVIDENCE_INVALID")
        require(duration(event["elapsed_ms"]) and event["elapsed_ms"] >= self.elapsed,
                "EVIDENCE_INVALID")
        stamp = event["utc"]
        require(type(stamp) is str and re.fullmatch(
            r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z", stamp,
        ), "EVIDENCE_INVALID")
        try:
            utc = datetime.fromisoformat(stamp)
        except ValueError:
            raise Rejected("EVIDENCE_INVALID") from None
        require(utc.utcoffset() == UTC.utcoffset(utc)
                and (self.utc is None or utc >= self.utc), "EVIDENCE_INVALID")

        elapsed = event["elapsed_ms"]
        if kind == "root_started":
            require(event["preflight_sha256"] == preflight_digest(self.contract),
                    "IDENTITY_REJECTED")
            self.root_id, self.started = event["root_job_id"], elapsed
        elif kind == "worker_started":
            self.worker_started = elapsed
        elif kind == "stage":
            self.add_stage(event)
        elif kind == "root_frozen":
            self.freeze(event)
        elif kind == "post_root_validation":
            self.validate_business(event)
        elif kind == "cleanup":
            self.validate_cleanup(event)
        elif kind == "failure":
            require(type(event["failure_code"]) is str and event["failure_code"] in FAILURE_CODES,
                    "EVIDENCE_INVALID")
            self.failure = self.failure or event["failure_code"]
        self.seq, self.phase, self.elapsed, self.utc = event["seq"], kind, elapsed, utc

    def add_stage(self, event):
        name, started = event["stage_name"], event["started_ms"]
        require(type(name) is str and name in STAGES and type(event["instrumented"]) is bool
                and duration(started) and self.worker_started <= started <= event["elapsed_ms"],
                "EVIDENCE_INVALID")
        metrics = ("sql_execute_ms", "fetch_observed_ms", "sql_calls", "fetched_rows")
        observation(event, metrics[:2], metrics[2:])
        instrumented = event["instrumented"]
        if instrumented:
            require(event["coverage_reason"] == "RECORDED", "EVIDENCE_INVALID")
        else:
            require(event["coverage_reason"] in ("NOT_INSTRUMENTED", "NOT_APPLICABLE")
                    and all(event[k] == UNKNOWN for k in metrics), "EVIDENCE_INVALID")
        self.stages.append(dict(
            stage_name=name, stage_inclusive_ms=event["elapsed_ms"] - started
            if instrumented else UNKNOWN, instrumented=instrumented,
            coverage_reason=event["coverage_reason"], **{k: event[k] for k in metrics},
        ))

    def freeze(self, event):
        elapsed = event["elapsed_ms"]
        observation(event, ("process_cpu_ms", "fetch_observed_ms"),
                    ("rss_peak_bytes", "fetched_rows"))
        require(elapsed > self.started and type(event["sql_counts"]) is dict
                and event["sql_counts"].keys() <= SQL_OPERATIONS,
                "EVIDENCE_INVALID")
        try:
            counts = build(event["sql_counts"],
                           head_sha=self.contract["measurement_implementation_sha"],
                           root_job_id=self.root_id, started=self.started / 1000,
                           ended=elapsed / 1000)
        except (TypeError, ValueError):
            raise Rejected("EVIDENCE_INVALID") from None
        self.snapshot = {
            **self.binding(),
            "root_elapsed_ms": elapsed - self.started,
            "execute_claimed_job_ms": elapsed - self.worker_started,
            "root_ended_ms": elapsed,
            "sql_snapshot": counts,
            **{key: event[key] for key in (
                "process_cpu_ms", "rss_peak_bytes", "fetch_observed_ms", "fetched_rows",
            )},
        }

    def validate_business(self, event):
        status, publication = event["job_status"], event["publication_state"]
        tables = event["tables_sha256"]
        checks = ("quality_verified", "no_candidate_leak", "atomic_publication_verified")
        require(type(status) is str and status in ROOT_STATES
                and type(publication) is str and publication in PUBLICATION_STATES
                and type(tables) is dict and tables.keys() <= TABLES
                and all(hex_value(v, 64) for v in tables.values())
                and all(type(event[k]) is bool for k in checks)
                and (event["source_mismatches"] == UNKNOWN or uint(event["source_mismatches"])),
                "EVIDENCE_INVALID")
        self.post = {**self.binding(),
                     **{k: event[k] for k in EVENT_FIELDS["post_root_validation"]},
                     "post_root_validation_ms": event["elapsed_ms"]
                     - self.snapshot["root_ended_ms"]}
        self.failure = ROOT_STATES[status]
        if status == "SUCCESS" and not (
            publication == "PUBLISHED" and tables.keys() == TABLES
            and all(event[k] for k in checks)
            and event["source_mismatches"] == 0
        ):
            self.failure = "BUSINESS_VALIDATION_FAILED"

    def validate_cleanup(self, event):
        require(event["cleanup_status"] in ("COMPLETE", "BLOCKED"), "EVIDENCE_INVALID")
        try:
            instance_identity(event["instance"])
        except Rejected:
            raise Rejected("CLEANUP_BLOCKED") from None
        if (event["cleanup_status"] == "BLOCKED"
                or event["instance"] != self.contract["expected_instance"]):
            self.failure = "CLEANUP_BLOCKED"

    def summary(self):
        if self.failure is not None:
            raise Rejected(self.failure)
        require(self.phase == "cleanup" and self.snapshot["sql_snapshot"]["total"] > 0
                and any(row["instrumented"] for row in self.stages),
                "EVIDENCE_INCOMPLETE")
        cpu = self.snapshot["process_cpu_ms"]
        # The ratio is wall/CPU. A zero CPU sample has no meaningful denominator.
        wall_per_cpu = (self.snapshot["root_elapsed_ms"] / cpu
                        if cpu not in (UNKNOWN, 0) else "UNDEFINED")
        if type(wall_per_cpu) is float and not math.isfinite(wall_per_cpu):
            wall_per_cpu = "UNDEFINED"
        observed = {row["stage_name"] for row in self.stages}
        wall = self.snapshot["root_elapsed_ms"]
        by_stage = {}
        for row in self.stages:
            if row["instrumented"]:
                name = row["stage_name"]
                by_stage[name] = by_stage.get(name, 0) + row["stage_inclusive_ms"]
        ranking = sorted(by_stage, key=lambda name: (-by_stage[name], name))[:3]
        return dict(
            **self.binding(), evidence_complete=True,
            status="OFFLINE_VALIDATED", hotspot_decision="NONE_PROVEN",
            production_read_authorized=False, root_attempts=0,
            wall_per_cpu=wall_per_cpu, aggregation="INCLUSIVE_DO_NOT_SUM",
            fixture_stage_top3=[dict(stage_name=name, stage_inclusive_ms=by_stage[name],
                                    stage_to_root_ratio=by_stage[name] / wall)
                                for name in ranking],
            stage_observations=self.stages + [
                dict(stage_name=name, instrumented=False, coverage_reason="NOT_INSTRUMENTED",
                     stage_inclusive_ms=UNKNOWN, sql_execute_ms=UNKNOWN, sql_calls=UNKNOWN,
                     fetch_observed_ms=UNKNOWN, fetched_rows=UNKNOWN)
                for name in sorted(STAGES - observed)
            ],
        )


def validate_bundle(input_dir, output_dir, expected_sha):
    """Preserve only accepted fixture events; independent report generation comes last."""
    source = directory(input_dir)
    destination = Path(output_dir)
    require(destination.name not in ("", ".", ".."), "PATH_REJECTED")
    parent = directory(destination.parent)
    destination = parent / destination.name
    require(re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", destination.name)
            and not destination.name.endswith(".")
            and not destination.is_relative_to(Path(__file__).resolve().parents[1]),
            "PATH_REJECTED")
    try:
        destination.mkdir(mode=0o700)
    except FileExistsError:
        raise Rejected("OUTPUT_EXISTS") from None
    replay = None
    durable_seq = 0
    try:
        contract = preflight(decode(read_file(source / "preflight.json", MAX_LINE_BYTES)),
                             expected_sha)
        replay = Replay(contract)
        manifest = {"preflight.json": publish(destination / "preflight.json", contract)}
        incoming = read_file(source / "events.jsonl", MAX_RAW_BYTES)
        raw_path = destination / "raw_events.jsonl"
        digest, size = hashlib.sha256(), 0
        with raw_path.open("xb") as stream:
            sync_directory(destination)
            for line in incoming.splitlines(keepends=True):
                require(len(line) <= MAX_LINE_BYTES and line.endswith(b"\n"), "EVIDENCE_INVALID")
                event = decode(line)
                replay.accept(event)
                sync_write(stream, line)
                digest.update(line)
                size += len(line)
                durable_seq = replay.seq
                if replay.phase == "root_frozen":
                    publish_member(destination, manifest, "root_snapshot.json", replay.snapshot,
                                   raw_bytes=size)
                elif replay.phase == "post_root_validation":
                    publish_member(destination, manifest, "post_root_validation.json", replay.post,
                                   raw_bytes=size)
        saved = read_file(raw_path, MAX_RAW_BYTES)
        require(len(saved) == size and hashlib.sha256(saved).digest() == digest.digest(),
                "EVIDENCE_INCOMPLETE")
        manifest[raw_path.name] = {"bytes": size, "sha256": digest.hexdigest()}
        for name, expected in manifest.items():
            if name == raw_path.name:
                continue
            data = read_file(destination / name, MAX_RAW_BYTES)
            require(len(data) == expected["bytes"]
                    and hashlib.sha256(data).hexdigest() == expected["sha256"],
                    "EVIDENCE_INCOMPLETE")
        result = replay.summary()
        publish_member(destination, manifest, "summary.json", result)
        require(sum(item["bytes"] for item in manifest.values()) + len(encode(manifest))
                <= MAX_BUNDLE_BYTES, "SIZE_LIMIT")
        publish(destination / "integrity.json", manifest)  # Completion marker, written last.
        return result
    except Exception as error:
        code = str(error) if isinstance(error, Rejected) else "EVIDENCE_INCOMPLETE"
        failure = dict(schema_version=SCHEMA, evidence_kind=FIXTURE, evidence_complete=False,
                       status=code, hotspot_decision="NONE_PROVEN", root_attempts=0,
                       last_durable_seq=durable_seq)
        if replay:
            failure.update(replay.binding())
        if replay and replay.post:
            failure.update(job_status=replay.post["job_status"],
                           publication_state=replay.post["publication_state"])
        try:
            publish(destination / "failure_receipt.json", failure)
        except OSError:
            pass  # A failed volume may prevent a receipt; the caller still gets a failure.
        raise Rejected(code) from None


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "CLI_ARGUMENTS_REJECTED\n")


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    offline = modes.add_parser("validate", help="validate a local offline fixture")
    offline.add_argument("--input-dir", required=True, type=Path)
    offline.add_argument("--output-dir", required=True, type=Path)
    offline.add_argument("--expected-implementation-sha", required=True)
    modes.add_parser("execute", help="reserved live mode (closed)")
    args = parser.parse_args(argv)
    if args.mode == "execute":
        print("AUTHORIZATION_PENDING")
        return 2
    try:
        result = validate_bundle(args.input_dir, args.output_dir, args.expected_implementation_sha)
    except Rejected as error:
        print(error)
        return 1
    except OSError:
        print("PATH_REJECTED")
        return 1
    print(result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
