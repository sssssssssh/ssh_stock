"""Explicit fake DB-API identity tests; never opens a network connection."""

import copy
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from scripts import r1_integration_pg_guard as g
from scripts.r1_real_root_protocol import Refused

NOW = datetime(2026, 2, 24, tzinfo=UTC)


def target():
    return g.ReviewedTarget(
        config_ref="reviewed-lab",
        system_identifier="7123456789012345678",
        marker=UUID(int=100),
        database_oid=100,
        postmaster_start=NOW,
        database_name="r1_isolated_test",
        role="r1_export_reader",
        environment=UUID(int=101),
        owner_scope="single-lab",
    )


def observation(t=None):
    t = t or target()
    return (
        170004,
        t.system_identifier,
        str(t.marker),
        t.database_oid,
        t.postmaster_start,
        t.database_name,
        t.role,
        False,
        False,
        False,
        False,
        False,
        False,
        [],
        str(t.environment),
        True,
    )


class FakeCursor:
    def __init__(self, connection):
        self.connection, self.rows, self.description = connection, [], None
        self.closed = False

    def execute(self, sql, params=None):
        self.connection.calls.append((sql, params))
        db = self.connection
        if not db.autocommit and db.info.transaction_status == 0:
            db.info.transaction_status = 2
            db.isolation, db.readonly = "read committed", "off"
        if sql == g.BEGIN_SQL and db.info.transaction_status == 0:
            db.info.transaction_status = 2
            db.isolation, db.readonly = "repeatable read", "on"
        if sql == g.IDENTITY_SQL:
            self.rows = [self.connection.identity]
        elif sql == "SHOW transaction_isolation":
            self.rows = [(db.isolation,)]
        elif sql == "SHOW transaction_read_only":
            self.rows = [(db.readonly,)]
        else:
            self.rows = []
        return self

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchmany(self, size=128):
        rows, self.rows = self.rows[:size], self.rows[size:]
        return rows

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, identity=None):
        self.identity = identity or observation()
        self.calls, self.cursors = [], []
        self.closed, self.rolled_back = False, False
        self.autocommit = False
        self.info = SimpleNamespace(transaction_status=0)
        self.isolation, self.readonly = "read committed", "off"

    def cursor(self, **_kwargs):
        cursor = FakeCursor(self)
        self.cursors.append(cursor)
        return cursor

    def rollback(self):
        self.rolled_back = True
        self.info.transaction_status = 0

    def close(self):
        self.closed = True


def guard():
    # External approval is injected; this test verifier is not a production authority.
    return g.Pg17ResourceGuard(lambda t: g.review_binding(t), evidence_kind="FAKE")


class GuardTests(unittest.TestCase):
    def test_driver_auto_begin_is_not_server_rr_readonly(self):
        db = FakeConnection()
        # Faithful default psycopg auto-BEGIN followed by ignored explicit BEGIN.
        db.cursor().execute(g.BEGIN_SQL)
        self.assertEqual((db.isolation, db.readonly), ("read committed", "off"))
        with self.assertRaises(Refused):
            guard().check_connection(db, target())
        self.assertFalse(any(sql == g.IDENTITY_SQL for sql, _ in db.calls))

    def test_controlled_begin_checks_server_and_rejects_active_or_unknown_connection(self):
        db = FakeConnection()
        guard().inspect(lambda _: db, target())
        self.assertTrue(db.autocommit)
        self.assertEqual([sql for sql, _ in db.calls[:3]], [g.BEGIN_SQL,
                         "SHOW transaction_isolation", "SHOW transaction_read_only"])
        for status in (1, 2, 3, 4, None, True):
            db = FakeConnection()
            db.info.transaction_status = status
            with self.subTest(status=status), self.assertRaises(Refused):
                guard().inspect(lambda _, db=db: db, target())
            self.assertEqual(db.calls, [])
            self.assertTrue(db.closed)

    def test_server_value_mismatch_and_query_errors_fail_closed(self):
        for iso, ro in (("read committed", "on"), ("repeatable read", "off"),
                        (None, "on"), ("REPEATABLE READ", "on")):
            db = FakeConnection()
            db.autocommit = True
            db.info.transaction_status = 2
            db.isolation, db.readonly = iso, ro
            with self.subTest(iso=iso, ro=ro), self.assertRaises(Refused):
                guard().check_connection(db, target())
            self.assertFalse(any(sql == g.IDENTITY_SQL for sql, _ in db.calls))

    def test_rollback_failure_still_attempts_close_and_never_issues_receipt(self):
        class Broken(FakeConnection):
            def rollback(self):
                raise OSError("PRIVATE")
        db, subject = Broken(), guard()
        with self.assertRaisesRegex(Refused, "PG_CLEANUP_UNCERTAIN"):
            subject.inspect(lambda _: db, target())
        self.assertTrue(db.closed)
        self.assertEqual(subject.issued, [])

    def test_query_or_close_failure_cannot_issue_ack(self):
        for operation in ("show", "close"):
            class BrokenCursor(FakeCursor):
                def execute(self, sql, params=None, _operation=operation):
                    if _operation == "show" and sql.startswith("SHOW"):
                        raise OSError("PRIVATE")
                    return super().execute(sql, params)

            class BrokenDB(FakeConnection):
                def cursor(self, **_):
                    cur = BrokenCursor(self)
                    self.cursors.append(cur)
                    return cur

                def close(self, _operation=operation):
                    self.closed = True
                    if _operation == "close":
                        raise OSError("PRIVATE")

            db, subject = BrokenDB(), guard()
            with self.subTest(operation=operation), self.assertRaises(Refused) as error:
                subject.inspect(lambda _, db=db: db, target())
            self.assertNotIn("PRIVATE", str(error.exception))
            self.assertTrue(db.closed)
            self.assertEqual(subject.issued, [])

    def test_AC01_preconnect_unknown_configuration(self):
        calls = []
        with self.assertRaises(Refused):
            guard().inspect(lambda ref: calls.append(ref), replace(target(), config_ref=""))
        self.assertEqual(calls, [])

    def test_AC02_external_review_precedes_connect(self):
        calls = []
        with self.assertRaises(Refused):
            g.Pg17ResourceGuard(lambda _: None).inspect(lambda x: calls.append(x), target())
        self.assertEqual(calls, [])

    def test_AC03_physical_identity_and_readonly_sql(self):
        db, subject = FakeConnection(), guard()
        receipt = subject.inspect(lambda _: db, target())
        subject.require_ready(receipt, "single-lab")
        self.assertEqual(receipt.evidence_kind, "FAKE")
        self.assertTrue(db.closed and db.rolled_back)
        self.assertTrue(all(c.closed for c in db.cursors))
        self.assertEqual(db.calls[0][0], g.BEGIN_SQL)
        self.assertNotIn("r1_export_reader", repr(receipt))
        with self.assertRaises(Refused):
            subject.require_ready(copy.copy(receipt), "single-lab")

    def test_AC04_physical_version_database_marker_replay(self):
        for index, value in (
            (0, 160004),
            (1, "999"),
            (2, str(UUID(int=999))),
            (3, 999),
            (5, "business"),
            (14, str(UUID(int=999))),
            (15, False),
        ):
            with self.subTest(index=index):
                row = list(observation())
                row[index] = value
                db = FakeConnection(tuple(row))
                with self.assertRaises(Refused):
                    guard().inspect(lambda _, db=db: db, target())
                self.assertTrue(db.closed)

    def test_AC05_role_privileges_and_unknown(self):
        for index, value in (
            (6, "admin"),
            (7, True),
            (8, True),
            (9, True),
            (10, True),
            (11, True),
            (12, True),
            (13, ["rds_superuser"]),
        ):
            with self.subTest(index=index):
                row = list(observation())
                row[index] = value
                with self.assertRaises(Refused):
                    guard().inspect(lambda _, row=row: FakeConnection(tuple(row)), target())

    def test_AC06_reconnect_restart_permissions_and_safe_errors(self):
        subject = guard()
        row = list(observation())
        row[4] = NOW.replace(day=25)
        with self.assertRaisesRegex(Refused, "PG_IDENTITY_MISMATCH"):
            subject.inspect(lambda _: FakeConnection(tuple(row)), target())

        def broken(_):
            raise RuntimeError("PRIVATE-DSN-password")

        with self.assertRaises(Refused) as error:
            subject.inspect(broken, target())
        self.assertEqual(str(error.exception), "PG_INSPECTION_INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
