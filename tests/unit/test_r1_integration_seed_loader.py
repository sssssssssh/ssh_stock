"""One frozen entity, two independent consumers, no database loader invocation."""

import copy
import unittest

from scripts import r1_integration_seed_loader as s
from scripts.r1_real_root_protocol import Refused


class SeedLoaderTests(unittest.TestCase):
    def test_independent_oracle_catches_orm_default_not_generator_self_comparison(self):
        entity, origins = s.original_fixture_oracle()
        self.assertTrue(entity["tables"]["sector"][0]["is_active"])
        self.assertEqual(origins["sector"][0]["is_active"], "orm_default")
        self.assertEqual(s.entity_digest(entity), s.entity_digest(s.generate_original_input()))
        self.assertEqual([r["exchange"] for r in entity["tables"]["stock_basic"]],
                         ["SZSE", "SZSE"])
        wrong = copy.deepcopy(entity)
        wrong["tables"]["stock_basic"][1]["exchange"] = None
        # The original recipe's explicit-value guard rejects this before hashing.
        with self.assertRaisesRegex(Refused, "^R1_SEED_VALUE$"):
            s.FrozenSeed(wrong)
        for table, rows in entity["tables"].items():
            for i, row in enumerate(rows):
                self.assertEqual(set(row), set(origins[table][i]))

    def test_capture_does_not_trust_replaced_generator(self):
        from unittest.mock import patch

        bad = copy.deepcopy(self.source)
        bad["tables"]["sector"][0]["is_active"] = False
        with patch.object(s, "generate_original_input", return_value=bad):
            with self.assertRaisesRegex(Refused, "SEED_ENTITY_MISMATCH"):
                s.FrozenSeed(bad)

    def test_all_frozen_timestamps_and_absent_nulls_have_explicit_origins(self):
        from scripts.r1_seed_snapshot_recipe import FROZEN_COLUMNS

        entity, origins = s.original_fixture_oracle()
        seen = set()
        for table, rows in entity["tables"].items():
            for index, row in enumerate(rows):
                for col, value in row.items():
                    if origins[table][index][col] == "frozen_timestamp":
                        seen.add(table + "." + col)
                        self.assertEqual(value, s.FROZEN_TIME)
                    if origins[table][index][col] == "nullable_absent":
                        self.assertIsNone(value)
        self.assertEqual(seen, FROZEN_COLUMNS)

    @classmethod
    def setUpClass(cls):
        cls.source = s.generate_original_input()

    def loader(self):
        return s.FrozenSeed(self.source)

    def test_AC07_generate_once_complete_original(self):
        subject = self.loader()
        result = subject.prepare_manifest()
        self.assertEqual(result["rows"], 4024)
        self.assertEqual(len(result["tables"]), 18)
        self.assertEqual(result["owner_selection"], "NOT_SELECTED")
        self.assertFalse(result["real_input_equal"])

    def test_AC08_default_timestamps_frozen(self):
        subject = self.loader()
        plan = subject.plan_load("OFF1", "loader-a", "physical-a")
        bad = copy.deepcopy(self.source)
        bad["tables"]["stock_basic"][0]["updated_at"] = s.FROZEN_TIME.replace(microsecond=2)
        with self.assertRaises(Refused):
            subject.verify_loaded_snapshot(plan, lambda _: bad)

    def test_AC09_sequences_and_catalog_exact(self):
        subject = self.loader()
        plan = subject.plan_load("OFF1", "loader-a", "physical-a")
        for field in ("sequences", "catalog"):
            bad = copy.deepcopy(self.source)
            bad[field] = {}
            with self.subTest(field=field), self.assertRaises(Refused):
                subject.verify_loaded_snapshot(plan, lambda _, bad=bad: bad)

    def test_AC10_independent_dual_loads_and_entity_values(self):
        subject = self.loader()
        a = subject.plan_load("OFF1", "loader-a", "physical-a")
        b = subject.plan_load("ON1", "loader-b", "physical-b")
        left = subject.verify_loaded_snapshot(a, lambda _: copy.deepcopy(self.source))
        right = subject.verify_loaded_snapshot(b, lambda _: copy.deepcopy(self.source))
        result = subject.compare_loaded(left, right)
        self.assertTrue(result["fake_entity_bytes_equal"])
        self.assertFalse(result["real_input_equal"])
        with self.assertRaises(Refused):
            subject.plan_load("ON1", "loader-c", "physical-a")

    def test_AC11_source_tampering_partial_duplicate_theme_type(self):
        subject = self.loader()
        plan = subject.plan_load("OFF1", "loader-a", "physical-a")
        mutations = [
            lambda x: x["tables"]["stock_daily"].pop(),
            lambda x: x["tables"]["stock_daily"].append(x["tables"]["stock_daily"][0]),
            lambda x: x["tables"]["theme"].append({}),
            lambda x: x["tables"]["stock_daily"][0].update(close="20"),
            lambda x: x.update(fixture_sha="0" * 64),
        ]
        for mutate in mutations:
            bad = copy.deepcopy(self.source)
            mutate(bad)
            with self.subTest(mutate=mutate), self.assertRaises(Refused):
                subject.verify_loaded_snapshot(plan, lambda _, bad=bad: bad)

    def test_AC12_no_plan_only_proof_or_live_loading(self):
        subject = self.loader()
        plan = subject.plan_load("OFF1", "loader-a", "physical-a")
        with self.assertRaises(Refused):
            subject.verify_loaded_snapshot(plan, lambda _: subject.prepare_manifest())
        with self.assertRaisesRegex(Refused, "R1_REAL_EXECUTION_NOT_AUTHORIZED"):
            subject.load_real(plan, authorized=True)
        self.assertEqual(subject.prepare_manifest(), self.loader().prepare_manifest())

    def test_capture_callback_once_row_order_and_catalog_index_tamper(self):
        calls = []

        def capture():
            calls.append(1)
            return copy.deepcopy(self.source)

        subject = s.FrozenSeed.capture_once(capture)
        subject.prepare_manifest()
        self.assertEqual(calls, [1])
        plan = subject.plan_load("OFF1", "loader-a", "physical-a")
        shuffled = copy.deepcopy(self.source)
        for rows in shuffled["tables"].values():
            rows.reverse()
        self.assertFalse(
            subject.verify_loaded_snapshot(plan, lambda _: shuffled)["real_input_equal"]
        )
        bad = copy.deepcopy(self.source)
        bad["catalog"]["stock_daily"]["indexes"] = []
        with self.assertRaises(Refused):
            subject.verify_loaded_snapshot(plan, lambda _: bad)


if __name__ == "__main__":
    unittest.main()
