"""Controller executes injected fake stages, public real execution always denied."""

import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import r1_integration_controller as c
from scripts.r1_integration_evidence import require_lineage, source_identity
from scripts.r1_real_root_protocol import Refused, real_execution_bridge


class Stages:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def step(self, name, **_):
        self.calls.append(name)
        if name == self.fail:
            raise RuntimeError("PRIVATE-DSN")
        if name == "comparison":
            return {"synthetic_equal": True}
        return {"status": "FAKE_CONFIRMED"}


class ControllerTests(unittest.TestCase):
    def test_AC28_order_cleanup_and_source_dual_identity(self):
        stages = Stages()
        result = c.run_injected(stages.step, c.DevelopmentPermit())
        self.assertEqual(stages.calls, list(c.STAGES))
        self.assertEqual(result["status"], "INTEGRATION_CODE_READY_FOR_REVIEW")
        self.assertEqual(result["experiment"], "NO_GO")
        identity = source_identity()
        require_lineage(identity)
        self.assertNotEqual(identity["integration_baseline"], identity["fixture_business_baseline"])

    def test_AC29_failure_stops_no_on_retry_and_cleanup_always(self):
        for name in c.STAGES[:-1]:
            stages = Stages(name)
            result = c.run_injected(stages.step, c.DevelopmentPermit())
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertEqual(stages.calls[-1], "cleanup")
            self.assertEqual(stages.calls.count(name), 1)
            self.assertNotIn("PRIVATE", repr(result))
        stages = Stages("cleanup")
        self.assertEqual(c.run_injected(stages.step, c.DevelopmentPermit())["status"], "INCOMPLETE")

    def test_AC30_diagnostics_and_business_flags_separate(self):
        a, b = c.arm_plan("OFF1"), c.arm_plan("ON1")
        self.assertFalse(a["perf_diagnostics_enabled"])
        self.assertTrue(b["perf_diagnostics_enabled"])
        self.assertEqual(a["business_flags"], b["business_flags"])
        self.assertFalse(any(a["business_flags"].values()))

    def test_AC31_cli_no_json_environment_authorization(self):
        with patch.object(c, "run_injected") as invoked:
            for argv in ([], ["--real"], ["--authorized=true"], ["--token=anything"]):
                self.assertEqual(c.main(argv), 2)
            invoked.assert_not_called()
        with self.assertRaises(Refused):
            c.require_human_authorization({"authorized": True})

    def test_AC32_immutable_original_bridge_and_two_levels(self):
        with self.assertRaisesRegex(Refused, "R1_REAL_EXECUTION_NOT_AUTHORIZED"):
            real_execution_bridge(authorized=True)
        with self.assertRaises(Refused):
            c.run_injected(Stages().step, {"development": True})
        with self.assertRaises(Refused):
            c.require_human_authorization(c.DevelopmentPermit())

    def test_AC33_metrics_unmeasured_and_bad_comparison(self):
        stages = Stages()

        def mismatch(name, **kw):
            return {"synthetic_equal": False} if name == "comparison" else stages.step(name, **kw)

        result = c.run_injected(mismatch, c.DevelopmentPermit())
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertTrue(all(x == "NOT_MEASURED" for x in result["measurements"].values()))

    def test_AC34_old_62_nodes_and_additional_20_not_double_counted(self):
        import ast

        root = Path(__file__).resolve().parents[2]
        files = list((root / "tests/unit").glob("test_r1_real_root_*.py"))
        files += [
            root / ("tests/unit/test_" + name + ".py")
            for name in (
                "r1_business_snapshot_contract",
                "r1_seed_snapshot_recipe",
                "perf03_lnx_w04a_offline_contract",
            )
        ]
        count = sum(
            sum(
                isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
                for n in ast.walk(ast.parse(p.read_text(encoding="utf8")))
            )
            for p in files
        )
        self.assertEqual(count, 62)

    def test_AC35_source_module_count_no_business_imports(self):
        import ast

        from scripts.r1_integration_evidence import MODULES

        root = Path(__file__).resolve().parents[2]
        self.assertEqual(len(MODULES), 7)
        for name in MODULES:
            tree = ast.parse((root / "scripts" / name).read_text(encoding="utf8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or "").startswith(("app.", "sqlalchemy")))

    def test_AC36_source_tamper_and_compileable(self):
        identity = source_identity()
        identity["tool_digest"] = "0" * 64
        with self.assertRaises(Refused):
            require_lineage(identity)
        root = Path(__file__).resolve().parents[2]
        for p in (root / "scripts").glob("r1_integration_*.py"):
            compile(p.read_bytes(), p.name, "exec")

    def test_AC38_upstream_ci_is_evidence_not_runtime_permission(self):
        for status in ("SUCCESS", "PENDING", "UPSTREAM_CI_FAILURE"):
            stages = Stages()
            result = c.run_injected(stages.step, c.DevelopmentPermit(), ci=status)
            self.assertEqual(result["experiment"], "NO_GO")
            self.assertEqual(result["ci"], status)
        self.assertEqual(len(hashlib.sha256(b"synthetic").hexdigest()), 64)

    def test_composed_real_adapters_fake_io_not_just_callback_labels(self):
        import tempfile

        from scripts.r1_integration_seed_loader import FrozenSeed, generate_original_input
        from tests.unit.test_r1_integration_durable_owner import owner
        from tests.unit.test_r1_integration_pg_export import ExportDB
        from tests.unit.test_r1_integration_pg_guard import FakeConnection, guard, target
        from tests.unit.test_r1_real_root_adapter import FakeFacade, FakeOwner
        from tests.unit.test_r1_real_root_protocol import request, sources

        with tempfile.TemporaryDirectory() as directory:
            components = c.OfflineIntegrationComponents(
                pg_guard=guard(),
                target=target(),
                connector=lambda _: FakeConnection(),
                seed=FrozenSeed(generate_original_input()),
                owner=owner(directory),
                offline_context=c.make_offline_context(request(), sources(), FakeOwner()),
                facade=FakeFacade(),
                fake_domain=lambda: {"status": "OFFLINE_MODEL_COMPLETE"},
                export_pair=lambda: (ExportDB(), ExportDB()),
            )
            self.assertTrue(components.preflight()["fake_only"])
            self.assertEqual(components.reserve_owner(), "LOCAL_RESERVED")
            self.assertEqual(components.execute_fake_root()["status"], "OFFLINE_SIMULATED")
            self.assertFalse(components.real_execution_allowed)


if __name__ == "__main__":
    unittest.main()
