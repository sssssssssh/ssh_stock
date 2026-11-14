"""File prefixes, unknown ACK and failure simulation; no live resource actions."""

import json

import pytest
from test_biz_perf_p1_04_e03_guard import FixturePorts
from test_biz_perf_p1_04_e03_guard import g as g
from test_biz_perf_p1_04_e03_guard import plan as plan

from scripts import biz_perf_p1_04_diagnostic as d
from scripts import biz_perf_p1_04_measure_wiring as w
from scripts.biz_perf_p1_04_e03_collectors import CollectorPorts
from scripts.biz_perf_p1_04_e03_evidence import (
    BoundedEvidenceSink,
    MockLifecycle,
    OfflineFailure,
)

ROOT = "00000000-0000-0000-0000-000000000002"


class FakeExecutor:
    def __init__(self, clock, failure=None, at="create"):
        self.clock, self.failure, self.at = clock, failure, at
        self.calls = []
        self.counts = None

    def create_and_claim(self, _identity):
        self.calls.append("create_claim")
        self.clock.advance(5)
        if self.failure and self.at == "create":
            raise OfflineFailure(self.failure)
        return ROOT

    def execute_claimed_job(self, _root):
        self.calls.append("worker")
        self.clock.advance(20)
        if self.failure:
            raise OfflineFailure(self.failure)
        for _ in range(2):
            assert self.counts.begin("SELECT")
            self.counts.end()
        return dict(root_job_id=ROOT, status="SUCCESS")


def build(plan, tmp_path, *, failure=None, at="create", collectors=None):
    source = tmp_path / "input"
    source.mkdir()
    (source / "preflight.json").write_bytes(d.encode(plan["preflight"]))
    clock = w.FakeClock()
    sink = BoundedEvidenceSink(source / "events.jsonl", plan["preflight"])
    executor = FakeExecutor(clock, failure, at)
    session = MockLifecycle(
        plan=plan, expected_sha="a" * 40, clock=clock,
        collectors=collectors or CollectorPorts(), sink=sink, executor=executor,
        root_id_factory=lambda: ROOT,
    )
    executor.counts = session.recorder.counts()
    return source, clock, sink, executor, session


@pytest.mark.parametrize("failure,at", [
    ("CREATE_FAILED", "create"), ("CLAIM_FAILED", "create"), ("UNKNOWN_ACK", "create"),
    ("WORKER_FAILED", "worker"), ("TIMEOUT", "worker"), ("BUDGET_EXCEEDED", "worker"),
])
def test_one_attempt_failures_leave_inspectable_prefix(plan, tmp_path, failure, at):
    source, _clock, sink, executor, session = build(plan, tmp_path, failure=failure, at=at)
    with pytest.raises(OfflineFailure, match=failure):
        session.run_offline(stages=w.DEFAULT_STAGES)
    calls = list(executor.calls)
    with pytest.raises(OfflineFailure, match="ONE_ATTEMPT_CONSUMED"):
        session.run_offline()
    assert calls == executor.calls
    assert calls.count("create_claim") == 1
    assert ("worker" in calls) == (at == "worker")
    assert session.recorder.counts().begin("UPDATE") is False
    sink.close()
    events = [json.loads(line) for line in (source / "events.jsonl").read_bytes().splitlines()]
    assert events[-1]["event_kind"] == "failure"
    assert not any(event["event_kind"] in {"root_frozen", "cleanup"} for event in events)
    replay = d.Replay(plan["preflight"])
    for event in events:
        replay.accept(event)
    assert replay.phase == "failure"
    with pytest.raises(d.Rejected):
        d.validate_bundle(source, tmp_path / "rejected", "a" * 40)
    assert not (tmp_path / "rejected" / "summary.json").exists()


def post(recorder, clock):
    clock.advance(7)
    recorder.record_post_validation(
        job_status="SUCCESS", publication_state="PUBLISHED", quality_verified=True,
        no_candidate_leak=True, atomic_publication_verified=True,
        source_mismatches=0, tables_sha256=dict.fromkeys(d.TABLES, "9" * 64),
    )


def test_file_evidence_original_validator_and_post_boundary(g, plan, tmp_path):
    ports = FixturePorts(g.validate_plan(plan, "a" * 40))
    proof = g.OfflineGuard(inspector=ports, attestor=ports, approvals=ports, budgets=ports,
                           journal=g.OfflineJournal()).inspect(plan, "a" * 40)
    assert proof["authorization"] == "AUTHORIZATION_PENDING"
    cpu, rss = [100], [2048]
    ports = CollectorPorts(cpu_reader=lambda: cpu[0], rss_reader=lambda: rss[0])
    source, clock, sink, _executor, session = build(plan, tmp_path, collectors=ports)
    result = session.run_offline(stages=w.DEFAULT_STAGES)
    assert result["root_attempts"] == 0
    cpu[0], rss[0] = 900, 9999
    clock.advance(50)
    assert session.recorder.counts().begin("SELECT") is False
    post(session.recorder, clock)
    session.recorder.record_cleanup(cleanup_status="COMPLETE",
                                     instance=plan["preflight"]["expected_instance"])
    sink.close()
    output = tmp_path / "output"
    d.validate_bundle(source, output, "a" * 40)
    summary = json.loads((output / "summary.json").read_bytes())
    raw = (source / "events.jsonl").read_bytes()
    frozen = next(json.loads(line) for line in raw.splitlines()
                  if json.loads(line)["event_kind"] == "root_frozen")
    assert frozen["process_cpu_ms"] == 0
    assert frozen["rss_peak_bytes"] == 2048
    assert frozen["fetch_observed_ms"] == frozen["fetched_rows"] == "UNKNOWN"
    assert frozen["sql_counts"] == {"SELECT": 2}
    assert frozen["elapsed_ms"] == 45
    assert summary["root_attempts"] == 0
    assert summary["hotspot_decision"] == "NONE_PROVEN"
    assert "LIVE_VERIFIED" not in str(summary)
    assert (output / "integrity.json").is_file()
    assert g.execute() == 2


def test_unknown_cleanup_is_blocked_without_resource_action(g, plan, tmp_path):
    source, clock, sink, executor, session = build(plan, tmp_path)
    session.run_offline(stages=w.DEFAULT_STAGES)
    plan["observed"]["resources"]["volume_sha256"] = "0" * 64
    assert g.cleanup_status(plan["expected"], plan["observed"]) == "CLEANUP_BLOCKED"
    post(session.recorder, clock)
    session.recorder.record_cleanup(cleanup_status="BLOCKED",
                                     instance=plan["preflight"]["expected_instance"])
    sink.close()
    with pytest.raises(d.Rejected, match="CLEANUP_BLOCKED"):
        d.validate_bundle(source, tmp_path / "blocked", "a" * 40)
    assert executor.calls == ["create_claim", "worker"]
    assert not hasattr(executor, "cleanup")
    assert not hasattr(session, "cleanup")


@pytest.mark.parametrize("fault", ["short", "fsync"])
def test_file_faults_poison_evidence(plan, tmp_path, monkeypatch, fault):
    source, _clock, sink, executor, session = build(plan, tmp_path)
    if fault == "fsync":
        monkeypatch.setattr(w.os, "fsync", lambda *_: (_ for _ in ()).throw(OSError("PRIVATE")))
    else:
        original = sink._sink._fh

        class Short:
            closed = False

            def write(self, raw):
                return original.write(raw[:-2])

            def close(self):
                original.close()

        sink._sink._fh = Short()
    with pytest.raises(OfflineFailure, match="SINK_FAILED"):
        session.run_offline()
    with pytest.raises(w.SinkRejected, match="SINK_FAILED"):
        sink.append({})
    assert sink.count == 0
    assert executor.calls == []
    sink.close()
    with pytest.raises(d.Rejected):
        d.validate_bundle(source, tmp_path / "fault", "a" * 40)
    assert not (tmp_path / "fault" / "integrity.json").exists()


@pytest.mark.parametrize("change", ["seq", "root_job_id", "run_uuid", "private", "size"])
def test_sink_rejects_wrong_identity_and_unstructured_text(plan, tmp_path, change):
    _source, _clock, sink, _executor, session = build(plan, tmp_path)
    event = dict(seq=1, event_kind="root_started", run_uuid=plan["preflight"]["run_uuid"],
                 root_job_id=ROOT, utc="2026-11-14T00:00:00Z", elapsed_ms=0,
                 preflight_sha256=session.contract["preflight_sha256"])
    sink.append(event)
    if change == "private":
        event["error"] = "PRIVATE_PASSWORD"
    elif change == "size":
        event["error"] = "PRIVATE" * d.MAX_LINE_BYTES
    else:
        event[change] = 9 if change == "seq" else "00000000-0000-0000-0000-000000000009"
    with pytest.raises(w.SinkRejected, match="SINK_FAILED"):
        sink.append(event)
    assert sink.count == 1
    sink.close()


def test_collect_failure_seals_root_and_no_completed_bundle(plan, tmp_path):
    def broken():
        raise OSError("PRIVATE_COLLECTOR")

    # Direct malformed port is fail-closed. CollectorPorts separately tests
    # supported missing/failed readers producing UNKNOWN, never a fake zero.
    class BrokenPorts:
        stats = w.ProcessStats(cpu_reader=lambda: 100, rss_reader=broken)

        def fetch(self):
            return dict(observed_ms="UNKNOWN", rows="UNKNOWN")

    source, _clock, sink, executor, session = build(plan, tmp_path, collectors=BrokenPorts())
    with pytest.raises(OfflineFailure, match="COLLECTOR_FAILED"):
        session.run_offline(stages=w.DEFAULT_STAGES)
    assert session.recorder.counts().begin("SELECT") is False
    with pytest.raises(OfflineFailure, match="ONE_ATTEMPT_CONSUMED"):
        session.run_offline()
    assert executor.calls == ["create_claim", "worker"]
    sink.close()
    assert b"PRIVATE_COLLECTOR" not in (source / "events.jsonl").read_bytes()
    with pytest.raises(d.Rejected):
        d.validate_bundle(source, tmp_path / "collector-fault", "a" * 40)


def test_default_executor_is_refused_without_any_resource(plan, tmp_path):
    source = tmp_path / "default.jsonl"
    sink = BoundedEvidenceSink(source, plan["preflight"])
    session = MockLifecycle(plan=plan, expected_sha="a" * 40, clock=w.FakeClock(),
                            collectors=CollectorPorts(), sink=sink)
    with pytest.raises(OfflineFailure, match="EXECUTION_NOT_AVAILABLE"):
        session.run_offline()
    sink.close()
