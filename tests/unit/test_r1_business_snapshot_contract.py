"""Full schema golden and every-column negative coverage; no database imports."""

import ast
import copy
import unittest
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from scripts import r1_business_snapshot_contract as c
from scripts.r1_real_root_protocol import BASELINE, Refused, canonical

ROOT = Path(__file__).absolute().parents[2]
TIME = datetime(2026, 2, 24, 1, 2, 3, 456789, tzinfo=UTC)


def golden(side="left", lifecycle="SUCCESS"):
    schema = c.load_schema()
    right = side == "right"
    job, token, scope = (
        UUID(int=11 if right else 1),
        UUID(int=12 if right else 2),
        UUID(int=13 if right else 3),
    )
    moment = TIME + timedelta(seconds=10) if right else TIME
    queue = {
        key: "identity-" + key
        for key in schema["json_contracts"]["data_publication.identity"]["keys"]
    }
    tables = {}
    for table, spec in schema["tables"].items():
        row = {}
        for col, rule in spec["columns"].items():
            val = {
                "text": "synthetic",
                "int": 1,
                "bool": False,
                "float": 1.25,
                "date": date(2026, 2, 23),
                "datetime": TIME,
                "uuid": UUID(int=99),
                "json": {},
                "array": (),
            }[rule["type"]]
            if rule["domain"] in ("job", "token", "scope"):
                val = {"job": job, "token": token, "scope": scope}[rule["domain"]]
            if rule["policy"] == "TIMESTAMP_EVENT_MAPPING":
                val = moment
            if col in ("sector_id", "industry_sector_id", "primary_sector_id"):
                val = 101
            if col == "ts_code":
                val = "000001.SZ"
            if col in ("theme_code", "primary_theme_code"):
                val = "THEME"
            row[col] = val
        tables[table] = [row]
    j = tables["job_run"][0]
    j.update(
        status=lifecycle,
        worker_id="perf03-r1-synthetic",
        parent_job_id=None,
        depends_on_job_id=None,
        cancel_requested=lifecycle == "CANCELLED",
        job_metadata={
            "queue_identity": queue,
            "calc_run_id": str(job),
            "start": "2026-02-23",
            "end": "2026-02-24",
            "mode": "manual",
            "source": "manual",
            "evaluate_signals": False,
            "dirty_range_ids": [],
        },
        job_type="recalculate",
        target_trade_date=date(2026, 2, 24),
    )
    tables["data_publication"][0].update(
        identity=queue, state="PUBLISHED" if lifecycle == "SUCCESS" else "ABORTED", row_counts={}
    )
    tables["data_publication_source"][0].update(
        role="root", validation={"days": ["2026-02-23", "2026-02-24"], "pending_dirty_ids": []}
    )
    tables["stock_basic"][0].update(list_date=date(2025, 1, 1), delist_date=None, list_status="L")
    target = "stock_factor_daily"
    key = tuple(tables[target][0][k] for k in schema["tables"][target]["primary_key"])
    tables["data_publication_row"][0].update(
        table_name=target,
        row_key=key,
        row_data=copy.deepcopy(tables[target][0]),
        base_row=None,
        is_deleted=False,
    )
    tables["data_publication_preimage"][0].update(
        table_name=target, row_key=key, row_data=copy.deepcopy(tables[target][0])
    )
    tables["data_publication_scope"][0].update(table_name=target)
    return {
        "schema_version": c.VERSION,
        "source_sha": BASELINE,
        "evidence_kind": "SYNTHETIC_ONLY",
        "root_id": job,
        "input_ref": "a" * 64,
        "lifecycle": lifecycle,
        "commit_ack": "KNOWN",
        "tables": tables,
        "counts": {t: len(rows) for t, rows in tables.items()},
        "columns": {t: list(s["columns"]) for t, s in schema["tables"].items()},
        "ordering": "BOUNDED_UNORDERED",
        "resource_binding": {
            "evidence_kind": "SYNTHETIC_ONLY",
            "pg_ref": "offline-pg-resource",
            "database_oid": 100,
            "postmaster_start": TIME - timedelta(days=1),
        },
    }


def mapping():
    return {
        "job": [(UUID(int=1), UUID(int=11))],
        "token": [(UUID(int=2), UUID(int=12))],
        "scope": [(UUID(int=3), UUID(int=13))],
        "events": [(TIME, TIME + timedelta(seconds=10))],
    }


class SnapshotTests(unittest.TestCase):
    def assert_rejected(self, left, right=None, ids=None):
        result = c.compare_snapshots(
            left, golden("right") if right is None else right, mapping() if ids is None else ids
        )
        self.assertIs(result["equal"], False, result)
        return result

    def test_AC18_exact_orm_inventory_types_keys_foreign_keys(self):
        schema = c.load_schema()
        self.assertEqual(len(schema["tables"]), 37)
        self.assertEqual(sum(len(s["columns"]) for s in schema["tables"].values()), 520)
        count = 0
        for _table, spec in schema["tables"].items():
            self.assertTrue(spec["primary_key"])
            for col, rule in spec["columns"].items():
                tree = ast.parse((ROOT / rule["source"]["path"]).read_text(encoding="utf8"))
                node = next(
                    n
                    for n in ast.walk(tree)
                    if isinstance(n, ast.AnnAssign) and n.lineno == rule["source"]["line"]
                )
                self.assertEqual(node.target.id, col)
                self.assertEqual(ast.unparse(node.value), rule["source"]["declaration"])
                fks = [
                    a.args[0].value
                    for a in node.value.args
                    if isinstance(a, ast.Call)
                    and isinstance(a.func, ast.Name)
                    and a.func.id == "ForeignKey"
                ]
                self.assertEqual(fks, [rule["foreign_key"]] if rule["foreign_key"] else [])
                count += 1
        self.assertEqual(count, 520)

    def test_AC19_policies_total_no_blanket_exemptions(self):
        policies = {
            r["policy"] for t in c.load_schema()["tables"].values() for r in t["columns"].values()
        }
        self.assertEqual(
            policies,
            {
                "EXACT_TYPED_VALUE",
                "UUID_BIJECTION",
                "TIMESTAMP_EVENT_MAPPING",
                "STRICT_JSON_SUBPATHS",
            },
        )
        result = c.compare_snapshots(golden(), golden("right"), mapping())
        self.assertTrue(result["equal"], result)
        self.assertFalse(result["performance_pass"])

    def test_AC20_all_520_columns_type_mutation_and_missing_detected(self):
        schema = c.load_schema()
        covered = []
        for table, spec in schema["tables"].items():
            for column, rule in spec["columns"].items():
                with self.subTest(table=table, column=column, mutation="missing"):
                    left = golden()
                    del left["tables"][table][0][column]
                    self.assert_rejected(left)
                with self.subTest(table=table, column=column, mutation="wrong_type"):
                    left = golden()
                    left["tables"][table][0][column] = 1 if rule["type"] != "int" else True
                    self.assert_rejected(left)
                covered.append((table, column))
        self.assertEqual(len(set(covered)), 520)

    def test_AC21_lossless_types_nonfinite_null_timezone(self):
        values = [
            None,
            False,
            0,
            Decimal("1.00"),
            Decimal("1.0"),
            1.0,
            -0.0,
            0.0,
            date(2026, 2, 23),
            TIME,
            b"0",
            "0",
            [1],
            (1,),
            {"v": 1},
        ]
        encoded = [c.frame(v) for v in values]
        self.assertEqual(len(encoded), len(set(encoded)))
        for v in (
            float("nan"),
            float("inf"),
            Decimal("NaN"),
            datetime(2026, 1, 1),
            TIME.astimezone(__import__("datetime").timezone(timedelta(hours=8))),
            object(),
        ):
            with self.subTest(kind=type(v).__name__), self.assertRaises(Refused):
                c.typed(v)
        for change in (None, False, Decimal("1.25"), float("nan")):
            left = golden()
            left["tables"]["stock_factor_daily"][0]["close"] = change
            self.assert_rejected(left)

    def test_AC22_scope_multiset_ordinal_and_unordered_rows(self):
        left, right, ids = golden(), golden("right"), mapping()
        for snap, identifier in ((left, 4), (right, 14)):
            row = copy.deepcopy(snap["tables"]["data_publication_scope"][0])
            row["id"] = UUID(int=identifier)
            snap["tables"]["data_publication_scope"].append(row)
            snap["counts"]["data_publication_scope"] = 2
        ids["scope"].append((UUID(int=4), UUID(int=14)))
        right["tables"]["data_publication_scope"].reverse()
        result = c.compare_snapshots(left, right, ids)
        self.assertTrue(result["equal"], result)
        right["tables"]["data_publication_scope"].pop()
        right["counts"]["data_publication_scope"] = 1
        self.assert_rejected(left, right, ids)

    def test_AC23_full_identity_fk_json_candidate_and_orphan_closure(self):
        for table, column, value in (
            ("data_publication_row", "source_id", UUID(int=444)),
            ("data_quality_daily", "job_id", UUID(int=444)),
            ("signal_forward_eval", "signal_id", 999),
            ("theme_member_snapshot", "theme_code", "ORPHAN"),
        ):
            left, right = golden(), golden("right")
            for snap in (left, right):
                snap["tables"][table][0][column] = value
            self.assert_rejected(left, right)
        left = golden()
        left["tables"]["job_run"][0]["job_metadata"]["calc_run_id"] = str(UUID(int=222))
        self.assert_rejected(left)
        left = golden()
        left["tables"]["data_publication_row"][0]["row_data"]["calc_run_id"] = None
        self.assert_rejected(left)
        ids = mapping()
        ids["job"].append((UUID(int=8), UUID(int=11)))
        self.assert_rejected(golden(), ids=ids)

    def test_AC24_wrong_root_worker_token_parent_and_dependency(self):
        for col, val in (
            ("worker_id", "foreign-worker"),
            ("execution_token", UUID(int=99)),
            ("parent_job_id", UUID(int=1)),
            ("depends_on_job_id", UUID(int=1)),
        ):
            left = golden()
            left["tables"]["job_run"][0][col] = val
            self.assert_rejected(left)
        left = golden()
        left["root_id"] = UUID(int=222)
        self.assert_rejected(left)

    def test_AC25_three_lifecycles_and_unknown_ack_never_equal(self):
        for lifecycle in ("SUCCESS", "FAILED", "CANCELLED"):
            with self.subTest(lifecycle=lifecycle):
                left, right = golden(lifecycle=lifecycle), golden("right", lifecycle)
                result = c.compare_snapshots(left, right, mapping())
                self.assertTrue(result["equal"], result)
                for snap in (left, right):
                    snap["tables"]["data_publication"][0]["state"] = "PREPARING"
                self.assert_rejected(left, right)
        left = golden()
        left["commit_ack"] = "UNKNOWN"
        self.assert_rejected(left)

    def test_AC26_input_output_evidence_and_originals_separate(self):
        left, right = golden(), golden("right")
        before = c.frame(left), c.frame(right)
        for snap, duration in ((left, 0.5), (right, 2.0)):
            snap["tables"]["job_run"][0]["job_metadata"]["calculation_execution"] = {
                "job_id": str(snap["root_id"]),
                "elapsed_seconds": duration,
                "sql": {"SELECT": {"count": 1, "seconds": duration, "failures": 0}},
            }
        original_left, original_right = c.frame(left), c.frame(right)
        result = c.compare_snapshots(left, right, mapping())
        self.assertTrue(result["equal"], result)
        self.assertNotEqual(result["left_evidence"], result["right_evidence"])
        self.assertNotEqual(result["input_digest"], result["output_digest"])
        self.assertEqual((c.frame(left), c.frame(right)), (original_left, original_right))
        self.assertNotEqual(before, (original_left, original_right))
        self.assertFalse(result["real_pg_input_equal"])

    def test_full_execution_policy_and_consistently_wrong_nested_identities(self):
        schema = c.load_schema()
        left, right = golden(), golden("right")
        for snap in (left, right):
            source = {
                "source_sha256": schema["runtime_source_sha256"],
                "commit_sha": BASELINE,
                "worktree": "CLEAN",
            }
            snap["tables"]["job_run"][0]["job_metadata"]["calculation_execution"] = {
                "schema_version": "biz-perf-01.execution.v1",
                "job_id": str(snap["root_id"]),
                "root_job_id": str(snap["root_id"]),
                "flags": {
                    "factor_input_reuse_enabled": False,
                    "raw_preflight_batch_enabled": False,
                    "factor_cpu_optimization_enabled": False,
                },
                "source": source,
                "request": {"start": "2026-02-23", "end": "2026-02-24", "mode": "manual"},
                "commit_status": "LOCAL_HEAD_WITH_ACTUAL_SOURCE_DIGEST",
                "source_diagnostics": {
                    "worker_source": source,
                    "observed_source": source,
                    "git_metadata_changed": False,
                },
                "reads": {},
                "driver_reads": {},
                "sql": {},
                "stages": {},
                "elapsed_seconds": 0.1,
                "fetch_scope": "DELIVERED_PARTITIONS_NOT_WIRE_FETCH",
                "driver_fetch_scope": "SERVER_CURSOR_FETCHMANY_INCLUDING_PRIMING_AND_EOF",
                "timings_nested": True,
                "counter_scope": "ROOT_CUMULATIVE_INCLUDING_CHILDREN",
            }
        self.assertTrue(c.compare_snapshots(left, right, mapping())["equal"])
        for snap in (left, right):
            snap["tables"]["job_run"][0]["job_metadata"]["calculation_execution"][
                "source_diagnostics"
            ]["unexpected_financial"] = "PRIVATE"
        self.assert_rejected(left, right)

    def test_candidate_public_scope_and_stream_exception_are_fail_closed(self):
        left, right = golden(), golden("right")
        for snap in (left, right):
            snap["tables"]["data_publication_row"][0]["row_data"]["ma20"] = 123.0
        self.assert_rejected(left, right)
        left, right = golden(), golden("right")
        for snap in (left, right):
            snap["tables"]["data_publication_scope"][0]["start_date"] = date(2026, 2, 24)
            snap["tables"]["data_publication_scope"][0]["end_date"] = date(2026, 2, 24)
        self.assert_rejected(left, right)

        def broken_stream():
            raise Refused("PRIVATE_SQL_AND_DSN")
            yield None

        left = golden()
        left["tables"]["stock_daily"] = broken_stream()
        result = self.assert_rejected(left)
        self.assertNotIn("PRIVATE", str(result))

    def test_byte_budget_checked_before_unordered_buffer_grows(self):
        snap, schema, consumed = golden(), c.load_schema(), []
        original = snap["tables"]["trade_calendar"][0]

        def rows():
            for n in range(10):
                consumed.append(n)
                yield {**original, "cal_date": date(2025, 1, 1) + timedelta(days=n)}

        snap["tables"]["trade_calendar"] = rows()
        snap["counts"]["trade_calendar"] = 10
        schema["limits"]["total_bytes"] = 1
        reader = c.SnapshotReader(snap, schema, c.IdentityMap(mapping()), "left")
        with self.assertRaisesRegex(Refused, "R1_INCOMPLETE_RESOURCE_LIMIT"):
            next(reader.rows("trade_calendar"))
        self.assertEqual(consumed, [0])

    def test_stream_order_count_limits_and_bounded_errors(self):
        left, right = golden(), golden("right")
        left["ordering"] = right["ordering"] = "CANONICAL_STREAM"
        for snap in (left, right):
            snap["tables"] = {t: iter(rows) for t, rows in snap["tables"].items()}
        self.assertTrue(c.compare_snapshots(left, right, mapping())["equal"])
        left = golden()
        left["counts"]["stock_daily"] = 10001
        result = self.assert_rejected(left)
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertLess(len(canonical(result)), 1000)

    def test_unknown_json_time_bijection_delist_and_issue_code_tamper(self):
        left = golden()
        left["tables"]["data_quality_daily"][0]["issue_codes"] = {"unknown_private": "PRIVATE"}
        result = self.assert_rejected(left)
        self.assertNotIn("PRIVATE", str(result))
        left = golden()
        left["tables"]["job_run"][0]["heartbeat_at"] += timedelta(microseconds=1)
        self.assert_rejected(left)
        for snap in (golden(),):
            row = copy.deepcopy(snap["tables"]["stock_basic"][0])
            row.update(
                ts_code="000002.SZ",
                list_date=date(2025, 1, 11),
                delist_date=date(2025, 1, 27),
                list_status="D",
            )
            snap["tables"]["stock_basic"].append(row)
            snap["counts"]["stock_basic"] = 2
            self.assert_rejected(snap)

    def test_session_heartbeat_and_progress_copies_validate_before_observable_mapping(self):
        import hashlib

        left, right = golden(), golden("right")
        for snap, token, moment in (
            (left, UUID(int=2), TIME),
            (right, UUID(int=12), TIME + timedelta(seconds=10)),
        ):
            fp = hashlib.sha256(str(token).encode()).hexdigest()[:16]
            fact = {
                "application_name": f"space2/m/{snap['root_id'].hex}/{fp}",
                "pid": 101,
                "backend_start": (moment - timedelta(minutes=1)).isoformat(),
                "database_oid": 100,
                "postmaster_start": (TIME - timedelta(days=1)).isoformat(),
                "observed_at": moment.isoformat(),
            }
            meta = snap["tables"]["job_run"][0]["job_metadata"]
            meta["database_sessions"] = {
                "schema": "worker.sessions.v1",
                "root_job_id": str(snap["root_id"]),
                "execution_fingerprint": fp,
                "owner_fingerprint": hashlib.sha256(b"perf03-r1-synthetic").hexdigest()[:16],
                "roles": {"main": {"first": fact, "latest": copy.deepcopy(fact)}},
                "process_exit_proven": False,
                "status": "SERVER_OBSERVED_NOT_EXIT_PROOF",
            }
            meta["heartbeat_health"] = {
                "schema": "worker.heartbeat.v1",
                "state": "COMMUNICATION_CONFIRMED",
                "phase": "COMPLETE",
                "sqlstate": None,
                "computation_success_proven": False,
                "execution_fingerprint": fp,
                "consecutive_failures": 0,
                "unconfirmed_seconds": 1.0,
                "observed_at": moment.isoformat(),
                "last_confirmed_at": moment.isoformat(),
            }
            meta["calculation_progress"] = {
                "name": "factors.compute",
                "kind": "compute",
                "phase": "complete",
                "batch_index": 1,
                "batch_count": 1,
                "completed_rows": 1,
                "total_rows": 1,
                "started_at": moment.isoformat(),
                "updated_at": moment.isoformat(),
                "operation_started_at": moment.isoformat(),
                "advanced_at": moment.isoformat(),
                "elapsed_seconds": 1.0,
                "operation_elapsed_seconds": 1.0,
                "recent_events": [],
            }
        result = c.compare_snapshots(left, right, mapping())
        self.assertTrue(result["equal"], result)
        for change in ("fingerprint", "pg", "proof", "health", "unknown"):
            bad = copy.deepcopy(left)
            meta = bad["tables"]["job_run"][0]["job_metadata"]
            if change == "fingerprint":
                meta["database_sessions"]["execution_fingerprint"] = "0" * 16
            elif change == "pg":
                meta["database_sessions"]["roles"]["main"]["first"]["database_oid"] = 999
            elif change == "proof":
                meta["database_sessions"]["process_exit_proven"] = True
            elif change == "health":
                meta["heartbeat_health"]["state"] = "HEARTBEAT_DEGRADED"
            else:
                meta["calculation_progress"]["financial_private"] = 1
            self.assert_rejected(bad, right)
