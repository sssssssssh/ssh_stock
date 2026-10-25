"""Transaction protocol fault injection, NOT durable PostgreSQL integration evidence."""

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from scripts import a42361_one_shot_store as s
from scripts import a42361_trust_verifier as t
from scripts.a42361_contract import Fault, canonical, sha
from scripts.a42361_offline_cases import approval, payload


def model_grant():
    p = payload()
    digest = sha(canonical(p.model_dump()))
    return t.VerifiedGrant(p, digest, approval(p, digest), "a" * 64, 110, t._VERIFIED)


class ProtocolConnection:
    def __init__(self, grant, config, fault=None, shared=None):
        self.grant, self.config, self.fault = grant, config, fault
        self.shared = shared if shared is not None else dict(lock=threading.Lock(), tokens=set())
        self.calls = []
        self.row = None
        self.did_commit = False

    def execute(self, query, parameters=None):
        self.calls.append(query)
        if self.fault == "disconnect":
            raise RuntimeError("OFFLINE_SENSITIVE_SENTINEL")
        if "current_database" in query:
            self.row = (
                self.config.control_database,
                self.config.control_role,
                170010,
                self.config.control_instance_sha256,
                "G1_CONTROL_PLANE_ONLY",
            )
            if self.fault == "identity":
                self.row = ("business_db", *self.row[1:])
        elif query == s.CONSUME_SQL:
            if self.fault == "permission":
                raise PermissionError("OFFLINE_SENSITIVE_SENTINEL")
            with self.shared["lock"]:
                token = self.grant.payload.token_id
                if token in self.shared["tokens"] or self.fault == "conflict":
                    self.row = None
                else:
                    self.shared["tokens"].add(token)
                    self.row = (
                        *parameters[:2],
                        parameters[2],
                        parameters[3],
                        *parameters[4:],
                        "offline-time",
                    )
        elif "g1_audit_events" in query and "RETURNING event_id" in query:
            self.row = None if self.fault == "conflict" else (1,)
        return self

    def fetchone(self):
        return self.row

    def commit(self):
        self.calls.append("COMMIT")
        self.did_commit = True
        if self.fault == "commit_unknown":
            raise ConnectionError("OFFLINE_SENSITIVE_SENTINEL")

    def rollback(self):
        self.calls.append("ROLLBACK")


def setup(monkeypatch):
    config = NS(
        control_database="a42361_control_offline",
        control_role="g1_consumer",
        control_instance_sha256="1" * 64,
    )
    monkeypatch.setattr(s, "installed", lambda _: config)
    monkeypatch.setattr(s.time, "time", lambda: 110)
    grant = model_grant()

    def receipt(self, method, body):
        p = grant.payload
        return dict(
            event="CONSUMED",
            token_id=p.token_id,
            nonce=p.binding.nonce,
            approval_id=p.approval_id,
            payload_sha256=grant.payload_sha256,
            head_sha=p.binding.identity.head_sha,
            run_id=p.binding.identity.run_id,
            attempt=p.binding.identity.attempt,
            control_instance_sha256=config.control_instance_sha256,
            committed=True,
        )

    monkeypatch.setattr(s.LocalService, "call", receipt)
    return grant, config


def test_AT11_model_two_consumers_one_commit(monkeypatch):
    grant, config = setup(monkeypatch)
    shared = dict(lock=threading.Lock(), tokens=set())
    connections = [ProtocolConnection(grant, config, shared=shared) for _ in range(2)]

    def consume(conn):
        try:
            return s.PostgresConsumer(object()).consume_transaction(grant, conn)
        except Fault as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(consume, connections))
    assert sum(isinstance(x, s.CommittedConsumption) for x in result) == 1
    assert result.count("A42361_GRANT_ALREADY_CONSUMED") == 1
    assert sum(c.did_commit for c in connections) == 1


def test_AT12_schema_and_CAS_are_atomic_not_select_then_insert():
    raw = Path("infra/g1_control_plane/001_control.sql").read_text()
    assert "token_id uuid PRIMARY KEY" in raw
    assert "nonce uuid NOT NULL UNIQUE" in raw
    assert "approval_id uuid NOT NULL UNIQUE REFERENCES" in raw
    assert "ON CONFLICT DO NOTHING" in s.CONSUME_SQL and "RETURNING" in s.CONSUME_SQL
    assert "BEFORE UPDATE OR DELETE OR TRUNCATE" in raw
    assert "UNIQUE(token_id,event)" in raw
    assert "GRANT UPDATE" not in raw


@pytest.mark.parametrize(
    "fault,code",
    [
        ("disconnect", "CONSUME_FAILED_NO_RETRY"),
        ("permission", "CONSUME_FAILED_NO_RETRY"),
        ("identity", "CONTROL_DATABASE_REJECTED"),
        ("conflict", "GRANT_ALREADY_CONSUMED"),
        ("commit_unknown", "COMMIT_UNKNOWN_NO_RETRY"),
    ],
)
def test_AT13_AT14_fault_no_retry_or_secret(monkeypatch, fault, code):
    grant, config = setup(monkeypatch)
    conn = ProtocolConnection(grant, config, fault)
    with pytest.raises(Fault, match=code) as result:
        s.PostgresConsumer(object()).consume_transaction(grant, conn)
    assert "SENSITIVE" not in str(result.value)
    assert conn.calls.count(s.CONSUME_SQL) <= 1
    assert conn.calls.count("COMMIT") <= 1
    assert "ROLLBACK" in conn.calls


def test_AT13_lost_independent_ack_never_grants_fixture(monkeypatch):
    grant, config = setup(monkeypatch)
    conn = ProtocolConnection(grant, config)
    monkeypatch.setattr(s.LocalService, "call", lambda *a: dict(committed=False))
    with pytest.raises(Fault, match="COMMIT_UNKNOWN_NO_RETRY"):
        s.PostgresConsumer(object()).consume_transaction(grant, conn)
    assert conn.did_commit and conn.calls.count("COMMIT") == 1


def test_AT13_commit_precedes_fresh_receipt_query(monkeypatch):
    grant, config = setup(monkeypatch)
    conn = ProtocolConnection(grant, config)
    original = s.LocalService.call

    def query(*args):
        assert conn.did_commit
        return original(*args)

    monkeypatch.setattr(s.LocalService, "call", query)
    result = s.PostgresConsumer(object()).consume_transaction(grant, conn)
    assert s.committed(result) is result


@pytest.mark.parametrize("database", ["stock_db", "postgres", "a42361_control_offline"])
def test_AT15_unconfigured_or_business_database_no_connect(monkeypatch, database):
    import psycopg

    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: pytest.fail("unexpected connection"))
    if database != "a42361_control_offline":
        monkeypatch.setattr(s, "installed", lambda _: NS(control_database=database))
        with pytest.raises(Fault, match="CONTROL_DATABASE_REJECTED"):
            s.PostgresConsumer(object())._connect()
    else:
        with pytest.raises(Fault, match="DEPLOYMENT_NOT_CONFIGURED"):
            s.PostgresConsumer().consume_once(None)


@pytest.mark.parametrize("fault", [None, "conflict", "commit_unknown"])
def test_AT12_resource_creation_reservation_not_repeatable(monkeypatch, fault):
    grant, config = setup(monkeypatch)
    conn = ProtocolConnection(grant, config, fault)
    body = dict(
        event="CREATE_REQUESTED",
        token_id=grant.payload.token_id,
        payload_sha256=grant.payload_sha256,
        names=["offline"],
    )
    if fault:
        with pytest.raises(Fault):
            s.PostgresConsumer(object()).journal_transaction(body, conn)
    else:
        result = s.PostgresConsumer(object()).journal_transaction(body, conn)
        assert result == dict(
            event=body["event"], committed=True, request_sha256=sha(canonical(body))
        )
