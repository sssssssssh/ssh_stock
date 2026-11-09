"""Bounded offline typed row comparison, provenance and identity closure.

No SQL, ORM, environment, process or network APIs. Exporters supply typed Python
values, declared counts/columns, and either canonical streams or bounded batches.
"""

import hashlib
import math
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import zip_longest
from pathlib import Path
from uuid import UUID

from scripts.r1_real_root_protocol import BASELINE, Refused, canonical, parse_json, require

SCHEMA_PATH = "docs/acceptance/r1_business_compare_schema_v1.json"
SCHEMA_SHA256 = "f6be0a5de1ce46e30758039a3ab345a308ff96cb36f6ee86ec3ccdc39759f297"
VERSION = "r1.business-snapshot.v1"
PUBLIC_CODES = frozenset(
    [
        "R1_ACK_UNKNOWN",
        "R1_ARM",
        "R1_BLOCKED_UNMAPPED",
        "R1_BLOCKED_UNMAPPED_JSON_PATH",
        "R1_CANCEL_RELATION",
        "R1_CANDIDATE_COLUMNS",
        "R1_CANDIDATE_KEY",
        "R1_CANDIDATE_PUBLIC_MISMATCH",
        "R1_CANDIDATE_SCOPE_MISSING",
        "R1_CANDIDATE_SOURCE",
        "R1_CANDIDATE_TABLE",
        "R1_CLOCK",
        "R1_COLUMNS",
        "R1_COLUMN_DECLARATION",
        "R1_DANGLING_REFERENCE",
        "R1_DELIST_BOUNDARY",
        "R1_DEPTH",
        "R1_DUPLICATE_KEY",
        "R1_DUPLICATE_PK",
        "R1_ERROR_CODE",
        "R1_FIELDS",
        "R1_FIELD_TYPE",
        "R1_FIELD_VALUE",
        "R1_FLAGS",
        "R1_HEARTBEAT_ORDER",
        "R1_HEARTBEAT_UNCONFIRMED",
        "R1_IDENTITY_DOMAIN_COLLISION",
        "R1_IDENTITY_FIELDS",
        "R1_IDENTITY_NOT_BIJECTIVE",
        "R1_IDENTITY_TYPE",
        "R1_IDENTITY_UNMAPPED",
        "R1_INCOMPLETE_RESOURCE_LIMIT",
        "R1_INPUT_PLAN_MISMATCH",
        "R1_INPUT_REF",
        "R1_INVALID_JSON",
        "R1_INVALID_SNAPSHOT",
        "R1_JSON_COUNTS",
        "R1_JSON_DEPTH",
        "R1_JSON_REFERENCE",
        "R1_JSON_TYPE",
        "R1_JSON_VALIDATION",
        "R1_KEY_MISMATCH",
        "R1_LIFECYCLE",
        "R1_NONFINITE",
        "R1_NULL",
        "R1_ORDER",
        "R1_PUBLICATION_COPY",
        "R1_QUEUE_IDENTITY",
        "R1_REAL_EXECUTION_NOT_AUTHORIZED",
        "R1_REFERENCE",
        "R1_REFUSED",
        "R1_RESOURCE_BINDING",
        "R1_ROOT",
        "R1_ROOT_LEDGER_COUNT",
        "R1_ROOT_NOT_PUBLISHED",
        "R1_ROOT_REQUEST",
        "R1_ROWS",
        "R1_ROW_BUDGET",
        "R1_ROW_COUNT",
        "R1_SCHEMA_LINK",
        "R1_SCOPE_RANGE",
        "R1_SESSION_FACT",
        "R1_SESSION_IDENTITY",
        "R1_SESSION_ORDER",
        "R1_SESSION_ROLE",
        "R1_SIZE",
        "R1_SNAPSHOT_AUTHORITY",
        "R1_SNAPSHOT_FIELDS",
        "R1_SOURCE",
        "R1_SOURCE_CONTRACT_DRIFT",
        "R1_SOURCE_ROLE",
        "R1_TABLE_SET",
        "R1_TELEMETRY",
        "R1_TIMEZONE",
        "R1_TIME_ORDER",
        "R1_TOMBSTONE",
        "R1_TRANSITION",
        "R1_TYPE_MISMATCH",
        "R1_UNUSED_IDENTITY",
        "R1_VALUE_BUDGET",
        "R1_VALUE_MISMATCH",
        "R1_WRONG_OWNER_TOKEN",
        "R1_WRONG_ROOT",
    ]
)


def load_schema():
    path = Path(__file__).absolute().parents[1] / SCHEMA_PATH
    require(not path.is_symlink() and not path.is_junction(), "R1_SCHEMA_LINK")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SCHEMA_SHA256, "R1_SOURCE_CONTRACT_DRIFT")
    value = parse_json(raw)
    require(
        len(value["tables"]) == 37
        and sum(len(t["columns"]) for t in value["tables"].values()) == 520,
        "R1_BLOCKED_UNMAPPED",
    )
    return value


def typed(value, depth=0):
    """Lossless versioned encoding, including Decimal scale and float signed zero."""
    require(depth <= 32, "R1_DEPTH")
    kind = type(value)
    if value is None:
        return ["null"]
    if kind in (bool, int):
        return ["bool" if kind is bool else "int", value]
    if kind is str:
        require(len(value.encode("utf8")) <= 65536, "R1_VALUE_BUDGET")
        return ["text", value]
    if kind is bytes:
        require(len(value) <= 65536, "R1_VALUE_BUDGET")
        return ["bytes", value.hex()]
    if kind is UUID:
        return ["uuid", str(value)]
    if kind is Decimal:
        require(value.is_finite(), "R1_NONFINITE")
        return ["decimal", str(value)]
    if kind is float:
        require(math.isfinite(value), "R1_NONFINITE")
        return ["float", value.hex()]
    if kind is date:
        return ["date", value.isoformat()]
    if kind is datetime:
        require(value.tzinfo is not None and value.utcoffset() == timedelta(0), "R1_TIMEZONE")
        return ["datetime", value.isoformat(timespec="microseconds")]
    if kind in (list, tuple):
        require(len(value) <= 4096, "R1_VALUE_BUDGET")
        return ["list" if kind is list else "tuple", [typed(x, depth + 1) for x in value]]
    if kind is dict:
        require(len(value) <= 4096 and all(type(k) is str for k in value), "R1_JSON_TYPE")
        return ["dict", [[k, typed(value[k], depth + 1)] for k in sorted(value)]]
    raise Refused("R1_TYPE_MISMATCH")


def frame(value):
    raw = canonical(typed(value))
    require(len(raw) <= 262144, "R1_ROW_BUDGET")
    return len(raw).to_bytes(8, "big") + raw


def check_type(value, rule):
    if value is None:
        require(rule["nullable"], "R1_NULL")
        return
    expected = {
        "text": str,
        "int": int,
        "bool": bool,
        "float": float,
        "date": date,
        "datetime": datetime,
        "uuid": UUID,
        "json": dict,
        "array": tuple,
    }
    require(type(value) is expected[rule["type"]], "R1_TYPE_MISMATCH")
    typed(value)


class IdentityMap:
    def __init__(self, pairs):
        require(
            type(pairs) is dict and set(pairs) == {"job", "token", "scope", "events"},
            "R1_IDENTITY_FIELDS",
        )
        self.forward, self.reverse, self.used = {}, {}, set()
        count = 0
        for domain, entries in pairs.items():
            require(type(entries) is list, "R1_IDENTITY_TYPE")
            for entry in entries:
                require(type(entry) is tuple and len(entry) == 2, "R1_IDENTITY_TYPE")
                a, b = entry
                require(
                    type(a) is (datetime if domain == "events" else UUID) and type(b) is type(a),
                    "R1_IDENTITY_TYPE",
                )
                typed(a)
                typed(b)
                require(
                    (domain, a) not in self.forward and (domain, b) not in self.reverse,
                    "R1_IDENTITY_NOT_BIJECTIVE",
                )
                self.forward[domain, a], self.reverse[domain, b] = b, a
                count += 1
        require(count <= 20000, "R1_INCOMPLETE_RESOURCE_LIMIT")
        # A token or Scope UUID cannot masquerade as a Job entity.
        for side in (self.forward, self.reverse):
            ids = [v for d, v in side if d != "events"]
            require(len(ids) == len(set(ids)), "R1_IDENTITY_DOMAIN_COLLISION")

    def value(self, domain, value, side):
        if value is None:
            return None
        mapping = self.forward if side == "left" else self.reverse
        require((domain, value) in mapping, "R1_IDENTITY_UNMAPPED")
        self.used.add((side, domain, value))
        return value if side == "left" else mapping[domain, value]

    def closed(self):
        require(
            all(
                ("left", d, a) in self.used and ("right", d, b) in self.used
                for (d, a), b in self.forward.items()
            ),
            "R1_UNUSED_IDENTITY",
        )
        # Preserve temporal ordering as well as a bijection; no arbitrary reversal.
        events = sorted((a, b) for (d, a), b in self.forward.items() if d == "events")
        require(all(x[1] < y[1] for x, y in zip(events, events[1:], strict=False)), "R1_TIME_ORDER")


class SnapshotReader:
    def __init__(self, snapshot, schema, identity, side):
        require(
            type(snapshot) is dict
            and set(snapshot)
            == {
                "schema_version",
                "source_sha",
                "evidence_kind",
                "root_id",
                "input_ref",
                "lifecycle",
                "commit_ack",
                "tables",
                "counts",
                "columns",
                "ordering",
                "resource_binding",
            },
            "R1_SNAPSHOT_FIELDS",
        )
        require(
            snapshot["schema_version"] == VERSION
            and snapshot["source_sha"] == BASELINE
            and snapshot["evidence_kind"] == "SYNTHETIC_ONLY",
            "R1_SNAPSHOT_AUTHORITY",
        )
        require(type(snapshot["root_id"]) is UUID, "R1_ROOT")
        require(
            type(snapshot["input_ref"]) is str
            and len(snapshot["input_ref"]) == 64
            and all(c in "0123456789abcdef" for c in snapshot["input_ref"]),
            "R1_INPUT_REF",
        )
        require(
            snapshot["commit_ack"] in ("KNOWN", "UNKNOWN")
            and snapshot["lifecycle"] in ("SUCCESS", "FAILED", "CANCELLED", "UNKNOWN"),
            "R1_LIFECYCLE",
        )
        for field in ("tables", "counts", "columns"):
            require(
                type(snapshot[field]) is dict and set(snapshot[field]) == set(schema["tables"]),
                "R1_TABLE_SET",
            )
        require(snapshot["ordering"] in ("BOUNDED_UNORDERED", "CANONICAL_STREAM"), "R1_ORDER")
        resource = snapshot["resource_binding"]
        require(
            type(resource) is dict
            and set(resource) == {"evidence_kind", "pg_ref", "database_oid", "postmaster_start"},
            "R1_RESOURCE_BINDING",
        )
        require(
            resource["evidence_kind"] == "SYNTHETIC_ONLY"
            and resource["pg_ref"] == "offline-pg-resource"
            and type(resource["database_oid"]) is int
            and resource["database_oid"] > 0
            and type(resource["postmaster_start"]) is datetime,
            "R1_RESOURCE_BINDING",
        )
        typed(resource["postmaster_start"])
        self.snapshot, self.schema, self.identity, self.side = snapshot, schema, identity, side
        self.total_bytes = 0
        self.targets, self.references, self.critical, self.scope_groups = {}, set(), {}, Counter()
        self.raw_hashes, self.hashes = {}, {}
        self.public_rows = {}
        self.evidence = hashlib.sha256()
        self.partitions = {k: hashlib.sha256() for k in ("INPUT", "OUTPUT")}
        self.last_table = self.last_column = ""
        self.last_role = "UNKNOWN"
        self.reference_targets = {
            v["foreign_key"]
            for t in schema["tables"].values()
            for v in t["columns"].values()
            if v["foreign_key"]
        }
        self.reference_targets.update(schema["semantic_references"].values())

    def normalize_value(self, table, column, value, row):
        try:
            return self._normalize_value(table, column, value, row)
        except Refused as error:
            if not hasattr(error, "location"):
                error.location = (table, column)
                error.role_key = self.last_role
            raise

    def _normalize_value(self, table, column, value, row):
        rule = self.schema["tables"][table]["columns"][column]
        self.last_table, self.last_column = table, column
        check_type(value, rule)
        if value is None:
            return None
        if rule["policy"] == "UUID_BIJECTION":
            return self.identity.value(rule["domain"], value, self.side)
        if rule["policy"] == "TIMESTAMP_EVENT_MAPPING":
            # Seed Raw quality has fixed input timestamps, root quality is dynamic.
            if table == "data_quality_daily" and row["job_id"] is None:
                return value
            return self.identity.value("events", value, self.side)
        if rule["policy"] == "STRICT_JSON_SUBPATHS":
            return self.json_value(table, column, value, row)
        return value

    def job_ref(self, value):
        require(type(value) is str, "R1_JSON_REFERENCE")
        try:
            parsed = UUID(value)
        except (ValueError, TypeError):
            raise Refused("R1_JSON_REFERENCE") from None
        require(str(parsed) == value and parsed == self.snapshot["root_id"], "R1_WRONG_ROOT")
        return str(self.identity.value("job", parsed, self.side))

    def json_value(self, table, column, value, row):
        contract = self.schema["json_contracts"][table + "." + column]
        special = contract["special"]
        if special == "CANDIDATE_KEY":
            target = row["table_name"]
            require(target in self.schema["registry"], "R1_CANDIDATE_TABLE")
            keys = self.schema["registry_keys"].get(
                target, self.schema["tables"][target]["primary_key"]
            )
            require(len(value) == len(keys), "R1_CANDIDATE_KEY")
            for key, val in zip(keys, value, strict=True):
                check_type(val, self.schema["tables"][target]["columns"][key])
            return value
        if special == "CANDIDATE_ROW":
            target = row["table_name"]
            require(target in self.schema["registry"], "R1_CANDIDATE_TABLE")
            spec = self.schema["tables"][target]
            require(set(value) == set(spec["columns"]), "R1_CANDIDATE_COLUMNS")
            # Exporter must decode JSONB strings back to declared native types.
            clean = {c: self.normalize_value(target, c, v, value) for c, v in value.items()}
            keys = self.schema["registry_keys"].get(target, spec["primary_key"])
            require(tuple(value[c] for c in keys) == row["row_key"], "R1_CANDIDATE_KEY")
            if table == "data_publication_row" and column == "row_data" and "calc_run_id" in value:
                require(value["calc_run_id"] == row.get("source_id"), "R1_CANDIDATE_SOURCE")
            return clean
        require(
            type(value) is dict
            and set(value) <= set(contract["keys"])
            and set(contract["required"]) <= set(value),
            "R1_BLOCKED_UNMAPPED_JSON_PATH",
        )
        if special == "JOB_METADATA":
            return self.metadata(value)
        if special == "COUNTS":
            require(all(type(v) is int and v >= 0 for v in value.values()), "R1_JSON_COUNTS")
        if special == "VALIDATION":
            require(
                type(value["days"]) is list and type(value["pending_dirty_ids"]) is list,
                "R1_JSON_VALIDATION",
            )
            days = value["days"]
            require(
                all(type(d) is str and date.fromisoformat(d).isoformat() == d for d in days)
                and days == sorted(set(days)),
                "R1_JSON_VALIDATION",
            )
            require(all(type(x) is int for x in value["pending_dirty_ids"]), "R1_JSON_VALIDATION")
            self.references.update(("data_dirty_range.id", x) for x in value["pending_dirty_ids"])
        if special == "QUEUE_IDENTITY":
            require(all(type(v) is str for v in value.values()), "R1_QUEUE_IDENTITY")
        # Exact business JSON remains wholly present; finite primitive-only tree.
        canonical(value)
        return value

    def metadata(self, value):
        clean = dict(value)
        queue = value["queue_identity"]
        contract = self.schema["json_contracts"]["data_publication.identity"]
        require(
            type(queue) is dict
            and set(queue) == set(contract["keys"])
            and all(type(v) is str for v in queue.values()),
            "R1_QUEUE_IDENTITY",
        )
        require("policy_change" not in value, "R1_SOURCE_CONTRACT_DRIFT")
        require(value.get("execution_unconfirmed", False) is False, "R1_ACK_UNKNOWN")
        for key, expected in {
            "start": "2026-02-23",
            "end": "2026-02-24",
            "mode": "manual",
            "source": "manual",
            "evaluate_signals": False,
            "dirty_range_ids": [],
        }.items():
            require(
                type(value.get(key)) is type(expected) and value[key] == expected, "R1_ROOT_REQUEST"
            )
        if value.get("calc_run_id") is not None:
            clean["calc_run_id"] = self.job_ref(value["calc_run_id"])
        if "publication" in value:
            pub = value["publication"]
            require(
                type(pub) is dict
                and {"state", "identity"}
                <= set(pub)
                <= {"state", "identity", "parent_owned", "published_at", "row_counts"},
                "R1_BLOCKED_UNMAPPED_JSON_PATH",
            )
            clean["publication"] = {**pub, "identity": self.job_ref(pub["identity"])}
            if "published_at" in pub:
                require(type(pub["published_at"]) is datetime, "R1_TIMEZONE")
                clean["publication"]["published_at"] = self.identity.value(
                    "events", pub["published_at"], self.side
                )
        for key in ("calculation_execution", "calculation_progress"):
            if key in value:
                clean[key] = self.telemetry(key, value[key])
        if "database_sessions" in value:
            clean["database_sessions"] = self.sessions(value["database_sessions"])
        if "heartbeat_health" in value:
            clean["heartbeat_health"] = self.health(value["heartbeat_health"])
        # Identity mappings may contain typed datetime; use typed rather than json default=str.
        typed(clean)
        return clean

    def token_fingerprint(self):
        token = self.identity.value("token", self.critical_token(), self.side)
        return hashlib.sha256(str(token).encode()).hexdigest()[:16]

    def critical_token(self):
        # Snapshot rows are streams: use explicit mapped root token domain, not a reread.
        pairs = self.identity.forward if self.side == "left" else self.identity.reverse
        tokens = [v for d, v in pairs if d == "token"]
        require(len(tokens) == 1, "R1_WRONG_OWNER_TOKEN")
        return tokens[0]

    def utc_text(self, value):
        require(type(value) is str and len(value) <= 40, "R1_TIMEZONE")
        try:
            time = datetime.fromisoformat(value)
        except ValueError:
            raise Refused("R1_TIMEZONE") from None
        typed(time)
        return time

    def sessions(self, value):
        require(
            type(value) is dict
            and set(value)
            == {
                "schema",
                "root_job_id",
                "execution_fingerprint",
                "owner_fingerprint",
                "roles",
                "process_exit_proven",
                "status",
            },
            "R1_BLOCKED_UNMAPPED_JSON_PATH",
        )
        token = self.critical_token()
        fingerprint = hashlib.sha256(str(token).encode()).hexdigest()[:16]
        owner = hashlib.sha256(b"perf03-r1-synthetic").hexdigest()[:16]
        require(
            value["schema"] == "worker.sessions.v1"
            and value["process_exit_proven"] is False
            and value["execution_fingerprint"] == fingerprint
            and value["owner_fingerprint"] == owner
            and value["status"] == "SERVER_OBSERVED_NOT_EXIT_PROOF",
            "R1_SESSION_IDENTITY",
        )
        clean = {
            **value,
            "root_job_id": self.job_ref(value["root_job_id"]),
            "execution_fingerprint": self.token_fingerprint(),
            "roles": {},
        }
        roles = value["roles"]
        require(
            type(roles) is dict
            and bool(roles)
            and set(roles) <= {"main", "heartbeat", "diagnostic"},
            "R1_SESSION_ROLE",
        )
        resource = self.snapshot["resource_binding"]
        for role, observations in roles.items():
            require(
                type(observations) is dict and set(observations) == {"first", "latest"},
                "R1_SESSION_ROLE",
            )
            clean["roles"][role] = {}
            for event, fact in observations.items():
                require(
                    type(fact) is dict
                    and set(fact)
                    == {
                        "application_name",
                        "pid",
                        "backend_start",
                        "database_oid",
                        "postmaster_start",
                        "observed_at",
                    },
                    "R1_SESSION_FACT",
                )
                short = {"main": "m", "heartbeat": "h", "diagnostic": "d"}[role]
                expected = f"space2/{short}/{self.snapshot['root_id'].hex}/{fingerprint}"
                require(
                    fact["application_name"] == expected
                    and type(fact["pid"]) is int
                    and fact["pid"] > 0
                    and type(fact["database_oid"]) is int
                    and fact["database_oid"] == resource["database_oid"],
                    "R1_SESSION_IDENTITY",
                )
                post, backend, observed = (
                    self.utc_text(fact[k])
                    for k in ("postmaster_start", "backend_start", "observed_at")
                )
                require(
                    post == resource["postmaster_start"] and post <= backend <= observed,
                    "R1_SESSION_IDENTITY",
                )
                self.evidence.update(frame([role, event, fact]))
                # Keep first/latest order; hash every raw observation separately.
                clean["roles"][role][event] = {
                    "role": short,
                    "pg_ref": resource["pg_ref"],
                    "root": clean["root_job_id"],
                    "execution": clean["execution_fingerprint"],
                }
            require(
                self.utc_text(observations["first"]["observed_at"])
                <= self.utc_text(observations["latest"]["observed_at"]),
                "R1_SESSION_ORDER",
            )
        return clean

    def health(self, value):
        require(
            type(value) is dict
            and set(value)
            == {
                "schema",
                "observed_at",
                "state",
                "last_confirmed_at",
                "consecutive_failures",
                "unconfirmed_seconds",
                "phase",
                "sqlstate",
                "computation_success_proven",
                "execution_fingerprint",
            },
            "R1_BLOCKED_UNMAPPED_JSON_PATH",
        )
        fp = hashlib.sha256(str(self.critical_token()).encode()).hexdigest()[:16]
        require(
            value["schema"] == "worker.heartbeat.v1"
            and value["state"] == "COMMUNICATION_CONFIRMED"
            and value["phase"] == "COMPLETE"
            and value["computation_success_proven"] is False
            and value["sqlstate"] is None
            and value["execution_fingerprint"] == fp
            and type(value["consecutive_failures"]) is int
            and value["consecutive_failures"] == 0,
            "R1_HEARTBEAT_UNCONFIRMED",
        )
        require(
            type(value["unconfirmed_seconds"]) is float
            and math.isfinite(value["unconfirmed_seconds"])
            and value["unconfirmed_seconds"] >= 0,
            "R1_TELEMETRY",
        )
        observed, confirmed = (
            self.utc_text(value["observed_at"]),
            self.utc_text(value["last_confirmed_at"]),
        )
        require(confirmed <= observed, "R1_HEARTBEAT_ORDER")
        self.evidence.update(frame(["heartbeat_health", value]))
        clean = dict(
            value,
            execution_fingerprint=self.token_fingerprint(),
            unconfirmed_seconds={"observable": "finite_nonnegative_float"},
        )
        clean["observed_at"] = self.identity.value("events", observed, self.side)
        clean["last_confirmed_at"] = self.identity.value("events", confirmed, self.side)
        return clean

    def telemetry(self, name, value):
        require(type(value) is dict, "R1_BLOCKED_UNMAPPED_JSON_PATH")
        if name == "calculation_progress":
            allowed = {
                "name",
                "kind",
                "phase",
                "batch_index",
                "batch_count",
                "completed",
                "total",
                "completed_rows",
                "total_rows",
                "started_at",
                "operation_started_at",
                "updated_at",
                "advanced_at",
                "elapsed",
                "operation_elapsed",
                "elapsed_seconds",
                "operation_elapsed_seconds",
                "recent_events",
            }
        else:
            allowed = {
                "schema_version",
                "job_id",
                "root_job_id",
                "flags",
                "request",
                "source",
                "commit_status",
                "source_diagnostics",
                "reads",
                "driver_reads",
                "sql",
                "stages",
                "elapsed_seconds",
                "fetch_scope",
                "driver_fetch_scope",
                "timings_nested",
                "counter_scope",
            }
        require(set(value) <= allowed, "R1_BLOCKED_UNMAPPED_JSON_PATH")
        if name == "calculation_execution":
            # A partial observation may omit counters, but any identity supplied is fixed.
            if "schema_version" in value:
                require(value["schema_version"] == "biz-perf-01.execution.v1", "R1_TELEMETRY")
            if "flags" in value:
                require(
                    type(value["flags"]) is dict
                    and set(value["flags"])
                    == {
                        "factor_input_reuse_enabled",
                        "raw_preflight_batch_enabled",
                        "factor_cpu_optimization_enabled",
                    }
                    and all(v is False for v in value["flags"].values()),
                    "R1_FLAGS",
                )
            if "source" in value:
                require(
                    value["source"]
                    == {
                        "source_sha256": self.schema["runtime_source_sha256"],
                        "commit_sha": BASELINE,
                        "worktree": "CLEAN",
                    },
                    "R1_SOURCE_CONTRACT_DRIFT",
                )
            if "request" in value:
                require(
                    value["request"]
                    == {
                        "start": "2026-02-23",
                        "end": "2026-02-24",
                        "mode": "manual",
                    },
                    "R1_TELEMETRY",
                )
            if "source_diagnostics" in value:
                diagnostics = value["source_diagnostics"]
                expected_source = {
                    "source_sha256": self.schema["runtime_source_sha256"],
                    "commit_sha": BASELINE,
                    "worktree": "CLEAN",
                }
                require(
                    type(diagnostics) is dict
                    and set(diagnostics)
                    == {"worker_source", "observed_source", "git_metadata_changed"}
                    and diagnostics["worker_source"] == expected_source
                    and diagnostics["observed_source"] == expected_source
                    and diagnostics["git_metadata_changed"] is False,
                    "R1_SOURCE_CONTRACT_DRIFT",
                )
            for key, expected in {
                "commit_status": "LOCAL_HEAD_WITH_ACTUAL_SOURCE_DIGEST",
                "fetch_scope": "DELIVERED_PARTITIONS_NOT_WIRE_FETCH",
                "driver_fetch_scope": "SERVER_CURSOR_FETCHMANY_INCLUDING_PRIMING_AND_EOF",
                "timings_nested": True,
                "counter_scope": "ROOT_CUMULATIVE_INCLUDING_CHILDREN",
            }.items():
                if key in value:
                    require(
                        type(value[key]) is type(expected) and value[key] == expected,
                        "R1_TELEMETRY",
                    )
        else:
            require(
                {
                    "name",
                    "kind",
                    "phase",
                    "batch_index",
                    "batch_count",
                    "completed_rows",
                    "total_rows",
                    "updated_at",
                }
                <= set(value),
                "R1_TELEMETRY",
            )
        clean = {}
        for key, item in value.items():
            if key in ("job_id", "root_job_id"):
                clean[key] = self.job_ref(item)
            elif key in (
                "elapsed",
                "operation_elapsed",
                "elapsed_seconds",
                "operation_elapsed_seconds",
            ):
                require(type(item) is float and math.isfinite(item) and item >= 0, "R1_TELEMETRY")
                self.evidence.update(frame([name, key, item]))
                clean[key] = {"observable": "finite_nonnegative_float"}
            elif key.endswith("_at"):
                time = self.utc_text(item) if type(item) is str else item
                typed(time)
                clean[key] = self.identity.value("events", time, self.side) if time else None
            elif key in ("reads", "driver_reads", "sql", "stages"):
                require(type(item) is dict and len(item) <= 64, "R1_TELEMETRY")
                metrics = {}
                for label, counters in item.items():
                    require(label in self.schema["metric_labels"][key], "R1_TELEMETRY")
                    fields = {
                        "reads": {"rows", "fetches", "seconds"},
                        "driver_reads": {
                            "rows",
                            "calls",
                            "seconds",
                            "failures",
                            "incomplete_calls",
                        },
                        "sql": {"count", "seconds", "failures"},
                        "stages": {"kind", "calls", "seconds", "failures"},
                    }[key]
                    require(type(counters) is dict and set(counters) == fields, "R1_TELEMETRY")
                    require(
                        type(label) is str
                        and len(label) <= 80
                        and type(counters) is dict
                        and set(counters)
                        <= {
                            "rows",
                            "calls",
                            "count",
                            "fetches",
                            "seconds",
                            "failures",
                            "incomplete_calls",
                            "kind",
                        },
                        "R1_TELEMETRY",
                    )
                    require("seconds" in counters, "R1_TELEMETRY")
                    duration = counters["seconds"]
                    require(
                        type(duration) is float and math.isfinite(duration) and duration >= 0,
                        "R1_TELEMETRY",
                    )
                    self.evidence.update(frame([name, key, label, duration]))
                    metrics[label] = dict(
                        counters, seconds={"observable": "finite_nonnegative_float"}
                    )
                    for k, v in counters.items():
                        if k not in ("seconds", "kind"):
                            require(type(v) is int and v >= 0, "R1_TELEMETRY")
                clean[key] = metrics
            elif key == "recent_events":
                require(type(item) is list and len(item) <= 32, "R1_TELEMETRY")
                clean[key] = [self.telemetry("calculation_progress", e) for e in item]
            else:
                # No exemptions for unknown nested objects or financial fields.
                canonical(item)
                if name == "calculation_progress":
                    if key in {
                        "batch_index",
                        "batch_count",
                        "completed_rows",
                        "total_rows",
                        "completed",
                        "total",
                    }:
                        require(
                            item is None
                            and key in {"batch_count", "total_rows", "total"}
                            or type(item) is int
                            and item >= 0,
                            "R1_TELEMETRY",
                        )
                    else:
                        require(type(item) is str and len(item) <= 80, "R1_TELEMETRY")
                    if key == "phase":
                        require(
                            item
                            in {
                                "started",
                                "query",
                                "fetch",
                                "frame",
                                "compute",
                                "prepare",
                                "lookup_candidate",
                                "lookup_published",
                                "store",
                                "batch_complete",
                                "complete",
                                "failed",
                                "cancelled",
                            },
                            "R1_TELEMETRY",
                        )
                clean[key] = item
        return clean

    def rows(self, table):
        self.last_table, self.last_column = table, ""
        snapshot, spec = self.snapshot, self.schema["tables"][table]
        count = snapshot["counts"][table]
        require(type(count) is int and 0 <= count <= 2000000, "R1_ROW_COUNT")
        require(snapshot["columns"][table] == list(spec["columns"]), "R1_COLUMN_DECLARATION")
        source = snapshot["tables"][table]
        require(not isinstance(source, (str, bytes, dict)), "R1_ROWS")
        key_columns = spec["natural_key"]

        def row_pair(row):
            require(type(row) is dict and set(row) == set(spec["columns"]), "R1_COLUMNS")
            self.last_role = hashlib.sha256(frame(tuple(row[k] for k in key_columns))).hexdigest()[
                :16
            ]
            clean = {c: self.normalize_value(table, c, row[c], row) for c in spec["columns"]}
            sort_key = frame(tuple(clean[k] for k in key_columns))
            rb, cb = frame(row), frame(clean)
            self.total_bytes += len(rb) + len(cb)
            require(
                self.total_bytes <= self.schema["limits"]["total_bytes"],
                "R1_INCOMPLETE_RESOURCE_LIMIT",
            )
            return sort_key, row, clean, rb, cb

        if snapshot["ordering"] == "BOUNDED_UNORDERED":
            require(count <= 10000, "R1_INCOMPLETE_RESOURCE_LIMIT")
            pairs = []
            for n, row in enumerate(source):
                require(n < count, "R1_ROW_COUNT")
                pairs.append(row_pair(row))
            # Scope duplicates retain IDs; matching must validate the ordinal pairing.
            pairs.sort(
                key=lambda x: (
                    x[0],
                    frame(x[1]["id"]) if table == "data_publication_scope" else b"",
                )
            )
        else:
            pairs = (row_pair(row) for row in source)
        last = None
        n = 0
        raw_hash, normalized_hash = hashlib.sha256(), hashlib.sha256()
        raw_hash.update(frame([table, snapshot["columns"][table], count]))
        normalized_hash.update(frame([table, snapshot["columns"][table], count]))
        seen_pk = set() if key_columns != spec["primary_key"] else None
        for key, row, clean, rb, cb in pairs:
            require(last is None or key >= last, "R1_ORDER")
            require(last != key or spec["multiplicity"] == "MULTISET_ORDINAL", "R1_DUPLICATE_KEY")
            last = key
            if seen_pk is not None:
                pk = frame(tuple(row[k] for k in spec["primary_key"]))
                require(pk not in seen_pk, "R1_DUPLICATE_PK")
                seen_pk.add(pk)
                require(len(seen_pk) <= 20000, "R1_INCOMPLETE_RESOURCE_LIMIT")
            n += 1
            require(n <= count, "R1_ROW_COUNT")
            raw_hash.update(rb)
            normalized_hash.update(cb)
            partition = "INPUT" if spec["domain"] == "INPUT" else "OUTPUT"
            if table == "data_quality_daily" and row["job_id"] is not None:
                partition = "OUTPUT"
            self.partitions[partition].update(frame([table, clean]))
            self.collect(table, row, clean)
            yield key, clean
        require(n == count, "R1_ROW_COUNT")
        self.raw_hashes[table], self.hashes[table] = (
            raw_hash.hexdigest(),
            normalized_hash.hexdigest(),
        )

    def collect(self, table, row, clean):
        spec = self.schema["tables"][table]
        for col, value in row.items():
            target = table + "." + col
            if target in self.reference_targets:
                self.targets.setdefault(target, set()).add(value)
            fk = spec["columns"][col]["foreign_key"]
            if fk and value is not None:
                self.references.add((fk, value))
            semantic = self.schema["semantic_references"].get(table + "." + col)
            if semantic and value is not None:
                self.references.add((semantic, value))
            if spec["columns"][col]["domain"] == "job" and value is not None:
                require(value == self.snapshot["root_id"], "R1_WRONG_ROOT")
        require(
            sum(map(len, self.targets.values())) + len(self.references) <= 20000,
            "R1_INCOMPLETE_RESOURCE_LIMIT",
        )
        if table.startswith("data_publication") or table == "job_run":
            require(sum(map(len, self.critical.values())) < 10000, "R1_INCOMPLETE_RESOURCE_LIMIT")
            self.critical.setdefault(table, []).append(row)
        if table in self.schema["registry"]:
            keys = self.schema["registry_keys"].get(table, spec["primary_key"])
            key = frame(tuple(row[k] for k in keys))
            self.public_rows.setdefault(table, {})[key] = hashlib.sha256(frame(clean)).hexdigest()
            require(
                sum(map(len, self.public_rows.values())) <= 20000, "R1_INCOMPLETE_RESOURCE_LIMIT"
            )
        if table == "data_publication_scope":
            require(
                row["table_name"] in self.schema["registry"]
                and (
                    row["start_date"] is None
                    or row["end_date"] is None
                    or row["start_date"] <= row["end_date"]
                ),
                "R1_SCOPE_RANGE",
            )
            key = frame(tuple(row[c] for c in spec["natural_key"]))
            self.scope_groups[key] += 1
        if table == "stock_basic" and row["ts_code"] == "000002.SZ":
            require(
                row["list_date"] == date(2025, 1, 11)
                and row["delist_date"] == date(2025, 1, 26)
                and row["list_status"] == "D",
                "R1_DELIST_BOUNDARY",
            )

    def closure(self):
        for target, value in self.references:
            require(value in self.targets.get(target, set()), "R1_DANGLING_REFERENCE")
        jobs = self.critical.get("job_run", [])
        ledgers = self.critical.get("data_publication", [])
        require(len(jobs) == len(ledgers) == 1, "R1_ROOT_LEDGER_COUNT")
        job, ledger = jobs[0], ledgers[0]
        require(
            job["id"] == ledger["job_id"] == self.snapshot["root_id"]
            and job["execution_token"] == ledger["execution_token"]
            and job["worker_id"] == "perf03-r1-synthetic"
            and job["parent_job_id"] is None
            and job["depends_on_job_id"] is None,
            "R1_WRONG_OWNER_TOKEN",
        )
        require(
            job["job_type"] == "recalculate" and job["target_trade_date"] == date(2026, 2, 24),
            "R1_ROOT_REQUEST",
        )
        require(job["job_metadata"]["queue_identity"] == ledger["identity"], "R1_QUEUE_IDENTITY")
        lifecycle = self.snapshot["lifecycle"]
        require(self.snapshot["commit_ack"] == "KNOWN" and lifecycle != "UNKNOWN", "R1_ACK_UNKNOWN")
        require(
            job["status"] == lifecycle
            and (lifecycle, ledger["state"])
            in {
                ("SUCCESS", "PUBLISHED"),
                ("FAILED", "ABORTED"),
                ("CANCELLED", "ABORTED"),
            },
            "R1_ROOT_NOT_PUBLISHED",
        )
        if lifecycle == "CANCELLED":
            require(job["cancel_requested"] is True, "R1_CANCEL_RELATION")
        pub = job["job_metadata"].get("publication")
        if pub:
            require(
                pub["state"] == ledger["state"] and pub["identity"] == str(job["id"]),
                "R1_PUBLICATION_COPY",
            )
            if "published_at" in pub:
                require(pub["published_at"] == ledger["published_at"], "R1_PUBLICATION_COPY")
        for candidate in self.critical.get("data_publication_row", []):
            require(candidate["is_deleted"] == (candidate["row_data"] is None), "R1_TOMBSTONE")
            target = candidate["table_name"]
            key = frame(candidate["row_key"])
            if lifecycle == "SUCCESS":
                public_hash = self.public_rows.get(target, {}).get(key)
                if candidate["is_deleted"]:
                    require(public_hash is None, "R1_CANDIDATE_PUBLIC_MISMATCH")
                else:
                    clean = self.json_value(
                        "data_publication_row", "row_data", candidate["row_data"], candidate
                    )
                    require(
                        public_hash == hashlib.sha256(frame(clean)).hexdigest(),
                        "R1_CANDIDATE_PUBLIC_MISMATCH",
                    )
            scopes = self.critical.get("data_publication_scope", [])
            require(
                any(
                    scope["table_name"] == target
                    and scope["publication_id"] == candidate["publication_id"]
                    and scope["source_id"] == candidate["source_id"]
                    and (
                        candidate["trade_date"] is None
                        or (
                            scope["start_date"] is None
                            or scope["start_date"] <= candidate["trade_date"]
                        )
                        and (
                            scope["end_date"] is None
                            or scope["end_date"] >= candidate["trade_date"]
                        )
                    )
                    for scope in scopes
                ),
                "R1_CANDIDATE_SCOPE_MISSING",
            )
        for src in self.critical.get("data_publication_source", []):
            require(
                src["source_job_id"] == job["id"] and src["role"] in ("root", "child"),
                "R1_SOURCE_ROLE",
            )
        # A Root success requires no unknown/unconfirmed heartbeat fact.
        require(job["job_metadata"].get("execution_unconfirmed", False) is False, "R1_ACK_UNKNOWN")


def compare_snapshots(left, right, mappings):
    """Only an offline equality claim. One bounded sanitized error, never row values."""
    a = b = None
    try:
        schema = load_schema()
        ids = IdentityMap(mappings)
        a, b = (
            SnapshotReader(left, schema, ids, "left"),
            SnapshotReader(right, schema, ids, "right"),
        )
        require(
            left["input_ref"] == right["input_ref"] and left["lifecycle"] == right["lifecycle"],
            "R1_INPUT_PLAN_MISMATCH",
        )
        missing = object()
        for table in schema["tables"]:
            for x, y in zip_longest(a.rows(table), b.rows(table), fillvalue=missing):
                require(x is not missing and y is not missing, "R1_ROW_COUNT")
                require(x[0] == y[0], "R1_KEY_MISMATCH")
                for column in schema["tables"][table]["columns"]:
                    a.last_column = column
                    require(frame(x[1][column]) == frame(y[1][column]), "R1_VALUE_MISMATCH")
        a.closure()
        b.closure()
        ids.closed()
        return {
            "status": "OFFLINE_GOLDEN_EQUAL",
            "decision": "NO_GO",
            "equal": True,
            "real_pg_input_equal": False,
            "real_worker_output_equal": False,
            "performance_pass": False,
            "left_raw": a.raw_hashes,
            "right_raw": b.raw_hashes,
            "input_digest": a.partitions["INPUT"].hexdigest(),
            "output_digest": a.partitions["OUTPUT"].hexdigest(),
            "left_evidence": a.evidence.hexdigest(),
            "right_evidence": b.evidence.hexdigest(),
        }
    except Exception:
        # No repr(error), SQL, row text, URI, path or original key in public output.
        import sys

        error = sys.exception()
        code = (
            str(error)
            if isinstance(error, Refused) and str(error) in PUBLIC_CODES
            else "R1_INVALID_SNAPSHOT"
        )
        location = getattr(
            error, "location", (a.last_table if a else "", a.last_column if a else "")
        )
        table, column = location if type(location) is tuple and len(location) == 2 else ("", "")
        safe_tables = schema["tables"] if a else {}
        if type(table) is not str or table not in safe_tables:
            table, column = "", ""
        elif type(column) is not str or column not in safe_tables[table]["columns"]:
            column = ""
        role = getattr(error, "role_key", a.last_role if a else "UNKNOWN")
        if (
            type(role) is not str
            or len(role) != 16
            or any(x not in "0123456789abcdef" for x in role)
        ):
            role = "UNKNOWN"
        return {
            "status": "INCOMPLETE" if code == "R1_INCOMPLETE_RESOURCE_LIMIT" else "UNEQUAL",
            "equal": False,
            "decision": "NO_GO",
            "errors": [
                {
                    "code": code,
                    "table": table,
                    "column": column,
                    "role_key": role,
                }
            ],
            "real_pg_input_equal": False,
            "real_worker_output_equal": False,
            "performance_pass": False,
        }
