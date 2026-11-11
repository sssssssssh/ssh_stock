"""Offline D04 review and independent Git-blob source checks."""

import ast
import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import r1_d04_decision_review as review

ROOT = Path(__file__).resolve().parents[2]
BASE = "f7d8e264041db4f7d5600e1ce5b2bbd6b7ff0345"
V2 = "997f0a26f259424e3c566bff96bcae407e69f674"
SCHEMA = "docs/acceptance/r1_business_compare_schema_v1.json"
FROZEN = {
    "stock_basic.updated_at", "stock_daily.source_updated_at", "stock_limit_daily.created_at",
    "stock_limit_daily.updated_at", "data_quality_daily.checked_at",
}
FIXTURES = "tests/fixtures/r1_reviewed_snapshot_v2/"


def blob(path, sha=BASE):
    return subprocess.check_output(["git", "cat-file", "blob", f"{sha}:{path}"], cwd=ROOT)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def wire(value):
    return json.dumps(value, ensure_ascii=False).encode()


@pytest.fixture(scope="module")
def original_packet():
    def read(name):
        return (ROOT / f"docs/acceptance/r1_d04_{name}_v1.json").read_bytes()

    contract, inventory = read("decision_contract"), read("timestamp_inventory")
    source = {
        "reviewed_head_sha": BASE,
        "historical_baseline_sha": "b6ffb7bf8ec7d26f771d9b89923e4f7e926edbed",
        "frozen_schema_sha256": digest(blob(SCHEMA)),
        "v2_commit_sha": V2,
        "d04_inventory_sha256": digest(inventory),
        "d04_contract_sha256": digest(contract),
        "v2_oracle_sha256": digest(blob(FIXTURES + "expected_oracle_v2.json", V2)),
        "v2_scenarios_sha256": digest(blob(FIXTURES + "scenarios_v2.json", V2)),
        "v2_contract_sha256": digest(blob(FIXTURES + "evidence_contract_v2.json", V2)),
    }
    return json.loads(read("decision_request")), contract, inventory, source


@pytest.fixture
def packet(original_packet):
    return deepcopy(original_packet)


def run(packet):
    request, contract, inventory, source = packet
    return review.review_decision_request(
        request if type(request) is bytes else wire(request), contract, inventory, source
    )


def refused(result, code):
    assert result["status"] == "D04_BLOCKED"
    assert result["errors"] == [code]
    states = list(result["checks"].values())
    failure = states.index("REJECT")
    assert states[:failure] == ["PASS"] * failure
    assert all(s == "NOT_RUN" for s in states[failure + 1:])
    assert_safe(result)


def assert_safe(result):
    assert result["decision"] == "NO_GO" and result["authorization"] == "NOT_AUTHORIZED"
    for k in ("owner_signature_verified", "independent_reviewer_accepted",
              "business_golden_approved", "real_input_equal", "real_worker_output_equal",
              "performance_pass"):
        assert result[k] is False
    assert [result[k] for k in ("physical_proof", "G05", "G08", "G09")] == [
        "NOT_PROVEN", "MISSING", "PARTIAL", "PARTIAL",
    ]


def test_T01_T29_pending_replay_and_independent_inventory(packet):
    result = run(packet)
    assert result["status"] == "READY_FOR_OWNER_REVIEW"
    assert result["owner_state"] == "OWNER_DECISION_PENDING"
    assert result["unresolved"] == [f"D04-{i:02d}" for i in range(1, 10)]
    assert_safe(result)
    before = deepcopy(packet)
    assert run(packet) == result and packet == before
    assert review.summarize_unresolved(wire(packet[0]), *packet[1:]) == result
    schema = json.loads(blob(SCHEMA))
    expected = {(t, c): (r["source"], r["policy"])
                for t, v in schema["tables"].items() for c, r in v["columns"].items()
                if r["type"] == "datetime"}
    rows = json.loads(packet[2])["columns"]
    assert len(rows) == len(expected) == 49
    assert [(r["table"], r["column"]) for r in rows] == sorted(expected)
    assert {(r["table"], r["column"]): (r["source"], r["policy"]) for r in rows} == expected
    assert {r["table"] + "." + r["column"] for r in rows if r["role"] == "SEED_INPUT"} == FROZEN
    for r in rows:
        key = r["table"] + "." + r["column"]
        role = "SEED_INPUT" if key in FROZEN else (
            "ROOT_RUNTIME" if r["policy"] == "TIMESTAMP_EVENT_MAPPING" else "EVIDENCE"
        )
        assert r["role"] == role
    assert digest(packet[2]) == "25eac0b98acd3ac67046cf5be7a690b09b8ed790d59338df3f27316cf62eb65b"
    assert digest(packet[1]) == "45f4d2e8d9c8c4aa8f144ff55b1794d9a0e50977e9e15789cc34d9ea57f9dcdc"


@pytest.mark.parametrize(("raw", "code"), [
    (b'{"a":1,"a":2}', "D04_JSON"), (b'{"a":NaN}', "D04_JSON"),
    (b'{"a":Infinity}', "D04_JSON"), (b'{"a":1e999}', "D04_JSON"),
    (b'\xff', "D04_JSON"), (b" " * 1048577, "D04_LIMIT"),
    (b"[" * 25 + b"]" * 25, "D04_LIMIT"),
    (wire([[0] * 100] * 200), "D04_LIMIT"),
    (wire([0] * 257), "D04_LIMIT"), (wire("a" * 2049), "D04_LIMIT"),
    (b'{"a":999999999999999999999999}', "D04_LIMIT"),
    (b'{"a":"\\ud800"}', "D04_JSON"),
], ids=[
    "duplicate-key", "nan", "infinity", "overflow-float", "utf8", "bytes",
    "depth", "nodes", "items", "text", "integer", "surrogate",
])
def test_T02_T03_json_and_limits(packet, raw, code):
    refused(run((raw, *packet[1:])), code)


@pytest.mark.parametrize(("section", "key", "value", "code"), [
    ("", "authorization", "GRANTED", "D04_AUTHORIZATION"),
    ("", "decision", "GO", "D04_AUTHORIZATION"),
    ("", "real_worker_output_equal", True, "D04_AUTHORIZATION"),
    ("", "real_input_equal", True, "D04_AUTHORIZATION"),
    ("", "owner_approved", True, "D04_FIELDS"),
    ("", "reviewer", "private-dsn-SECRET-SQL", "D04_OWNER_NOT_SIGNED"),
    ("method", "selection", ["A", "B"], "D04_METHOD"),
    ("method", "selection", "BOTH", "D04_METHOD"),
    ("method", "selection", "NONE", "D04_METHOD"),
    ("method", "event_copy_policy", [], "D04_EVENT_CLOSURE"),
    ("seed", "fixture", {}, "D04_SEED_DRIFT"),
    ("seed", "strategy_sha256", "a" * 64, "D04_SEED_DRIFT"),
    ("sequence_policy", "columns", [], "D04_SEQUENCE_POLICY"),
    ("sequence_policy", "state_fields", ["last_value"], "D04_SEQUENCE_POLICY"),
    ("sequence_policy", "generator_fields", [], "D04_SEQUENCE_POLICY"),
    ("golden", "financial_values_approved", "FINANCIAL_CALCULATION_VERIFIED",
     "D04_FALSE_BUSINESS_CLAIM"),
])
def test_request_mutations_T04_T13_T19_T20_T21_T23_T25_T26_T28(
    packet, section, key, value, code
):
    target = packet[0] if not section else packet[0][section]
    if section == "golden":
        target = target[0]
    target[key] = value
    result = run(packet)
    refused(result, code)
    assert "private-dsn-SECRET-SQL" not in json.dumps(result)


@pytest.mark.parametrize("field", ["frozen_schema_sha256", "v2_commit_sha",
                                  "historical_baseline_sha"])
def test_T05_rebound_old_sources(packet, field):
    packet[3][field] = "a" * len(packet[3][field])
    packet[0]["source"][field] = packet[3][field]
    refused(run(packet), "D04_SOURCE")


def test_T06_rebound_contract_and_both_arms(packet):
    r, c, i, source = packet
    c = json.loads(c)
    c["allowed_methods"] = ["BOTH"]
    c = wire(c)
    source["d04_contract_sha256"] = r["source"]["d04_contract_sha256"] = digest(c)
    r["method"]["arms"] = [{"arm": "OFF1"}, {"arm": "ON1"}]
    refused(run((r, c, i, source)), "D04_CONTRACT")


@pytest.mark.parametrize(("mutation", "code"), [
    ("short", "D04_TIMESTAMP_COVERAGE"), ("long", "D04_TIMESTAMP_COVERAGE"),
    ("duplicate", "D04_TIMESTAMP_COVERAGE"), ("replacement", "D04_TIMESTAMP_COVERAGE"),
    ("order", "D04_TIMESTAMP_COVERAGE"), ("seed", "D04_FROZEN_COLUMNS"),
    ("extra_seed", "D04_FROZEN_COLUMNS"), ("source", "D04_SOURCE_POLICY"),
    ("timezone", "D04_TIME_POLICY"), ("precision", "D04_TIME_POLICY"),
    ("owner", "D04_OWNER_NOT_SIGNED"), ("field", "D04_FIELDS"),
])
def test_T07_T12_T29_inventory_mutations(packet, mutation, code):
    r, c, i, source = packet
    inventory = json.loads(i)
    rows = inventory["columns"]
    if mutation == "short":
        rows.pop()
    elif mutation == "long":
        rows.append(deepcopy(rows[0]))
    elif mutation == "duplicate":
        rows[0] = deepcopy(rows[1])
    elif mutation == "replacement":
        rows[0]["column"] = "unregistered"
    elif mutation == "order":
        rows.reverse()
    elif mutation == "seed":
        next(x for x in rows if x["role"] == "SEED_INPUT")["role"] = "ROOT_RUNTIME"
    elif mutation == "extra_seed":
        next(x for x in rows if x["role"] == "EVIDENCE")["role"] = "SEED_INPUT"
    elif mutation == "source":
        rows[0]["source"]["line"] += 1
    elif mutation == "timezone":
        rows[0]["timezone"] = "+08:00"
    elif mutation == "precision":
        rows[0]["precision"] = "second"
    elif mutation == "owner":
        rows[0]["owner_decision"] = "APPROVED"
    else:
        del rows[0]["source_ref"]
    raw = wire(inventory)
    source["d04_inventory_sha256"] = r["source"]["d04_inventory_sha256"] = digest(raw)
    refused(run((r, c, raw, source)), code)


def choose(request, method):
    selection = {"A": "BASELINE_SNAPSHOT_ONCE_THEN_LOAD_TWICE",
                 "B": "EXPLICIT_PER_ARM_TIMESTAMP_MAPPING"}[method]
    request["questions"][0]["owner_choice"] = selection
    proposal = request["method"]
    proposal["selection"] = selection
    proposal["arms"] = [
        dict(arm=arm, raw_sha256=raw * 64, business_source_sha256="c" * 64)
        for arm, raw in [("OFF1", "a"), ("ON1", "a" if method == "A" else "b")]
    ]
    if method == "B":
        proposal["events"] = [
            dict(column=k, domain=k,
                 source_ref=f"{SCHEMA}#tables/{k.replace('.', '/columns/')}", pairs=[
                dict(left=f"2026-02-24T00:00:0{n}.000001Z",
                     right=f"2026-02-24T00:00:0{n}.000002Z",
                     left_id=f"00000000-0000-0000-0000-{100*j+n:012d}",
                     right_id=f"00000000-0000-0000-0000-{100*j+n+10:012d}")
                for n in (1, 2)
            ]) for j, k in enumerate(sorted(FROZEN))
        ]
    return proposal


@pytest.mark.parametrize("method", ["A", "B"])
def test_candidate_shapes_remain_pending(packet, method):
    choose(packet[0], method)
    result = run(packet)
    assert result["status"] == "READY_FOR_OWNER_REVIEW"
    assert result["owner_state"] == "OWNER_DECISION_PENDING"
    assert result["proposed_method"] == packet[0]["method"]["selection"]
    assert_safe(result)


@pytest.mark.parametrize(("mutation", "code"), [
    ("raw", "D04_RAW_CLAIM"), ("rewrite", "D04_SOURCE_HASH_REWRITE"),
    ("source_hash", "D04_SOURCE_HASH_REWRITE"),
    ("many_to_one", "D04_TIME_MAPPING_AMBIGUOUS"),
    ("one_to_many", "D04_TIME_MAPPING_AMBIGUOUS"),
    ("reverse", "D04_TIME_MAPPING_AMBIGUOUS"), ("date", "D04_BUSINESS_DATE_MAPPING"),
    ("identity", "D04_IDENTITY_MAPPING"), ("cross_domain", "D04_IDENTITY_MAPPING"),
    ("invalid", "D04_TIME_POLICY"), ("copy", "D04_EVENT_CLOSURE"),
    ("missing", "D04_EVENT_CLOSURE"), ("source", "D04_TIME_POLICY"),
])
def test_T15_T19_T27_candidate_rejections(packet, mutation, code):
    proposal = choose(packet[0], "B")
    first = proposal["events"][0]
    a, b = first["pairs"]
    if mutation == "raw":
        proposal["raw_byte_identical"] = True
    elif mutation == "rewrite":
        proposal["source_hash_policy"] = "NORMALIZE"
    elif mutation == "source_hash":
        proposal["arms"][1]["business_source_sha256"] = "d" * 64
    elif mutation == "many_to_one":
        b["right"] = a["right"]
    elif mutation == "one_to_many":
        b["left"] = a["left"]
    elif mutation == "reverse":
        a["right"], b["right"] = b["right"], a["right"]
    elif mutation == "date":
        first["column"] = "stock_daily.trade_date"
    elif mutation == "identity":
        first["domain"] = "job"
    elif mutation == "cross_domain":
        proposal["events"][1]["pairs"][0]["left_id"] = a["left_id"]
    elif mutation == "invalid":
        a["left"] = "2026-02-30T00:00:00.000000Z"
    elif mutation == "copy":
        proposal["event_copy_policy"].pop()
    elif mutation == "source":
        first["source_ref"] = ""
    else:
        proposal["events"].pop()
    refused(run(packet), code)


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "repeat", "c11", "c12", "c13", "c15", "c16"],
)
def test_T22_T24_golden_drift(packet, mutation):
    cases = packet[0]["golden"]
    if mutation == "missing":
        cases.pop()
    elif mutation == "extra":
        cases.append(deepcopy(cases[0]))
    elif mutation == "repeat":
        cases[0]["case_id"] = "C02"
    elif mutation == "c11":
        cases[10]["policy_owner_decision"] = "APPROVED"
    else:
        cases[int(mutation[1:])-1]["observed_draft_status"] = "OFFLINE_ORACLE_MATCH"
    refused(run(packet), "D04_GOLDEN_STATUS_DRIFT" if mutation in {
        "c12", "c13", "c15", "c16",
    } else "D04_GOLDEN_COVERAGE")


def test_T04_missing_and_T03_cycle(packet):
    del packet[0]["seed"]
    refused(run(packet), "D04_FIELDS")
    packet[3]["cycle"] = packet[3]
    refused(run(packet), "D04_LIMIT")


def test_T09_unverified_frozen_time(packet):
    packet[0]["seed_times"][0]["value"] = "2026-02-24T00:00:00.000000Z"
    refused(run(packet), "D04_UNVERIFIED_CLAIM")


def test_T14_a_still_requires_complete_sequence_policy(packet):
    choose(packet[0], "A")
    packet[0]["sequence_policy"]["state_fields"].remove("is_called")
    refused(run(packet), "D04_SEQUENCE_POLICY")


def test_T22_oracle_metadata_matches_raw_blob(packet):
    oracle = json.loads(blob(FIXTURES + "expected_oracle_v2.json"))
    assert oracle["approval"] == "PENDING_D04" and oracle["reviewer"] == "NOT_SIGNED"
    assert [(c["case_id"], c["observed_draft_status"], c["draft_error"])
            for c in packet[0]["golden"]] == [
        (c["case_id"], c["expected_status"], c["expected_error"]) for c in oracle["cases"]
    ]


def test_T30_imports_and_review_stay_in_memory(packet, monkeypatch):
    import os
    import socket

    tree = ast.parse((ROOT / "scripts/r1_d04_decision_review.py").read_bytes())
    imports = {alias.name for n in ast.walk(tree) if isinstance(n, ast.Import)
               for alias in n.names}
    imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imports == {"hashlib", "json", "re", "datetime", "uuid"}

    def denied(*args, **kwargs):
        pytest.fail("unexpected I/O from D04 review")

    with monkeypatch.context() as m:
        m.setattr("builtins.open", denied)
        m.setattr(os, "getenv", denied)
        m.setattr(socket, "socket", denied)
        m.setattr(subprocess, "Popen", denied)
        result = run(packet)
    assert result["status"] == "READY_FOR_OWNER_REVIEW"


def test_T30_old_bridge_still_rejects_real_exports():
    from scripts.r1_integration_pg_export import ExportResult, compare_fake_exports
    from scripts.r1_real_root_protocol import Refused

    packet = ExportResult({}, "PG_TYPED_UNVERIFIED", "", "", {}, False, 0, "")
    with pytest.raises(Refused, match="^REAL_COMPARATOR_BRIDGE_NOT_AUTHORIZED$"):
        compare_fake_exports(packet, packet, {}, {}, {})
