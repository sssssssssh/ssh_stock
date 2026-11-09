"""Explicit fake DB-API identity tests; never opens a network connection."""

import copy
import unittest
from dataclasses import replace
from datetime import UTC, datetime
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
        if sql == g.IDENTITY_SQL:
            self.rows = [self.connection.identity]
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

    def cursor(self, **_kwargs):
        cursor = FakeCursor(self)
        self.cursors.append(cursor)
        return cursor

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def guard():
    # External approval is injected; this test verifier is not a production authority.
    return g.Pg17ResourceGuard(lambda t: g.review_binding(t), evidence_kind="FAKE")


class GuardTests(unittest.TestCase):
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
