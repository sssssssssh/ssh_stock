"""Pure, bounded offline review. Caller provenance is a trust input, never a permit.

This semantic projection supplements, and never replaces, the frozen 37/520
contract. No file, environment, clock, Git, application, process or network I/O.
The draft oracle can establish offline agreement, never owner approval.
"""

import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

PROTOCOL = "r1.reviewed-evidence.v2"
HISTORICAL_BASELINE = "b6ffb7bf8ec7d26f771d9b89923e4f7e926edbed"
FROZEN_SCHEMA = "f6be0a5de1ce46e30758039a3ab345a308ff96cb36f6ee86ec3ccdc39759f297"
MAX_BYTES = 1024 * 1024
MAX_NODES = 20000
MAX_DEPTH = 24
MAX_TEXT = 2048
MAX_ITEMS = 256
MAX_ROWS = 128
CASES = tuple(f"C{n:02}" for n in range(1, 17))
DOMAINS = ("RAW_INPUT", "TYPED_OUTPUT", "BUSINESS_EXPECTATION", "TELEMETRY")
PREFIXES = (b"R1-V2-RAW\0", b"R1-V2-TYPED\0", b"R1-V2-BUSINESS\0", b"R1-V2-TELEMETRY\0")
IDENTITIES = ("job", "token", "scope", "worker", "event")
SOURCE_FIELDS = frozenset(
    (
        "reviewed_head_sha",
        "historical_baseline_sha",
        "frozen_schema_sha256",
        "tool_identity_sha256",
        "golden_sha256",
        "fixture_sha256",
        "contract_sha256",
        "fixture_namespace",
        "golden_revision",
    )
)
CONTROLS = {
    "pg_physical_attestation": "NOT_PROVEN",
    "os_reaped": "NOT_PROVEN",
    "cleanup_absent": "NOT_PROVEN",
    "external_owner_ack": "NOT_PROVEN",
    "business_policy_approval": "PENDING_D04",
}
CHECKS = ("parse", "source", "oracle", "types", "relations", "expectation", "physical")
PACKET_FIELDS = (
    "schema_version",
    "evidence_kind",
    "scope",
    "authorization",
    "source_context",
    "subject",
    "domains",
    "controls",
)
SUBJECT_FIELDS = (
    "case_id",
    "arm",
    "lifecycle",
    "commit_ack",
    "root_id",
    "worker_id",
    "execution_token",
    "scope_identity",
    "input_ref",
)
DOMAIN_FIELDS = {
    "RAW_INPUT": ["status", "fixture_id", "rows", "declared_sha256"],
    "TYPED_OUTPUT": ["status", "rows", "sentinels"],
    "BUSINESS_EXPECTATION": ["status", "case_id", "revision"],
    "TELEMETRY": ["status", "heartbeat", "local_cleanup", "measurements"],
}


class Refused(ValueError):
    """Internal fixed-code failure; values and exception repr never leave review."""


def require(ok, code):
    if not ok:
        raise Refused(code)


def fields(value, names, code="V2_FIELDS"):
    require(type(value) is dict and set(value) == set(names), code)


def _bounded(value):
    nodes, size, active = 0, 0, set()

    def walk(item, depth):
        nonlocal nodes, size
        nodes += 1
        require(nodes <= MAX_NODES and depth <= MAX_DEPTH, "V2_LIMIT")
        kind = type(item)
        if kind in (dict, list):
            require(len(item) <= MAX_ITEMS and id(item) not in active, "V2_LIMIT")
            active.add(id(item))
            if kind is dict:
                for key, val in item.items():
                    require(type(key) is str, "V2_TYPE")
                    walk(key, depth + 1)
                    walk(val, depth + 1)
            else:
                for val in item:
                    walk(val, depth + 1)
            active.remove(id(item))
        elif kind is str:
            require(len(item) <= MAX_TEXT, "V2_LIMIT")
            size += len(item.encode("utf-8"))
        elif kind is int:
            require(item.bit_length() <= 63, "V2_LIMIT")
            size += 20
        else:
            require(item is None or kind is bool, "V2_TYPE")
            size += 5
        require(size <= MAX_BYTES, "V2_LIMIT")

    walk(value, 0)


def parse(value):
    """Accept exact built-in objects or bounded UTF-8 JSON bytes, never paths."""
    if type(value) is bytes:
        require(len(value) <= MAX_BYTES, "V2_LIMIT")
        # Bound nesting before the JSON decoder allocates recursive containers.
        depth, quoted, escaped = 0, False, False
        for ch in value:
            if quoted:
                if escaped:
                    escaped = False
                elif ch == 92:
                    escaped = True
                elif ch == 34:
                    quoted = False
            elif ch == 34:
                quoted = True
            elif ch in (91, 123):
                depth += 1
                require(depth <= MAX_DEPTH, "V2_LIMIT")
            elif ch in (93, 125):
                depth -= 1

        def pairs(items):
            result = {}
            for key, val in items:
                require(key not in result, "V2_DUPLICATE_KEY")
                result[key] = val
            return result

        def bad_number(_value):
            raise Refused("V2_TYPE")

        def integer(text):
            require(len(text) <= 20, "V2_LIMIT")
            return int(text)

        try:
            value = json.loads(
                value.decode("utf-8"),
                object_pairs_hook=pairs,
                parse_constant=bad_number,
                parse_float=bad_number,
                parse_int=integer,
            )
        except (ValueError, UnicodeError, RecursionError) as error:
            if isinstance(error, Refused):
                raise
            raise Refused("V2_JSON") from None
    _bounded(value)
    return value


def _wire(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _hex(value, length=64):
    require(
        type(value) is str and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None, "V2_SOURCE"
    )


def _label(value):
    require(
        type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is not None, "V2_TYPE"
    )


def _uuid(value):
    require(type(value) is str, "V2_IDENTITY")
    try:
        require(str(UUID(value)) == value, "V2_IDENTITY")
    except ValueError:
        raise Refused("V2_IDENTITY") from None


def _utc(value):
    require(
        type(value) is str
        and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", value) is not None,
        "V2_TIME",
    )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.utcoffset() == timedelta(0), "V2_TIME")
    except ValueError:
        raise Refused("V2_TIME") from None


def _source(actual, expected):
    fields(expected, SOURCE_FIELDS, "V2_SOURCE")
    fields(actual, SOURCE_FIELDS, "V2_SOURCE")
    for key in SOURCE_FIELDS - {"fixture_namespace", "golden_revision"}:
        _hex(expected[key], 40 if key.endswith("head_sha") or key.endswith("baseline_sha") else 64)
    require(
        expected["historical_baseline_sha"] == HISTORICAL_BASELINE
        and expected["frozen_schema_sha256"] == FROZEN_SCHEMA,
        "V2_SOURCE",
    )
    require(
        expected["fixture_namespace"] == "r1-w04c-manual-v2"
        and expected["golden_revision"] == "manual-draft-01",
        "V2_SOURCE",
    )
    require(actual == expected, "V2_SOURCE")


def _identities(definitions):
    fields(definitions, IDENTITIES, "V2_IDENTITY")
    maps = {side: {} for side in ("left", "right")}
    seen = {side: set() for side in maps}
    for domain, entries in definitions.items():
        require(type(entries) is list and len(entries) <= 16, "V2_IDENTITY")
        roles, previous = set(), None
        for entry in entries:
            fields(entry, ("role", "left", "right"), "V2_IDENTITY")
            _label(entry["role"])
            require(entry["role"] not in roles, "V2_IDENTITY")
            roles.add(entry["role"])
            for side in maps:
                value = entry[side]
                if domain == "event":
                    _utc(value)
                elif domain == "worker":
                    _label(value)
                else:
                    _uuid(value)
                require((domain, value) not in maps[side], "V2_IDENTITY")
                if domain != "event":
                    require(value not in seen[side], "V2_IDENTITY")
                    seen[side].add(value)
                maps[side][domain, value] = "@" + entry["role"]
            if domain == "event":
                pair = (entry["left"], entry["right"])
                require(
                    previous is None or previous[0] < pair[0] and previous[1] < pair[1],
                    "V2_TIME_MAPPING",
                )
                previous = pair
    return maps


def _cell(value, identities=None, *, expected=False):
    require(type(value) is dict and type(value.get("type")) is str, "V2_TYPE")
    tag = value["type"]
    if tag in ("sql_null", "json_null", "missing"):
        fields(value, ("type",), "V2_TYPE")
        return value
    mapped = tag in ("uuid", "worker", "event")
    fields(value, ("type", "domain", "value") if mapped else ("type", "value"), "V2_TYPE")
    item = value["value"]
    if mapped:
        domain = value["domain"]
        require(
            domain in IDENTITIES
            and (
                tag == "uuid"
                and domain in ("job", "token", "scope")
                or tag == "worker"
                and domain == "worker"
                or tag == "event"
                and domain == "event"
            ),
            "V2_IDENTITY",
        )
        if expected:
            require(type(item) is str and item.startswith("@"), "V2_IDENTITY")
            _label(item[1:])
            require(item in (v for (d, _), v in identities.items() if d == domain), "V2_IDENTITY")
            return value
        if tag == "uuid":
            _uuid(item)
        elif tag == "event":
            _utc(item)
        else:
            _label(item)
        require((domain, item) in identities, "V2_REFERENCE")
        return {**value, "value": identities[domain, item]}
    if tag == "bool":
        require(type(item) is bool, "V2_TYPE")
    elif tag == "int":
        require(type(item) is int, "V2_TYPE")
    elif tag == "text":
        require(type(item) is str, "V2_TYPE")
    elif tag == "bytes":
        require(
            type(item) is str and re.fullmatch(r"(?:[0-9a-f]{2})*", item) is not None, "V2_TYPE"
        )
    elif tag == "decimal":
        require(
            type(item) is str
            and re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d+)?", item) is not None
            and Decimal(item).is_finite(),
            "V2_TYPE",
        )
    elif tag == "float":
        require(type(item) is str and len(item) <= 32, "V2_TYPE")
        try:
            floating = float.fromhex(item)
            require(math.isfinite(floating) and floating.hex() == item, "V2_TYPE")
        except (ValueError, OverflowError):
            raise Refused("V2_TYPE") from None
    elif tag == "date":
        require(type(item) is str, "V2_TIME")
        try:
            require(date.fromisoformat(item).isoformat() == item, "V2_TIME")
        except ValueError:
            raise Refused("V2_TIME") from None
    elif tag == "datetime":
        _utc(item)
    elif tag == "array":
        require(type(item) is list, "V2_TYPE")
        return {"type": tag, "value": [_cell(v, identities, expected=expected) for v in item]}
    elif tag == "object":
        require(type(item) is dict, "V2_TYPE")
        return {
            "type": tag,
            "value": {k: _cell(v, identities, expected=expected) for k, v in item.items()},
        }
    else:
        raise Refused("V2_TYPE")
    return value


def _rows(rows, contract, identities, *, expected=False):
    require(type(rows) is list and len(rows) <= MAX_ROWS, "V2_LIMIT")
    result, keys = [], set()
    for row in rows:
        fields(row, ("table", "key", "ordinal", "values"))
        table, key = row["table"], row["key"]
        require(type(table) is str and table in contract["projection_columns"], "V2_SCHEMA")
        _label(key)
        require(type(row["ordinal"]) is int and 0 <= row["ordinal"] < MAX_ROWS, "V2_TYPE")
        require((table, key) not in keys, "V2_DUPLICATE_ROW")
        keys.add((table, key))
        fields(row["values"], contract["projection_columns"][table], "V2_SCHEMA")
        values = {col: _cell(v, identities, expected=expected) for col, v in row["values"].items()}
        require(
            table == "synthetic_type_probe" or all(v["type"] != "missing" for v in values.values()),
            "V2_SCHEMA",
        )
        result.append({**row, "values": values})
    return sorted(result, key=lambda r: (r["table"], r["key"], r["ordinal"]))


def _contract(raw, provenance):
    require(type(raw) is bytes, "V2_CONTRACT")
    require(hashlib.sha256(raw).hexdigest() == provenance["contract_sha256"], "V2_SOURCE")
    contract = parse(raw)
    fields(
        contract,
        (
            "schema_version",
            "scope",
            "projection_scope",
            "limits",
            "projection_columns",
            "identity_domains",
            "cell_types",
            "source_fields",
            "statuses",
            "failure_codes",
            "packet_fields",
            "subject_fields",
            "domain_fields",
            "controls",
            "digest_prefixes",
            "provenance_trust",
            "cell_shapes",
        ),
        "V2_CONTRACT",
    )
    require(
        contract["schema_version"] == PROTOCOL
        and contract["scope"] == "OFFLINE_GOLDEN_CONTRACT_ONLY"
        and contract["projection_scope"] == "MANUAL_PROJECTION_NOT_FULL_DATABASE",
        "V2_CONTRACT",
    )
    require(
        contract["limits"]
        == {
            "bytes": MAX_BYTES,
            "nodes": MAX_NODES,
            "depth": MAX_DEPTH,
            "text": MAX_TEXT,
            "items": MAX_ITEMS,
            "rows": MAX_ROWS,
        },
        "V2_CONTRACT",
    )
    require(
        contract["identity_domains"] == list(IDENTITIES)
        and len(contract["source_fields"]) == len(SOURCE_FIELDS)
        and set(contract["source_fields"]) == SOURCE_FIELDS,
        "V2_CONTRACT",
    )
    require(
        contract["packet_fields"] == list(PACKET_FIELDS)
        and contract["subject_fields"] == list(SUBJECT_FIELDS)
        and contract["domain_fields"] == DOMAIN_FIELDS
        and contract["controls"] == CONTROLS
        and contract["provenance_trust"] == "CALLER_SUPPLIED_NOT_AUTHENTICATED"
        and contract["digest_prefixes"] == [p.decode("ascii") for p in PREFIXES],
        "V2_CONTRACT",
    )
    require(
        type(contract["projection_columns"]) is dict and len(contract["projection_columns"]) <= 16,
        "V2_CONTRACT",
    )
    for name, columns in contract["projection_columns"].items():
        _label(name)
        require(
            type(columns) is list and 0 < len(columns) <= 32 and len(set(columns)) == len(columns),
            "V2_CONTRACT",
        )
        for col in columns:
            _label(col)
    return contract


def _oracle(raw, provenance):
    require(
        type(raw) is bytes and hashlib.sha256(raw).hexdigest() == provenance["golden_sha256"],
        "V2_GOLDEN",
    )
    oracle = parse(raw)
    fields(
        oracle,
        (
            "schema_version",
            "revision",
            "approval",
            "reviewer",
            "authorship",
            "source_context",
            "identities",
            "base_rows",
            "base_raw",
            "base_sentinels",
            "cases",
        ),
        "V2_GOLDEN",
    )
    require(
        oracle["schema_version"] == "r1.independent-oracle.v2"
        and oracle["revision"] == provenance["golden_revision"]
        and oracle["approval"] == "PENDING_D04"
        and oracle["reviewer"] == "NOT_SIGNED"
        and oracle["authorship"] == "CODEX_MANUAL_DRAFT_NOT_OWNER_APPROVAL",
        "V2_GOLDEN",
    )
    require(
        oracle["source_context"]
        == {
            k: provenance[k]
            for k in (
                "reviewed_head_sha",
                "historical_baseline_sha",
                "frozen_schema_sha256",
                "fixture_namespace",
            )
        },
        "V2_SOURCE",
    )
    require(type(oracle["cases"]) is list and len(oracle["cases"]) == len(CASES), "V2_GOLDEN")
    require(
        [c.get("case_id") for c in oracle["cases"] if type(c) is dict] == list(CASES), "V2_GOLDEN"
    )
    for case in oracle["cases"]:
        fields(
            case,
            (
                "case_id",
                "meaning",
                "spec_refs",
                "columns",
                "group",
                "d04_required",
                "lifecycle",
                "commit_ack",
                "expected_status",
                "expected_error",
                "changes",
            ),
            "V2_GOLDEN",
        )
        require(
            case["group"] in ("FROZEN_SEMANTICS_DRAFT", "PENDING_D04")
            and type(case["d04_required"]) is bool
            and case["d04_required"] == (case["group"] == "PENDING_D04")
            and type(case["spec_refs"]) is list
            and bool(case["spec_refs"])
            and type(case["columns"]) is list
            and bool(case["columns"])
            and type(case["meaning"]) is str
            and bool(case["meaning"]),
            "V2_GOLDEN",
        )
    return oracle


def _packet(packet, provenance, arm, contract, identities):
    packet = parse(packet)
    fields(packet, PACKET_FIELDS)
    require(
        packet["schema_version"] == PROTOCOL
        and packet["evidence_kind"] == "OFFLINE_REVIEW_PACKET"
        and packet["scope"] == "OFFLINE_GOLDEN_CONTRACT_ONLY",
        "V2_PROTOCOL",
    )
    require(packet["authorization"] == "NOT_AUTHORIZED", "V2_AUTHORIZATION")
    _source(packet["source_context"], provenance)
    require(packet["controls"] == CONTROLS, "V2_PHYSICAL_CLAIM")
    subject = packet["subject"]
    fields(subject, SUBJECT_FIELDS)
    require(subject["case_id"] in CASES and subject["arm"] == arm, "V2_CASE")
    require(
        subject["lifecycle"] in ("SUCCESS", "FAILED", "CANCELLED", "UNKNOWN")
        and subject["commit_ack"] in ("KNOWN", "UNKNOWN"),
        "V2_LIFECYCLE",
    )
    for domain, field in (
        ("job", "root_id"),
        ("worker", "worker_id"),
        ("token", "execution_token"),
        ("scope", "scope_identity"),
    ):
        require((domain, subject[field]) in identities, "V2_IDENTITY")
        require(
            identities[domain, subject[field]]
            == "@" + ("scope-1" if domain == "scope" else domain),
            "V2_IDENTITY",
        )
    _hex(subject["input_ref"])
    domains = packet["domains"]
    fields(domains, DOMAINS)
    raw = domains["RAW_INPUT"]
    fields(raw, ("status", "fixture_id", "rows", "declared_sha256"))
    require(
        raw["status"] == "OFFLINE_FIXTURE_ONLY"
        and type(raw["rows"]) is int
        and 0 <= raw["rows"] <= MAX_ROWS,
        "V2_TYPE",
    )
    _label(raw["fixture_id"])
    _hex(raw["declared_sha256"])
    require(subject["input_ref"] == raw["declared_sha256"], "V2_SOURCE")
    out = domains["TYPED_OUTPUT"]
    fields(out, ("status", "rows", "sentinels"))
    require(out["status"] == "OFFLINE_FIXTURE_ONLY", "V2_PROTOCOL")
    normalized = _rows(out["rows"], contract, identities)
    business = domains["BUSINESS_EXPECTATION"]
    require(
        business
        == {
            "status": "HUMAN_DRAFT_PENDING_D04",
            "case_id": subject["case_id"],
            "revision": provenance["golden_revision"],
        },
        "V2_GOLDEN",
    )
    telemetry = domains["TELEMETRY"]
    fields(telemetry, ("status", "heartbeat", "local_cleanup", "measurements"))
    require(
        telemetry["status"] == "NOT_PROVEN"
        and telemetry["measurements"] == "NOT_MEASURED"
        and telemetry["heartbeat"] in ("OFFLINE_MODEL_CONFIRMED", "UNKNOWN")
        and telemetry["local_cleanup"] in ("OFFLINE_MODEL_COMPLETE", "UNKNOWN"),
        "V2_TYPE",
    )
    return packet, normalized


def _sentinels(value):
    fields(
        value,
        ("status", "revision", "schema_sha256", "sequences", "outside_tables", "physical"),
        "V2_SENTINEL_UNKNOWN",
    )
    require(value["status"] == "OFFLINE_ASSERTED", "V2_SENTINEL_UNKNOWN")
    require(value["physical"] == "NOT_PROVEN", "V2_PHYSICAL_CLAIM")
    require(
        value["revision"] == "0058_data_publication" and value["schema_sha256"] == FROZEN_SCHEMA,
        "V2_SCHEMA",
    )
    require(type(value["sequences"]) is dict and bool(value["sequences"]), "V2_SENTINEL_UNKNOWN")
    for name, sequence in value["sequences"].items():
        _label(name)
        fields(sequence, ("last_value", "is_called"), "V2_SENTINEL_UNKNOWN")
        require(
            type(sequence["last_value"]) is int
            and sequence["last_value"] > 0
            and type(sequence["is_called"]) is bool,
            "V2_TYPE",
        )
    require(
        type(value["outside_tables"]) is dict and bool(value["outside_tables"]),
        "V2_SENTINEL_UNKNOWN",
    )
    for name, pair in value["outside_tables"].items():
        _label(name)
        fields(pair, ("before", "after"), "V2_SENTINEL_UNKNOWN")
        _hex(pair["before"])
        _hex(pair["after"])
        require(pair["before"] == pair["after"], "V2_OUTSIDE_CHANGED")


def _relations(packet, rows):
    subject = packet["subject"]
    require(
        subject["commit_ack"] == "KNOWN" and subject["lifecycle"] != "UNKNOWN", "V2_ACK_UNKNOWN"
    )
    telemetry = packet["domains"]["TELEMETRY"]
    require(telemetry["heartbeat"] == "OFFLINE_MODEL_CONFIRMED", "V2_HEARTBEAT_UNKNOWN")
    require(telemetry["local_cleanup"] == "OFFLINE_MODEL_COMPLETE", "V2_CLEANUP_UNKNOWN")
    _sentinels(packet["domains"]["TYPED_OUTPUT"]["sentinels"])
    by_table = {}
    for row in rows:
        by_table.setdefault(row["table"], []).append(row)

    def one(table):
        require(len(by_table.get(table, [])) == 1, "V2_RELATION")
        return by_table[table][0]["values"]

    def val(row, name):
        return row[name].get("value")

    job, pub, source = (one(t) for t in ("job_run", "data_publication", "data_publication_source"))
    candidate, preimage = one("data_publication_row"), one("data_publication_preimage")
    require(
        val(job, "id")
        == val(pub, "job_id")
        == val(source, "publication_id")
        == val(source, "source_job_id")
        == val(candidate, "publication_id")
        == val(candidate, "source_id")
        == val(preimage, "publication_id")
        == "@job",
        "V2_REFERENCE",
    )
    require(
        val(job, "execution_token") == val(pub, "execution_token") == "@token"
        and val(job, "worker_id") == "@worker",
        "V2_REFERENCE",
    )
    lifecycle = subject["lifecycle"]
    require(
        val(job, "status") == lifecycle
        and val(pub, "state") == ("PUBLISHED" if lifecycle == "SUCCESS" else "ABORTED"),
        "V2_LIFECYCLE",
    )
    require(val(job, "cancel_requested") is (lifecycle == "CANCELLED"), "V2_LIFECYCLE")
    require(
        job["job_metadata"]["value"]["calc_run_id"]["value"] == "@job"
        and job["job_metadata"]["value"]["queue_identity"] == pub["identity"],
        "V2_REFERENCE",
    )
    require(val(source, "role") == "root", "V2_RELATION")
    target = val(candidate, "table_name")
    require(
        target == val(preimage, "table_name") == "stock_factor_daily"
        and candidate["row_key"] == preimage["row_key"],
        "V2_RELATION",
    )
    require(candidate["base_row"] == preimage["row_data"], "V2_PREIMAGE")
    deleted = val(candidate, "is_deleted")
    require(
        type(deleted) is bool and (candidate["row_data"]["type"] == "sql_null") is deleted,
        "V2_CANDIDATE",
    )
    public = by_table.get("stock_factor_daily", [])
    if lifecycle == "SUCCESS":
        if deleted:
            require(not public, "V2_CANDIDATE")
        else:
            require(len(public) == 1, "V2_CANDIDATE")
            expected_row = candidate["row_data"].get("value")
            require(
                type(expected_row) is dict
                and all(public[0]["values"].get(k) == v for k, v in expected_row.items()),
                "V2_CANDIDATE",
            )
    else:
        require(
            len(public) == 1
            and all(
                public[0]["values"].get(k) == v for k, v in preimage["row_data"]["value"].items()
            ),
            "V2_PREIMAGE",
        )
    scopes = by_table.get("data_publication_scope", [])
    require(bool(scopes), "V2_SCOPE")
    seen_scope_ids = set()
    raw_scope_ids = {
        row["key"]: row["values"]["id"].get("value")
        for row in packet["domains"]["TYPED_OUTPUT"]["rows"]
        if row["table"] == "data_publication_scope"
    }
    previous = None
    for ordinal, row in enumerate(sorted(scopes, key=lambda r: r["ordinal"])):
        scope = row["values"]
        require(
            row["ordinal"] == ordinal
            and val(scope, "publication_id") == "@job"
            and val(scope, "source_id") == "@job"
            and val(scope, "table_name") == target
            and val(scope, "start_date")
            <= candidate["row_key"]["value"][0]["value"]
            <= val(scope, "end_date"),
            "V2_SCOPE",
        )
        raw_id = raw_scope_ids[row["key"]]
        require(
            raw_id not in seen_scope_ids and (previous is None or previous < raw_id), "V2_SCOPE"
        )
        seen_scope_ids.add(raw_id)
        previous = raw_id
    for row in by_table.get("stock_opportunity_daily", []):
        opportunity = row["values"]
        require(
            opportunity["calc_run_id"]["value"] == "@job"
            and any(
                r["values"]["id"] == opportunity["primary_sector_id"]
                for r in by_table.get("sector", [])
            )
            and any(
                r["values"]["theme_code"] == opportunity["primary_theme_code"]
                for r in by_table.get("theme", [])
            ),
            "V2_REFERENCE",
        )


def _expected_rows(oracle, case):
    # Only the independently supplied oracle is expanded; never derive expected
    # values from either packet, the old schema/generator, or encoder output.
    rows = json.loads(_wire(oracle["base_rows"]))
    for change in case["changes"]:
        fields(change, ("table", "key", "row"), "V2_GOLDEN")
        rows = [r for r in rows if (r["table"], r["key"]) != (change["table"], change["key"])]
        if change["row"] is not None:
            require(
                change["row"]["table"] == change["table"] and change["row"]["key"] == change["key"],
                "V2_GOLDEN",
            )
            rows.append(change["row"])
    return rows


def _domain_digests(packet, normalized, expected_rows, provenance):
    subject = packet["subject"]
    binding = {
        "protocol": PROTOCOL,
        "source": provenance,
        "case_id": subject["case_id"],
        "arm": subject["arm"],
        "input_ref": subject["input_ref"],
        "subject": subject,
    }
    values = (
        packet["domains"]["RAW_INPUT"],
        packet["domains"]["TYPED_OUTPUT"],
        {"actual_canonical": normalized, "independent_expected": expected_rows},
        packet["domains"]["TELEMETRY"],
    )
    result = {}
    for domain, prefix, value in zip(DOMAINS, PREFIXES, values, strict=True):
        header, payload = _wire(binding), _wire(value)
        result[domain] = hashlib.sha256(
            prefix
            + len(header).to_bytes(8, "big")
            + header
            + len(payload).to_bytes(8, "big")
            + payload
        ).hexdigest()
    return result


def review_pair(left, right, oracle_bytes, contract_bytes, expected_provenance):
    """Review two memory-only drafts against separately supplied fixed expected.

    The caller must obtain expected_provenance independently. Matching a caller's
    own fabricated provenance is not source authenticity or owner endorsement.
    No v2 output is consumable as a real-PG, execution or authorization receipt.
    """
    result = {
        "protocol": PROTOCOL,
        "status": "INCOMPLETE",
        "decision": "NO_GO",
        "evidence_kind": "OFFLINE_REVIEW_ONLY",
        "errors": [],
        "domain_digests": {
            side: dict.fromkeys(DOMAINS, "NOT_COMPUTED") for side in ("left", "right")
        },
        "checks": dict.fromkeys(CHECKS, "NOT_RUN"),
        "oracle_match": False,
        "business_golden_status": "PENDING_OWNER_DECISION",
        "authorization": "NOT_AUTHORIZED",
        "real_pg_input_equal": False,
        "real_worker_output_equal": False,
        "performance_pass": False,
        "production_authorized": False,
        "physical_proof": "NOT_PROVEN",
        "trust": ["SOURCE_DECLARED", "PHYSICAL_NOT_PROVEN", "OWNER_NOT_SIGNED"],
    }
    phase = "parse"
    try:
        left, right, expected_provenance = (
            parse(obj) for obj in (left, right, expected_provenance)
        )
        result["checks"]["parse"] = "PASS"
        phase = "source"
        _source(expected_provenance, expected_provenance)
        contract = _contract(contract_bytes, expected_provenance)
        for packet in (left, right):
            fields(packet, PACKET_FIELDS)
            require(
                packet["schema_version"] == PROTOCOL
                and packet["evidence_kind"] == "OFFLINE_REVIEW_PACKET"
                and packet["scope"] == "OFFLINE_GOLDEN_CONTRACT_ONLY",
                "V2_PROTOCOL",
            )
            require(packet["authorization"] == "NOT_AUTHORIZED", "V2_AUTHORIZATION")
            _source(packet["source_context"], expected_provenance)
        result["checks"]["source"] = "PASS"
        phase = "oracle"
        oracle = _oracle(oracle_bytes, expected_provenance)
        identity = _identities(oracle["identities"])
        result["checks"]["oracle"] = "PASS"
        phase = "types"
        packets, normalized = [], []
        for raw, arm, side in ((left, "OFFLINE_LEFT", "left"), (right, "OFFLINE_RIGHT", "right")):
            packet, rows = _packet(raw, expected_provenance, arm, contract, identity[side])
            packets.append(packet)
            normalized.append(rows)
        case_id = packets[0]["subject"]["case_id"]
        require(packets[1]["subject"]["case_id"] == case_id, "V2_CASE")
        case = next(c for c in oracle["cases"] if c["case_id"] == case_id)
        expected = _rows(_expected_rows(oracle, case), contract, identity["left"], expected=True)
        result["checks"]["types"] = "PASS"
        phase = "relations"
        for packet, rows, side in zip(packets, normalized, ("left", "right"), strict=True):
            result["domain_digests"][side] = _domain_digests(
                packet, rows, expected, expected_provenance
            )
            _relations(packet, rows)
        result["checks"]["relations"] = "PASS"
        phase = "expectation"
        for packet, rows in zip(packets, normalized, strict=True):
            require(
                packet["subject"]["lifecycle"] == case["lifecycle"]
                and packet["subject"]["commit_ack"] == case["commit_ack"]
                and packet["domains"]["RAW_INPUT"] == oracle["base_raw"]
                and packet["domains"]["TYPED_OUTPUT"]["sentinels"] == oracle["base_sentinels"]
                and _wire(rows) == _wire(expected),
                "V2_ORACLE_MISMATCH",
            )
        result["checks"]["expectation"] = "PASS"
        result["oracle_match"] = True
        result["trust"].extend(("STATIC_HASH_MATCH", "OFFLINE_ORACLE_MATCH"))
        if case["d04_required"]:
            result["status"] = "PENDING_OWNER_DECISION"
            result["errors"] = [{"code": "V2_PENDING_D04"}]
        else:
            result["status"] = "OFFLINE_ORACLE_MATCH"
    except Refused as error:
        # All Refused instances are created internally with fixed literal codes.
        code = error.args[0]
        result["checks"][phase] = "FAIL"
        result["errors"] = [{"code": code}]
        if code in {
            "V2_ORACLE_MISMATCH",
            "V2_REFERENCE",
            "V2_CANDIDATE",
            "V2_PREIMAGE",
            "V2_SCOPE",
            "V2_LIFECYCLE",
            "V2_IDENTITY",
            "V2_TIME_MAPPING",
        }:
            result["status"] = "UNEQUAL"
    except Exception:
        # Malformed input must not expose object repr, SQL, token or tracebacks.
        # Unexpected failure is INCOMPLETE, never equality or empty success.
        result["errors"] = [{"code": "V2_INVALID_INPUT"}]
        result["checks"][phase] = "FAIL"
    return result
