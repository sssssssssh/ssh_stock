"""R1 protocol regressions; only offline memory or fixed source reads."""

import ast
import copy
import hashlib
import io
import stat
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import r1_real_root_protocol as p
from scripts.r1_business_snapshot_contract import load_schema

ROOT = Path(__file__).absolute().parents[2]
ORIGINALS = {
    "docs/acceptance/BIZ_PERF_03_A_R1_LNX_W03_PREFLIGHT.md": (
        "21e9f0acc048d1724be985b13667a2cd71572992096abea9d8fbd57699455c9d"
    ),
    "docs/acceptance/BIZ_PERF_03_A_R1_LNX_W04_READINESS.md": (
        "09ac6d54828cdc085e134c5a54f91e3a1efa8933d42dea1e9bc7ae3967370f0d"
    ),
    "docs/acceptance/biz_perf_03_a_r1_lnx_w04a_contract.json": (
        "0f464a6acc4efc651fdea798fac1b0b4b3b61069147515115afa5b9f2d91d2f8"
    ),
    "scripts/perf03_lnx_w04a_offline_contract.py": (
        "b11a4a2b8e6da6224ab8c503130073bef5ace9ec701dbf43649e116c0be6c5a0"
    ),
    "tests/unit/test_perf03_lnx_w04a_offline_contract.py": (
        "f3232a88f0be68ca710ffba337e8dcfae9fa096d54a681ee8dc2eb760efce2ef"
    ),
    "docs/acceptance/BIZ_PERF_03_A_R1_LNX_W04A.md": (
        "25bffe509c2f78473221bbb39c61bac95eec6db5e0930828205072ea46e66b20"
    ),
}

CURRENT_APPROVED_SOURCE_VERSION = "60dacb8f96013439ebb8490b78eaffd6a3cfbcbd"
# Historical ORIGINALS stays immutable evidence; only this reviewed version is current.
CURRENT_APPROVED_SOURCE_HASHES = {
    "docs/acceptance/BIZ_PERF_03_A_R1_LNX_W03_PREFLIGHT.md": (
        "21e9f0acc048d1724be985b13667a2cd71572992096abea9d8fbd57699455c9d",
        "8f2c90e4f8b56a246e8835476da7b69c11152d388440d40720b7016049acee3d",
    ),
    "docs/acceptance/BIZ_PERF_03_A_R1_LNX_W04_READINESS.md": (
        "09ac6d54828cdc085e134c5a54f91e3a1efa8933d42dea1e9bc7ae3967370f0d",
        "39fd9206c63287106220e61f349dfabe659f0804ed6c728d09bc03e060b6bb6c",
    ),
    "docs/acceptance/biz_perf_03_a_r1_lnx_w04a_contract.json": (
        "0f464a6acc4efc651fdea798fac1b0b4b3b61069147515115afa5b9f2d91d2f8",
        "023f36644e2c498ee70f0c5f52b6b930164fa2b58f6d23991ffbeffb97016cd5",
    ),
    "scripts/perf03_lnx_w04a_offline_contract.py": (
        "b11a4a2b8e6da6224ab8c503130073bef5ace9ec701dbf43649e116c0be6c5a0",
        "17a09bc86be0bdbdd0b2b0e60897210ac9c31de94e0fdde16fce9ec368245add",
    ),
    "tests/unit/test_perf03_lnx_w04a_offline_contract.py": (
        "c5dd882ad80cf753a1423aba1aea7c474742886d9a20bac31807641531fb9a38",
        "ad6fb96689c8d25569cdb1eecd2dcf007e7e2f1cbabcaf69342ad4431a510c41",
    ),
    "docs/acceptance/BIZ_PERF_03_A_R1_LNX_W04A.md": (
        "25bffe509c2f78473221bbb39c61bac95eec6db5e0930828205072ea46e66b20",
        "4baac2a22ac14f6f659698dcafc77b93896a60bc1f9ecb3b8a6f324004b59133",
    ),
}


def verify_approved_sources(root, paths=None, *, approved_version=None):
    """Validate exactly six current sources; no Git, env, network or normalization."""
    p.require(CURRENT_APPROVED_SOURCE_VERSION == "60dacb8f96013439ebb8490b78eaffd6a3cfbcbd"
              and approved_version in (None, CURRENT_APPROVED_SOURCE_VERSION),
              "R1_APPROVED_SOURCE_VERSION")
    mapping = CURRENT_APPROVED_SOURCE_HASHES
    p.require(type(mapping) is dict and set(mapping) == set(ORIGINALS) and len(mapping) == 6,
              "R1_APPROVED_SOURCE_MANIFEST")
    p.require(all(type(v) is tuple and len(v) == 2
                  and all(type(h) is str and len(h) == 64
                          and all(ch in "0123456789abcdef" for ch in h) for h in v)
                  for v in mapping.values()),
              "R1_APPROVED_SOURCE_MANIFEST")
    identity = "\n".join([CURRENT_APPROVED_SOURCE_VERSION,
                           *(f"{name}:{mapping[name][0]}:{mapping[name][1]}"
                             for name in sorted(mapping))])
    p.require(hashlib.sha256(identity.encode("ascii")).hexdigest()
              == "d155355ab8807b5ee5d9dde44be8c02ef80fb6f5870978b8f09a9c8749e788a5",
              "R1_APPROVED_SOURCE_MANIFEST")
    paths = tuple(ORIGINALS) if paths is None else paths
    p.require(type(paths) in (list, tuple) and len(paths) == 6
              and all(type(name) is str for name in paths) and set(paths) == set(mapping),
              "R1_APPROVED_SOURCE_PATH_SET")
    root, observed = Path(root).absolute(), {}
    for name in paths:
        try:
            parent = root
            for part in (None, *Path(name).parts[:-1]):
                parent = parent if part is None else parent / part
                p.require(stat.S_ISDIR(parent.lstat().st_mode)
                          and not parent.is_symlink() and not parent.is_junction(),
                          "R1_APPROVED_SOURCE_PATH")
            file = root / name
            p.require(stat.S_ISREG(file.lstat().st_mode)
                      and not file.is_symlink() and not file.is_junction(),
                      "R1_APPROVED_SOURCE_PATH")
            observed[name] = hashlib.sha256(file.read_bytes()).hexdigest()
        except OSError:
            raise p.Refused("R1_APPROVED_SOURCE_PATH") from None
        p.require(observed[name] in mapping[name], "R1_APPROVED_SOURCE_HASH")
    return observed


MODULES = [
    "r1_real_root_protocol",
    "r1_real_root_adapter",
    "r1_real_root_supervisor",
    "r1_business_snapshot_contract",
    "r1_seed_snapshot_recipe",
]


def sources():
    return {k: v["sha256"] for k, v in load_schema()["sources"].items()}


def request(arm="OFF1"):
    return p.request_template(sources(), arm=arm)


class ProtocolTests(unittest.TestCase):
    def test_AC01_original_six_and_baseline_preserved(self):
        self.assertEqual(set(verify_approved_sources(ROOT)), set(ORIGINALS))
        self.assertEqual(load_schema()["target_sha"], p.BASELINE)
        paths = [f"scripts/{n}.py" for n in MODULES]
        paths += [f"tests/unit/test_{n}.py" for n in MODULES]
        paths += [
            "docs/acceptance/r1_business_compare_schema_v1.json",
            "docs/acceptance/BIZ_PERF_03_A_R1_LNX_REAL_ADAPTER_01.md",
        ]
        self.assertEqual(len(set(paths)), 12)
        for path in paths:
            self.assertTrue((ROOT / path).is_file())

    def test_AC02_fixed_request_and_flags(self):
        for key, bad in [
            ("attempt", 2),
            ("target_sha", "0" * 40),
            ("requested_arm", "OFF2"),
            ("r1_fixture", {"history_days": 900}),
        ]:
            value = request()
            value[key] = bad
            with self.subTest(key=key), self.assertRaises(p.Refused):
                p.validate_request(value, sources())
        for key in p.FLAGS:
            value = request()
            value["flags"][key] = True
            with self.subTest(flag=key), self.assertRaises(p.Refused):
                p.validate_request(value, sources())
        for arm in ("OFF1", "ON1"):
            value = request(arm)
            self.assertEqual(p.validate_request(value, sources())["decision"], "NO_GO")
            self.assertIs(value["flags"]["perf_diagnostics_enabled"], arm == "ON1")

    def test_AC03_json_strict_types_and_private_errors(self):
        for raw in (
            b'{"x":1,"x":2}',
            b"NaN",
            b"Infinity",
            b"1e999",
            b'"\xff"',
            b"\xef\xbb\xbf{}",
            b" " * 1048577,
            b"[" * 40 + b"0" + b"]" * 40,
        ):
            with self.subTest(length=len(raw)), self.assertRaises(p.Refused):
                p.parse_json(raw)
        for key, bad in (
            ("attempt", True),
            ("attempt", 1.0),
            ("owner_reservation_ref", "../private"),
            ("shell", "PRIVATE_DSN"),
        ):
            value = request()
            value[key] = bad
            with self.assertRaisesRegex(p.Refused, "^R1_[A-Z_]+$") as caught:
                p.validate_request(value, sources())
            self.assertNotIn("PRIVATE", str(caught.exception))

    def test_AC05_hashes_and_refs_never_authorize(self):
        value = request()
        result = p.validate_request(value, sources())
        self.assertEqual(result, {"decision": "NO_GO", "evidence_kind": "OFFLINE_CONTRACT_TESTED"})
        with self.assertRaisesRegex(p.Refused, "R1_REAL_EXECUTION_NOT_AUTHORIZED"):
            p.real_execution_bridge(value, digest=p.digest(value), authorized=True)

    def test_AC06_finite_state_transitions_and_sticky_error(self):
        machine = p.StateMachine()
        with self.assertRaises(p.Refused):
            machine.move("OUTPUT_FROZEN", 0)
        machine.move("REGISTERED", 0)
        machine.move("SPAWN_REQUESTED", 1)
        machine.fail("SPAWN_UNCERTAIN", 2, uncertain=True)
        machine.fail("BUSINESS_ERROR", 3)
        self.assertEqual(machine.first_error, "SPAWN_UNCERTAIN")
        with self.assertRaises(p.Refused):
            machine.move("CLEANUP_CONFIRMED", 4)

    def test_AC28_cli_sealed_and_static_capabilities(self):
        from scripts import r1_real_root_adapter as adapter

        for module in (p, adapter):
            output = io.StringIO()
            with (
                patch("builtins.open", side_effect=AssertionError("NO_IO")),
                redirect_stdout(output),
            ):
                self.assertEqual(module.main(["--execute", "PRIVATE"]), 2)
            self.assertEqual(output.getvalue(), "R1_REAL_EXECUTION_NOT_AUTHORIZED\n")
        forbidden = {"subprocess", "socket", "requests", "psycopg", "sqlalchemy", "os"}
        for name in MODULES:
            tree = ast.parse((ROOT / f"scripts/{name}.py").read_text(encoding="utf8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertFalse({a.name.split(".")[0] for a in node.names} & forbidden)
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], forbidden)
            if name == "r1_real_root_adapter":
                for cl in tree.body:
                    if isinstance(cl, ast.ClassDef) and cl.name == "BusinessFacade":
                        for fn in cl.body:
                            if isinstance(fn, ast.FunctionDef):
                                self.assertEqual(ast.unparse(fn.body[0]), "real_execution_bridge()")

    def test_AC31_source_sha_and_every_new_utf8_file(self):
        for path in [
            *(f"scripts/{n}.py" for n in MODULES),
            *(f"tests/unit/test_{n}.py" for n in MODULES),
        ]:
            text = (ROOT / path).read_bytes().decode("utf8")
            self.assertFalse(text.startswith("\ufeff"))
            self.assertTrue(text.endswith("\n"))
            self.assertTrue(all(line == line.rstrip() for line in text.splitlines()))
        # Verify pinned source bytes while explicitly accounting for Windows checkout CRLF.
        for path, source in load_schema()["sources"].items():
            raw = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(hashlib.sha256(raw).hexdigest(), source["sha256"])

    def test_AC32_no_offline_state_upgrades_admission(self):
        before = request()
        changed = copy.deepcopy(before)
        changed["environment_verified"] = True
        with self.assertRaises(p.Refused):
            p.validate_request(changed, sources())
        self.assertEqual(p.validate_request(before, sources())["decision"], "NO_GO")
