"""Closed, data-only Fake factories and orchestration; never a real transport fallback."""

from scripts.a4235_calibration_adapter_contract import Identity, digest
from scripts.a4235_prepared_probe import Session
from scripts.a4235_resource_bridge import Metric
from scripts.a4236_g1_harness_contract import (
    Context,
    FakeClock,
    FakeHarness,
    Fault,
    Fixture,
    require,
    validate_cleanup,
)
from scripts.a4236_g1_probe import (
    ALLOWLIST_SHA,
    FakeConnection,
    SqlBudget,
    request,
    run_mock_requests,
)
from scripts.a4236_grant_verifier import FakeAtomicConsumer, FakeIssuer, Grant
from scripts.a4236_observer_feasibility import Tick, Window, review_window
from scripts.a4236_resource_probe import CpuPoint, Environment, ResourceSet, backend_cpu
from scripts.a4236_session_prepared import PreparedRow, Snapshot, cache_key, compare


def context(identity=None, overlay="b" * 64, kind="MOCK_ONLY"):
    identity = identity or Identity(
        head_sha="1" * 40,
        run_id="local",
        attempt=1,
        source_sha256="a" * 64,
        protocol_sha256="c" * 64,
        frozen_sha256="d" * 64,
    )
    return Context(
        identity=identity,
        overlay_sha256=overlay,
        fixture_uuid="11111111-1111-4111-8111-111111111111",
        nonce="22222222-2222-4222-8222-222222222222",
        marker_sha256=digest("mock-marker"),
        evidence_kind=kind,
    )


def fixture(c=None):
    c = c or context()
    return Fixture(
        context=c,
        host="127.0.0.1",
        database="a4236_" + c.fixture_uuid.replace("-", ""),
        owner_sha256=digest("mock-owner"),
        probe_role_sha256=digest("mock-probe"),
        system_identifier_sha256=digest("mock-system"),
        container_sha256=digest("mock-container"),
        image_digest=digest("mock-image"),
        namespace_sha256=digest("mock-namespace"),
    )


def grant(c=None):
    c = c or context()
    return Grant(
        context=c,
        token_id_sha256=digest(["mock-token", c.model_dump()]),
        approval_record_sha256=digest("mock-approval"),
        issuer_sha256=digest("mock-issuer"),
        key_id_sha256=digest("mock-key"),
        audit_object_sha256=digest("mock-audit"),
        allowlist_sha256=ALLOWLIST_SHA,
        issued_ns=1,
        expires_ns=10_000_000_000,
        mock_signature_sha256=digest("not-a-real-signature"),
    )


def prepared():
    session = Session(
        backend_pid=500,
        backend_start_sha256=digest("mock-backend-start"),
        connection_generation=1,
        process_sha256=digest("mock-process"),
        connection_sha256=digest("mock-connection"),
    )
    sql = request("I4")
    a = Snapshot(
        session=session,
        driver_sql_sha256=sql.driver_sql_sha256,
        protocol_sql_sha256=sql.protocol_sql_sha256,
        parameter_oids=sql.parameter_oids,
        cache_key_sha256=cache_key(session, sql.driver_sql_sha256, sql.parameter_oids),
        observed_ns=1000,
        driver_executions=5,
        driver_prepare_sent=False,
        row=None,
        projection_executions=1,
    )
    # Explicit MOCK observation, not an executions-5 prediction of server counters.
    b = a.model_copy(
        update=dict(
            observed_ns=2000,
            driver_executions=6,
            driver_prepare_sent=True,
            projection_executions=2,
            row=PreparedRow(
                identifier_sha256=digest("mock-name"),
                parameter_oids=(23,),
                generic_plans=0,
                custom_plans=1,
            ),
        )
    )
    return session, a, b


def cpu():
    before = CpuPoint(
        backend_pid=500,
        reverse_backend_pid=500,
        mapped_proc_pid=1500,
        backend_start_sha256=digest("mock-start"),
        proc_start_ticks=10,
        namespace_sha256=digest("mock-proc-ns"),
        pg_namespace_sha256=digest("mock-pg-ns"),
        container_sha256=digest("mock-container"),
        clock_domain_sha256=digest("mock-clock"),
        mapping_reference_sha256=digest("mock-reciprocal-map"),
        clock_ticks=100,
        observed_ns=1_000_000_000,
        user_ticks=1000,
        system_ticks=100,
    )
    after = before.model_copy(update=dict(observed_ns=2_000_000_000, user_ticks=1001))
    return before, after


def resources():
    identity = digest("mock-process")
    specs = [
        ("PROCESS_CPU", "MOCK_PROCESS_TIME", "ns", 1_000_000_000, 2_000_000_000, 20_000_000),
        (
            "ENTIRE_OBSERVER_THREAD_CPU",
            "MOCK_THREAD_TIME",
            "ns",
            1_100_000_000,
            1_900_000_000,
            10_000_000,
        ),
        ("WORKER_ELAPSED", "MOCK_MONOTONIC", "ns", 1_100_000_000, 1_900_000_000, 800_000_000),
        (
            "PROCESS_LIFETIME_RSS_HIGH_WATER",
            "MOCK_RUSAGE",
            "bytes",
            500_000_000,
            2_000_000_000,
            100 * 1024**2,
        ),
        ("NATURAL_GC_EVENT", "MOCK_GC_CALLBACK", "ns", 1_200_000_000, 1_210_000_000, 1_000_000),
    ]
    return ResourceSet(
        metrics=tuple(
            Metric(
                scope=s,
                source=src,
                unit=u,
                started_ns=a,
                finished_ns=b,
                value=v,
                availability="MOCK_ONLY",
                identity_sha256=identity,
            )
            for s, src, u, a, b, v in specs
        ),
        process_started_ns=1_000_000_000,
        process_finished_ns=2_000_000_000,
        lifetime_started_ns=500_000_000,
        worker_started_ns=1_100_000_000,
        worker_finished_ns=1_900_000_000,
        joined=True,
        identity_sha256=identity,
        gc_thresholds_before=(700, 10, 10),
        gc_thresholds_after=(700, 10, 10),
    )


def environment():
    return Environment(
        relation_oids=(100, 101, 102, 103),
        statistics_sha256=digest("mock-stats"),
        indexes_sha256=digest("mock-indexes"),
        columns_sha256=digest("mock-columns"),
        settings_sha256=digest("mock-settings"),
        mvcc_sha256=digest("mock-mvcc"),
        fresh_plan_sha256=digest("mock-fresh-plan"),
        maintenance="NOT_OBSERVED",
    )


def window():
    return Window(
        mode="ON",
        planned_ticks=3,
        ticks=tuple(
            Tick(sequence=i, started_ms=i * 250, finished_ms=i * 250 + 1, sql_ms=(1,))
            for i in range(3)
        ),
        worker_started_ms=0,
        worker_finished_ms=503,
        thread_cpu_ns=1_000_000,
        worker_elapsed_ms=503,
        process_elapsed_ms=503,
        lookup_started_ms=240,
        lookup_finished_ms=260,
        state="MOCK_JOINED",
        lifecycle=("INIT", "RUNNING", "STOP_REQUESTED", "JOINED", "RECEIPT"),
        joined=True,
        stop_ms=1,
        cleanup_complete=True,
    )


def offline_design(c):
    from scripts.a4236_evidence import (
        Audit,
        Capability,
        Cleanup,
        FixtureEvidence,
        ProbeEvidence,
        failure,
    )

    require(c.evidence_kind == "OFFLINE_DESIGN", "A4236_EVIDENCE_KIND_MISMATCH")
    return {
        "grant-audit.json": Audit(context=c),
        "fixture.json": FixtureEvidence(context=c),
        "probe-events.json": ProbeEvidence(context=c),
        "capability-review.json": Capability(context=c),
        "failure.json": failure(c, "A4236_G1_NOT_RUN_NOT_AUTHORIZED", stage="LIVE_DENY"),
        "cleanup.json": Cleanup(context=c),
    }


def run_case(c=None, requests=None, replies=(), consumer=None, cleanup_failure=False):
    from scripts.a4236_evidence import (
        Audit,
        Capability,
        Cleanup,
        Event,
        FixtureEvidence,
        ProbeEvidence,
        failure,
    )

    c = c or context()
    require(c.evidence_kind == "MOCK_ONLY", "A4236_EVIDENCE_KIND_MISMATCH")
    require(
        consumer is None or type(consumer) is FakeAtomicConsumer, "A4236_REAL_ADAPTER_NOT_ALLOWED"
    )
    issuer, consumer = FakeIssuer(grant(c)), consumer or FakeAtomicConsumer()
    receipt = consumer.consume(issuer.verify(grant(c), 2))
    harness = FakeHarness(fixture(c))
    creation = harness.create(receipt)
    connection = FakeConnection(FakeClock(ns=5), replies=replies)
    result = run_mock_requests(
        connection, [request("I4")] * 6 + [request("PROJECTION")] if requests is None else requests
    )
    if cleanup_failure:
        cleanup, codes = (), ("A4236_CLEANUP_NOT_VERIFIED",)
    else:
        cleanup, codes = harness.destroy(fixture(c), observed_ns=connection.clock.ns + 1), ()
    events = tuple(
        Event(
            context=c,
            request=request(event["template"]),
            sequence=i,
            **{k: v for k, v in event.items() if k != "template"},
        )
        for i, event in enumerate(result["events"])
    )
    return {
        "grant-audit.json": Audit(context=c, mock_consumption=receipt),
        "fixture.json": FixtureEvidence(context=c, spec=fixture(c), mock_creation=creation),
        "probe-events.json": ProbeEvidence(context=c, events=events, capability_status="PARTIAL"),
        "capability-review.json": Capability(context=c, offline_contract_status="MOCK_ONLY"),
        "failure.json": failure(
            c,
            result["first_error"],
            codes,
            snapshot=digest(events[-1].model_dump()) if events else None,
            stage="MOCK_PROBE" if result["first_error"] or not codes else "MOCK_CLEANUP",
        ),
        "cleanup.json": Cleanup(
            context=c, mock_receipts=tuple(cleanup), mock_cleanup_complete=not codes
        ),
    }


def refusal_case(threat):
    if threat == "forged_grant":
        g = grant()
        FakeIssuer(g).verify(g.model_copy(update={"approval_record_sha256": "f" * 64}), 2)
    elif threat == "replay":
        g, consumer = grant(), FakeAtomicConsumer()
        v = FakeIssuer(g).verify(g, 2)
        consumer.consume(v)
        consumer.consume(v)
    elif threat == "pid_drift":
        before, after = cpu()
        result = backend_cpu(
            before,
            after.model_copy(update={"backend_pid": 501}),
            before,
            before.observed_ns,
            after.observed_ns,
        )
        require(result["mock_cpu_seconds"] is not None, "A4236_CPU_UNAVAILABLE")
    elif threat == "cache_key":
        session, before, after = prepared()
        compare(before, after.model_copy(update={"cache_key_sha256": "f" * 64}), session, "I4")
    elif threat == "false_join":
        review_window(
            window().model_copy(
                update=dict(
                    state="STOP_TIMEOUT",
                    worker_finished_ms=None,
                    lifecycle=("INIT", "RUNNING", "STOP_REQUESTED"),
                    thread_cpu_ns=None,
                    worker_elapsed_ms=None,
                )
            )
        )
    elif threat == "false_cleanup":
        h, g = FakeHarness(fixture()), grant()
        h.create(FakeAtomicConsumer().consume(FakeIssuer(g).verify(g, 2)))
        validate_cleanup(fixture(), h.destroy(fixture())[:-1])
    elif threat == "sql_budget":
        connection = FakeConnection(FakeClock())
        budget = SqlBudget(connection.clock)
        for _ in range(17):
            connection.execute(request("I4"), budget)
    elif threat == "history_write":
        from scripts.a4235_capability_guard import NEXT_STAGE_PATHS, validate_next_paths

        try:
            validate_next_paths(NEXT_STAGE_PATHS | {"backend/app/forbidden.py"})
        except Exception:
            raise Fault("A4236_SOURCE_CHANGED") from None
    else:
        raise Fault("A4236_UNKNOWN_REFUSAL_CASE")
