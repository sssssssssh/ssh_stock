"""Pure in-memory business-call wiring; no live port is instantiated or imported."""

import ast
import dataclasses
import json
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import biz_perf_p1_04_w05_root_bridge as b
from scripts.business_sql_snapshot import RootCounts

RUN = "12345678-1234-4234-8234-123456789abc"
ROOT_ID = uuid.UUID("22345678-1234-4234-8234-123456789abc")
TOKEN = uuid.UUID("32345678-1234-4234-8234-123456789abc")
OTHER = uuid.UUID("42345678-1234-4234-8234-123456789abc")
SHA = "a" * 40
REPO = Path(__file__).absolute().parents[2]


class FakePorts:
    def __init__(self):
        self.wall = 100
        self.cpu = 200
        self.calls = []
        self.claimed = ROOT_ID
        self.job = SimpleNamespace(id=ROOT_ID, parent_job_id=None, worker_id=b.WORKER_ID,
                                   execution_token=TOKEN, _queue_deduplicated=False)
        self.fault = None
        self.post_changes = {}
        self.counts = RootCounts()
        self.bridge = None

    def create(self, db, **kwargs):
        assert db is self
        self.calls.append(("create", kwargs))
        self.wall += 2
        self.counts.begin("INSERT")
        self.counts.end()
        if self.fault == "create":
            raise RuntimeError("postgresql://private:secret@production/stock_db")
        return self.job

    def claim(self, db, worker_id):
        assert db is self
        self.calls.append(("claim", worker_id))
        self.wall += 3
        if self.fault == "claim":
            raise b.BridgeRejected("UNKNOWN_ACK")
        return self.claimed

    def refresh(self, job):
        assert job is self.job
        self.calls.append(("refresh",))

    def create_claim(self, emit):
        return b._create_claim(self, self.create, self.claim, emit)

    def worker(self, db, identity, **kwargs):
        assert db is self
        self.calls.append(("worker", identity, kwargs))
        try:
            self.wall += 18
            self.cpu += 10
            self.counts.begin("SELECT")
            self.counts.end()
            if self.fault == "worker":
                raise RuntimeError("SQL SELECT secret FROM private")
            if self.fault == "unknown":
                raise b.BridgeRejected("UNKNOWN_ACK")
            if self.fault == "crash":
                raise KeyboardInterrupt("private crash detail")
            if self.fault == "reenter":
                self.bridge.run_offline()
            if self.fault == "stages":
                self.bridge.record_stage("factors.compute", begin_ms=5, end_ms=24)
                self.bridge.record_stage("publish_inclusive", begin_ms=10, end_ms=25)
        finally:
            self.wall += 2  # Worker finally must be in both root and Worker wall.

    def execute_claimed_job(self, claim):
        return b._execute(self, self.worker, claim)

    def post_validate(self, claim, *, run_uuid, implementation_sha):
        self.calls.append(("post", claim.root_id))
        assert self.bridge.snapshot["root_elapsed_ms"] == 25
        assert self.counts.begin("POST_SELECT") is False
        self.wall += 7
        self.cpu += 500
        if self.fault == "post":
            raise ValueError("postgresql://private:secret@production/stock_db")
        values = dict(root_id=claim.root_id, publication_job_id=claim.root_id,
                      run_uuid=run_uuid, implementation_sha=implementation_sha,
                      publication_token=claim.token, job_status="SUCCESS",
                      publication_state="PUBLISHED", ack="KNOWN_RETURN",
                      public_scope_verified=True, source_verified=True,
                      row_counts_verified=True, no_b_leak=True)
        values.update(self.post_changes)
        return b.PostRead(**values)


def setup(*, sql=True, cpu=True, sink=None):
    port = FakePorts()
    events = []
    bridge = b.RootBridge(run_uuid=RUN, implementation_sha=SHA, ports=port,
                          monotonic_ms=lambda: port.wall,
                          cpu_ms=(lambda: port.cpu) if cpu else None,
                          sql_counts=port.counts if sql else None,
                          sink=sink or events.append)
    if not sql:
        port.counts = bridge._counts
    port.bridge = bridge
    return port, bridge, events


def test_complete_fake_business_path_and_independent_intervals():
    port, bridge, events = setup()
    result = bridge.run_offline()
    assert result["status"] == "FAKE_VALIDATED"
    assert result["evidence_kind"] == "OFFLINE_FIXTURE"
    assert result["root_attempts"] == 0 and result["attempt_consumed"] is True
    assert result["root"]["root_elapsed_ms"] == 25
    assert result["root"]["execute_claimed_job_ms"] == 20
    assert result["post_root_validation_ms"] == 7
    assert result["root"]["process_cpu_ms"] == 10
    assert result["root"]["sql_counts"] == {"INSERT": 1, "SELECT": 1}
    assert [e["event_kind"] for e in events] == [
        "begin", "create", "claim", "worker_return", "root_freeze", "post_read"]
    assert [e["seq"] for e in events] == list(range(1, 7))
    assert [e["elapsed_ms"] for e in events] == [0, 2, 5, 25, 25, 32]
    assert all(e["run_uuid"] == RUN and e["implementation_sha"] == SHA for e in events)
    assert all(e["root_job_id"] == str(ROOT_ID) for e in events[1:])
    assert [c[0] for c in port.calls] == ["create", "claim", "refresh", "worker", "post"]
    assert port.calls[0][1] == dict(start=date(2025, 1, 1), end=date(2025, 1, 31),
                                     evaluate_signals=False, mode="manual")
    assert port.calls[1][1] == b.WORKER_ID
    assert port.calls[3][1:] == (ROOT_ID, dict(expected_worker=b.WORKER_ID,
                                            expected_token=TOKEN))
    assert result["B_GATE"] == result["TARGETED_PG17_GATE"] == "NOT_APPROVED"


@pytest.mark.parametrize("claimed", [None, OTHER, str(ROOT_ID)])
def test_claim_must_equal_native_created_uuid_without_second_claim(claimed):
    port, bridge, _ = setup()
    port.claimed = claimed
    with pytest.raises(b.BridgeRejected, match="CLAIM_IDENTITY_REJECTED"):
        bridge.run_offline()
    assert [c[0] for c in port.calls] == ["create", "claim"]
    assert bridge.attempt_consumed and bridge.snapshot is None


@pytest.mark.parametrize(("field", "value"), [
    ("id", None), ("id", str(ROOT_ID)), ("parent_job_id", OTHER),
    ("_queue_deduplicated", True), ("_queue_deduplicated", None),
])
def test_existing_or_invalid_created_root_cannot_be_claimed(field, value):
    port, bridge, _ = setup()
    setattr(port.job, field, value)
    with pytest.raises(b.BridgeRejected, match="CREATED_ROOT_REJECTED"):
        bridge.run_offline()
    assert len(port.calls) == 1


@pytest.mark.parametrize(("field", "value"), [
    ("execution_token", None), ("execution_token", str(TOKEN)),
    ("worker_id", None), ("worker_id", "other-worker"),
])
def test_refreshed_owner_and_token_required(field, value):
    port, bridge, _ = setup()
    setattr(port.job, field, value)
    with pytest.raises(b.BridgeRejected, match="CLAIM_OWNER_REJECTED"):
        bridge.run_offline()
    assert not any(c[0] == "worker" for c in port.calls)


@pytest.mark.parametrize(("fault", "code"), [
    ("create", "CREATE_CLAIM_FAILED"), ("claim", "UNKNOWN_ACK"),
    ("worker", "WORKER_FAILED"), ("unknown", "UNKNOWN_ACK"),
    ("crash", "WORKER_FAILED"), ("post", "POST_FAILED"),
    ("reenter", "ONE_ATTEMPT_CONSUMED"),
])
def test_failures_are_terminal_sanitized_and_never_replayed(fault, code):
    port, bridge, events = setup()
    port.fault = fault
    with pytest.raises(b.BridgeRejected) as error:
        bridge.run_offline()
    assert str(error.value) == code
    assert bridge.failure_code == code
    assert events[-1]["event_kind"] == "failure" and events[-1]["error_code"] == code
    assert "secret" not in json.dumps(events)
    calls = list(port.calls)
    with pytest.raises(b.BridgeRejected, match="ONE_ATTEMPT_CONSUMED"):
        bridge.run_offline()
    assert port.calls == calls and bridge.attempt_consumed
    assert port.counts.begin("LATE") is False
    if fault != "post":
        assert not any(c[0] == "post" for c in calls)


@pytest.mark.parametrize(("field", "value"), [
    ("job_status", "FAILED"), ("job_status", "CANCELLED"),
    ("publication_state", "PREPARING"), ("publication_state", None),
    ("public_scope_verified", False), ("source_verified", False),
    ("source_verified", "true"), ("row_counts_verified", None), ("no_b_leak", False),
])
def test_post_requires_independent_success_publication_scope_source_rows_no_leak(field, value):
    port, bridge, _ = setup()
    port.post_changes[field] = value
    result = bridge.run_offline()
    assert result["status"] == "INCONCLUSIVE"
    assert result["root"]["root_elapsed_ms"] == 25
    assert sum(c[0] == "worker" for c in port.calls) == 1


@pytest.mark.parametrize(("field", "value"), [
    ("root_id", OTHER), ("publication_job_id", OTHER),
    ("run_uuid", str(OTHER)), ("implementation_sha", "b" * 40),
    ("publication_token", OTHER), ("ack", "UNKNOWN_ACK"),
])
def test_post_cannot_splice_other_roots_runs_versions_or_unknown_ack(field, value):
    port, bridge, _ = setup()
    port.post_changes[field] = value
    with pytest.raises(b.BridgeRejected, match="UNKNOWN_ACK|POST_IDENTITY_REJECTED"):
        bridge.run_offline()
    assert bridge.snapshot["sql_counts"] == {"INSERT": 1, "SELECT": 1}
    assert len([c for c in port.calls if c[0] == "post"]) == 1


def test_second_successful_execution_refused():
    port, bridge, events = setup()
    bridge.run_offline()
    with pytest.raises(b.BridgeRejected, match="ONE_ATTEMPT_CONSUMED"):
        bridge.run_offline()
    assert len(events) == 6 and len(port.calls) == 5


def test_attempt_state_is_not_a_writable_permission_switch():
    _, bridge, _ = setup()
    bridge.run_offline()
    with pytest.raises(AttributeError):
        bridge.attempt_consumed = False
    with pytest.raises(b.BridgeRejected, match="ONE_ATTEMPT_CONSUMED"):
        bridge.run_offline()


def test_zero_root_interval_cannot_be_a_completed_observation():
    port, bridge, _ = setup()
    bridge._clock = lambda: 100
    with pytest.raises(b.BridgeRejected, match="ROOT_FREEZE_FAILED"):
        bridge.run_offline()
    assert bridge.snapshot is None and port.counts.begin("LATE") is False


def test_zero_cpu_is_recorded_ratio_undefined():
    port, bridge, _ = setup()
    bridge._cpu = lambda: 0
    root = bridge.run_offline()["root"]
    assert root["process_cpu_ms"] == 0 and root["wall_per_cpu"] == "UNDEFINED"


def test_absent_sql_fetch_cpu_rss_are_unknown_not_zero():
    _, bridge, _ = setup(sql=False, cpu=False)
    root = bridge.run_offline()["root"]
    assert all(root[k] == "UNKNOWN" for k in (
        "sql_counts", "sql_snapshot", "process_cpu_ms", "sql_execute_ms",
        "fetch_observed_ms", "fetched_rows", "rss_peak_bytes"))
    assert root["coverage"]["sql"] == "NOT_INSTRUMENTED"
    assert all(s["status"] == "NOT_INSTRUMENTED" for s in root["stages"].values())


def test_inclusive_stages_can_overlap_without_summing_into_root():
    port, bridge, _ = setup()
    port.fault = "stages"
    root = bridge.run_offline()["root"]
    assert root["stages"]["factors.compute"]["stage_inclusive_ms"] == 19
    assert root["stages"]["publish_inclusive"]["stage_inclusive_ms"] == 15
    assert root["root_elapsed_ms"] == 25
    assert root["interval_semantics"] == "INCLUSIVE_DO_NOT_SUM"


@pytest.mark.parametrize("name", ["factors.input_verify", "SQL secret", "", None])
def test_unknown_stage_names_refused(name):
    _, bridge, _ = setup()
    with pytest.raises(b.BridgeRejected, match="STAGE_REJECTED"):
        bridge.record_stage(name, begin_ms=0, end_ms=1)


@pytest.mark.parametrize("samples", [
    [100, 99], [100, 100, 99], [100, 100, 105, 1_200_101],
    [100, 100, 105, float("inf")], [True], [-1], [2**63],
])
def test_clock_reversal_overflow_and_nonfinite_refused(samples):
    _, bridge, _ = setup()
    iterator = iter(samples)
    bridge._clock = lambda: next(iterator)
    with pytest.raises(b.BridgeRejected, match="CLOCK_REJECTED|CLOCK_REGRESSION|ELAPSED_LIMIT"):
        bridge.run_offline()
    assert bridge.attempt_consumed


def test_cpu_reversal_stays_unknown_without_fabrication():
    _, bridge, _ = setup()
    values = iter([200, 199])
    bridge._cpu = lambda: next(values)
    assert bridge.run_offline()["root"]["process_cpu_ms"] == "UNKNOWN"


def test_root_snapshot_is_defensively_copied_and_sealed_before_post():
    _, bridge, events = setup()
    result = bridge.run_offline()
    result["root"]["sql_counts"]["INJECTED"] = 100
    saved = bridge.snapshot
    saved["sql_counts"].clear()
    events[-2]["root_job_id"] = str(OTHER)
    assert bridge.snapshot["sql_counts"] == {"INSERT": 1, "SELECT": 1}
    assert bridge.snapshot["process_cpu_ms"] == 10


def test_pending_sql_cannot_be_reported_as_complete():
    port, bridge, _ = setup()
    port.counts.begin("UNFINISHED")
    with pytest.raises(b.BridgeRejected, match="ROOT_FREEZE_FAILED"):
        bridge.run_offline()
    assert bridge.snapshot is None
    assert not any(c[0] == "post" for c in port.calls)


def test_return_collectors_are_sampled_once_and_cannot_add_root_sql():
    port, bridge, _ = setup()
    reads = []

    def fetch():
        reads.append("fetch")
        assert port.counts.begin("COLLECTOR") is False
        return dict(observed_ms=4, rows=8)

    def rss():
        reads.append("rss")
        return 1024

    from scripts.biz_perf_p1_04_e03_collectors import CollectorPorts
    bridge._collectors = CollectorPorts(cpu_reader=lambda: port.cpu, rss_reader=rss,
                                         fetch_reader=fetch)
    result = bridge.run_offline()
    assert reads == ["fetch", "rss"]
    assert result["root"]["fetch_observed_ms"] == 4
    assert result["root"]["fetched_rows"] == 8
    assert result["root"]["rss_peak_bytes"] == 1024
    assert result["root"]["sql_counts"] == {"INSERT": 1, "SELECT": 1}


def test_collector_failure_is_unknown_and_not_resampled_in_post():
    port, bridge, _ = setup()
    calls = []

    def bad_cpu():
        calls.append("cpu")
        raise RuntimeError("credential secret")

    bridge._cpu = bad_cpu
    result = bridge.run_offline()
    assert calls == ["cpu"]
    assert result["root"]["coverage"]["cpu"] == "UNKNOWN"
    assert result["root"]["process_cpu_ms"] == "UNKNOWN"
    assert port.calls[-1][0] == "post"


def test_freeze_sink_latency_belongs_only_to_post_and_cannot_amend_snapshot():
    port, bridge, events = setup()

    def slow_sink(event):
        events.append(event)
        if event["event_kind"] == "root_freeze":
            assert port.counts.begin("SINK_SELECT") is False
            port.wall += 40
            port.cpu += 100

    bridge._sink = slow_sink
    result = bridge.run_offline()
    assert result["root"]["root_elapsed_ms"] == 25
    assert result["root"]["process_cpu_ms"] == 10
    assert result["post_root_validation_ms"] == 47


def test_refresh_identity_change_is_not_executed():
    port, bridge, _ = setup()

    def refresh(_job):
        port.job.id = OTHER

    port.refresh = refresh
    with pytest.raises(b.BridgeRejected, match="CLAIM_OWNER_REJECTED"):
        bridge.run_offline()
    assert not any(c[0] == "worker" for c in port.calls)


def test_missing_create_claim_boundary_is_rejected():
    port, bridge, _ = setup()
    port.create_claim = lambda _emit: b.Claim(ROOT_ID, b.WORKER_ID, TOKEN)
    with pytest.raises(b.BridgeRejected, match="CLAIM_IDENTITY_REJECTED"):
        bridge.run_offline()
    assert port.calls == []


@pytest.mark.parametrize("stage", [(0, 26), (4, 20), (25, 24)])
def test_stage_must_be_inside_worker_interval(stage):
    port, bridge, _ = setup()

    def worker(_claim):
        port.wall += 20
        bridge.record_stage("factors.compute", begin_ms=stage[0], end_ms=stage[1])

    port.execute_claimed_job = worker
    with pytest.raises(b.BridgeRejected, match="STAGE_REJECTED"):
        bridge.run_offline()
    assert bridge.snapshot is None


@pytest.mark.parametrize("port", ["postgresql://secret@production/stock_db", {}, object()])
def test_uri_dict_or_session_object_is_not_a_business_port(port):
    with pytest.raises(b.BridgeRejected, match="PORT_REJECTED"):
        b.RootBridge(run_uuid=RUN, implementation_sha=SHA, ports=port)


def test_sink_failure_stops_before_business_and_consumes_attempt():
    def failed(_event):
        raise OSError("secret path")
    port, bridge, _ = setup(sink=failed)
    with pytest.raises(b.BridgeRejected, match="SINK_FAILED"):
        bridge.run_offline()
    assert port.calls == [] and bridge.attempt_consumed


def test_default_and_live_ports_refuse_without_session_or_permission_bypass():
    bridge = b.RootBridge(run_uuid=RUN, implementation_sha=SHA)
    with pytest.raises(b.BridgeRejected, match="EXECUTION_NOT_AVAILABLE"):
        bridge.run_offline()
    for kwargs in ({}, {"db": object()}, {"approved": True},
                   {"url": "postgresql://private:secret@production/stock_db"}):
        with pytest.raises(b.BridgeRejected, match="EXECUTION_NOT_AVAILABLE"):
            b.LiveBusinessPort(**kwargs)
    assert not hasattr(b, "main") and not hasattr(b, "execute")


@pytest.mark.parametrize(("run", "sha"), [
    (None, SHA), ("postgresql://private:secret@production/stock_db", SHA),
    (RUN, "postgresql://private:secret@production/stock_db"), (RUN, "a" * 39),
])
def test_identity_never_reads_connection_uri_or_environment(run, sha, monkeypatch):
    import os
    monkeypatch.setattr(os, "getenv", lambda *a: pytest.fail("environment read"))
    with pytest.raises(b.BridgeRejected, match="IDENTITY_REJECTED"):
        b.RootBridge(run_uuid=run, implementation_sha=sha)


def test_production_mapping_matches_current_signatures_without_importing_app():
    tree = ast.parse((REPO / "scripts/biz_perf_p1_04_w05_root_bridge.py").read_text("utf-8"))
    live = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                and n.name == "LiveBusinessPort")
    imports = [(n.module, a.name) for n in ast.walk(live)
               if isinstance(n, ast.ImportFrom) for a in n.names]
    assert imports == [("app.services.job_worker", "claim_next_job"),
                       ("app.services.recalculation", "create_recalculation_job"),
                       ("app.services.job_worker", "execute_claimed_job")]
    for relative, name, positional, keywords in [
        ("recalculation.py", "create_recalculation_job", ["db"],
         ["start", "end", "evaluate_signals", "mode", "dirty_ranges", "job_id"]),
        ("job_worker.py", "claim_next_job", ["db", "worker_id"], []),
        ("job_worker.py", "execute_claimed_job", ["db", "job_id"],
         ["expected_worker", "expected_token"]),
    ]:
        source = ast.parse((REPO / "backend/app/services" / relative).read_text("utf-8"))
        fn = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert [a.arg for a in fn.args.args] == positional
        assert [a.arg for a in fn.args.kwonlyargs] == keywords
    assert dataclasses.is_dataclass(b.Claim)


def test_subprocess_import_and_reflection_have_no_io_or_production_imports():
    script = r'''
import sys
def audit(name, args):
    if name in {"socket.__new__", "socket.connect", "subprocess.Popen", "os.system"}:
        raise AssertionError("side effect")
    if name == "open":
        path, mode, flags = args
        if isinstance(mode, str) and any(c in mode for c in "wax+"):
            raise AssertionError("write")
        if isinstance(path, str) and (".env" in path or "://" in path):
            raise AssertionError("resource read")
    if name == "import" and args[0].split(".")[0] in {
        "app", "backend", "sqlalchemy", "psycopg", "dotenv"}:
        raise AssertionError("production import")
sys.addaudithook(audit)
from scripts import biz_perf_p1_04_w05_root_bridge as b
import inspect
inspect.getmembers(b.LiveBusinessPort)
for method, arg in [(b.LiveBusinessPort.create_claim, None),
                    (b.LiveBusinessPort.execute_claimed_job, None)]:
    try:
        method(object(), arg)
    except b.BridgeRejected as error:
        assert str(error) == "EXECUTION_NOT_AVAILABLE"
    else:
        raise AssertionError("unbound live method accepted arbitrary object")
instance = b.RootBridge(run_uuid="12345678-1234-4234-8234-123456789abc",
                        implementation_sha="a"*40)
try:
    instance.run_offline()
except b.BridgeRejected as error:
    assert str(error) == "EXECUTION_NOT_AVAILABLE"
else:
    raise AssertionError("default allowed execution")
assert not {"app", "backend", "sqlalchemy", "psycopg", "dotenv"} & set(sys.modules)
print("IMPORT_REFUSED_WITHOUT_SIDE_EFFECTS")
'''
    result = subprocess.run([sys.executable, "-B", "-c", script], cwd=REPO,
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "IMPORT_REFUSED_WITHOUT_SIDE_EFFECTS"
