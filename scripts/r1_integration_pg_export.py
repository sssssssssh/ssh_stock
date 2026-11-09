"""Bounded DB-API PG exporter; full columns, repeatable read, native typed rows.

Only fake exports may enter the frozen synthetic comparator. Real typed exports
remain a distinct evidence class; the future real comparator bridge is denied.
No data files are written, and SQL/parameters/row contents are never logged.
"""

import math
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from time import monotonic
from uuid import UUID

from scripts.r1_business_snapshot_contract import (
    check_type,
    compare_snapshots,
    frame,
    load_schema,
    typed,
)
from scripts.r1_integration_evidence import sha, source_identity
from scripts.r1_integration_pg_guard import BEGIN_SQL
from scripts.r1_real_root_protocol import Refused, require

CATALOG_SQL = """SELECT c.relname, a.attname, format_type(a.atttypid,a.atttypmod),
 NOT a.attnotnull,
 COALESCE((SELECT array_position(k.conkey,a.attnum) FROM pg_constraint k
   WHERE k.conrelid=c.oid AND k.contype='p'),0),
 (SELECT fc.relname || '.' || fa.attname FROM pg_constraint k
  JOIN pg_class fc ON fc.oid=k.confrelid
  JOIN pg_attribute fa ON fa.attrelid=fc.oid
    AND fa.attnum=k.confkey[array_position(k.conkey,a.attnum)]
  WHERE k.conrelid=c.oid AND k.contype='f' AND a.attnum=ANY(k.conkey))
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 JOIN pg_attribute a ON a.attrelid=c.oid
 WHERE n.nspname='public' AND c.relkind='r' AND c.relname=ANY(%s)
 AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attname"""
SNAPSHOT_SQL = "SELECT pg_current_snapshot()::text"
TIMEOUT_SQL = "SELECT set_config('statement_timeout', %s, true)"


def expected_catalog():
    result = []
    for table, spec in load_schema()["tables"].items():
        for col, rule in spec["columns"].items():
            declaration = rule["source"]["declaration"]
            string = re.search(r"String\((\d+)\)", declaration)
            sql_type = (
                ("character varying(" + string[1] + ")")
                if string
                else {
                    "text": "text",
                    "int": "bigint" if "BigInteger" in declaration else "integer",
                    "float": "double precision",
                    "bool": "boolean",
                    "uuid": "uuid",
                    "date": "date",
                    "datetime": "timestamp with time zone",
                    "json": "jsonb",
                    "array": "jsonb",
                }[rule["type"]]
            )
            pk = spec["primary_key"].index(col) + 1 if col in spec["primary_key"] else 0
            result.append((table, col, sql_type, rule["nullable"], pk, rule["foreign_key"]))
    return sorted(result)


def decode_native(value, rule, *, json_cell=False):
    """Native DB values are strict. Only declared JSON subcolumns decode strings."""
    if value is None:
        require(rule["nullable"], "BLOCKED_UNMAPPED")
        return None
    kind = rule["type"]
    try:
        if json_cell and type(value) is str:
            if kind == "uuid":
                parsed = UUID(value)
                require(str(parsed) == value, "BLOCKED_UNMAPPED")
                value = parsed
            elif kind == "date":
                parsed = date.fromisoformat(value)
                require(parsed.isoformat() == value, "BLOCKED_UNMAPPED")
                value = parsed
            elif kind == "datetime":
                value = datetime.fromisoformat(value)
        if kind == "array":
            require(type(value) in (tuple, list), "BLOCKED_UNMAPPED")
            value = tuple(value)
        if kind == "decimal":
            require(type(value) is Decimal and value.is_finite(), "BLOCKED_UNMAPPED")
            require(
                -value.as_tuple().exponent == rule["scale"]
                and len(value.as_tuple().digits) <= rule["precision"],
                "DECIMAL_SCALE",
            )
            return value
        check_type(value, rule)
        if type(value) is float:
            require(math.isfinite(value), "BLOCKED_UNMAPPED")
        if type(value) is datetime:
            require(value.utcoffset() == timedelta(0), "BLOCKED_UNMAPPED")
        return value
    except (ValueError, TypeError, OverflowError):
        raise Refused("BLOCKED_UNMAPPED") from None


def decode_row(table, raw, schema):
    spec = schema["tables"][table]
    require(type(raw) is dict and set(raw) == set(spec["columns"]), "SCHEMA_DRIFT")
    row = {c: decode_native(raw[c], rule) for c, rule in spec["columns"].items()}
    for col, rule in spec["columns"].items():
        if rule["type"] not in ("json", "array") or row[col] is None:
            continue
        contract = schema["json_contracts"][table + "." + col]
        special = contract["special"]
        value = row[col]
        if special in ("CANDIDATE_KEY", "CANDIDATE_ROW"):
            target = row["table_name"]
            require(target in schema["registry"], "BLOCKED_UNMAPPED")
            target_spec = schema["tables"][target]
            keys = schema["registry_keys"].get(target, target_spec["primary_key"])
            if special == "CANDIDATE_KEY":
                require(len(value) == len(keys), "CANDIDATE_KEY")
                row[col] = tuple(
                    decode_native(v, target_spec["columns"][k], json_cell=True)
                    for k, v in zip(keys, value, strict=True)
                )
            else:
                require(set(value) == set(target_spec["columns"]), "CANDIDATE_COLUMNS")
                row[col] = {
                    k: decode_native(v, target_spec["columns"][k], json_cell=True)
                    for k, v in value.items()
                }
        else:
            require(
                set(value) <= set(contract["keys"]) and set(contract["required"]) <= set(value),
                "BLOCKED_UNMAPPED_JSON",
            )
            typed(value)
    if "row_key" in row:
        target = row["table_name"]
        keys = schema["registry_keys"].get(target, schema["tables"][target]["primary_key"])
        for col in ("row_data", "base_row"):
            if row.get(col) is not None:
                require(tuple(row[col][k] for k in keys) == row["row_key"], "CANDIDATE_KEY")
    return row


def validate_closure(tables, root_id, schema, identity_limit=20000):
    needed = {
        r["foreign_key"]
        for s in schema["tables"].values()
        for r in s["columns"].values()
        if r["foreign_key"]
    }
    needed.update(schema["semantic_references"].values())
    targets, references, indexed = {}, set(), 0
    for table, spec in schema["tables"].items():
        for col in spec["columns"]:
            name = table + "." + col
            if name not in needed:
                continue
            values = set()
            for row in tables[table]:
                value = frame(row[col])
                if value not in values:
                    require(indexed < identity_limit, "EXPORT_IDENTITY_LIMIT")
                    indexed += 1
                    values.add(value)
            targets[name] = values
    for table, spec in schema["tables"].items():
        for row in tables[table]:
            for col, rule in spec["columns"].items():
                ref = rule["foreign_key"] or schema["semantic_references"].get(table + "." + col)
                if ref and row[col] is not None:
                    value = (ref, frame(row[col]))
                    if value not in references:
                        require(len(references) < identity_limit, "EXPORT_IDENTITY_LIMIT")
                        references.add(value)
                    require(frame(row[col]) in targets.get(ref, set()), "EXPORT_DANGLING_REFERENCE")
    jobs, pubs = tables["job_run"], tables["data_publication"]
    require(len(jobs) == len(pubs) == 1, "EXPORT_ROOT_LEDGER_COUNT")
    job, pub = jobs[0], pubs[0]
    require(
        job["id"] == pub["job_id"] == root_id
        and job["execution_token"] == pub["execution_token"]
        and job["parent_job_id"] is None
        and job["depends_on_job_id"] is None,
        "EXPORT_ROOT_IDENTITY",
    )
    require(
        (job["status"], pub["state"])
        in (("SUCCESS", "PUBLISHED"), ("FAILED", "ABORTED"), ("CANCELLED", "ABORTED")),
        "EXPORT_NONTERMINAL",
    )
    for candidate in tables["data_publication_row"]:
        require(candidate["is_deleted"] is (candidate["row_data"] is None), "EXPORT_TOMBSTONE")
        data = candidate["row_data"]
        if data and "calc_run_id" in data:
            require(data["calc_run_id"] == candidate["source_id"], "EXPORT_CANDIDATE_SOURCE")
        require(
            any(
                s["publication_id"] == candidate["publication_id"]
                and s["source_id"] == candidate["source_id"]
                and s["table_name"] == candidate["table_name"]
                and (
                    candidate["trade_date"] is None
                    or (s["start_date"] is None or s["start_date"] <= candidate["trade_date"])
                    and (s["end_date"] is None or candidate["trade_date"] <= s["end_date"])
                )
                for s in tables["data_publication_scope"]
            ),
            "EXPORT_SCOPE_MISSING",
        )
    return job, pub


@dataclass
class ExportResult:
    tables: dict = field(repr=False)
    evidence_kind: str
    binding: str
    snapshot_digest: str
    source: dict = field(repr=False)
    cleanup_ack: bool
    row_count: int
    _seal: str = field(repr=False)

    def safe_summary(self):
        return {
            "evidence_kind": self.evidence_kind,
            "binding": self.binding,
            "snapshot_digest": self.snapshot_digest,
            "row_count": self.row_count,
            "cleanup_ack": self.cleanup_ack,
            "real_pg_export_verified": False,
        }


class PgTypedExporter:
    def __init__(
        self,
        guard,
        target,
        *,
        evidence_kind="PG_TYPED_UNVERIFIED",
        max_rows=10000,
        max_bytes=64 * 1024 * 1024,
        seconds=30,
        clock=monotonic,
        identity_limit=20000,
    ):
        require(evidence_kind in ("FAKE", "PG_TYPED_UNVERIFIED"), "EXPORT_EVIDENCE_KIND")
        require(
            type(max_rows) is int
            and 0 <= max_rows <= 10000
            and type(max_bytes) is int
            and 0 <= max_bytes <= 64 * 1024 * 1024
            and type(seconds) in (int, float)
            and math.isfinite(seconds)
            and 0 <= seconds <= 30,
            "EXPORT_BUDGET",
        )
        require(
            type(identity_limit) is int and 0 <= identity_limit <= 20000, "EXPORT_IDENTITY_LIMIT"
        )
        self.identity_limit = identity_limit
        self.guard, self.target, self.kind = guard, target, evidence_kind
        self.rows, self.bytes, self.seconds, self.clock = max_rows, max_bytes, seconds, clock

    def export(self, connector, *, root_id, independent_evidence):
        self.guard.preconnect(self.target)
        require(
            type(root_id) is UUID and callable(independent_evidence), "EXPORT_EVIDENCE_REQUIRED"
        )
        connection, cursors = None, []
        deadline, byte_count, row_count = self.clock() + self.seconds, 0, 0
        schema, tables = load_schema(), {}

        def check():
            require(self.clock() < deadline, "EXPORT_TIMEOUT")

        def cursor(**kwargs):
            cur = connection.cursor(**kwargs)
            cursors.append(cur)
            return cur

        try:
            check()
            connection = connector(self.target.config_ref)
            control = cursor()
            control.execute(BEGIN_SQL)
            control.execute(TIMEOUT_SQL, (str(max(1, int(self.seconds * 1000))) + "ms",))
            self.guard.check_connection(connection, self.target)
            control.execute(SNAPSHOT_SQL)
            snapshot = control.fetchone()
            require(
                type(snapshot) in (tuple, list) and len(snapshot) == 1 and type(snapshot[0]) is str,
                "EXPORT_SNAPSHOT_UNKNOWN",
            )
            control.execute(CATALOG_SQL, (list(schema["tables"]),))
            catalog = []
            while batch := control.fetchmany(128):
                check()
                catalog.extend(batch)
                require(len(catalog) <= 520, "SCHEMA_DRIFT")
            require(sorted(catalog) == expected_catalog(), "SCHEMA_DRIFT")
            for table, spec in schema["tables"].items():
                check()
                columns = list(spec["columns"])
                # Identifiers come only from the pinned schema, never CLI/JSON.
                require(
                    all(re.fullmatch(r"[a-z_][a-z0-9_]*", x) for x in [table, *columns]),
                    "SCHEMA_DRIFT",
                )
                order = list(dict.fromkeys(spec["natural_key"] + spec["primary_key"]))
                sql = (
                    "SELECT "
                    + ",".join('"' + c + '"' for c in columns)
                    + ' FROM public."'
                    + table
                    + '" ORDER BY '
                    + ",".join('"' + c + '"' for c in order)
                )
                cur = cursor(name="r1_export_" + table)
                cur.execute(sql)
                require([x[0] for x in cur.description] == columns, "SCHEMA_DRIFT")
                rows, seen, natural_seen = [], set(), set()
                while batch := cur.fetchmany(64):
                    check()
                    for values in batch:
                        check()
                        require(len(values) == len(columns), "SCHEMA_DRIFT")
                        row = decode_row(table, dict(zip(columns, values, strict=True)), schema)
                        raw = frame(row)
                        byte_count += len(raw)
                        row_count += 1
                        require(
                            byte_count <= self.bytes and row_count <= self.rows,
                            "EXPORT_INCOMPLETE_RESOURCE_LIMIT",
                        )
                        key = frame(tuple(row[k] for k in spec["primary_key"]))
                        require(key not in seen, "EXPORT_DUPLICATE_KEY")
                        seen.add(key)
                        natural_key = frame(tuple(row[k] for k in spec["natural_key"]))
                        if spec["multiplicity"] != "MULTISET_ORDINAL":
                            require(natural_key not in natural_seen, "EXPORT_DUPLICATE_NATURAL_KEY")
                            natural_seen.add(natural_key)
                        rows.append(row)
                cur.close()
                rows.sort(key=lambda r, spec=spec: frame(tuple(r[k] for k in spec["natural_key"])))
                tables[table] = rows
            check()
            job, _ = validate_closure(tables, root_id, schema, self.identity_limit)
            # Re-observe physical identity on the same connection before closing.
            identity = self.guard.check_connection(connection, self.target)
            binding = sha((identity, snapshot[0], root_id, sha(tables), source_identity()))
            evidence = independent_evidence(binding)
            require(
                type(evidence) is dict
                and evidence
                == {
                    "binding": binding,
                    "root_id": root_id,
                    "worker": job["worker_id"],
                    "token": job["execution_token"],
                    "commit_ack": "KNOWN",
                    "lease": "CONFIRMED",
                    "connections_closed": True,
                    "cleanup_ack": "CONFIRMED",
                    "os_exit": "CONFIRMED",
                },
                "EXPORT_INDEPENDENT_ACK_UNKNOWN",
            )
            check()
            for cur in cursors:
                cur.close()
            connection.rollback()
            connection.close()
            connection = None
            return ExportResult(
                tables,
                self.kind,
                binding,
                sha(snapshot[0]),
                source_identity(),
                True,
                row_count,
                sha(tables),
            )
        except Refused:
            raise
        except Exception:
            raise Refused("EXPORT_INCOMPLETE") from None
        finally:
            if connection is not None:
                try:
                    for cur in cursors:
                        cur.close()
                    connection.rollback()
                    connection.close()
                except Exception:
                    raise Refused("EXPORT_CLEANUP_UNCERTAIN") from None


def compare_fake_exports(left, right, left_fixture, right_fixture, mappings):
    """Explicit fake-fixture bridge ONLY. Never relabel a real PG export."""
    for packet in (left, right):
        require(
            type(packet) is ExportResult and packet.evidence_kind == "FAKE",
            "REAL_COMPARATOR_BRIDGE_NOT_AUTHORIZED",
        )
        require(packet.cleanup_ack and sha(packet.tables) == packet._seal, "EXPORT_TAMPERED")
    fixtures = []
    for packet, fixture in ((left, left_fixture), (right, right_fixture)):
        require(fixture["evidence_kind"] == "SYNTHETIC_ONLY", "EXPORT_FAKE_FIXTURE_REQUIRED")
        result = deepcopy(fixture)
        result["tables"] = packet.tables
        result["counts"] = {t: len(r) for t, r in packet.tables.items()}
        fixtures.append(result)
    result = compare_snapshots(*fixtures, mappings)
    return {
        "synthetic_equal": result["equal"],
        "comparison": result,
        "real_worker_output_equal": False,
    }
