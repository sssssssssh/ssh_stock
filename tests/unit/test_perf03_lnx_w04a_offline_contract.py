"""W04-A deterministic stdlib tests; also collectable by pytest when installed."""

import ast
import builtins
import copy
import hashlib
import importlib.util
import io
import json
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import perf03_lnx_w04a_offline_contract as c

ROOT = Path(__file__).absolute().parents[2]
NEW_FILES = {
    c.CONTRACT_PATH,
    "scripts/perf03_lnx_w04a_offline_contract.py",
    "tests/unit/test_perf03_lnx_w04a_offline_contract.py",
    "docs/acceptance/BIZ_PERF_03_A_R1_LNX_W04A.md",
}
REPORTS = {
    "docs/acceptance/BIZ_PERF_03_A_R1_LNX_W03_PREFLIGHT.md": c.W03_HASH,
    "docs/acceptance/BIZ_PERF_03_A_R1_LNX_W04_READINESS.md": c.W04_HASH,
}
# BEGIN PROTECTED WORKTREE HASHES
PROTECTED = {
    "AGENTS.md": "56fc204c15a6885649ff6dc65d470e9237c0ccb1e49dd14e4f69b58907054ba5",
    "PROJECT_CHARTER.md": "adb7899d0b4c475e16da61cb70fb019e8aa310769eb6c35610b1f304cbc7e19f",
    "PROJECT_STATUS.md": "0387567183f3480d2c2205244fedd081f7b9cc43566b4b0e1c262b3d82fe3029",
    "PROJECT_ROADMAP.md": "e3dce0289ea90ce2424c6a172969f64aa8d6f6396781e05f1ada5abced1295c5",
    "DECISION_LOG.md": "a4ea4f4d6fa997821b5155cfa2af75ad6537c80cd6898c560491ab27c29094d1",
    "docs/tasks/README.md": "fe5e71a7a73055859b8d21efbbf60fd86a5176674ee495a94a26941e22b9eed9",
    "backend/app/models/market_data.py": (
        "d798f2486ca8880e5128ba3383effa72e8d950b24f34ee543add71914955bc77"
    ),
    "backend/app/models/job.py": "dc213147ea1516797b6cae2b944cc771668263df81333ed023478669df68e950",
    "backend/app/models/data_publication.py": (
        "79e8df3a75f32c0468a427e2dd78fc66162186dc27579f41d8aee421d13d129f"
    ),
    "backend/app/models/data_schedule.py": (
        "b6c18834bf1dbc3bca50288b99889712639747d68055aee2fed0b69d8ff0ecb3"
    ),
    ("tests/integration/test_business_recalc_performance.py"): (
        "c6cc8cf4145d3dbefd259417e08c06ac7470a39adeca654ce9fe2f5483f2ba27"
    ),
    ("tests/integration/test_perf03_root_diagnostics.py"): (
        "5f6ac7c5c063a60cf06ac6edfbd739e548bea58c58b000f1657b43e4a5f81a4f"
    ),
    "scripts/business_recalc_measure.py": (
        "49a10219c68a19406bd0cf4720400c99d82277e9db20bde411dd7bddafae2475"
    ),
    "config/strategy.yaml": "bb824f8a3ef90442eafc8d0dae7796bc3d9992f671c6d06733975c7f877ce28b",
    "requirements-biz-perf-linux-py312-v1.lock": (
        "b87f3582f3d20814dd42146fde807709526764ff0d8b6713683e5645c72b7fc5"
    ),
    "scripts/perf03_lnx_hard_watchdog.py": (
        "7216e1475612f3ef688790b65d684d0a6fd15eb6ba02bed5f0d9960f78537e6d"
    ),
}
# END PROTECTED WORKTREE HASHES


PROTECTION_BASELINE = "8443b7cd524a6964b24cecd60df5be5b6c46783b"
# SHA256 of each Git Blob at first W04-A tracking, and its full LF->CRLF form.
# Fixed reviewed anchors; never derived from HEAD or the worktree at runtime.
FROZEN_CONTENT = {
    "docs/acceptance/BIZ_PERF_03_A_R1_LNX_W03_PREFLIGHT.md": (
        "21e9f0acc048d1724be985b13667a2cd71572992096abea9d8fbd57699455c9d",
        "8f2c90e4f8b56a246e8835476da7b69c11152d388440d40720b7016049acee3d",
    ),
    "docs/acceptance/BIZ_PERF_03_A_R1_LNX_W04_READINESS.md": (
        "09ac6d54828cdc085e134c5a54f91e3a1efa8933d42dea1e9bc7ae3967370f0d",
        "39fd9206c63287106220e61f349dfabe659f0804ed6c728d09bc03e060b6bb6c",
    ),
    "AGENTS.md": (
        "6ab8120da451af72d09aebbc3ccaa512841804b98aac292f94df3e5050111b37",
        "56fc204c15a6885649ff6dc65d470e9237c0ccb1e49dd14e4f69b58907054ba5",
    ),
    "PROJECT_CHARTER.md": (
        "adb7899d0b4c475e16da61cb70fb019e8aa310769eb6c35610b1f304cbc7e19f",
        "a346a0fbe06d8146222b8cb5825fd4fab06b571ea4bcbf0325792f19cb37e210",
    ),
    "PROJECT_STATUS.md": (
        "68616b6f2d6450dda8f6646b3ae4ab66598db63ae4747296f0214603111e1790",
        "0387567183f3480d2c2205244fedd081f7b9cc43566b4b0e1c262b3d82fe3029",
    ),
    "PROJECT_ROADMAP.md": (
        "378f9a911ac2dac0b93c8c0e633694bcfe91b93170aa13ea42bf45e13842e0b8",
        "e3dce0289ea90ce2424c6a172969f64aa8d6f6396781e05f1ada5abced1295c5",
    ),
    "DECISION_LOG.md": (
        "87b4861d05b67ecb5f03ca6de44f860fa33236d3434c9a109f07b30674da481b",
        "a4ea4f4d6fa997821b5155cfa2af75ad6537c80cd6898c560491ab27c29094d1",
    ),
    "docs/tasks/README.md": (
        "6c633a682f8fda47dfd867c22f79b4f5a054964374e5ff7dc009bea04ee72307",
        "fe5e71a7a73055859b8d21efbbf60fd86a5176674ee495a94a26941e22b9eed9",
    ),
    "backend/app/models/market_data.py": (
        "c0207d196fb9777bfd5c83284ca9d36f5b2cbf9ea5191ca149fbce9afcee9261",
        "d798f2486ca8880e5128ba3383effa72e8d950b24f34ee543add71914955bc77",
    ),
    "backend/app/models/job.py": (
        "fc795d1d4fb92ff3b8a10d41e19898e392e236ca84c661e78dfa2b02519ecc11",
        "dc213147ea1516797b6cae2b944cc771668263df81333ed023478669df68e950",
    ),
    "backend/app/models/data_publication.py": (
        "c9163a6e8386404d3b9faf9eaa1bf064d4a476b986e8fcc452ba9ce382aca63c",
        "79e8df3a75f32c0468a427e2dd78fc66162186dc27579f41d8aee421d13d129f",
    ),
    "backend/app/models/data_schedule.py": (
        "1c02583b6d8b455be81a3fc7f34c7aa93c167a6e516395e6688c24939fdf48c2",
        "b6c18834bf1dbc3bca50288b99889712639747d68055aee2fed0b69d8ff0ecb3",
    ),
    "tests/integration/test_business_recalc_performance.py": (
        "c6cc8cf4145d3dbefd259417e08c06ac7470a39adeca654ce9fe2f5483f2ba27",
        "2014d6ea07f4de77cd1f75ac9e0d41fb3e49056ecbc6f4ed80f7628b51f389f1",
    ),
    "tests/integration/test_perf03_root_diagnostics.py": (
        "7f9a5a16e19d64e7215466e8593f9fad3e1ab630a23cd036d087fba81fb9683a",
        "5f6ac7c5c063a60cf06ac6edfbd739e548bea58c58b000f1657b43e4a5f81a4f",
    ),
    "scripts/business_recalc_measure.py": (
        "edbd4b0d290fdf41ace88f2d8b15fb395c86eed2a7ae99daad5814975d114108",
        "49a10219c68a19406bd0cf4720400c99d82277e9db20bde411dd7bddafae2475",
    ),
    "config/strategy.yaml": (
        "2ac50c63f3b522ae84e97dad2c9eb2eabd2206c224cea25f83d8d049e7d2864b",
        "bb824f8a3ef90442eafc8d0dae7796bc3d9992f671c6d06733975c7f877ce28b",
    ),
    "requirements-biz-perf-linux-py312-v1.lock": (
        "88549dce3164364430e20970fa10eb2125b60ff05f456d7bef4474876a98dcfc",
        "b87f3582f3d20814dd42146fde807709526764ff0d8b6713683e5645c72b7fc5",
    ),
    "scripts/perf03_lnx_hard_watchdog.py": (
        "02d8c6f939c694410c04fb7bc449f030e0e2c8708c1c801b08e5a2eba5940454",
        "7216e1475612f3ef688790b65d684d0a6fd15eb6ba02bed5f0d9960f78537e6d",
    ),
}


def assert_frozen_file(root, relative):
    """Accept only the two exact frozen byte representations, never normalization."""
    path = Path(root) / relative
    if relative not in FROZEN_CONTENT:
        raise AssertionError("W04A_UNREGISTERED_FROZEN_PATH")
    mode = path.lstat().st_mode
    if not stat.S_ISREG(mode) or path.is_symlink():
        raise AssertionError("W04A_FROZEN_REGULAR_FILE_REQUIRED")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest not in FROZEN_CONTENT[relative]:
        raise AssertionError("W04A_FROZEN_CONTENT_MISMATCH")
    return digest


def cell(tag, value):
    return {"type": tag, "value": value}


def snapshot():
    tables = {name: [] for name in c.INPUT_SCHEMA}
    tables["synthetic_type_probe"] = [
        {
            "id": cell("int", 1),
            "bool": cell("bool", False),
            "int": cell("int", 0),
            "decimal": cell("decimal", "1.00"),
            "float": cell("float", (1.0).hex()),
            "date": cell("date", "2026-02-23"),
            "datetime": cell("datetime", "2025-01-01T00:00:00.000001Z"),
            "text": cell("text", "SYNTHETIC"),
            "bytes": cell("bytes", "00ff"),
        }
    ]
    return {
        "schema": c.SNAPSHOT_SCHEMA,
        "evidence_kind": "SYNTHETIC_ONLY",
        "plan_sha256": c.plan_fingerprint(c.contract_definition()),
        "tables": tables,
    }


class W04AContracts(unittest.TestCase):
    def rejected(self, operation, code=None):
        with self.assertRaises(c.Refused) as caught:
            operation()
        self.assertRegex(str(caught.exception), r"^W04A_[A-Z0-9_]+$")
        if code is not None:
            self.assertEqual(str(caught.exception), code)

    def test_A01_no_authority_or_real_execution(self):
        value = c.contract_definition()
        result = c.validate_contract(value)
        self.assertEqual((result["decision"], result["authorization"]), ("NO_GO", "NOT_AUTHORIZED"))
        self.assertEqual(result["target_verification"], "NOT_VERIFIED")
        for key, replacement in [
            ("off_on_pairs_executed", 1),
            ("production_read_authorized", True),
            ("capacity_authorized", True),
            ("deploy_authorized", True),
            ("authorization", "EXPERIMENT_AUTHORIZED"),
        ]:
            with self.subTest(key=key):
                changed = copy.deepcopy(value)
                changed["execution"][key] = replacement
                self.rejected(lambda changed=changed: c.validate_contract(changed))

    def test_A02_schema_fields_versions_and_strict_scalar_types(self):
        for change in ("missing", "extra", "version", "bool_int", "float_int"):
            with self.subTest(change=change):
                value = c.contract_definition()
                if change == "missing":
                    del value["purpose"]
                elif change == "extra":
                    value["command"] = "PRIVATE"
                elif change == "version":
                    value["schema"] = "perf03-lnx.w04a.offline-readiness.v2"
                else:
                    value["r1_input"]["history_days"] = True if change == "bool_int" else 420.0
                self.rejected(lambda value=value: c.validate_contract(value))

    def test_A03_json_duplicate_nonfinite_utf8_size_and_depth(self):
        for raw in (
            b'{"x":1,"x":2}',
            b'{"x":NaN}',
            b'{"x":Infinity}',
            b'{"x":-Infinity}',
            b'{"x":1e999}',
            b'"\xff"',
            b"\xef\xbb\xbf{}",
            b" " * (c.MAX_BYTES + 1),
            b"[" * 40 + b"0" + b"]" * 40,
        ):
            with self.subTest(length=len(raw)):
                self.rejected(lambda raw=raw: c.parse_json(raw))
        self.assertEqual(c.parse_json(b'{"x":false}'), {"x": False})

    def test_A04_private_input_never_echoed(self):
        private = "postgresql://PRIVATE:SECRET@PRIVATE/private.env"
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(c.main(["--command", private]), 2)
        self.assertEqual(output.getvalue(), "W04A_CLI_REFUSED\n")
        for action in (
            lambda private=private: c.parse_json(private.encode()),
            lambda ROOT=ROOT, private=private: c.read_safe(ROOT, private),
        ):
            self.rejected(action)

    def test_A05_stdlib_ast_and_fresh_import_without_business_or_environment(self):
        path = ROOT / "scripts/perf03_lnx_w04a_offline_contract.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        allowed = {
            "hashlib",
            "json",
            "math",
            "os",
            "re",
            "stat",
            "sys",
            "datetime",
            "decimal",
            "pathlib",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertTrue(all(x.name in allowed for x in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertIn(node.module, allowed)
            elif isinstance(node, ast.Attribute):
                self.assertNotIn(
                    node.attr,
                    {
                        "environ",
                        "getenv",
                        "Popen",
                        "system",
                        "write_text",
                        "write_bytes",
                        "unlink",
                        "mkdir",
                        "connect",
                    },
                )
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"eval", "exec", "__import__", "open"})
        original = builtins.__import__

        def guard(name, *args, **kwargs):
            if name.split(".")[0] in {
                "app",
                "backend",
                "psycopg",
                "sqlalchemy",
                "socket",
                "subprocess",
                "fastapi",
                "tushare",
            }:
                raise AssertionError("FORBIDDEN_IMPORT")
            return original(name, *args, **kwargs)

        before = set(sys.modules)
        spec = importlib.util.spec_from_file_location("w04a_fresh_test", path)
        module = importlib.util.module_from_spec(spec)
        with patch("builtins.__import__", guard):
            spec.loader.exec_module(module)
            self.assertEqual(
                module.validate_contract(module.contract_definition())["decision"], "NO_GO"
            )
        self.assertFalse(
            any(
                n.split(".")[0] in {"app", "backend", "psycopg", "sqlalchemy"}
                for n in set(sys.modules) - before
            )
        )

    def test_A06_hash_references_not_git_identity_and_wrong_values_refused(self):
        for sha in ("A" * 40, "a" * 39, "a" * 41, "g" * 40, "0" * 40, True):
            with self.subTest(sha_type=type(sha).__name__):
                value = c.contract_definition()
                value["source_baseline_sha"] = sha
                self.rejected(lambda value=value: c.validate_contract(value))
        material = next(iter(c.MATERIALS))
        for sha in ("A" * 64, "a" * 63, "g" * 64, "0" * 64, True):
            with self.subTest(artifact_type=type(sha).__name__):
                value = c.contract_definition()
                value["source_artifacts"][material]["sha256"] = sha
                self.rejected(lambda value=value: c.validate_contract(value))
        self.assertEqual(
            c.validate_contract(c.contract_definition())["source_identity"],
            "REFERENCE_ONLY_NOT_VERIFIED",
        )
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, material)
            target.parent.mkdir(parents=True)
            raw = (ROOT / material).read_bytes().replace(b"\r\n", b"\n")
            target.write_bytes(raw)
            expected = c.MATERIALS[material]["sha256"]
            self.assertEqual(
                c.material_digest(directory, material, expected)["status"],
                "TEXT_BYTES_MATCH_ONLY_NOT_GIT_IDENTITY",
            )
            target.write_bytes(raw + b"\n")
            self.rejected(
                lambda directory=directory, expected=expected, material=material: c.material_digest(
                    directory, material, expected
                ),
                "W04A_MATERIAL_BYTES_MISMATCH",
            )

    def test_A07_path_links_traversal_outside_and_file_types(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            target = base / "fixture.json"
            target.write_bytes(b"{}")
            self.assertEqual(c.read_safe(base, "fixture.json"), b"{}")
            for name in (
                "../fixture.json",
                "/fixture.json",
                "C:/PRIVATE.json",
                "a/../fixture.json",
                "a\\fixture.json",
                "./fixture.json",
                ".env",
                "a//fixture.json",
                "fixture.json/",
            ):
                with self.subTest(path_kind=name[:1]):
                    self.rejected(lambda base=base, name=name: c.read_safe(base, name))
            folder = base / "folder.json"
            folder.mkdir()
            self.rejected(lambda base=base: c.read_safe(base, "folder.json"), "W04A_FILE_TYPE")
            # Deterministic link/type injection works on Windows without symlink privilege.
            original = Path.is_symlink
            with patch.object(Path, "is_symlink", lambda p: p == target or original(p)):
                self.rejected(lambda base=base: c.read_safe(base, "fixture.json"), "W04A_LINK")
            original_lstat = Path.lstat

            def special(path):
                if path == target:
                    return type("Fact", (), {"st_mode": stat.S_IFIFO})()
                return original_lstat(path)

            with patch.object(Path, "lstat", special):
                self.rejected(lambda base=base: c.read_safe(base, "fixture.json"), "W04A_FILE_TYPE")
            target.write_bytes(b" " * (c.MAX_BYTES + 1))
            self.rejected(lambda base=base: c.read_safe(base, "fixture.json"), "W04A_SIZE")

    def test_A08_canonical_plan_digest_order_and_content(self):
        value = c.contract_definition()
        reverse = dict(reversed(list(value.items())))
        self.assertEqual(c.plan_fingerprint(value), c.plan_fingerprint(reverse))
        self.assertEqual(c.plan_fingerprint(value), c.plan_fingerprint(copy.deepcopy(value)))
        changed = copy.deepcopy(value)
        changed["r1_input"]["timestamp_columns"][0]["frozen_value"] = "2025-01-01T00:00:00.000009Z"
        self.assertNotEqual(c.plan_fingerprint(value), c.plan_fingerprint(changed))

    def test_A09_plan_equal_is_not_input_equal(self):
        value = c.contract_definition()
        result = c.compare_plans(value, copy.deepcopy(value))
        self.assertEqual(result["status"], "PLAN_EQUAL")
        self.assertNotIn("INPUT_EQUAL", json.dumps(result))
        self.assertEqual(result["real_input_equality"], "NOT_VERIFIED")
        changed = copy.deepcopy(value)
        changed["r1_input"]["timestamp_columns"][0]["frozen_value"] = "2025-01-01T00:00:00.000009Z"
        self.rejected(
            lambda changed=changed, value=value: c.compare_plans(value, changed),
            "W04A_PLAN_MISMATCH",
        )

        sample = snapshot()
        self.rejected(
            lambda: c.synthetic_snapshot_fingerprint(sample, plan=changed), "W04A_SNAPSHOT_PLAN"
        )
        sample["plan_sha256"] = c.plan_fingerprint(changed)
        self.assertEqual(
            c.compare_synthetic_snapshots(sample, copy.deepcopy(sample), plan=changed)["decision"],
            "NO_GO",
        )

    def test_A10_r1_fixed_input_values(self):
        for field, bad in [
            ("history_days", 900),
            ("include_closed", True),
            ("symbols", ["000001.SZ"]),
            ("request_start", "2025-01-01"),
            ("request_end", "2025-01-31"),
            ("mode", "daily"),
            ("evaluate_signals", True),
            ("benchmark_indices", ["PRIVATE"]),
        ]:
            with self.subTest(field=field):
                value = c.contract_definition()
                value["r1_input"][field] = bad
                self.rejected(lambda value=value: c.validate_contract(value))

    def test_A11_other_seed_and_protocol_refused(self):
        for field, bad in [
            ("seed_entry", "scripts.business_recalc_measure.main"),
            ("seed_protocol", "constant-price-frozen-audit-v2"),
            ("calendar_start", "2022-07-16"),
        ]:
            with self.subTest(field=field):
                value = c.contract_definition()
                value["r1_input"][field] = bad
                self.rejected(lambda value=value: c.validate_contract(value))
        value = c.contract_definition()
        value["schema"] = "biz-perf-03-b.actions-once.v1"
        self.rejected(lambda value=value: c.compare_plans(c.contract_definition(), value))

    def test_A12_timestamp_inventory_and_unresolved_never_ready(self):
        rows = c.contract_definition()["r1_input"]["timestamp_columns"]
        self.assertEqual(len(rows), 49)
        self.assertEqual(len({(r["table"], r["column"]) for r in rows}), 49)
        self.assertEqual(sum(r["classification"] == "FROZEN_SEED_VALUE" for r in rows), 5)
        expected = set()
        for file in ("market_data", "job", "data_publication", "data_schedule"):
            tree = ast.parse((ROOT / f"backend/app/models/{file}.py").read_text(encoding="utf-8"))
            for cls in tree.body:
                if not isinstance(cls, ast.ClassDef) or cls.name in {
                    "OpportunityForwardEval",
                    "ThemeForwardEval",
                    "ResearchTransitionEval",
                }:
                    continue
                table = next(
                    (
                        ast.literal_eval(n.value)
                        for n in cls.body
                        if isinstance(n, ast.Assign)
                        and any(
                            isinstance(x, ast.Name) and x.id == "__tablename__" for x in n.targets
                        )
                    ),
                    None,
                )
                if table:
                    for node in cls.body:
                        if isinstance(node, ast.AnnAssign) and "datetime" in ast.unparse(
                            node.annotation
                        ):
                            expected.add((table, node.target.id))
        self.assertEqual(expected, {(r["table"], r["column"]) for r in rows})
        for change in ("missing", "duplicate", "unresolved"):
            value = c.contract_definition()
            entries = value["r1_input"]["timestamp_columns"]
            if change == "missing":
                entries.pop()
            elif change == "duplicate":
                entries[-1] = entries[0]
            else:
                entries[0]["classification"] = "UNRESOLVED"
                result = c.validate_contract(value)
                self.assertEqual(
                    (result["decision"], result["G05"], result["timestamp_unresolved"]),
                    ("NO_GO", "SEED_FIELD_UNRESOLVED", 1),
                )
                continue
            self.rejected(lambda value=value: c.validate_contract(value))

    def test_A13_utc_microseconds_and_timestamp_differences(self):
        for bad in (
            "2025-01-01T00:00:00",
            "2025-01-01T00:00:00Z",
            "2025-01-01T01:00:00.000001+01:00",
            "2025-02-30T00:00:00.000001Z",
        ):
            with self.subTest(bad_kind=len(bad)):
                value = snapshot()
                value["tables"]["synthetic_type_probe"][0]["datetime"]["value"] = bad
                self.rejected(
                    lambda value=value: c.synthetic_snapshot_fingerprint(value), "W04A_UTC"
                )
        left, right = snapshot(), snapshot()
        right["tables"]["synthetic_type_probe"][0]["datetime"]["value"] = (
            "2025-01-01T00:00:00.000002Z"
        )
        self.rejected(
            lambda left=left, right=right: c.compare_synthetic_snapshots(left, right),
            "W04A_SNAPSHOT_MISMATCH",
        )

    def test_A14_typed_values_never_collapse(self):
        for field, bad in [
            ("int", cell("int", True)),
            ("bool", cell("bool", 0)),
            ("decimal", cell("float", (1.0).hex())),
            ("float", cell("decimal", "1.00")),
            ("bytes", cell("bytes", "FF")),
        ]:
            with self.subTest(field=field):
                value = snapshot()
                value["tables"]["synthetic_type_probe"][0][field] = bad
                self.rejected(lambda value=value: c.synthetic_snapshot_fingerprint(value))
        for field, replacement in [
            ("int", cell("null", None)),
            ("float", cell("float", "NaN")),
            ("decimal", cell("decimal", "1.0")),
        ]:
            with self.subTest(field=field):
                left, right = snapshot(), snapshot()
                right["tables"]["synthetic_type_probe"][0][field] = replacement
                self.rejected(
                    lambda left=left, right=right: c.compare_synthetic_snapshots(left, right)
                )

    def test_A15_pk_duplicates_and_canonical_row_column_table_order(self):
        left = snapshot()
        rows = left["tables"]["synthetic_type_probe"]
        second = copy.deepcopy(rows[0])
        second["id"] = cell("int", 2)
        rows.append(second)
        right = copy.deepcopy(left)
        right["tables"] = dict(reversed(list(right["tables"].items())))
        right["tables"]["synthetic_type_probe"] = [
            dict(reversed(list(r.items()))) for r in reversed(rows)
        ]
        self.assertEqual(
            c.compare_synthetic_snapshots(left, right)["status"], "SYNTHETIC_SNAPSHOT_EQUAL"
        )
        rows.append(copy.deepcopy(rows[0]))
        self.rejected(lambda left=left: c.synthetic_snapshot_fingerprint(left), "W04A_DUPLICATE_PK")
        wrong = snapshot()
        wrong["tables"]["other_table"] = wrong["tables"].pop("stock_daily")
        self.rejected(lambda wrong=wrong: c.synthetic_snapshot_fingerprint(wrong), "W04A_TABLES")

    def test_A16_every_declared_column_is_required_and_hashed(self):
        defaults = {
            "int": 7,
            "float": (2.0).hex(),
            "bool": True,
            "text": "SYNTHETIC",
            "date": "2025-01-01",
            "datetime": "2025-01-01T00:00:00.000001Z",
            "json": {},
        }
        for table, spec in c.INPUT_SCHEMA.items():
            if table == "synthetic_type_probe":
                continue
            row = {
                k: cell(rule["type"], defaults[rule["type"]]) for k, rule in spec["columns"].items()
            }
            base = snapshot()
            base["tables"][table] = [row]
            c.synthetic_snapshot_fingerprint(base)
            for column, rule in spec["columns"].items():
                with self.subTest(table=table, column=column):
                    missing = copy.deepcopy(base)
                    del missing["tables"][table][0][column]
                    self.rejected(
                        lambda missing=missing: c.synthetic_snapshot_fingerprint(missing),
                        "W04A_COLUMNS",
                    )
                    changed = copy.deepcopy(base)
                    target = changed["tables"][table][0][column]
                    if rule["nullable"]:
                        changed["tables"][table][0][column] = cell("null", None)
                    elif rule["type"] == "bool":
                        target["value"] = False
                    elif rule["type"] == "int":
                        target["value"] += 1
                    elif rule["type"] == "date":
                        target["value"] = "2025-01-02"
                    else:
                        target["value"] += "_CHANGED"
                    self.rejected(
                        lambda base=base, changed=changed: c.compare_synthetic_snapshots(
                            base, changed
                        )
                    )
            unknown = copy.deepcopy(base)
            unknown["tables"][table][0]["private_column"] = cell("text", "PRIVATE")
            self.rejected(
                lambda unknown=unknown: c.synthetic_snapshot_fingerprint(unknown), "W04A_COLUMNS"
            )

    def test_A17_root_lifecycle_error_cancel_not_seed(self):
        value = c.contract_definition()
        for row in value["r1_input"]["timestamp_columns"]:
            if row["table"] == "job_run":
                self.assertEqual(row["classification"], "DYNAMIC_ROOT_VALUE")
                self.assertIsNone(row["frozen_value"])
        quality = next(
            r
            for r in value["r1_input"]["timestamp_columns"]
            if (r["table"], r["column"]) == ("data_quality_daily", "checked_at")
        )
        self.assertEqual(quality["root_policy"], "DYNAMIC_ROOT_VALUE")
        changed = copy.deepcopy(value)
        row = next(
            r
            for r in changed["r1_input"]["timestamp_columns"]
            if r["table"] == "job_run" and r["column"] == "cancel_requested_at"
        )
        row["classification"] = "FROZEN_SEED_VALUE"
        self.rejected(lambda changed=changed: c.validate_contract(changed))
        for column in ("started_at", "finished_at", "cancel_requested_at", "error_message"):
            sample = snapshot()
            sample["tables"]["synthetic_type_probe"][0][column] = cell("null", None)
            self.rejected(
                lambda sample=sample: c.synthetic_snapshot_fingerprint(sample), "W04A_COLUMNS"
            )

    def test_A18_historical_verification_cannot_upgrade_target(self):
        value = c.contract_definition()
        self.assertEqual(value["history"]["04-D"]["installation"], "VERIFIED")
        self.assertEqual(value["history"]["04-E"]["integrity"], "VALID")
        self.assertEqual(value["target_environment"]["dependencies_67_on_target"], "NOT_VERIFIED")
        for key in ("machine_identity", "dependencies_67_on_target", "pg17_physical_identity"):
            changed = copy.deepcopy(value)
            changed["target_environment"][key] = "VERIFIED"
            self.rejected(lambda changed=changed: c.validate_contract(changed))

    def test_A19_all_twelve_gates_cannot_authorize(self):
        value = c.contract_definition()
        self.assertEqual(list(value["gates"]), [f"G{i:02}" for i in range(1, 13)])
        for gate in value["gates"]:
            changed = copy.deepcopy(value)
            changed["gates"][gate]["admission"] = "GO"
            self.rejected(lambda changed=changed: c.validate_contract(changed))
        for key in (
            "environment_verified",
            "environment_cpu_verified",
            "performance_pass",
            "production_authorized",
            "ready_to_run",
        ):
            changed = copy.deepcopy(value)
            changed[key] = True
            self.rejected(lambda changed=changed: c.validate_contract(changed))

    def test_A20_four_files_original_reports_and_sources_unchanged_no_writes(self):
        self.assertEqual(len(NEW_FILES), 4)
        for relative in NEW_FILES:
            self.assertTrue((ROOT / relative).is_file())
        for relative, expected in {**REPORTS, **PROTECTED}.items():
            self.assertIn(expected, FROZEN_CONTENT[relative])  # Retain historical byte identity.
            self.assertIn(assert_frozen_file(ROOT, relative), FROZEN_CONTENT[relative])
        self.assertEqual(set(FROZEN_CONTENT), set(REPORTS) | set(PROTECTED))
        raw = (ROOT / c.CONTRACT_PATH).read_bytes()
        value = c.parse_json(raw)
        c.validate_contract(value)
        c.compare_plans(value, copy.deepcopy(value))
        c.compare_synthetic_snapshots(snapshot(), snapshot())
        self.assertEqual((ROOT / c.CONTRACT_PATH).read_bytes(), raw)
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory, "fixture.json")
            file.write_bytes(b"{}")
            before = {p.name: p.read_bytes() for p in Path(directory).iterdir()}
            c.read_safe(directory, "fixture.json")
            self.assertEqual({p.name: p.read_bytes() for p in Path(directory).iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
