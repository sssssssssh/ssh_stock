"""Transaction protocol fault injection, NOT durable PostgreSQL integration evidence."""

import json
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
        self.shared = shared if shared is not None else config.shared
        self.calls = []
        self.row = None
        self.did_commit = False
        self.closed = False
        self.pending = None
        self.journal = None

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
                        parameters[3],
                        parameters[4],
                        *parameters[5:],
                        "offline-time",
                    )
                    self.pending = self.row
        elif "FROM g1_control.g1_consumptions" in query and query.startswith("SELECT"):
            row = self.shared.get("committed", {}).get(parameters[0])
            self.row = row[:7] if row is not None and row[3] == parameters[1] else None
        elif query.startswith("SELECT details"):
            self.row = self.shared.get("journals", {}).get((parameters[0], parameters[2]))
        elif "g1_audit_events" in query and "RETURNING event_id" in query:
            base = "a42361-" + self.grant.payload.binding.fixture_uuid.replace("-", "")
            journals = self.shared.get("journals", {})
            permitted = (
                parameters[-1] == base
                and parameters[2] in self.shared.get("committed", {})
                and (parameters[2], parameters[0]) not in journals
                and (parameters[4] == "CONSUMED" or (parameters[2], parameters[4]) in journals)
            )
            self.row = None if self.fault == "conflict" or not permitted else (1,)
            self.journal = json.loads(parameters[1])
        return self

    def fetchone(self):
        return self.row

    def commit(self):
        self.calls.append("COMMIT")
        self.did_commit = True
        if self.pending:
            self.shared.setdefault("committed", {})[self.pending[0]] = self.pending
        if self.journal:
            j = self.journal
            self.shared.setdefault("journals", {})[(j["token_id"], j["event"])] = (j,)
        if self.fault == "commit_unknown":
            raise ConnectionError("OFFLINE_SENSITIVE_SENTINEL")

    def rollback(self):
        self.calls.append("ROLLBACK")

    def close(self):
        self.closed = True


def setup(monkeypatch):
    config = NS(
        control_database="a42361_control_offline",
        control_role="g1_consumer",
        control_instance_sha256="1" * 64,
        shared=dict(lock=threading.Lock(), tokens=set()),
    )
    monkeypatch.setattr(s, "installed", lambda _: config)
    monkeypatch.setattr(s.time, "time", lambda: 110)
    grant = model_grant()

    monkeypatch.setattr(s.PostgresConsumer, "_connect", lambda _: ProtocolConnection(grant, config))
    monkeypatch.setattr(
        s.LocalService, "call", lambda *a: pytest.fail("consumer must not call its own RPC")
    )
    return grant, config


def test_AT11_model_two_consumers_one_commit(monkeypatch):
    grant, config = setup(monkeypatch)
    shared = dict(lock=threading.Lock(), tokens=set())
    config.shared = shared
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
    assert "fixture_uuid uuid NOT NULL UNIQUE" in raw
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
    monkeypatch.setattr(s.PostgresConsumer, "_fresh_receipt", lambda *a: dict(committed=False))
    with pytest.raises(Fault, match="COMMIT_UNKNOWN_NO_RETRY"):
        s.PostgresConsumer(object()).consume_transaction(grant, conn)
    assert conn.did_commit and conn.calls.count("COMMIT") == 1


def test_AT13_commit_precedes_fresh_receipt_query(monkeypatch):
    grant, config = setup(monkeypatch)
    conn = ProtocolConnection(grant, config)
    reader = ProtocolConnection(grant, config)

    def query(*args):
        assert conn.did_commit
        return reader

    monkeypatch.setattr(s.PostgresConsumer, "_connect", query)
    result = s.PostgresConsumer(object()).consume_transaction(grant, conn)
    assert s.committed(result) is result
    assert reader.closed and sum("current_database" in q for q in reader.calls) == 1
    assert "COMMIT" not in reader.calls


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
    s.PostgresConsumer(object()).consume_transaction(grant, ProtocolConnection(grant, config))
    conn = ProtocolConnection(grant, config, fault)
    base = "a42361-" + grant.payload.binding.fixture_uuid.replace("-", "")
    body = dict(
        event="CREATE_REQUESTED",
        token_id=grant.payload.token_id,
        payload_sha256=grant.payload_sha256,
        names=[base, base + "-data", base + "-owner-init"],
    )
    if fault:
        with pytest.raises(Fault):
            s.PostgresConsumer(object()).journal_transaction(body, conn)
    else:
        result = s.PostgresConsumer(object()).journal_transaction(body, conn)
        assert result == dict(
            event=body["event"], committed=True, request_sha256=sha(canonical(body))
        )
        duplicate = ProtocolConnection(grant, config)
        with pytest.raises(Fault, match="RESOURCE_ALREADY_RESERVED"):
            s.PostgresConsumer(object()).journal_transaction(body, duplicate)
        assert not duplicate.did_commit


def test_receiver_source_gap_has_real_bounded_server_not_only_rpc_client():
    from scripts import a42361_deployment as d

    assert callable(getattr(d, "LocalReceiver", None))
    assert callable(getattr(s, "ConsumerService", None))


def test_committed_receipt_rechecks_database_identity_on_new_connection(monkeypatch):
    grant, config = setup(monkeypatch)
    writer = ProtocolConnection(grant, config)
    reader = ProtocolConnection(grant, config, fault="identity")
    reader.close = lambda: None
    consumer = s.PostgresConsumer(object())
    monkeypatch.setattr(consumer, "_connect", lambda: reader)
    with pytest.raises(Fault, match="COMMIT_UNKNOWN_NO_RETRY"):
        consumer.consume_transaction(grant, writer)
    assert writer.did_commit
    assert not any("FROM g1_control.g1_consumptions" in q for q in reader.calls)


def test_receipt_rejects_malformed_lookup_before_connect(monkeypatch):
    setup(monkeypatch)
    consumer = s.PostgresConsumer(object())
    monkeypatch.setattr(consumer, "_connect", lambda: pytest.fail("malformed receipt connected"))
    with pytest.raises(Fault, match="SCHEMA_INVALID"):
        consumer.read_receipt("not-a-uuid", "a" * 64)


def consumer_service_model(monkeypatch):
    """OFFLINE_MODEL: no socket, PostgreSQL, signature or installed identity."""
    grant, config = setup(monkeypatch)
    for index, domain in enumerate(
        ("consumer", "controller", "supervisor", "pg_owner", "absence_auditor")
    ):
        setattr(config, domain, NS(peer_uid=1000 + index))
    monkeypatch.setattr(s.os, "getuid", lambda: config.consumer.peer_uid)
    return s.ConsumerService(object()), grant, config


@pytest.mark.parametrize(
    "method,peer", [("consume", 1001), ("journal", 1002), ("receipt", 0), ("run", 1002)]
)
def test_consumer_receiver_peer_and_method_denied_before_any_backend(monkeypatch, method, peer):
    service, _, _ = consumer_service_model(monkeypatch)
    monkeypatch.setattr(s.PostgresConsumer, "_connect", lambda _: pytest.fail("backend reached"))
    monkeypatch.setattr(
        s.TrustVerifier, "verify_signature", lambda *a: pytest.fail("crypto reached")
    )
    with pytest.raises(Fault, match="PEER_IDENTITY_MISMATCH|RPC_METHOD_REJECTED"):
        service.dispatch(peer, method, {})


def test_consumer_receiver_reverifies_original_envelope_and_exact_source(monkeypatch):
    from scripts import a42361_source_guard as guard

    service, grant, config = consumer_service_model(monkeypatch)
    calls = []
    b = grant.payload.binding

    def source(*args):
        calls.append("source")
        assert args == (
            b.identity.run_id,
            b.identity.attempt,
            b.fixture_uuid,
            b.nonce,
            b.marker_sha256,
        )
        return b

    def verify(self, envelope, expected):
        calls.append("verify")
        assert envelope == b"original-signed-envelope" and expected == b
        return grant

    def consume(self, incoming):
        calls.append("consume")
        assert incoming is grant
        return NS(receipt_sha256="c" * 64)

    monkeypatch.setattr(guard, "independent_binding", source)
    monkeypatch.setattr(s.TrustVerifier, "verify_signature", verify)
    monkeypatch.setattr(s.PostgresConsumer, "consume_once", consume)
    body = dict(
        envelope_hex=b"original-signed-envelope".hex(),
        payload_sha256=grant.payload_sha256,
        binding=b.model_dump(),
    )
    assert service.dispatch(config.supervisor.peer_uid, "consume", body) == dict(
        receipt_sha256="c" * 64, committed=True
    )
    assert calls == ["source", "verify", "consume"]


@pytest.mark.parametrize("change", ["source", "digest", "signature", "unknown", "badhex"])
def test_consumer_receiver_rejects_drift_or_signature_without_consumption(monkeypatch, change):
    from scripts import a42361_source_guard as guard

    service, grant, config = consumer_service_model(monkeypatch)
    b = grant.payload.binding
    monkeypatch.setattr(guard, "independent_binding", lambda *a: b if change != "source" else None)

    def verify(*args):
        if change == "signature":
            raise Fault("A42361_SIGNATURE_INVALID")
        return grant

    monkeypatch.setattr(s.TrustVerifier, "verify_signature", verify)
    monkeypatch.setattr(
        s.PostgresConsumer, "consume_once", lambda *a: pytest.fail("consume reached")
    )
    body = dict(
        envelope_hex=b"signed".hex(), payload_sha256=grant.payload_sha256, binding=b.model_dump()
    )
    if change == "digest":
        body["payload_sha256"] = "0" * 64
    if change == "unknown":
        body["approved"] = True
    if change == "badhex":
        body["envelope_hex"] = "ff "
    with pytest.raises(Fault):
        service.dispatch(config.supervisor.peer_uid, "consume", body)


def test_consumer_default_receiver_refuses_even_supplied_fd_before_inspection(monkeypatch):
    from scripts import a42361_deployment as d

    monkeypatch.setattr(d.socket, "fromfd", lambda *a: pytest.fail("FD inspected"))
    with pytest.raises(Fault, match="DEPLOYMENT_NOT_CONFIGURED"):
        s.ConsumerService().serve_once(0)


@pytest.mark.parametrize(
    "fault", ["missing", "wrong_digest", "wrong_identity", "same_connection", "close"]
)
def test_committed_receipt_failure_never_refunds_or_repeats_transaction(monkeypatch, fault):
    grant, config = setup(monkeypatch)
    consumer = s.PostgresConsumer(object())
    writer = ProtocolConnection(grant, config)
    reader = ProtocolConnection(
        grant, config, fault="identity" if fault == "wrong_identity" else None
    )
    original_execute = reader.execute

    def execute(query, parameters=None):
        result = original_execute(query, parameters)
        if query.startswith("SELECT token_id"):
            if fault == "missing":
                reader.row = None
            elif fault == "wrong_digest":
                row = list(reader.row)
                row[3] = "0" * 64
                reader.row = tuple(row)
        return result

    reader.execute = execute
    if fault == "close":

        def close():
            raise RuntimeError("OFFLINE_SECRET_SENTINEL")

        reader.close = close
    monkeypatch.setattr(
        consumer, "_connect", lambda: writer if fault == "same_connection" else reader
    )
    with pytest.raises(Fault, match="COMMIT_UNKNOWN_NO_RETRY") as result:
        consumer.consume_transaction(grant, writer)
    assert "SECRET" not in str(result.value)
    assert writer.did_commit and writer.calls.count("COMMIT") == 1
    assert writer.calls.count(s.CONSUME_SQL) == 1


def test_journal_ack_reads_committed_event_on_fresh_identity_checked_connection(monkeypatch):
    grant, config = setup(monkeypatch)
    s.PostgresConsumer(object()).consume_transaction(grant, ProtocolConnection(grant, config))
    writer, reader = ProtocolConnection(grant, config), ProtocolConnection(grant, config)
    base = "a42361-" + grant.payload.binding.fixture_uuid.replace("-", "")
    body = dict(
        event="CREATE_REQUESTED",
        token_id=grant.payload.token_id,
        payload_sha256=grant.payload_sha256,
        names=[base, base + "-data", base + "-owner-init"],
    )
    consumer = s.PostgresConsumer(object())

    def connect():
        assert writer.did_commit
        return reader

    monkeypatch.setattr(consumer, "_connect", connect)
    result = consumer.journal_transaction(body, writer)
    assert result == dict(event=body["event"], committed=True, request_sha256=sha(canonical(body)))
    assert reader.closed and any(q.startswith("SELECT details") for q in reader.calls)
    assert sum("current_database" in q for q in reader.calls) == 1


def test_journal_cannot_reserve_names_for_a_different_approved_fixture(monkeypatch):
    grant, config = setup(monkeypatch)
    consumer = s.PostgresConsumer(object())
    consumer.consume_transaction(grant, ProtocolConnection(grant, config))
    base = "a42361-" + "f" * 32
    body = dict(
        event="CREATE_REQUESTED",
        token_id=grant.payload.token_id,
        payload_sha256=grant.payload_sha256,
        names=[base, base + "-data", base + "-owner-init"],
    )
    writer = ProtocolConnection(grant, config)
    with pytest.raises(Fault, match="RESOURCE_ALREADY_RESERVED"):
        consumer.journal_transaction(body, writer)
    assert not writer.did_commit
    query = next(q for q in writer.calls if "RETURNING event_id" in q)
    assert "replace(c.fixture_uuid::text" in query


@pytest.mark.parametrize(
    "change", ["names", "path", "secret_missing", "secret_extra", "token", "unknown"]
)
def test_journal_malformed_request_rejected_before_connection(monkeypatch, change):
    grant, _ = setup(monkeypatch)
    base = "a42361-" + "1" * 32
    body = dict(
        event="CREATE_REQUESTED",
        token_id=grant.payload.token_id,
        payload_sha256=grant.payload_sha256,
        names=[base, base + "-data", base + "-owner-init"],
    )
    if change == "names":
        body["names"][1] = "unrelated-volume"
    elif change == "path":
        body["names"][0] = "../" + base
    elif change == "secret_missing":
        body["event"] = "SECRET_CREATED"
    elif change == "secret_extra":
        body["secret_id"] = "unexpected"
    elif change == "token":
        body["token_id"] = "invalid"
    else:
        body["approved"] = True
    monkeypatch.setattr(
        s.PostgresConsumer, "_connect", lambda *a: pytest.fail("invalid journal connected")
    )
    with pytest.raises(Fault):
        s.PostgresConsumer(object()).append_journal(body)


def framed_receiver_model(monkeypatch, frame, *, peer_uid=1002, error=None, ticks=None):
    """Byte-backed OFFLINE_MODEL, not a socket or service installation."""
    import socket
    import stat
    import struct

    from scripts import a42361_deployment as d

    config = NS(
        root_directory="/run/a42361-offline", consumer=NS(socket_name="consumer", peer_uid=1000)
    )
    calls = []
    path = config.root_directory + "/consumer.sock"
    meta = NS(st_mode=stat.S_IFSOCK | 0o660, st_uid=1000)

    class Peer:
        def __init__(self):
            self.input = frame
            self.output = b""
            self.timeouts = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def getsockopt(self, *args):
            return struct.pack("3i", 123, peer_uid, 2000)

        def settimeout(self, value):
            self.timeouts.append(value)

        def recv(self, n):
            data, self.input = self.input[: min(n, 3)], self.input[min(n, 3) :]
            return data

        def sendall(self, value):
            self.output += value

    peer = Peer()

    class Listener(Peer):
        family, type = socket.AF_UNIX, socket.SOCK_STREAM

        def getsockname(self):
            return path

        def getsockopt(self, *args):
            return 1

        def accept(self):
            calls.append("accept")
            return peer, None

    class Receiver(d.LocalReceiver):
        domain = "consumer"

        def allowed_uids(self, config):
            return {1002}

        def dispatch(self, uid, method, body):
            calls.append((uid, method, body))
            if error:
                raise error
            return dict(committed=True)

    monkeypatch.setattr(d, "installed", lambda _: config)
    monkeypatch.setattr(d.os, "getuid", lambda: 1000)
    monkeypatch.setattr(d.Path, "is_symlink", lambda _: False)
    monkeypatch.setattr(d.Path, "stat", lambda _: meta)
    monkeypatch.setattr(d.socket, "SO_PEERCRED", 17, raising=False)
    monkeypatch.setattr(d.socket, "fromfd", lambda *a: Listener())
    if ticks:
        clock = iter(ticks)
        monkeypatch.setattr(d.time, "monotonic_ns", lambda: next(clock))
    return Receiver(object()), peer, calls


def rpc_frame(body=None):
    import struct

    raw = canonical(dict(schema_version="a42361.rpc.v1", method="receipt", body=body or {}))
    return struct.pack("!I", len(raw)) + raw


def test_receiver_parses_fragmented_frame_with_authenticated_peer_and_bounded_reply(monkeypatch):
    import struct

    receiver, peer, calls = framed_receiver_model(monkeypatch, rpc_frame(dict(token_id="model")))
    receiver.serve_once(3)
    assert calls == ["accept", (1002, "receipt", dict(token_id="model"))]
    expected = canonical(dict(committed=True))
    assert peer.output == struct.pack("!I", len(expected)) + expected
    assert all(0 < x <= 1 for x in peer.timeouts)


@pytest.mark.parametrize("raw", [b"", b"\0\0\0\0", b"\0\1\0\1", b"\0\0\0\x02{", b"\0\0\0\x02[]"])
def test_receiver_bad_frames_never_dispatch_or_echo_request(monkeypatch, raw):
    receiver, peer, calls = framed_receiver_model(monkeypatch, raw)
    receiver.serve_once(3)
    assert calls == ["accept"]
    assert b"rpc-error.v1" in peer.output and b"committed" not in peer.output


def test_receiver_foreign_uid_denied_before_reading_even_a_valid_frame(monkeypatch):
    receiver, peer, calls = framed_receiver_model(monkeypatch, rpc_frame(), peer_uid=0)
    with pytest.raises(Fault, match="PEER_IDENTITY_MISMATCH"):
        receiver.serve_once(3)
    assert peer.input == rpc_frame() and not peer.output and calls == ["accept"]


def test_receiver_absolute_deadline_not_reset_by_fragmented_progress(monkeypatch):
    receiver, peer, calls = framed_receiver_model(
        monkeypatch, rpc_frame(), ticks=[1, 2, 3, 4, 1_000_000_002, 1_000_000_003]
    )
    with pytest.raises(Fault, match="RPC_TIMEOUT"):
        receiver.serve_once(3)
    assert calls == ["accept"] and not peer.output


def test_receiver_unknown_backend_error_is_redacted_and_never_retried(monkeypatch):
    receiver, peer, calls = framed_receiver_model(
        monkeypatch, rpc_frame(), error=RuntimeError("OFFLINE_SECRET_SENTINEL")
    )
    receiver.serve_once(3)
    assert b"A42361_SERVICE_UNAVAILABLE" in peer.output and b"SECRET" not in peer.output
    assert len(calls) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "999"),
        ("attempt", 2),
        ("attempt", True),
        ("payload_sha256", "0" * 64),
        ("control_instance_sha256", "0" * 64),
        ("nonce", "92345678-1234-4234-8234-123456789012"),
        ("committed", False),
        ("unknown", True),
    ],
)
def test_control_service_checks_full_receipt_identity_before_controller(monkeypatch, field, value):
    from scripts import a42361_control_service as c
    from scripts import a42361_source_guard as guard

    _, grant, config = consumer_service_model(monkeypatch)
    monkeypatch.setattr(c, "installed", lambda _: config)
    monkeypatch.setattr(c.os, "getuid", lambda: config.supervisor.peer_uid)
    monkeypatch.setattr(guard, "independent_binding", lambda *a: grant.payload.binding)
    monkeypatch.setattr(c.TrustVerifier, "verify_signature", lambda *a: grant)
    receipt = s.expected_receipt(grant, config)
    receipt[field] = value
    calls = []

    def rpc(self, method, body, timeout_ms=200):
        assert self.domain == "consumer"  # No C/D/E resource call may occur.
        calls.append(method)
        if method == "consume":
            return dict(receipt_sha256=sha(canonical(receipt)), committed=True)
        return receipt

    monkeypatch.setattr(c.LocalService, "call", rpc)
    with pytest.raises(Fault):
        c.ControlService(object()).run_approved(b"original-envelope", grant.payload.binding)
    assert calls == ["consume", "receipt"]
