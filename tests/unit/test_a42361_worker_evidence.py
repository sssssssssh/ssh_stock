"""Wire conversion is real and offline; driver, OS and service evidence stays modeled."""

import json
from types import SimpleNamespace as NS

import pytest
from psycopg.adapt import Transformer as OfflineTransformer

from scripts import a42361_live_probe_worker as w
from scripts import a42361_trusted_evidence as e
from scripts.a42361_contract import Capability, Fault, canonical, sha
from scripts.a42361_offline_cases import binding


@pytest.mark.parametrize("template", ["I4", "I8", "PROJECTION"])
def test_AT23_real_locked_driver_conversion_without_SQL(template):
    import psycopg
    from psycopg._queries import PostgresQuery
    from psycopg.adapt import Transformer
    from psycopg.types.numeric import Int4, Int8

    assert psycopg.__version__ == "3.3.4"
    query = PostgresQuery(Transformer())
    params = (Int4(1),) if template == "I4" else (Int8(1),) if template == "I8" else None
    driver = w.TEMPLATES[template][0]
    query.convert(driver, params)
    w.validate_wire(template, driver, query.query, query.types, len(params or ()))


@pytest.mark.parametrize("change", ["driver", "protocol", "oids", "count", "allowlist", "stage"])
def test_AT23_mismatch_denies_before_send(change):
    d, p, oids, _ = w.TEMPLATES["I4"]
    args = ["I4", d, p, oids, 1, w.ALLOWLIST_SHA]
    values = {
        "driver": (1, b"SELECT 9"),
        "protocol": (2, b"SELECT 9"),
        "oids": (3, (20,)),
        "count": (4, 2),
        "allowlist": (5, "0" * 64),
        "stage": (0, "C1"),
    }
    index, value = values[change]
    args[index] = value
    with pytest.raises(Fault, match="NOT_ALLOWLISTED"):
        w.validate_wire(*args)


def test_AT24_projections_count_and_seventeenth_denied():
    assert len(w.SCHEDULE) == 16 and w.SCHEDULE.count("PROJECTION") == 4
    assert w.SCHEDULE.count("I4") == w.SCHEDULE.count("I8") == 6
    budget = w.SqlBudget()
    for index in range(16):
        start = budget.reserve(1 + index * 1_000_000)
        budget.finish(start, start + 1, 1)
    with pytest.raises(Fault, match="BUDGET_EXCEEDED"):
        budget.reserve(18_000_001)
    assert budget.count == 16 and budget.stopped


@pytest.mark.parametrize(
    "end,rows", [(100_000_002, 1), (2_000_000_002, 1), (0, 1), (2, 9), (2, -1)]
)
def test_AT25_first_budget_fault_sticky_no_refund(end, rows):
    budget = w.SqlBudget()
    start = budget.reserve(1)
    with pytest.raises(Fault, match="BUDGET_EXCEEDED"):
        budget.finish(start, end, rows)
    assert budget.count == 1 and budget.stopped
    with pytest.raises(Fault):
        budget.reserve(2)


def test_AT25_reserve_clock_backwards_rejected():
    budget = w.SqlBudget()
    budget.reserve(100)
    with pytest.raises(Fault):
        budget.reserve(99)


@pytest.mark.parametrize(
    "rows",
    [
        [("_pg3_0", [23], False, 1, 1)],
        [("_pg3_0", [23], False, 0, 7)],
        [("_pg3_0", [21], False, 0, 1)],
        [("_pg3_0", [23], True, 0, 1)],
        [("_pg3_other", [23], False, 0, 1)],
        [],
    ],
)
def test_AT30_server_missing_mode_drift_or_counter_loss(rows):
    previous = {sha(b"_pg3_0"): dict(oids=[23], generic=0, custom=2)}
    with pytest.raises(Fault, match="PREPARED_NOT_PROVEN"):
        w.prepared_projection(rows, previous)


def evidence():
    return e.Evidence(
        binding=binding(),
        evidence_kind="OFFLINE_CONTRACT_ONLY",
        payload_sha256="a" * 64,
        references={},
        worker_sha256=None,
        first_error=None,
        cleanup_codes=(),
        last_incomplete=None,
    )


def test_AT31_AT32_AT35_AT40_capability_unknowns_are_not_zero_or_approval():
    value = Capability().model_dump()
    assert value["g1_physical"] == "G1_PHYSICAL_NOT_RUN" and value["real_sql_executed"] == 0
    assert value["warmups_total"] == 8 and value["g3"] == "G3_NOT_AUTHORIZED"
    for key in (
        "production_read_authorized",
        "performance_eligible",
        "capacity_ready",
        "attribution_authorized",
    ):
        assert value[key] is False
    assert value["unique_repair_candidate"] is None


def test_AT36_offline_bundle_cannot_self_sign_authority(tmp_path):
    path = tmp_path / "offline"
    e.write_bundle(path, evidence())
    result = e.Reviewer().review(path, binding())
    assert result["status"] == "OFFLINE_CONTRACT_VALID"
    assert result["exit_code"] != 0 and not result["qualifies"]
    assert result["physical_capabilities"] == "NOT_PROVEN"


def test_AT36_rehashed_bundle_is_still_not_a_physical_receipt(tmp_path):
    path = tmp_path / "forged"
    value = evidence().model_copy(
        update={
            "evidence_kind": "UNATTESTED_RECEIPT_REFERENCES",
            "references": {"absence_auditor": "f" * 64},
        }
    )
    e.write_bundle(path, value)
    result = e.Reviewer().review(path, binding())
    assert result["status"] == "OFFLINE_CONTRACT_VALID" and not result["qualifies"]
    with pytest.raises(Fault):
        e.Reviewer(object()).review(path, binding())


def test_AT21_AT36_first_error_sticky_cleanup_bounded_and_distinct():
    ledger = e.FailureLedger()
    ledger.fail("A42361_SQL_FAILED_NO_RETRY")
    for _ in range(3):
        ledger.fail("A42361_CLEANUP_NOT_VERIFIED", cleanup=True)
    assert ledger.first_error == "A42361_SQL_FAILED_NO_RETRY"
    assert ledger.last_incomplete == "A42361_CLEANUP_NOT_VERIFIED"
    assert ledger.cleanup_codes == ["A42361_CLEANUP_NOT_VERIFIED"]


@pytest.mark.parametrize(
    "case",
    ["permissions", "symlink", "extra", "size", "hash", "incomplete", "unknown", "duplicate"],
)
def test_AT37_bundle_tampering_rejected(tmp_path, case):
    path = tmp_path / "evidence"
    e.write_bundle(path, evidence())
    target = path / "evidence.json"
    if case == "permissions":
        target.chmod(0o644)
    elif case == "symlink":
        target.rename(tmp_path / "other")
        target.symlink_to(tmp_path / "other")
    elif case == "extra":
        (path / "extra").touch()
    elif case == "size":
        target.write_bytes(b"x" * 65537)
    elif case == "hash":
        target.write_bytes(b"{}")
    elif case == "incomplete":
        (path / ".incomplete").touch()
    else:
        raw = target.read_bytes()
        data = json.loads(raw)
        if case == "unknown":
            data["approved"] = True
            raw = canonical(data)
        else:
            raw = b'{"binding":{},"binding":{}}'
        target.write_bytes(raw)
        (path / "manifest.json").write_bytes(
            canonical(
                dict(
                    schema_version="a42361.manifest.v1",
                    files={"evidence.json": dict(bytes=len(raw), sha256=sha(raw))},
                )
            )
        )
    with pytest.raises(Fault):
        e.read_bundle(path)


def test_AT37_exclusive_output_and_fsync_failure_keeps_marker(tmp_path, monkeypatch):
    path = tmp_path / "evidence"
    e.write_bundle(path, evidence())
    before = (path / "manifest.json").read_bytes()
    with pytest.raises(Fault):
        e.write_bundle(path, evidence())
    assert (path / "manifest.json").read_bytes() == before

    def fsync_fault(fd):
        raise OSError("OFFLINE_SECRET_SENTINEL")

    monkeypatch.setattr(e.os, "fsync", fsync_fault)
    failed = tmp_path / "failed"
    with pytest.raises(Fault, match="ARTIFACT_INCOMPLETE"):
        e.write_bundle(failed, evidence())
    assert (failed / ".incomplete").exists() and not (failed / "manifest.json").exists()


def test_AT37_parent_symlink_and_traversal_no_output(tmp_path):
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    for path in (alias / "evidence", tmp_path / ".." / "outside"):
        with pytest.raises(Fault, match="UNSAFE_OUTPUT"):
            e.write_bundle(path, evidence())
    assert not (tmp_path / "evidence").exists()


def test_AT27_worker_default_before_psycopg(monkeypatch):
    import psycopg

    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: pytest.fail("SQL reached"))
    with pytest.raises(Fault, match="DEPLOYMENT_NOT_CONFIGURED"):
        w.ProbeWorker().run_owned(None)


def test_probe_lease_requires_post_connection_session_binding_source_gap():
    assert callable(getattr(w, "validate_probe_lease", None))
    assert callable(getattr(w, "validate_probe_session", None))


def session_model():
    """OFFLINE_MODEL for phase binding only: no owner, lease issuer or database."""
    from scripts.a42361_offline_cases import payload

    p = payload()
    fixture = NS(
        consumption=NS(grant=NS(payload=p, payload_sha256="a" * 64)),
        receipt_sha256="b" * 64,
        socket_directory="/run/a42361-offline/fixture",
        pg_identity=dict(probe_role_sha256="c" * 64, system_identifier_sha256="d" * 64),
    )
    lease = dict(
        schema_version="a42361.probe-lease.v2",
        lease_id="92345678-1234-4234-8234-123456789012",
        worker_pid=123,
        payload_sha256="a" * 64,
        creation_sha256="b" * 64,
        socket_directory=fixture.socket_directory,
        database="a42361_" + p.binding.fixture_uuid.replace("-", ""),
        password="OFFLINE_TEST_VALUE_NOT_A_CREDENTIAL_1",
        supervised=True,
        statement_timeout_ms=100,
        read_only=True,
        probe_role_sha256="c" * 64,
        lease_expires_at=150,
    )
    session = dict(
        schema_version="a42361.probe-session.v2",
        lease_id=lease["lease_id"],
        worker_pid=123,
        payload_sha256="a" * 64,
        creation_sha256="b" * 64,
        backend_pid=234,
        backend_start_sha256="e" * 64,
        system_identifier_sha256="d" * 64,
        probe_role_sha256="c" * 64,
        checkout_generation=1,
        read_only=True,
        statement_timeout_ms=100,
        pg_major=17,
        driver_version="3.3.4",
        application_name="a42361-" + lease["lease_id"].replace("-", ""),
    )
    return fixture, lease, session


def test_post_connection_attestation_has_actual_start_not_predicted_by_lease():
    fixture, raw, session = session_model()
    assert "backend_start_sha256" not in raw
    lease = w.validate_probe_lease(raw, fixture, 123, 110)
    result = w.validate_probe_session(session, lease, fixture, 234, 110)
    assert result["backend_start_sha256"] == "e" * 64


@pytest.mark.parametrize(
    "change,value",
    [
        ("backend_start_sha256", "e" * 64),
        ("worker_pid", 124),
        ("payload_sha256", "0" * 64),
        ("creation_sha256", "0" * 64),
        ("probe_role_sha256", "0" * 64),
        ("read_only", False),
        ("statement_timeout_ms", True),
        ("socket_directory", "/tmp/untrusted"),
        ("lease_expires_at", 110),
        ("lease_expires_at", 999),
        ("supervised", False),
    ],
)
def test_pre_connect_lease_mismatch_rejected_without_backend(change, value):
    fixture, lease, _ = session_model()
    lease[change] = value
    with pytest.raises(Fault):
        w.validate_probe_lease(lease, fixture, 123, 110)


@pytest.mark.parametrize(
    "change,value",
    [
        ("backend_pid", 235),
        ("backend_pid", True),
        ("backend_start_sha256", None),
        ("lease_id", "82345678-1234-4234-8234-123456789012"),
        ("worker_pid", 124),
        ("payload_sha256", "0" * 64),
        ("creation_sha256", "0" * 64),
        ("system_identifier_sha256", "0" * 64),
        ("probe_role_sha256", "0" * 64),
        ("application_name", "another-lease"),
        ("checkout_generation", 2),
        ("statement_timeout_ms", 101),
        ("read_only", False),
        ("pg_major", 16),
        ("driver_version", "3.3.5"),
        ("approved", True),
    ],
)
def test_post_connect_session_drift_cannot_send_first_probe_sql(change, value):
    fixture, raw, session = session_model()
    lease = w.validate_probe_lease(raw, fixture, 123, 110)
    session[change] = value
    with pytest.raises(Fault):
        w.validate_probe_session(session, lease, fixture, 234, 110)


def test_post_connect_lease_expiry_stops_before_probe():
    fixture, raw, session = session_model()
    lease = w.validate_probe_lease(raw, fixture, 123, 110)
    with pytest.raises(Fault, match="SESSION_IDENTITY_UNPROVEN"):
        w.validate_probe_session(session, lease, fixture, 234, 150)


@pytest.mark.parametrize("failure", [None, "lease", "session", "expiry", "disconnect"])
def test_owned_worker_connect_then_attest_then_execute_no_hidden_identity_sql(monkeypatch, failure):
    import psycopg

    fixture, lease, session = session_model()
    config = NS(worker_uid=1000)
    calls = []
    connection = NS(info=NS(backend_pid=234), close=lambda: calls.append("close"))
    monkeypatch.setattr(w, "installed", lambda _: config)
    monkeypatch.setattr(w, "created", lambda _: fixture)
    # This test exercises the old driver *model*, not the newly blocked real entrance.
    monkeypatch.setattr(w, "require_session_method", lambda: None)
    monkeypatch.setattr(w.os, "getuid", lambda: 1000)
    monkeypatch.setattr(w.os, "getpid", lambda: 123)
    monkeypatch.setattr(w.time, "time", lambda: 110)
    for key in tuple(w.os.environ):
        if key.startswith("PG") or key in ("DATABASE_URL", "TEST_DATABASE_URL"):
            monkeypatch.delenv(key)
    if failure == "lease":
        lease["backend_start_sha256"] = "e" * 64  # The old premature prediction is forbidden.
    if failure == "session":
        session["lease_id"] = "82345678-1234-4234-8234-123456789012"

    def service(self, method, body):
        assert self.domain == "pg_owner"
        calls.append(method)
        assert body["worker_pid"] == 123 and body["schedule"] == list(w.SCHEDULE)
        if method == "run":
            assert "backend_pid" not in body
            return lease.copy()
        assert calls == ["run", "connect", "receipt"]
        assert body["backend_pid"] == 234 and body["lease_id"] == lease["lease_id"]
        if failure == "expiry":
            monkeypatch.setattr(w.time, "time", lambda: 150)
        return session.copy()

    def connect(*args, **kwargs):
        calls.append("connect")
        assert not args and kwargs["prepare_threshold"] == 5
        assert kwargs["host"] == fixture.socket_directory and kwargs["user"] == "g1_probe"
        assert kwargs["application_name"] == session["application_name"]
        assert kwargs["options"] == (
            "-c statement_timeout=100 -c default_transaction_read_only=on -c search_path=pg_catalog"
        )
        if failure == "disconnect":
            raise RuntimeError("OFFLINE_SECRET_SENTINEL")
        return connection

    def execute(self, conn, identity):
        calls.append("execute")
        assert conn is connection and identity == session
        assert "password" not in identity
        return dict(status="OFFLINE_MODEL_ONLY")

    monkeypatch.setattr(w.LocalService, "call", service)
    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr(w.ProbeWorker, "_execute_fixed", execute)
    if failure:
        with pytest.raises(Fault):
            w.ProbeWorker(object()).run_owned(fixture)
        assert "execute" not in calls and calls.count("connect") <= 1
        assert ("connect" not in calls) if failure == "lease" else True
    else:
        assert w.ProbeWorker(object()).run_owned(fixture) == dict(status="OFFLINE_MODEL_ONLY")
        assert calls == ["run", "connect", "receipt", "execute", "close"]


class DriverModel:
    def __init__(self, fault=None):
        self.prepare_threshold = 5
        self.closed = False
        self.info = NS(backend_pid=123)
        self._prepared = NS(_names={})
        self.calls = []
        self.counts = {}
        self.fault = fault

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, driver, params):
        from psycopg._queries import PostgresQuery

        self._query = PostgresQuery(OfflineTransformer())
        self._query.convert(driver, params)
        self.calls.append(driver)
        if self.fault == "driver":
            raise RuntimeError("OFFLINE_SECRET_SENTINEL")
        if self.fault == "reconnect":
            self.info.backend_pid += 1
        key = (self._query.query, self._query.types)
        self.counts[key] = self.counts.get(key, 0) + 1
        if self.counts[key] == 6:
            self._prepared._names[key] = b"_pg3_" + str(len(self._prepared._names)).encode()
        self.rows = (
            [
                (v.decode(), list(k[1]), False, 0, self.counts[k] - 5)
                for k, v in self._prepared._names.items()
            ]
            if params is None
            else [(1,)]
        )

    def fetchmany(self, n):
        return self.rows[:n]


@pytest.mark.parametrize("fault", [None, "driver", "reconnect"])
def test_AT29_AT30_same_session_driver_model_is_not_physical(monkeypatch, fault):
    import psycopg.adapt

    original = psycopg.adapt.Transformer
    # Query conversion is still the locked real implementation, only its context is
    # replaced. Never call PrepareManager.get() to create an observational side effect.
    monkeypatch.setattr(psycopg.adapt, "Transformer", NS(from_context=lambda _: original()))
    conn = DriverModel(fault)
    if fault == "reconnect":
        value = w.ProbeWorker()._execute_fixed(conn, {})
        assert value["first_error"] == "A42361_SESSION_IDENTITY_DRIFT"
        assert value["collection_status"] == "INCOMPLETE"
        assert value["sql_count"] == len(value["events"]) == 1
        assert len(conn.calls) == 1
    else:
        value = w.ProbeWorker()._execute_fixed(conn, {})
        assert value["sql_count"] == (1 if fault else 16)
        assert value["evidence_kind"] == "WORKER_UNATTESTED"
        assert value["cached_plan_structure"] == "CACHED_PLAN_STRUCTURE_NOT_VERIFIED"
        assert value["backend_cpu"]["availability"] == "METRIC_UNAVAILABLE"
        assert value["backend_cpu"]["value"] is None
        assert value["observer"]["joined"] is False
        assert value["observer"]["thread_cpu_ns"] is None
        assert value["observer"]["elapsed_ns"] is None
        assert value["observer"]["status"] == "BRACKET_UNCOVERED"
        assert value["business_environment"]["maintenance"] == "UNKNOWN"
        assert value["process"]["gc_subtracted"] is False
        assert len(conn.calls) == value["sql_count"]
