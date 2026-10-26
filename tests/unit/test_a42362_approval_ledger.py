"""Transaction doubles test failure order, never PostgreSQL durability or live approvals."""

import json
import uuid

import pytest

from scripts.a42361_contract import Fault, canonical, sha
from scripts.a42361_offline_cases import binding
from scripts.a42362_approval_registry_service import ApprovalRegistryService
from scripts.a42362_contract import LedgerRequest, Scope, resources
from scripts.a42362_ledger import ResourceLedger
from scripts.a42362_service_host import ControlRepository


def scope():
    return Scope(
        token_id="32345678-1234-4234-8234-123456789012",
        binding=binding(),
        payload_sha256="1" * 64,
        image_digest="sha256:" + "2" * 64,
        controller_uid=1005,
        namespace_sha256="3" * 64,
        epoch="42345678-1234-4234-8234-123456789012",
    )


class Connection:
    def __init__(self, repo, role):
        self.repo, self.role, self.row, self.pending = repo, role, None, None
        self.calls = []

    def execute(self, query, parameters=None):
        self.calls.append(query)
        self.repo.calls.append((self.role, query))
        if "g1_consumptions" in query:
            s = scope()
            self.row = (
                s.payload_sha256,
                s.binding.fixture_uuid,
                s.binding.nonce,
                s.binding.identity.head_sha,
                "local",
                1,
            )
        elif query.startswith("INSERT"):
            self.pending = json.loads(parameters[-2])
            event_id = self.pending["event_id"]
            self.row = None if event_id in self.repo.rows else (len(self.repo.rows) + 1, "offline")
        elif "ORDER BY sequence DESC" in query:
            values = [
                v for v in self.repo.rows.values() if v[0]["resource"]["kind"] == parameters[1]
            ]
            self.row = (values[-1][0],) if values else None
        elif "WHERE event_id" in query:
            self.row = self.repo.rows.get(parameters[0])
        return self

    def fetchone(self):
        return self.row

    def commit(self):
        self.repo.commits += 1
        if self.pending:
            self.repo.rows[self.pending["event_id"]] = (
                self.pending,
                len(self.repo.rows) + 1,
                "offline",
            )
        if self.repo.fault == "commit":
            raise OSError("SECRET_SENTINEL")

    def rollback(self):
        self.calls.append("ROLLBACK")

    def close(self):
        self.calls.append("CLOSE")
        if self.repo.fault == "close":
            raise OSError("SECRET_SENTINEL")


class Repository:
    instance_sha256 = "a" * 64

    def __init__(self, fault=None):
        self.fault, self.rows, self.connections, self.calls, self.commits = fault, {}, [], [], 0

    def connect(self, role):
        c = Connection(self, role)
        if self.fault == "same" and self.connections:
            return self.connections[0]
        self.connections.append(c)
        return c

    def verify_scope(self, value):
        assert value == scope()  # Model only, never an independently verified deployment.

    def verify(self, connection, role):
        assert connection.role == role
        if self.fault == "identity":
            raise Fault("A42361_CONTROL_DATABASE_REJECTED")


def event(kind="SOCKET_DIR", state="RESERVED"):
    item = next(r for r in resources(scope()) if r.kind == kind)
    return LedgerRequest(resource=item, event=state, event_id=str(uuid.uuid4())).model_dump()


def test_AT15_AT16_actual_adapter_commits_then_uses_new_reader_connection():
    repo = Repository()
    q = event()
    result = ResourceLedger(repo).append(q)
    assert result["committed"] and repo.commits == 1 and len(repo.connections) == 2
    assert repo.connections[0] is not repo.connections[1]
    assert repo.connections[1].role == "receipt_reader" and result["request"] == q


@pytest.mark.parametrize("fault", ["commit", "same", "identity", "close"])
def test_AT14_AT15_bad_commit_or_read_never_retries_or_returns_success(fault):
    repo = Repository(fault)
    with pytest.raises(Fault):
        ResourceLedger(repo).append(event())
    assert repo.commits <= 1 and len(repo.connections) <= 2
    assert not any("CREATE TABLE" in query for _, query in repo.calls)


def test_AT18_no_second_create_after_committed_reservation():
    repo = Repository()
    ledger = ResourceLedger(repo)
    ledger.append(event())
    with pytest.raises(Fault):
        ledger.append(event())
    assert repo.commits == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("event", "DESTROY_ALL"),
        ("event_id", "bad"),
        ("approved", True),
        ("secret", "SECRET_SENTINEL"),
    ],
)
def test_AT17_closed_ledger_schema_rejects_before_connect(field, value):
    repo = Repository()
    q = event()
    q[field] = value
    with pytest.raises(Fault):
        ResourceLedger(repo).append(q)
    assert repo.connections == [] and repo.commits == 0


def test_AT07_AT11_AT12_default_approval_and_storage_cannot_mint_authority():
    with pytest.raises(Fault):
        ApprovalRegistryService().dispatch(1000, "import", dict(approved=True))
    with pytest.raises(Fault):
        ControlRepository().connect("consumer")


def test_AT19_schema_separates_actors_and_keeps_every_table_append_only():
    from pathlib import Path

    raw = (
        Path(__file__).resolve().parents[2] / "infra/g1_control_plane/002_services.sql"
    ).read_text()
    assert raw.count("BEFORE UPDATE OR DELETE OR TRUNCATE") == 7
    assert "GRANT INSERT,SELECT ON g1_control.resource_events TO g1_consumer" in raw
    assert "GRANT INSERT,SELECT ON g1_control.absence_events TO g1_auditor" in raw
    assert "pg_advisory_xact_lock_shared(42362,1)" in raw
    assert "pg_advisory_xact_lock(42362,1)" in raw
    assert "g1_approval_writer" in raw and "g1_receipt_reader" in raw


def test_AT62_records_contain_no_credential_field():
    raw = canonical(event())
    assert b"password" not in raw and b"SECRET_SENTINEL" not in raw
    assert len(sha(raw)) == 64
