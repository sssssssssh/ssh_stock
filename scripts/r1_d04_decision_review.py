"""Review a D04 draft in memory. Caller-provided provenance is not authentication."""

import hashlib
import json
import re
from datetime import datetime
from uuid import UUID

PROTOCOL = "r1.d04.business-decision-request.v1"
METHODS = ("NOT_SELECTED", "BASELINE_SNAPSHOT_ONCE_THEN_LOAD_TWICE",
           "EXPLICIT_PER_ARM_TIMESTAMP_MAPPING")
DECISIONS = tuple(f"D04-{n:02}" for n in range(1, 10))
CASES = tuple(f"C{n:02}" for n in range(1, 17))
FROZEN = (
    "data_quality_daily.checked_at", "stock_basic.updated_at", "stock_daily.source_updated_at",
    "stock_limit_daily.created_at", "stock_limit_daily.updated_at",
)
SCHEMA_REF = "docs/acceptance/r1_business_compare_schema_v1.json"
COPY_POLICY = [
    "JOB_UUID_TO_PUBLICATION_AND_METADATA",
    "EXECUTION_TOKEN_TO_PUBLICATION",
    "PUBLISHED_AT_TO_JOB_METADATA_PUBLICATION",
]
LIMITS = dict(bytes=1048576, depth=24, nodes=20000, text=2048, items=256, integer_bits=63)
SEQUENCE = {
    "columns": ["data_quality_daily.id", "sector.sector_id", "sector_member.id"],
    "state_fields": ["last_value", "is_called", "increment"],
    "generator_fields": ["algorithm", "state_sha256"],
    "status": "PENDING",
}
# Reviewed Git blobs. The fixture introduction and reviewed master are distinct commits.
SOURCE = {
    "reviewed_head_sha": "f7d8e264041db4f7d5600e1ce5b2bbd6b7ff0345",
    "historical_baseline_sha": "b6ffb7bf8ec7d26f771d9b89923e4f7e926edbed",
    "frozen_schema_sha256": "f6be0a5de1ce46e30758039a3ab345a308ff96cb36f6ee86ec3ccdc39759f297",
    "v2_commit_sha": "997f0a26f259424e3c566bff96bcae407e69f674",
    "d04_inventory_sha256": "25eac0b98acd3ac67046cf5be7a690b09b8ed790d59338df3f27316cf62eb65b",
    "d04_contract_sha256": "45f4d2e8d9c8c4aa8f144ff55b1794d9a0e50977e9e15789cc34d9ea57f9dcdc",
    "v2_oracle_sha256": "7351e99af94b9de89105d0a2ee9ec75b093f04a3c5ed09d1ed32627a7efda825",
    "v2_scenarios_sha256": "851365e3a60eb47b054c1e6da8fb83a99e4260069e510e13cca821225d0b98b7",
    "v2_contract_sha256": "610faf751e344b05732eb67310b39e0ced825376bd27301e8e58624d01a1734b",
}
CONTRACT_SHA = "ef936dc31c7ec87e3602f90c038d14737f9e4f43f8057b8d93b825d79c6d60d7"
QUESTIONS_SHA = "0159b1afd5e3fcb18b578eaaa1bcdb51f19a85582651900a99dcb06367c6c0e4"
SEED_SHA = "68168c5466fe48c9dc609b67fc7ab3b17fbab2b19aacfc211a5176e0b5b0bde5"
GOLDEN_SHA = "28d6a68b2600613a17549e86bec754d517d238915dc71c02f5da83dee645c858"
# Independent projections of the frozen datetime schema, in table/column order.
COLUMN_KEYS_SHA = "760fcce13be3edc4dfd3f47d7cffb740100430ec3cf93bbc7d52f1bf58e91e3a"
COLUMN_POLICY_SHA = "842e95e5cea34af9ae0657f803e7279f9be8c13104a03dfff403d3c0a2b8c50b"
EVIDENCE_KIND = "OFFLINE_OWNER_DECISION_REQUEST"
TRUST = "CALLER_SUPPLIED_NOT_AUTHENTICATED"
AUTHORITY = {
    "decision": "NO_GO", "authorization": "NOT_AUTHORIZED",
    "real_input_equal": False, "real_worker_output_equal": False, "performance_pass": False,
}
CHECKS = ("parse", "source", "contract", "fields", "inventory", "seed", "method", "golden")


class _Refused(ValueError):
    pass


def _require(condition, code):
    if not condition:
        raise _Refused(code)


def _fields(value, names, code="D04_FIELDS"):
    _require(type(value) is dict and set(value) == set(names.split()), code)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return _sha(raw)


def _hex(value, size=64):
    return type(value) is str and re.fullmatch(f"[0-9a-f]{{{size}}}", value) is not None


def _bounded(value):
    nodes = 0
    active = set()

    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        _require(depth <= LIMITS["depth"] and nodes <= LIMITS["nodes"], "D04_LIMIT")
        kind = type(item)
        if kind is str:
            _require(len(item) <= LIMITS["text"], "D04_LIMIT")
            _require(not any("\ud800" <= char <= "\udfff" for char in item), "D04_JSON")
        elif kind is int:
            _require(item.bit_length() <= LIMITS["integer_bits"], "D04_LIMIT")
        elif kind in (dict, list):
            identity = id(item)
            _require(identity not in active and len(item) <= LIMITS["items"], "D04_LIMIT")
            active.add(identity)
            if kind is dict:
                for key, child in item.items():
                    _require(type(key) is str, "D04_JSON")
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
            active.remove(identity)
        else:
            _require(kind is bool or item is None, "D04_JSON")

    visit(value, 1)


def _pairs(items):
    result = {}
    for key, value in items:
        _require(key not in result, "D04_JSON")
        result[key] = value
    return result


def _integer(text):
    _require(len(text.removeprefix("-")) <= 19, "D04_LIMIT")
    return int(text)


def _unsupported_number(_text):
    raise _Refused("D04_JSON")


def _parse(raw):
    _require(type(raw) is bytes, "D04_JSON")
    _require(len(raw) <= LIMITS["bytes"], "D04_LIMIT")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_int=_integer,
                           parse_constant=_unsupported_number, parse_float=_unsupported_number)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise _Refused("D04_JSON") from None
    except RecursionError:
        raise _Refused("D04_LIMIT") from None
    _bounded(value)
    return value


def _sources(request, expected, contract_raw, inventory_raw):
    _require(type(expected) is dict and set(expected) == set(SOURCE), "D04_SOURCE")
    _require(type(request) is dict and request.get("source") == expected, "D04_SOURCE")
    incoming_blobs = {"d04_inventory_sha256": inventory_raw, "d04_contract_sha256": contract_raw}
    for key, pinned in SOURCE.items():
        actual = expected[key]
        _require(_hex(actual, len(pinned)), "D04_SOURCE")
        # Check received bytes now. The protocol and inventory get their own semantic
        # checks before requiring the pinned raw digests.
        wanted = _sha(incoming_blobs[key]) if key in incoming_blobs else pinned
        _require(actual == wanted, "D04_SOURCE")


def _contract(contract, expected):
    _require(type(contract) is dict, "D04_CONTRACT")
    _require(contract.get("allowed_methods") == list(METHODS)
             and contract.get("decision_ids") == list(DECISIONS)
             and contract.get("limits") == LIMITS
             and _digest(contract) == CONTRACT_SHA, "D04_CONTRACT")
    _require(expected["d04_contract_sha256"] == SOURCE["d04_contract_sha256"], "D04_SOURCE")


def _inventory(inventory, expected):
    _fields(inventory, "schema_version frozen_schema_sha256 columns")
    _require(inventory["schema_version"] == "r1.d04.timestamp-inventory.v1"
             and inventory["frozen_schema_sha256"] == SOURCE["frozen_schema_sha256"], "D04_SOURCE")
    rows = inventory["columns"]
    _require(type(rows) is list and len(rows) == 49, "D04_TIMESTAMP_COVERAGE")
    keys, policies = [], []
    for row in rows:
        _fields(row, "table column source policy role timezone precision owner_decision "
                     "source_ref freeze event_mapping")
        table, column = row["table"], row["column"]
        _require(type(table) is str and type(column) is str, "D04_TIMESTAMP_COVERAGE")
        keys.append([table, column])
        policies.append([row["source"], row["policy"], row["source_ref"]])
        seed = f"{table}.{column}" in FROZEN
        role = ("SEED_INPUT" if seed else
                "ROOT_RUNTIME" if row["policy"] == "TIMESTAMP_EVENT_MAPPING" else "EVIDENCE")
        _require((row["role"] == "SEED_INPUT") == seed, "D04_FROZEN_COLUMNS")
        _require(row["role"] == role, "D04_SOURCE_POLICY")
        _require(row["timezone"] == "UTC" and row["precision"] == "microsecond", "D04_TIME_POLICY")
        _require(row["owner_decision"] == "PENDING", "D04_OWNER_NOT_SIGNED")
        _require(row["freeze"] == ("PENDING_OWNER_VALUE" if seed else "NOT_APPLICABLE")
                 and row["event_mapping"] == ("NOT_APPLICABLE" if role == "EVIDENCE"
                                              else "PENDING_OWNER_POLICY"), "D04_UNVERIFIED_CLAIM")
    _require(_digest(keys) == COLUMN_KEYS_SHA, "D04_TIMESTAMP_COVERAGE")
    _require(_digest(policies) == COLUMN_POLICY_SHA, "D04_SOURCE_POLICY")
    _require(expected["d04_inventory_sha256"] == SOURCE["d04_inventory_sha256"], "D04_SOURCE")


def _request_fields(request):
    _fields(request, "schema_version evidence_kind source decision authorization real_input_equal "
                     "real_worker_output_equal performance_pass reviewer signed_at seed questions "
                     "seed_times sequence_policy method golden")
    _require(request["schema_version"] == PROTOCOL and request["evidence_kind"] == EVIDENCE_KIND,
             "D04_CONTRACT")
    _require(all(type(request[key]) is type(value) and request[key] == value
                 for key, value in AUTHORITY.items()), "D04_AUTHORIZATION")
    _require(request["reviewer"] == request["signed_at"] == "NOT_SIGNED", "D04_OWNER_NOT_SIGNED")


def _seed(request):
    _fields(request["seed"], "fixture strategy_sha256 calendar_start calendar_end weekday_only "
                             "source_ref")
    _require(_digest(request["seed"]) == SEED_SHA, "D04_SEED_DRIFT")
    _require(request["sequence_policy"] == SEQUENCE, "D04_SEQUENCE_POLICY")
    times = request["seed_times"]
    _require(type(times) is list and len(times) == len(FROZEN), "D04_FROZEN_COLUMNS")
    for row, column in zip(times, FROZEN, strict=True):
        _fields(row, "column value")
        _require(row["column"] == column, "D04_FROZEN_COLUMNS")
        _require(row["value"] == "PENDING_OWNER_VALUE", "D04_UNVERIFIED_CLAIM")


def _questions(questions, selection):
    _require(type(questions) is list and len(questions) == len(DECISIONS), "D04_FIELDS")
    declarations = []
    state = {"owner_choice", "owner_reason", "reviewer", "signed_at"}
    for entry, decision in zip(questions, DECISIONS, strict=True):
        _fields(entry, "id background options recommendation risk evidence on_invalidation "
                       "owner_choice owner_reason reviewer signed_at")
        _require(entry["id"] == decision, "D04_FIELDS")
        _require(entry["owner_choice"] == (selection if decision == "D04-01" else "NOT_SELECTED"),
                 "D04_METHOD")
        _require(entry["owner_reason"] == "PENDING"
                 and entry["reviewer"] == entry["signed_at"] == "NOT_SIGNED",
                 "D04_OWNER_NOT_SIGNED")
        declarations.append({k: v for k, v in entry.items() if k not in state})
    _require(_digest(declarations) == QUESTIONS_SHA, "D04_FIELDS")


def _timestamp(text):
    _require(type(text) is str
             and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z",
                              text) is not None, "D04_TIME_POLICY")
    try:
        datetime.fromisoformat(text)
    except ValueError:
        raise _Refused("D04_TIME_POLICY") from None
    return text


def _event_id(text):
    _require(type(text) is str and len(text) == 36, "D04_IDENTITY_MAPPING")
    try:
        value = UUID(text)
    except ValueError:
        raise _Refused("D04_IDENTITY_MAPPING") from None
    _require(str(value) == text and value.int != 0, "D04_IDENTITY_MAPPING")
    return text


def _events(events):
    _require(len(events) == len(FROZEN), "D04_EVENT_CLOSURE")
    seen = set()
    for mapping, column in zip(events, FROZEN, strict=True):
        _fields(mapping, "column domain source_ref pairs")
        actual = mapping["column"]
        _require(type(actual) is str, "D04_TIME_POLICY")
        _require(actual.rsplit(".", 1)[-1] not in {
            "trade_date", "snapshot_date", "valid_from", "valid_to", "cal_date",
        }, "D04_BUSINESS_DATE_MAPPING")
        _require(actual == column, "D04_EVENT_CLOSURE")
        _require(mapping["domain"] == column, "D04_IDENTITY_MAPPING")
        table, field = column.split(".")
        _require(mapping["source_ref"] == f"{SCHEMA_REF}#tables/{table}/columns/{field}",
                 "D04_TIME_POLICY")
        pairs = mapping["pairs"]
        _require(type(pairs) is list and pairs, "D04_EVENT_CLOSURE")
        last = ("", "")
        for pair in pairs:
            _fields(pair, "left right left_id right_id")
            times = (_timestamp(pair["left"]), _timestamp(pair["right"]))
            _require(times[0] > last[0] and times[1] > last[1], "D04_TIME_MAPPING_AMBIGUOUS")
            last = times
            ids = {_event_id(pair["left_id"]), _event_id(pair["right_id"])}
            _require(len(ids) == 2 and seen.isdisjoint(ids), "D04_IDENTITY_MAPPING")
            seen.update(ids)


def _method(request):
    value = request["method"]
    _fields(value, "selection raw_byte_identical source_hash_policy arms events event_copy_policy")
    selection = value["selection"]
    _require(selection in METHODS, "D04_METHOD")
    _require(value["raw_byte_identical"] is False, "D04_RAW_CLAIM")
    _require(value["source_hash_policy"] == "PRESERVE_ORIGINAL", "D04_SOURCE_HASH_REWRITE")
    _require(value["event_copy_policy"] == COPY_POLICY, "D04_EVENT_CLOSURE")
    _questions(request["questions"], selection)
    arms, events = value["arms"], value["events"]
    _require(type(arms) is list and type(events) is list, "D04_METHOD")
    if selection == METHODS[0]:
        _require(not arms and not events, "D04_METHOD")
        return selection
    _require(len(arms) == 2, "D04_METHOD")
    for arm, label in zip(arms, ("OFF1", "ON1"), strict=True):
        _fields(arm, "arm raw_sha256 business_source_sha256")
        _require(arm["arm"] == label and _hex(arm["raw_sha256"])
                 and _hex(arm["business_source_sha256"]), "D04_SOURCE")
    _require(arms[0]["business_source_sha256"] == arms[1]["business_source_sha256"],
             "D04_SOURCE_HASH_REWRITE")
    same_raw = arms[0]["raw_sha256"] == arms[1]["raw_sha256"]
    if selection == METHODS[1]:
        _require(same_raw and not events, "D04_RAW_CLAIM")
    else:
        _require(not same_raw, "D04_RAW_CLAIM")
        _events(events)
    return selection


def _golden(cases):
    _require(type(cases) is list and len(cases) == len(CASES), "D04_GOLDEN_COVERAGE")
    for case, name in zip(cases, CASES, strict=True):
        _fields(case, "case_id observed_draft_status draft_error source_ref scope "
                      "policy_owner_decision business_semantics_approved financial_values_approved "
                      "review_note")
        pending = "EVENT_MAPPING_UNDECIDED" if name == "C11" else "PENDING"
        _require(case["case_id"] == name and case["policy_owner_decision"] == pending,
                 "D04_GOLDEN_COVERAGE")
        if name == "C11":
            _require(case["observed_draft_status"] == "PENDING_OWNER_DECISION",
                     "D04_GOLDEN_COVERAGE")
        _require(case["business_semantics_approved"] is False
                 and case["financial_values_approved"] is False, "D04_FALSE_BUSINESS_CLAIM")
    _require(_digest(cases) == GOLDEN_SHA, "D04_GOLDEN_STATUS_DRIFT")


def review_decision_request(
    request_bytes: bytes, contract_bytes: bytes, inventory_bytes: bytes, expected_source: dict,
) -> dict:
    """Check preparation only. No evidence of identity, execution or actual equivalence."""
    checks = dict.fromkeys(CHECKS, "NOT_RUN")
    result = dict(
        schema_version="r1.d04.review-result.v1", status="D04_BLOCKED", **AUTHORITY,
        owner_signature_verified=False, independent_reviewer_accepted=False,
        business_golden_approved=False, physical_proof="NOT_PROVEN", G05="MISSING",
        G08="PARTIAL", G09="PARTIAL", R1="PARTIAL", owner_state="OWNER_DECISION_PENDING",
        checks=checks, unresolved=list(DECISIONS), missing_fields=[], errors=[],
        source={"trust": TRUST}, counts={},
    )
    stage = "parse"
    try:
        request = _parse(request_bytes)
        contract = _parse(contract_bytes)
        inventory = _parse(inventory_bytes)
        _bounded(expected_source)
        checks[stage] = "PASS"
        stage = "source"
        _sources(request, expected_source, contract_bytes, inventory_bytes)
        checks[stage] = "PASS"
        stage = "contract"
        _contract(contract, expected_source)
        checks[stage] = "PASS"
        stage = "fields"
        _request_fields(request)
        checks[stage] = "PASS"
        stage = "inventory"
        _inventory(inventory, expected_source)
        checks[stage] = "PASS"
        stage = "seed"
        _seed(request)
        checks[stage] = "PASS"
        stage = "method"
        selection = _method(request)
        checks[stage] = "PASS"
        stage = "golden"
        _golden(request["golden"])
        checks[stage] = "PASS"
    except _Refused as error:
        checks[stage] = "REJECT"
        result["errors"] = [str(error)]
        return result
    result.update(
        status="READY_FOR_OWNER_REVIEW", structure_status="PACKET_STRUCTURALLY_VALID",
        proposed_method=selection, source={"trust": TRUST, **SOURCE},
        counts={"timestamp_columns": 49, "seed_frozen_columns": 5, "golden_cases": 16},
        missing_fields=[
            *(f"{decision}.owner_choice" for decision in DECISIONS
              if decision != "D04-01" or selection == METHODS[0]),
            "D04-02.seed_times", "D04-03.event_policy", "D04-04.sequence_and_generator_state",
            "D04-07.case_reviews", "D04-08.typed_original_evidence",
            "D04-09.owner_signature", "D04-09.independent_review",
        ],
    )
    return result


def summarize_unresolved(
    request_bytes: bytes, contract_bytes: bytes, inventory_bytes: bytes, expected_source: dict,
) -> dict:
    """Return the same bounded receipt with stable unresolved IDs and field names."""
    return review_decision_request(request_bytes, contract_bytes, inventory_bytes, expected_source)
