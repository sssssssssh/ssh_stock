"""Independent v2 oracle tests; fixtures are hand-drafted, never snapshot-updated."""

import ast
import copy
import hashlib
import importlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/r1_reviewed_snapshot_v2"
FIXTURE_HASHES = {
    "evidence_contract_v2.json": (
        "610faf751e344b05732eb67310b39e0ced825376bd27301e8e58624d01a1734b",
        "d0d257282a6ee4e101c7867f732304a866d8da45d78db562042f9da9e4cb6df4",
    ),
    "expected_oracle_v2.json": (
        "7351e99af94b9de89105d0a2ee9ec75b093f04a3c5ed09d1ed32627a7efda825",
        "fe22b72acd8a45b746be0531ab6c0defc11d1b91c908f835990ab95b5e68f4d1",
    ),
    "scenarios_v2.json": (
        "851365e3a60eb47b054c1e6da8fb83a99e4260069e510e13cca821225d0b98b7",
        "83588db09dc50a6cf19eaea4f34ea5447f943ece7d2db4f461137fd0e99fad1e",
    ),
}
FROZEN = {
    "scripts/r1_real_root_protocol.py": (
        "7e3f40d4452a9dc4a7b373b089c5f11ae9b213b163ac0c00fb2b3312cf0d997e",
        "415a2d8484413a9bede2e48cf299dda390e9d517a01d9946fa4ba2c82dc4e31f",
    ),
    "scripts/r1_business_snapshot_contract.py": (
        "7219c0ffb405f01c3f9af973bf8b38665f1a02afd32361aab30cf67ab132d74a",
        "929b83ef9f31269f9b2a4d393f6f5fc142eb5b0c63e001c12b5a05a21a6dc225",
    ),
    "scripts/r1_integration_pg_export.py": (
        "d9e1ccceca3c4d0b782302922ab430416e4e6cb17405148eabf062615d32fcf7",
        "c844decef905a1c353feb351d3b6b7ee3e3ac9cbe6ba0b9882eaf92fc0e8b65c",
    ),
    "scripts/r1_seed_snapshot_recipe.py": (
        "06d7a34b2a99139e1f7e66a593ccd03c9195098cd1252defb057242058a02f4c",
        "c3ed636e3fe3e7990270b8f602a5c4f82d7d62d704ccadd9de0de0e7d34ad01d",
    ),
    "scripts/r1_integration_seed_loader.py": (
        "6a8cd5ae64a81fa2d9bd992e2820616248ccba521f27740686743ab949f41a2e",
        "5d000bb6bbf7c4a6c8047638b2db6de05b4631f2cba35215fef9c235bb3c04de",
    ),
    "docs/acceptance/r1_business_compare_schema_v1.json": (
        "f6be0a5de1ce46e30758039a3ab345a308ff96cb36f6ee86ec3ccdc39759f297",
        "e023206e7209ff96ebeb0417dbd516a061c9dc58aee4bf98e9f63fc84e04ea47",
    ),
    "tests/unit/test_r1_business_snapshot_contract.py": (
        "5f9f0e6d19b2c2db8fda50d17fa0fd8f20ab0a8504ff8e89653cdf9a7548ac1e",
        "5bb0a63736ad24fe55a6393545c165d04bdc46be0555e1e80aa4f49fcd521124",
    ),
    "tests/unit/test_r1_integration_pg_export.py": (
        "16b90d44a26057c92bc3482e2cffd0058db468f5302f60b3ce047f02de81e7d6",
        "34ba5a2daf6f2f8f0bfddae4c5fb37bdd435adcd3df46c1e70cdf36050f7215c",
    ),
}


def module():
    return importlib.import_module("scripts.r1_reviewed_snapshot_v2")


def material(case_id="C01"):
    contract = (FIXTURES / "evidence_contract_v2.json").read_bytes()
    oracle = (FIXTURES / "expected_oracle_v2.json").read_bytes()
    source = (FIXTURES / "scenarios_v2.json").read_bytes()
    for name, raw in (
        ("evidence_contract_v2.json", contract),
        ("expected_oracle_v2.json", oracle),
        ("scenarios_v2.json", source),
    ):
        if hashlib.sha256(raw).hexdigest() not in FIXTURE_HASHES[name]:
            raise AssertionError("V2_FIXED_DRAFT_BYTES_CHANGED")
    scenarios = json.loads(source)
    case = next(c for c in scenarios["cases"] if c["case_id"] == case_id)
    provenance = {
        **scenarios["source_context"],
        "contract_sha256": hashlib.sha256(contract).hexdigest(),
        "golden_sha256": hashlib.sha256(oracle).hexdigest(),
        "fixture_sha256": hashlib.sha256(source).hexdigest(),
        "tool_identity_sha256": hashlib.sha256(
            (ROOT / "scripts/r1_reviewed_snapshot_v2.py").read_bytes()
        ).hexdigest(),
    }

    def expand(value, identities):
        if type(value) is dict:
            return {k: expand(v, identities) for k, v in value.items()}
        if type(value) is list:
            return [expand(v, identities) for v in value]
        return identities.get(value, value) if type(value) is str else value

    packets = []
    for arm in ("OFFLINE_LEFT", "OFFLINE_RIGHT"):
        packet = expand(scenarios["packet"], scenarios["identities"][arm])
        packet["source_context"] = copy.deepcopy(provenance)
        packet["subject"]["case_id"] = case_id
        packet["subject"]["arm"] = arm
        packet["domains"]["BUSINESS_EXPECTATION"]["case_id"] = case_id
        for operation in case["changes"]:
            target = packet
            for key in operation["path"][:-1]:
                target = target[key]
            key = operation["path"][-1]
            value = expand(operation["value"], scenarios["identities"][arm])
            if type(target) is list and value is None:
                target.pop(key)
            elif type(target) is list and key == len(target):
                target.append(value)
            else:
                target[key] = value
        packets.append(packet)
    return packets, oracle, contract, provenance


def review(case_id="C01", mutate=None):
    api = module()  # RED must fail for missing v2 capability, before fixture I/O.
    packets, oracle, contract, provenance = material(case_id)
    if mutate:
        mutate(packets)
    return api.review_pair(*packets, oracle, contract, provenance)


def rows(packet):
    return packet["domains"]["TYPED_OUTPUT"]["rows"]


def row(packet, table):
    return next(r["values"] for r in rows(packet) if r["table"] == table)


class ReviewedEvidenceTests(unittest.TestCase):
    def rejected(self, mutate, code=None, *, case_id="C01"):
        result = review(case_id, mutate)
        self.assertIn(result["status"], ("UNEQUAL", "INCOMPLETE"))
        self.assertFalse(result["oracle_match"])
        self.assertEqual(result["decision"], "NO_GO")
        self.assertEqual(len(result["errors"]), 1)
        if code:
            self.assertEqual(result["errors"], [{"code": code}])
        return result

    def test_T01_all_top_level_and_nested_fields_are_exact(self):
        prototype = material()[0][0]
        for key in prototype:
            with self.subTest(missing=key):
                self.rejected(lambda p, key=key: p[0].pop(key), "V2_FIELDS")
        self.rejected(lambda p: p[0].update(approved=True), "V2_FIELDS")
        for path in (
            ("subject",),
            ("domains", "RAW_INPUT"),
            ("domains", "TYPED_OUTPUT"),
            ("domains", "BUSINESS_EXPECTATION"),
            ("domains", "TELEMETRY"),
        ):
            with self.subTest(path=path):

                def mutate(p, path=path):
                    item = p[0]
                    for key in path:
                        item = item[key]
                    item["unknown"] = True

                self.rejected(mutate)

    def test_T06_same_wrong_values_cannot_self_certify(self):
        result = review("C14")
        self.assertEqual(result["status"], "UNEQUAL")
        self.assertEqual(result["errors"], [{"code": "V2_ORACLE_MISMATCH"}])

    def test_T02_wrong_evidence_kind_is_refused(self):
        result = review(mutate=lambda packets: packets[0].update(evidence_kind="SYNTHETIC_ONLY"))
        self.assertEqual(result["errors"], [{"code": "V2_PROTOCOL"}])
        self.assertEqual(result["decision"], "NO_GO")

    def test_T12_D04_never_becomes_real_equality(self):
        result = review("C11")
        self.assertEqual(result["status"], "PENDING_OWNER_DECISION")
        self.assertFalse(result["real_pg_input_equal"])
        self.assertFalse(result["real_worker_output_equal"])

    def test_T03_v2_and_unverified_pg_cannot_enter_old_fake_bridge(self):
        from scripts import r1_business_snapshot_contract as old
        from scripts import r1_integration_pg_export as export
        from scripts.r1_real_root_protocol import Refused

        packet = material()[0][0]
        old_result = old.compare_snapshots(packet, packet, {})
        self.assertFalse(old_result["equal"])
        self.assertEqual(old_result["decision"], "NO_GO")
        unverified = export.ExportResult({}, "PG_TYPED_UNVERIFIED", "", "", {}, False, 0, "")
        for wrong in (packet, unverified):
            with self.subTest(kind=type(wrong).__name__):
                with self.assertRaisesRegex(Refused, "^REAL_COMPARATOR_BRIDGE_NOT_AUTHORIZED$"):
                    export.compare_fake_exports(wrong, wrong, {}, {}, {})

    def test_T04_self_approval_and_physical_claims_are_denied(self):
        for claim in ("APPROVED", "AUTHORIZED", "PERMIT", True):
            with self.subTest(authorization=claim):
                self.rejected(
                    lambda p, claim=claim: p[0].update(authorization=claim), "V2_AUTHORIZATION"
                )
        for key in module().CONTROLS:
            with self.subTest(control=key):
                self.rejected(
                    lambda p, key=key: p[0]["controls"].update({key: "VERIFIED"}),
                    "V2_PHYSICAL_CLAIM",
                )

    def test_T05_double_source_drift_and_modified_golden_are_rejected(self):
        for field in module().SOURCE_FIELDS:
            with self.subTest(field=field):

                def mutate(p, field=field):
                    for packet in p:
                        packet["source_context"][field] = "0" * 64

                self.rejected(mutate, "V2_SOURCE")
        packets, oracle, contract, provenance = material()
        changed = json.loads(oracle)
        changed["approval"] = "APPROVED"
        changed_raw = json.dumps(changed).encode()
        for packet in packets:
            packet["source_context"]["golden_sha256"] = hashlib.sha256(changed_raw).hexdigest()
        result = module().review_pair(*packets, changed_raw, contract, provenance)
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertFalse(result["oracle_match"])

    def test_T07_domains_and_bijections_cannot_collapse(self):
        oracle = json.loads(material()[1])
        for domain in module().IDENTITIES:
            if not oracle["identities"][domain]:
                continue
            bad = copy.deepcopy(oracle["identities"])
            entry = copy.deepcopy(bad[domain][0])
            entry["role"] = "other-role"
            bad[domain].append(entry)
            with self.subTest(domain=domain):
                with self.assertRaises(module().Refused):
                    module()._identities(bad)
        self.rejected(
            lambda p: p[0]["subject"].update(execution_token=p[0]["subject"]["root_id"]),
            "V2_IDENTITY",
        )
        self.rejected(
            lambda p: row(p[0], "data_publication")["execution_token"].update(
                domain="job", value=p[0]["subject"]["root_id"]
            ),
            "V2_REFERENCE",
        )

    def test_T08_fk_and_non_fk_json_sector_theme_references(self):
        self.rejected(
            lambda p: row(p[0], "job_run")["job_metadata"]["value"]["calc_run_id"].update(
                value="00000000-0000-0000-0000-000000000099"
            ),
            "V2_REFERENCE",
        )
        self.rejected(
            lambda p: row(p[0], "data_publication_source")["source_job_id"].update(
                domain="token", value=p[0]["subject"]["execution_token"]
            ),
            "V2_REFERENCE",
        )
        for key, value in (("primary_sector_id", 102), ("primary_theme_code", "MISSING-THEME")):
            with self.subTest(reference=key):
                self.rejected(
                    lambda p, key=key, value=value: row(p[0], "stock_opportunity_daily")[
                        key
                    ].update(value=value),
                    "V2_REFERENCE",
                    case_id="C08",
                )

    def test_T09_all_seven_absent_empty_zero_states_are_distinct(self):
        keys = ("sql_null", "json_null", "missing", "empty_text", "empty_array", "zero", "false")
        probe = row(material()[0][0], "synthetic_type_probe")
        for key in keys:
            for other in keys:
                if key == other:
                    continue
                with self.subTest(destination=key, source=other):
                    self.rejected(
                        lambda p, key=key, other=other: row(p[0], "synthetic_type_probe").update(
                            {key: copy.deepcopy(probe[other])}
                        ),
                        "V2_ORACLE_MISMATCH",
                    )

    def test_T10_decimal_scale_signed_zero_and_bool_int_are_exact(self):
        for key, value in (("decimal", "1.0"), ("float", "0x0.0p+0")):
            with self.subTest(cell=key):
                self.rejected(
                    lambda p, key=key, value=value: row(p[0], "synthetic_type_probe")[key].update(
                        value=value
                    ),
                    "V2_ORACLE_MISMATCH",
                )
        self.rejected(
            lambda p: row(p[0], "synthetic_type_probe")["zero"].update(value=False), "V2_TYPE"
        )
        self.rejected(
            lambda p: row(p[0], "synthetic_type_probe")["false"].update(value=0), "V2_TYPE"
        )

    def test_T11_nonfinite_and_noncanonical_date_time_are_denied(self):
        for value in ("nan", "inf", "-inf", "1.0", "0x1p+0"):
            with self.subTest(value=value):
                self.rejected(
                    lambda p, value=value: row(p[0], "synthetic_type_probe")["float"].update(
                        value=value
                    ),
                    "V2_TYPE",
                )
        for value in (
            "2026-02-24T01:02:03",
            "2026-02-24T01:02:03.000001+08:00",
            "2026-02-30T01:02:03.000001Z",
            "2026-02-24T01:02:03Z",
        ):
            with self.subTest(time=value):
                self.rejected(
                    lambda p, value=value: row(p[0], "synthetic_type_probe")["datetime"].update(
                        value=value
                    ),
                    "V2_TIME",
                )

    def test_T13_tombstone_original_candidate_and_public_copies(self):
        self.rejected(
            lambda p: row(p[0], "data_publication_row")["is_deleted"].update(value=True),
            "V2_CANDIDATE",
        )
        self.rejected(
            lambda p: row(p[0], "data_publication_preimage")["row_data"]["value"]["ma20"].update(
                value="0x1.8000000000000p+0"
            ),
            "V2_PREIMAGE",
        )
        self.rejected(
            lambda p: row(p[0], "stock_factor_daily")["ma20"].update(value="0x1.8000000000000p+0"),
            "V2_CANDIDATE",
        )
        self.rejected(
            lambda p: row(p[0], "data_publication_row").update(row_data={"type": "json_null"}),
            "V2_CANDIDATE",
            case_id="C06",
        )

    def test_T14_scope_multiplicity_order_ordinal_and_range(self):
        self.rejected(
            lambda p: p[0]["domains"]["TYPED_OUTPUT"]["rows"].pop(),
            "V2_ORACLE_MISMATCH",
            case_id="C07",
        )
        self.rejected(
            lambda p: p[0]["domains"]["TYPED_OUTPUT"]["rows"][-1].update(ordinal=0),
            "V2_SCOPE",
            case_id="C07",
        )
        self.rejected(
            lambda p: row(p[0], "data_publication_scope")["start_date"].update(value="2026-02-25"),
            "V2_SCOPE",
        )

    def test_T15_three_lifecycles_cannot_be_relabelled(self):
        for case_id in ("C02", "C03"):
            with self.subTest(case_id=case_id):
                self.rejected(
                    lambda p: p[0]["subject"].update(lifecycle="SUCCESS"),
                    "V2_LIFECYCLE",
                    case_id=case_id,
                )
        self.rejected(
            lambda p: row(p[0], "job_run")["cancel_requested"].update(value=False),
            "V2_LIFECYCLE",
            case_id="C03",
        )

    def test_T16_unknown_ack_and_heartbeat_are_not_usable(self):
        result = review("C04")
        self.assertEqual(result["errors"], [{"code": "V2_ACK_UNKNOWN"}])
        self.assertEqual(result["checks"]["expectation"], "NOT_RUN")
        self.rejected(
            lambda p: p[0]["domains"]["TELEMETRY"].update(heartbeat="UNKNOWN"),
            "V2_HEARTBEAT_UNKNOWN",
        )

    def test_T17_physical_controls_never_upgrade_on_local_match(self):
        for case_id in ("C01", "C02", "C03", "C11", "C16"):
            with self.subTest(case_id=case_id):
                result = review(case_id)
                self.assertEqual(result["physical_proof"], "NOT_PROVEN")
                self.assertEqual(result["authorization"], "NOT_AUTHORIZED")
                self.assertEqual(result["business_golden_status"], "PENDING_OWNER_DECISION")
                for field in (
                    "real_pg_input_equal",
                    "real_worker_output_equal",
                    "performance_pass",
                    "production_authorized",
                ):
                    self.assertIs(result[field], False)

    def test_T18_schema_projection_is_exact_not_an_ignore_list(self):
        self.rejected(lambda p: rows(p[0])[0].update(table="unknown_table"), "V2_SCHEMA")
        self.rejected(
            lambda p: row(p[0], "stock_factor_daily").update(
                new_column={"type": "int", "value": 1}
            ),
            "V2_SCHEMA",
        )
        self.rejected(lambda p: row(p[0], "stock_factor_daily").pop("ma20"), "V2_SCHEMA")
        self.rejected(
            lambda p: row(p[0], "stock_factor_daily")["ma20"].update(type="unknown"), "V2_TYPE"
        )

    def test_T19_migration_sequence_outside_guards_and_missing_slots(self):
        self.assertEqual(review("C12")["errors"], [{"code": "V2_SENTINEL_UNKNOWN"}])
        self.assertEqual(review("C13")["errors"], [{"code": "V2_OUTSIDE_CHANGED"}])
        for key in ("revision", "schema_sha256", "sequences", "outside_tables", "physical"):
            with self.subTest(missing=key):
                self.rejected(
                    lambda p, key=key: p[0]["domains"]["TYPED_OUTPUT"]["sentinels"].pop(key),
                    "V2_SENTINEL_UNKNOWN",
                )
        self.rejected(
            lambda p: p[0]["domains"]["TYPED_OUTPUT"]["sentinels"]["sequences"][
                "strategy_signal"
            ].update(last_value=2),
            "V2_ORACLE_MISMATCH",
        )

    def test_T20_digests_are_framed_typed_bound_and_domain_separated(self):
        result = review()
        digests = [v for side in result["domain_digests"].values() for v in side.values()]
        self.assertEqual(len(set(digests)), 8)  # Arm and domain are distinct bindings.
        packets, oracle, contract, provenance = material()
        same = {"same": "content"}
        packet = copy.deepcopy(packets[0])
        packet["domains"]["RAW_INPUT"] = same
        packet["domains"]["TELEMETRY"] = same
        hashes = module()._domain_digests(packet, same, same, provenance)
        self.assertEqual(len(set(hashes.values())), 4)
        self.assertNotEqual(
            module()._wire({"type": "int", "value": 0}),
            module()._wire({"type": "bool", "value": False}),
        )
        bytes_packets = [json.dumps(p).encode() for p in packets]
        self.assertEqual(module().review_pair(*bytes_packets, oracle, contract, provenance), result)

    def test_T21_limits_cycles_large_text_nodes_rows_and_json(self):
        self.rejected(lambda p: p[0].update(extra="x" * (module().MAX_TEXT + 1)), "V2_LIMIT")
        self.rejected(lambda p: p[0].update(extra=p[0]), "V2_LIMIT")
        self.rejected(lambda p: p[0]["domains"]["TYPED_OUTPUT"].update(rows=[{}] * 129), "V2_LIMIT")
        for raw in (
            b" " * (module().MAX_BYTES + 1),
            b"[" * 25 + b"]" * 25,
            b'{"a":1,"a":2}',
            b'{"a":NaN}',
            b'{"a":1.0}',
            b'{"a":1e999}',
            b"\xff",
            b"\xef\xbb\xbf{}",
        ):
            with self.subTest(size=len(raw)):
                with self.assertRaises(module().Refused):
                    module().parse(raw)
        nested = None
        for _ in range(25):
            nested = [nested]
        with self.assertRaisesRegex(module().Refused, "V2_LIMIT"):
            module().parse(nested)
        with self.assertRaisesRegex(module().Refused, "V2_LIMIT"):
            module().parse([["x"] * 100 for _ in range(201)])

    def test_T22_failures_never_echo_untrusted_values_or_exceptions(self):
        private = "offline-private-sentinel-sql-uri-token"
        result = self.rejected(lambda p: p[0].update({private: private}))
        self.assertNotIn(private, json.dumps(result))
        self.assertLess(len(json.dumps(result)), 2500)
        for value in (object(), Path("not-an-input-file"), {"key": object()}):
            packets, oracle, contract, provenance = material()
            result = module().review_pair(value, packets[1], oracle, contract, provenance)
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertEqual(result["errors"], [{"code": "V2_TYPE"}])

    def test_T23_repeat_is_deterministic_nonmutating_no_snapshot_update(self):
        packets, oracle, contract, provenance = material()
        before = copy.deepcopy(packets)
        one = module().review_pair(*packets, oracle, contract, provenance)
        two = module().review_pair(*packets, oracle, contract, provenance)
        self.assertEqual(one, two)
        self.assertEqual(packets, before)
        wrong_order = module().review_pair(*reversed(packets), oracle, contract, provenance)
        self.assertEqual(wrong_order["errors"], [{"code": "V2_CASE"}])
        self.rejected(lambda p: rows(p[0]).append(copy.deepcopy(rows(p[0])[0])), "V2_DUPLICATE_ROW")

    def test_T24_import_whitelist_and_isolated_no_io(self):
        path = ROOT / "scripts/r1_reviewed_snapshot_v2.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            n.module if isinstance(n, ast.ImportFrom) else a.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in (n.names if isinstance(n, ast.Import) else [None])
        }
        self.assertEqual(imports, {"hashlib", "json", "math", "re", "datetime", "decimal", "uuid"})
        code = """
import sys,types,hashlib,json,math,re,datetime,decimal,uuid,os,socket,subprocess,io
from unittest.mock import patch
raw = io.open(sys.argv[1], encoding="utf-8").read()
compiled = compile(raw, "offline_v2", "exec")
def deny(*a, **k):
    raise AssertionError("V2_IMPORT_SIDE_EFFECT")
with patch("builtins.open", deny), patch("io.open", deny), patch("os.getenv", deny), \
     patch("socket.socket", deny), patch("subprocess.Popen", deny), patch("os.environ", {}):
    m = types.ModuleType("isolated_v2")
    exec(compiled, m.__dict__)
    assert not any(k == "app" or k.startswith("app.") for k in sys.modules)
    assert not any(k.startswith("scripts.r1_") for k in sys.modules)
print("V2_IMPORT_NO_IO")
"""
        process = subprocess.run(
            [sys.executable, "-I", "-B", "-c", code, str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout.strip(), "V2_IMPORT_NO_IO")

    def test_T25_all_sixteen_independent_case_expectations(self):
        oracle = json.loads(material()[1])
        self.assertEqual([c["case_id"] for c in oracle["cases"]], list(module().CASES))
        for case in oracle["cases"]:
            with self.subTest(case_id=case["case_id"]):
                result = review(case["case_id"])
                self.assertEqual(result["status"], case["expected_status"])
                errors = (
                    [] if case["expected_error"] is None else [{"code": case["expected_error"]}]
                )
                self.assertEqual(result["errors"], errors)
                self.assertEqual(result["decision"], "NO_GO")
                self.assertFalse(result["real_worker_output_equal"])

    def test_T26_all_frozen_boundaries_and_oracle_authorship(self):
        for path, hashes in FROZEN.items():
            with self.subTest(path=path):
                self.assertIn(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), hashes)
        oracle = json.loads(material()[1])
        self.assertEqual(oracle["approval"], "PENDING_D04")
        self.assertEqual(oracle["reviewer"], "NOT_SIGNED")
        self.assertEqual(oracle["authorship"], "CODEX_MANUAL_DRAFT_NOT_OWNER_APPROVAL")
        for name, hashes in FIXTURE_HASHES.items():
            with self.subTest(fixture=name):
                self.assertIn(hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest(), hashes)

    def test_parser_rejects_noncanonical_uppercase_versions_and_input_types(self):
        for field, value in (
            ("schema_version", "R1.REVIEWED-EVIDENCE.V2"),
            ("evidence_kind", "FAKE"),
            ("scope", "OFFLINE_GOLDEN_CONTRACT_only"),
        ):
            with self.subTest(field=field):
                self.rejected(
                    lambda p, field=field, value=value: p[0].update({field: value}), "V2_PROTOCOL"
                )
        self.rejected(lambda p: p[0]["domains"]["RAW_INPUT"].update(rows=True), "V2_TYPE")

    def test_bad_json_and_huge_integer_have_fixed_errors(self):
        for value in (b"{", b'{"x":' + b"9" * 100 + b"}", b'{"nested":{"a":1,"a":2}}'):
            with self.subTest(length=len(value)):
                with self.assertRaises(module().Refused):
                    module().parse(value)

    def test_identity_mapping_reversal_many_to_one_and_domain_collision(self):
        original = json.loads(material()[1])["identities"]
        examples = []
        many = copy.deepcopy(original)
        many["scope"][1]["right"] = many["scope"][0]["right"]
        examples.append(many)
        cross = copy.deepcopy(original)
        cross["token"][0]["left"] = cross["job"][0]["left"]
        examples.append(cross)
        reverse = copy.deepcopy(original)
        reverse["event"].append(
            {
                "role": "other-event",
                "left": "2026-02-24T01:02:05.000001Z",
                "right": "2026-02-24T01:02:03.000001Z",
            }
        )
        examples.append(reverse)
        for example in examples:
            with self.subTest(index=examples.index(example)):
                with self.assertRaises(module().Refused):
                    module()._identities(example)


if __name__ == "__main__":
    unittest.main()
