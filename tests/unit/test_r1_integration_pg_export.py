"""Real exporter SQL/decoding against fake DB-API, all 520 columns exercised."""

import copy
import unittest
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from scripts import r1_integration_pg_export as e
from scripts.r1_real_root_protocol import Refused
from tests.unit.test_r1_business_snapshot_contract import golden, mapping
from tests.unit.test_r1_integration_pg_guard import FakeConnection, FakeCursor, guard, target


class ExportCursor(FakeCursor):
    def execute(self, sql, params=None):
        super().execute(sql, params)
        db = self.connection
        if sql == e.CATALOG_SQL:
            self.rows = copy.deepcopy(db.catalog)
        elif sql == e.SNAPSHOT_SQL:
            self.rows = [("123:124:",)]
        elif sql.startswith('SELECT "'):
            table = sql.split('FROM public."')[1].split('"')[0]
            cols = list(e.load_schema()["tables"][table]["columns"])
            self.description = [(c,) for c in cols]
            self.rows = [tuple(r[c] for c in cols) for r in db.tables[table]]
        return self


class ExportDB(FakeConnection):
    def __init__(self, fixture=None):
        super().__init__()
        self.fixture = fixture or golden()
        self.tables = copy.deepcopy(self.fixture["tables"])
        self.catalog = e.expected_catalog()

    def cursor(self, **_kwargs):
        c = ExportCursor(self)
        self.cursors.append(c)
        return c


def export(db=None, **kwargs):
    db = db or ExportDB()
    return e.PgTypedExporter(guard(), target(), evidence_kind="FAKE", **kwargs).export(
        lambda _: db,
        root_id=db.fixture["root_id"],
        independent_evidence=lambda binding: {
            "binding": binding,
            "root_id": db.fixture["root_id"],
            "worker": "perf03-r1-synthetic",
            "token": db.tables["job_run"][0]["execution_token"],
            "commit_ack": "KNOWN",
            "lease": "CONFIRMED",
            "connections_closed": True,
            "cleanup_ack": "CONFIRMED",
            "os_exit": "CONFIRMED",
        },
    )


class ExportTests(unittest.TestCase):
    def test_AC13_all_37_520_catalog_native_and_negative(self):
        db = ExportDB()
        packet = export(db)
        self.assertEqual(sum(len(s["columns"]) for s in e.load_schema()["tables"].values()), 520)
        self.assertEqual(len(packet.tables), 37)
        # Every declared column must pass native decode and reject an alien type.
        for table, spec in e.load_schema()["tables"].items():
            for col, rule in spec["columns"].items():
                with self.subTest(table=table, column=col):
                    e.decode_native(packet.tables[table][0][col], rule)
                    with self.assertRaises(Refused):
                        e.decode_native(object(), rule)
        self.assertTrue(db.closed and all(c.closed for c in db.cursors))

    def test_AC14_readonly_repeatable_catalog_drift(self):
        db = ExportDB()
        export(db)
        self.assertEqual(db.calls[0][0], e.BEGIN_SQL)
        self.assertFalse(any("SELECT *" in sql for sql, _ in db.calls))
        bad = ExportDB()
        bad.catalog.pop()
        with self.assertRaisesRegex(Refused, "SCHEMA_DRIFT"):
            export(bad)
        self.assertTrue(bad.closed)

    def test_AC15_types_jsonb_candidates_and_tuple(self):
        db = ExportDB()
        for name in ("data_publication_row", "data_publication_preimage"):
            row = db.tables[name][0]
            row["row_key"] = [
                v.isoformat() if hasattr(v, "isoformat") else v for v in row["row_key"]
            ]
            row["row_data"] = {
                k: str(v)
                if isinstance(v, UUID)
                else v.isoformat()
                if hasattr(v, "isoformat")
                else v
                for k, v in row["row_data"].items()
            }
        packet = export(db)
        self.assertIs(type(packet.tables["data_publication_row"][0]["row_key"]), tuple)
        decimal = Decimal("1.2300")
        self.assertEqual(
            e.decode_native(
                decimal, {"type": "decimal", "nullable": False, "precision": 8, "scale": 4}
            ),
            decimal,
        )
        with self.assertRaises(Refused):
            e.decode_native(decimal, {"type": "float", "nullable": False})

    def test_AC16_duplicate_missing_fk_and_key_closure(self):
        mutations = [
            lambda db: db.tables["sector"].clear(),
            lambda db: db.tables["stock_basic"].append(db.tables["stock_basic"][0]),
            lambda db: db.tables["data_publication_row"][0].update(row_key=["wrong"]),
            lambda db: db.tables["data_publication"][0].update(execution_token=UUID(int=8)),
        ]
        for mutate in mutations:
            db = ExportDB()
            mutate(db)
            with self.subTest(mutate=mutate), self.assertRaises(Refused):
                export(db)

    def test_AC17_nonfinite_timezone_scale_unmapped_json(self):
        for table, col, value in (
            ("stock_daily", "close", float("nan")),
            ("stock_basic", "updated_at", target().postmaster_start.replace(tzinfo=None)),
            ("job_run", "job_metadata", {"private": "unknown"}),
        ):
            db = ExportDB()
            db.tables[table][0][col] = value
            with self.subTest(column=col), self.assertRaises(Refused):
                export(db)
        with self.assertRaises(Refused):
            e.decode_native(
                Decimal("1.23"), {"type": "decimal", "nullable": False, "precision": 8, "scale": 4}
            )

    def test_AC18_budget_timeout_and_connection_failure(self):
        for options in ({"max_rows": 0}, {"max_bytes": 1}, {"seconds": 0}):
            db = ExportDB()
            with self.subTest(options=options), self.assertRaises(Refused):
                export(db, **options)
        db = ExportDB()
        db.identity = tuple(
            list(db.identity[:4])
            + [target().postmaster_start + timedelta(days=1)]
            + list(db.identity[5:])
        )
        with self.assertRaises(Refused):
            export(db)
        self.assertTrue(db.closed)

    def test_AC19_real_evidence_never_relabelled_synthetic(self):
        left, right = export(), export(ExportDB(golden("right")))
        result = e.compare_fake_exports(left, right, golden(), golden("right"), mapping())
        self.assertTrue(result["synthetic_equal"])
        left.evidence_kind = "PG_TYPED_UNVERIFIED"
        with self.assertRaisesRegex(Refused, "REAL_COMPARATOR_BRIDGE_NOT_AUTHORIZED"):
            e.compare_fake_exports(left, right, golden(), golden("right"), mapping())
        self.assertNotIn("000001.SZ", repr(left.safe_summary()))

    def test_independent_ack_cleanup_failure_and_fetch_exception(self):
        subject = e.PgTypedExporter(guard(), target(), evidence_kind="FAKE")
        db = ExportDB()
        with self.assertRaisesRegex(Refused, "EXPORT_INDEPENDENT_ACK_UNKNOWN"):
            subject.export(
                lambda _: db,
                root_id=db.fixture["root_id"],
                independent_evidence=lambda _: {"commit_ack": "UNKNOWN"},
            )
        self.assertTrue(db.closed and db.rolled_back)

        class BrokenCursor(ExportCursor):
            def fetchmany(self, size=128):
                raise OSError("PRIVATE CONNECTION INTERRUPTED")

        class BrokenDB(ExportDB):
            def cursor(self, **_):
                cur = BrokenCursor(self)
                self.cursors.append(cur)
                return cur

        db = BrokenDB()
        with self.assertRaisesRegex(Refused, "EXPORT_INCOMPLETE"):
            export(db)
        self.assertTrue(db.closed and all(c.closed for c in db.cursors))

    def test_identity_budget_and_duplicate_natural_key(self):
        with self.assertRaisesRegex(Refused, "EXPORT_IDENTITY_LIMIT"):
            export(identity_limit=1)
        db = ExportDB()
        row = copy.deepcopy(db.tables["data_quality_daily"][0])
        row["id"] += 1
        db.tables["data_quality_daily"].append(row)
        with self.assertRaisesRegex(Refused, "EXPORT_DUPLICATE_NATURAL_KEY"):
            export(db)


if __name__ == "__main__":
    unittest.main()
