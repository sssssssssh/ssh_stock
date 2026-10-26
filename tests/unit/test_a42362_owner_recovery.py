"""Budget/method and partial-resource fault injection; no PG or Podman is invoked."""

import uuid

import pytest

from scripts.a42361_contract import Fault, canonical, sha
from scripts.a42361_offline_cases import binding
from scripts.a42362_contract import Scope, receipt, resources, transition
from scripts.a42362_pg_owner_service import MethodDecision, PgOwnerService, require_session_method
from scripts.a42362_reconcile import Reconciler


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


class Ledger:
    def __init__(self):
        self.rows = []

    def append(self, body):
        previous = [r for r in self.rows if r["request"]["resource"] == body["resource"]]
        transition(previous[-1]["request"]["event"] if previous else None, body)
        r = receipt(body, len(self.rows) + 1, "offline", "a" * 64).model_dump()
        self.rows.append(r)
        return r

    def scan(self, body):
        return dict(events=list(self.rows), snapshot_sha256=sha(canonical(self.rows)))


class Driver:
    def __init__(self, ledger, failure=None):
        self.ledger, self.failure, self.created, self.removed = ledger, failure, [], []

    def create(self, item):
        assert self.ledger.rows[-1]["request"]["event"] == "CREATE_ATTEMPTED"
        self.created.append(item.kind)
        if self.failure == item.kind:
            raise TimeoutError("SECRET_SENTINEL")
        return dict(kind=item.kind)

    def inspect(self, item):
        return dict(kind=item.kind)

    def verify(self, item, raw):
        assert raw == dict(kind=item.kind)
        return sha(canonical(raw))

    def remove(self, item, raw):
        assert self.ledger.rows[-1]["request"]["event"] == "REMOVE_ATTEMPTED"
        self.removed.append(item.kind)

    def absent(self, item):
        return item.kind in self.removed


@pytest.mark.parametrize("kind", ["SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER"])
def test_AT30_AT34_each_create_ack_loss_is_journaled_without_second_create(kind):
    ledger = Ledger()
    driver = Driver(ledger, failure=kind)
    c = Reconciler(ledger, driver)
    with pytest.raises(Fault):
        c.create(scope())
    assert ledger.rows[-1]["request"]["event"] == "UNKNOWN"
    count = len(driver.created)
    with pytest.raises(Fault):
        c.create(scope())
    assert len(driver.created) == count
    result = c.recover(scope())
    assert result["qualifies"] is False and result["independent_absent"] is False
    assert set(driver.removed) <= set(driver.created)


def test_AT16_uncommitted_reservation_prevents_first_side_effect():
    class Lost(Ledger):
        def append(self, body):
            return dict(committed=False)

    ledger = Lost()
    driver = Driver(ledger)
    with pytest.raises(Fault):
        Reconciler(ledger, driver).create(scope())
    assert driver.created == []


def test_AT37_missing_ledger_never_scans_or_deletes_similar_names():
    ledger = Ledger()
    driver = Driver(ledger)
    with pytest.raises(Fault):
        Reconciler(ledger, driver).recover(scope())
    assert driver.removed == [] and driver.created == []


def test_AT26_AT29_no_free_same_session_guc_proof_no_credentials_or_sql():
    with pytest.raises(Fault, match="METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION"):
        require_session_method()
    assert MethodDecision().session_guc == "CONFIGURED_NOT_INDEPENDENTLY_OBSERVED"
    assert MethodDecision().additional_probe_sql == 0
    with pytest.raises(Fault):
        PgOwnerService().dispatch(1, "run", dict(read_only=True, statement_timeout_ms=100))


def test_AT35_mutated_resource_binding_does_not_reach_remove():
    ledger = Ledger()
    driver = Driver(ledger)
    Reconciler(ledger, driver).create(scope())
    ledger.rows[0]["request"]["resource"]["scope"]["namespace_sha256"] = "b" * 64
    with pytest.raises(Fault):
        Reconciler(ledger, driver).recover(scope())
    assert driver.removed == []


@pytest.mark.parametrize("kind", ["SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER"])
def test_AT38_each_remove_failure_keeps_first_error_and_never_claims_cleanup(kind):
    ledger = Ledger()
    driver = Driver(ledger)
    c = Reconciler(ledger, driver)
    c.create(scope())

    def fail(item, raw):
        if item.kind == kind:
            raise OSError("SECRET_SENTINEL")
        driver.removed.append(item.kind)

    driver.remove = fail
    r = c.recover(scope())
    assert r["status"] == "INCOMPLETE_QUARANTINED" and r["qualifies"] is False
    assert (
        r["first_error"] and r["cleanup_codes"] and "SECRET_SENTINEL" not in canonical(r).decode()
    )


def test_AT18_resource_event_cannot_reopen_create_after_unknown():
    from scripts.a42362_contract import LedgerRequest

    q = LedgerRequest(
        resource=resources(scope())[0], event="CREATE_ATTEMPTED", event_id=str(uuid.uuid4())
    )
    with pytest.raises(Fault):
        transition("UNKNOWN", q)


def test_AT39_expired_cleanup_budget_never_deletes_or_claims_success(monkeypatch):
    from scripts import a42362_reconcile as module

    ledger = Ledger()
    driver = Driver(ledger)
    c = Reconciler(ledger, driver)
    c.create(scope())
    ticks = iter([1, 3_000_000_001, 4_000_000_001, 5_000_000_001, 6_000_000_001])
    monkeypatch.setattr(module.time, "monotonic_ns", lambda: next(ticks))
    result = c.recover(scope())
    assert result["status"] == "INCOMPLETE_QUARANTINED" and driver.removed == []
    assert result["first_error"] == "A42362_CLEANUP_TIMEOUT_QUARANTINE"


@pytest.mark.parametrize(
    "field,value",
    [
        ("initialization_sql", 9),
        ("initialization_commands", 13),
        ("initialization_ms", 2001),
        ("pg_major", 16),
    ],
)
def test_AT21_AT23_owner_raw_record_budget_or_version_cannot_be_promoted(field, value):
    from scripts.a42362_pg_owner_service import verify_raw_owner_identity

    s = scope()
    raw = dict(
        pg_major=17,
        system_identifier_sha256="b" * 64,
        image_digest=s.image_digest,
        namespace_sha256=s.namespace_sha256,
        marker_sha256=s.binding.marker_sha256,
        fixture_uuid=s.binding.fixture_uuid,
        nonce=s.binding.nonce,
        container_id="MODEL_ONLY",
        volume_id="MODEL_ONLY",
        initialization_sql=8,
        initialization_commands=12,
        initialization_ms=100,
        role_audit=dict(
            superuser=False,
            createdb=False,
            createrole=False,
            inherit=False,
            bypassrls=False,
            replication=False,
            memberships=[],
            public_write=False,
            public_execute=False,
            business_read=False,
            maintain=False,
            ddl=False,
            dml=False,
        ),
    )
    raw[field] = value
    with pytest.raises(Fault):
        verify_raw_owner_identity(raw, s)
