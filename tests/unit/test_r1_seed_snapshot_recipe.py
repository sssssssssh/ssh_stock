"""Both seed recipes remain offline and subject to an owner decision."""

import copy
import unittest
from datetime import date, timedelta

from test_r1_business_snapshot_contract import TIME

from scripts import r1_seed_snapshot_recipe as r
from scripts.r1_business_snapshot_contract import SCHEMA_SHA256, load_schema
from scripts.r1_real_root_protocol import Refused, digest


def manifest(recipe):
    schema = load_schema()
    inputs = {
        t: {
            "sha256": "a" * 64,
            "rows": r.expected_counts()[t],
            "columns": list(spec["columns"]),
            "type_hash": digest(
                {
                    c: {"type": rule["type"], "nullable": rule["nullable"]}
                    for c, rule in spec["columns"].items()
                }
            ),
            "non_timestamp_sha256": "b" * 64,
            "timestamp_values": {
                x.split(".")[1]: [TIME.strftime("%Y-%m-%dT%H:%M:%S.%fZ")] * r.expected_counts()[t]
                for x in r.FROZEN_COLUMNS
                if x.startswith(t + ".")
            },
        }
        for t, spec in schema["tables"].items()
        if spec["domain"] == "INPUT"
    }
    serials = {
        f"{t}.{c}": {"last_value": 1, "is_called": False, "increment": 1}
        for t, spec in schema["tables"].items()
        if t in inputs
        for c, rule in spec["columns"].items()
        if "autoincrement=True" in rule["source"]["declaration"]
    }
    return r.frozen_manifest(
        recipe,
        schema_sha256=SCHEMA_SHA256,
        ordered_tables=inputs,
        sequence_states=serials,
        random_state={
            "algorithm": "ORIGINAL_SEED_NO_RANDOM_CALLS",
            "state_sha256": digest({"random_calls": 0}),
        },
    )


def loaders(baseline):
    return [
        {
            "arm": arm,
            "loader_ref": arm.lower() + "-independent-consumer",
            "source_manifest_sha256": digest(baseline),
            "observed_manifest": copy.deepcopy(baseline),
        }
        for arm in ("OFF1", "ON1")
    ]


class SeedTests(unittest.TestCase):
    def test_AC27_two_recipes_no_owner_no_gate_upgrade(self):
        for method in r.METHODS:
            with self.subTest(method=method):
                recipe = r.recipe_template(method)
                base = manifest(recipe)
                left, right = loaders(base)
                for entry in right["observed_manifest"]["tables"].values():
                    if entry["timestamp_values"] and method == r.METHODS[1]:
                        entry["sha256"] = "b" * 64
                        for key, vector in entry["timestamp_values"].items():
                            entry["timestamp_values"][key] = [
                                (TIME + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                            ] * len(vector)
                events = {
                    c: {
                        "left_raw": "a" * 64,
                        "right_raw": "b" * 64,
                        "pairs": [(TIME, TIME + timedelta(seconds=1))],
                    }
                    for c in r.FROZEN_COLUMNS
                }
                result = r.compare_load_recipes(recipe, base, left, right, events)
                self.assertEqual(result["owner_selection"], "NOT_SELECTED")
                self.assertEqual(result["decision"], "DECISION_REQUIRED")
                self.assertFalse(result["real_pg_input_equal"])
                self.assertEqual((result["G05"], result["G08"]), ("MISSING", "PARTIAL"))
                changed = copy.deepcopy(recipe)
                changed["owner_selection"] = "APPROVED"
                with self.assertRaises(Refused):
                    r.validate_recipe(changed)

    def test_seed_dates_quality_boundaries_and_all_49_sources(self):
        recipe = r.recipe_template()
        self.assertEqual(len(recipe["timestamp_columns"]), 49)
        self.assertEqual(sum(x["role"] == "SEED_INPUT" for x in recipe["timestamp_columns"]), 5)
        self.assertEqual(recipe["fixture"]["warmup_trading_days"], 250)
        self.assertEqual(recipe["fixture"]["lookback_calendar_days"], 430)
        for field, value in (
            ("history_days", 900),
            ("include_closed", True),
            ("symbols", ["000001.SZ"]),
            ("evaluate_signals", True),
        ):
            changed = copy.deepcopy(recipe)
            changed["fixture"][field] = value
            with self.assertRaises(Refused):
                r.validate_recipe(changed)
        changed = copy.deepcopy(recipe)
        changed["timestamp_columns"].pop()
        with self.assertRaises(Refused):
            r.validate_recipe(changed)

    def test_sequence_schema_rows_and_hash_tamper_refused(self):
        recipe = r.recipe_template()
        base = manifest(recipe)
        left, right = loaders(base)
        before = copy.deepcopy(base)
        r.compare_load_recipes(recipe, base, left, right)
        self.assertEqual(before, base)
        for field in ("sha256", "rows", "columns", "type_hash"):
            changed = copy.deepcopy(right)
            table = next(iter(changed["observed_manifest"]["tables"]))
            changed["observed_manifest"]["tables"][table][field] = "PRIVATE"
            with self.assertRaises(Refused):
                r.compare_load_recipes(recipe, base, left, changed)
        changed = copy.deepcopy(right)
        col = next(iter(changed["observed_manifest"]["sequences"]))
        changed["observed_manifest"]["sequences"][col]["last_value"] += 1
        with self.assertRaises(Refused):
            r.compare_load_recipes(recipe, base, left, changed)
        changed = copy.deepcopy(right)
        changed["loader_ref"] = left["loader_ref"]
        with self.assertRaises(Refused):
            r.compare_load_recipes(recipe, base, left, changed)

    def test_AC29_environment_tools_and_w04a_suite_not_modified(self):
        # Byte assertions supplement separately recorded pytest/unittest/lint/compile commands.
        from test_r1_real_root_protocol import ORIGINALS, ROOT, verify_approved_sources

        self.assertEqual(set(verify_approved_sources(ROOT)), set(ORIGINALS))
        self.assertEqual(r.validate_recipe(r.recipe_template())["decision"], "DECISION_REQUIRED")

    def test_full_typed_original_input_snapshot_and_independent_consumers(self):
        schema, recipe = load_schema(), r.recipe_template()
        tables = {t: [] for t in r.expected_counts()}

        def row(table, **values):
            result = {}
            for col, rule in schema["tables"][table]["columns"].items():
                default = (
                    None
                    if rule["nullable"]
                    else {
                        "text": "",
                        "int": 1,
                        "float": 1.0,
                        "bool": True,
                        "date": date(2025, 1, 1),
                        "datetime": TIME,
                        "json": {},
                    }[rule["type"]]
                )
                result[col] = default
            result.update(values)
            tables[table].append(result)

        start = date(2025, 1, 1)
        for code, closed in (("000001.SZ", False), ("000002.SZ", True)):
            row(
                "stock_basic",
                ts_code=code,
                exchange="SZSE",
                list_status="D" if closed else "L",
                list_date=start + timedelta(days=10) if closed else start,
                delist_date=start + timedelta(days=25) if closed else None,
            )
        row("sector", sector_id=101, source="SW", source_code="BIZ", name="synthetic", level="L1")
        row("sector_member", sector_id=101, ts_code="000001.SZ", valid_from=start)
        quality_id = 0
        for n in range(420):
            day = start + timedelta(days=n)
            row("trade_calendar", cal_date=day, is_open=day.weekday() < 5)
            if day.weekday() >= 5:
                continue
            for code in ("000001.SZ", "000002.SZ"):
                row(
                    "stock_daily",
                    trade_date=day,
                    ts_code=code,
                    close=20.0,
                    open=20.0,
                    high=21.0,
                    low=19.0,
                    vol=100000.0,
                    amount=1000000.0,
                )
                row("stock_adj_factor", trade_date=day, ts_code=code, adj_factor=1.0)
                row(
                    "stock_daily_basic",
                    trade_date=day,
                    ts_code=code,
                    close=20.0,
                    total_mv=100.0,
                    circ_mv=100.0,
                )
                row(
                    "stock_limit_daily",
                    trade_date=day,
                    ts_code=code,
                    up_limit=22.0,
                    down_limit=18.0,
                )
            for code in ("000300.SH", "000001.SH"):
                row("index_daily", trade_date=day, ts_code=code, close=100.0, pre_close=100.0)
            for dataset in ("stock_st", "suspend_d"):
                quality_id += 1
                row(
                    "data_quality_daily",
                    id=quality_id,
                    trade_date=day,
                    dataset=dataset,
                    status="PASS",
                    expected_rows=0,
                    actual_rows=0,
                )
        states = manifest(recipe)["sequences"]
        states["sector_member.id"].update(last_value=1, is_called=True)
        states["data_quality_daily.id"].update(last_value=600, is_called=True)
        before = copy.deepcopy(tables)
        baseline = r.snapshot_input_rows(recipe, tables, states)
        first, second = loaders(baseline)
        self.assertTrue(
            r.compare_load_recipes(recipe, baseline, first, second)["synthetic_manifest_equal"]
        )
        self.assertEqual(tables, before)
        bad = copy.deepcopy(tables)
        bad["stock_daily"][0]["close"] = 20.01
        with self.assertRaises(Refused):
            r.snapshot_input_rows(recipe, bad, states)
        bad = copy.deepcopy(tables)
        bad["stock_basic"][1]["delist_date"] += timedelta(days=1)
        with self.assertRaises(Refused):
            r.snapshot_input_rows(recipe, bad, states)
        bad = copy.deepcopy(tables)
        bad["data_quality_daily"][0].pop("checked_at")
        with self.assertRaises(Refused):
            r.snapshot_input_rows(recipe, bad, states)
