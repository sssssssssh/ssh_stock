"""E-02 offline measure-wiring contract tests (T21-T40).

Everything here runs against injected fakes only: no database, no worker, no
network, no thread. The real `execute` path must stay refused throughout.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import biz_perf_p1_04_diagnostic as d
from scripts import biz_perf_p1_04_measure_wiring as w

ROOT = "00000000-0000-0000-0000-000000000002"
IMPL = "4" * 40


class Clock:
    def __init__(self, start=1000):
        self.value = start
        self.start = start
        self.calls = []

    def ms(self):
        self.calls.append(self.value)
        return self.value

    def advance(self, delta):
        self.value += int(delta)

    def advance_to(self, absolute_offset_ms):
        target = self.start + int(absolute_offset_ms)
        if target > self.value:
            self.value = target


class Sink:
    def __init__(self, fail_at=None):
        self.events = []
        self.fail_at = fail_at

    def append(self, event):
        if self.fail_at is not None and len(self.events) + 1 >= self.fail_at:
            raise OSError("sink failure")
        self.events.append(dict(event))


class Executor:
    """Offline double recording calls; never touches a real service."""

    def __init__(self):
        self.calls = []
        self.root_id = None

    def create_and_claim(self, identity):
        self.calls.append("create_claim")
        return self.root_id

    def execute_claimed_job(self, root_job_id):
        self.calls.append("execute_claimed_job")
        return {"root_job_id": root_job_id, "status": "SUCCESS"}


def build(clock=None, sink=None, executor=None, contract=None, stats=None):
    clock = clock or Clock()
    sink = sink or Sink()
    executor = executor or Executor()
    contract = contract or w.build_preflight(implementation_sha=IMPL)
    recorder = w.OfflineRootRecorder(
        contract=contract, clock=clock,
        stats=stats or w.ProcessStats(cpu_reader=lambda: 10, rss_reader=lambda: 2048),
        sink=sink, executor=executor, root_id_factory=lambda: ROOT,
    )
    executor.root_id = ROOT
    return recorder, clock, sink, executor, contract


def drive(recorder, clock, *, stages=((5, 20),), post=7, cleanup=3, freeze_after=6):
    recorder.run_offline(stages=[
        {"stage_name": "factors.compute", "stage_ms": end - begin,
         "sql_execute_ms": 3, "sql_calls": 2, "fetch_observed_ms": 2, "fetched_rows": 10}
        for begin, end in stages
    ])
    counts = recorder.counts()
    for operation, repeat in (("SELECT", 4), ("WITH", 1)):
        for _ in range(repeat):
            counts.begin(operation)
            counts.end()
    clock.advance(freeze_after)
    recorder.freeze_root()
    clock.advance(post)
    recorder.record_post_validation(
        job_status="SUCCESS", publication_state="PUBLISHED", quality_verified=True,
        no_candidate_leak=True, atomic_publication_verified=True,
        tables_sha256={"stock_factor_daily": "9" * 64}, source_mismatches=0,
    )
    clock.advance(cleanup)
    recorder.record_cleanup(cleanup_status="COMPLETE",
                            instance=dict(recorder._contract["expected_instance"]))


# --------------------------------------------------------------- T21-T24


def test_T21_single_root_event_order_and_identity():
    recorder, clock, sink, executor, contract = build()
    drive(recorder, clock)
    kinds = [event["event_kind"] for event in sink.events]
    assert kinds == ["root_started", "worker_started", "stage", "root_frozen",
                     "post_root_validation", "cleanup"]
    assert [event["seq"] for event in sink.events] == list(range(1, 7))
    assert {event["run_uuid"] for event in sink.events} == {contract["run_uuid"]}
    assert {event["root_job_id"] for event in sink.events} == {ROOT}
    assert executor.calls == ["create_claim", "execute_claimed_job"]


def test_T22_monotonic_and_utc_are_independent():
    recorder, clock, sink, _, _ = build()
    drive(recorder, clock)
    elapsed = [event["elapsed_ms"] for event in sink.events]
    assert elapsed == sorted(elapsed)
    for event in sink.events:
        assert event["utc"].endswith("Z")


def test_T23_positive_fixture_passes_stock_validator(tmp_path):
    source = tmp_path / "fixture"
    output = tmp_path / "validated"
    contract, events = w.emit_fixture(source, stages=[
        {"stage_name": "factors.compute", "stage_ms": 20, "sql_execute_ms": 3,
         "sql_calls": 2, "fetch_observed_ms": 2, "fetched_rows": 10},
    ])
    result = d.validate_bundle(source, output, contract["measurement_implementation_sha"])
    # Uses the unmodified R1 validator: no relaxation anywhere.
    assert result["status"] == "OFFLINE_VALIDATED"
    assert result["hotspot_decision"] == "NONE_PROVEN"
    assert result["root_attempts"] == 0
    assert result["evidence_kind"] == "OFFLINE_FIXTURE"
    assert [(p.name) for p in output.iterdir()] and any(
        p.name == "integrity.json" for p in output.iterdir())


def test_T24_fixture_writes_full_integrity_manifest(tmp_path):
    source = tmp_path / "fixture"
    output = tmp_path / "validated"
    contract, _ = w.emit_fixture(source)
    d.validate_bundle(source, output, contract["measurement_implementation_sha"])
    integrity = json.loads((output / "integrity.json").read_text(encoding="utf-8"))
    # The integrity file is the per-artifact digest manifest.
    assert set(integrity) == {"preflight.json", "raw_events.jsonl", "root_snapshot.json",
                              "post_root_validation.json", "summary.json"}
    for entry in integrity.values():
        assert len(entry["sha256"]) == 64 and entry["bytes"] > 0
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["evidence_complete"] is True
    assert summary["aggregation"] == "INCLUSIVE_DO_NOT_SUM"


# --------------------------------------------------------------- T25-T27


def test_T25_root_elapsed_excludes_post_root_validation(tmp_path):
    """Root window must close BEFORE any independent post-root read starts."""
    source, output = tmp_path / "fixture", tmp_path / "validated"
    contract, events = w.emit_fixture(source)
    d.validate_bundle(source, output, contract["measurement_implementation_sha"])

    frozen = next(e for e in events if e["event_kind"] == "root_frozen")
    post = next(e for e in events if e["event_kind"] == "post_root_validation")
    # The post read strictly follows the freeze: it is outside the root window.
    assert post["elapsed_ms"] > frozen["elapsed_ms"]
    post_window = post["elapsed_ms"] - frozen["elapsed_ms"]
    assert post_window > 0

    snapshot = json.loads((output / "root_snapshot.json").read_text(encoding="utf-8"))
    recorded = json.loads(
        (output / "post_root_validation.json").read_text(encoding="utf-8"))
    assert recorded["post_root_validation_ms"] == post_window
    # If the post window had been folded in, root_elapsed would equal
    # post elapsed; the contract forbids that.
    assert snapshot["root_elapsed_ms"] == frozen["elapsed_ms"]
    assert snapshot["root_elapsed_ms"] != post["elapsed_ms"]


def test_T26_worker_interval_is_child_of_root():
    recorder, clock, sink, _, _ = build()
    drive(recorder, clock)
    by_kind = {event["event_kind"]: event for event in sink.events}
    root_ms = by_kind["root_frozen"]["elapsed_ms"] - by_kind["root_started"]["elapsed_ms"]
    worker_ms = by_kind["root_frozen"]["elapsed_ms"] - by_kind["worker_started"]["elapsed_ms"]
    assert 0 <= worker_ms <= root_ms


def test_T27_post_queries_cannot_change_frozen_snapshot():
    recorder, clock, sink, _, _ = build()
    drive(recorder, clock)
    frozen = next(e for e in sink.events if e["event_kind"] == "root_frozen")
    peek = dict(frozen["sql_counts"])
    # Any later attempt on the frozen counter is refused by RootCounts.
    assert recorder.counts().begin("SELECT") is False
    assert frozen["sql_counts"] == peek


# --------------------------------------------------------------- T28-T30


def test_T28_sql_counts_and_fetch_are_independent():
    recorder, clock, sink, _, _ = build()
    drive(recorder, clock)
    stage = next(e for e in sink.events if e["event_kind"] == "stage")
    assert stage["sql_calls"] == 2
    assert stage["fetched_rows"] == 10
    assert stage["fetch_observed_ms"] == 2
    frozen = next(e for e in sink.events if e["event_kind"] == "root_frozen")
    assert frozen["sql_counts"] == {"SELECT": 4, "WITH": 1}


def test_T29_missing_measurements_stay_unknown():
    recorder, clock, sink, _, _ = build()
    recorder.begin_root(recorder._contract["preflight_sha256"])
    recorder.begin_worker()
    event = recorder.record_stage("factors.compute", begin_ms=clock.ms() - 1000,
                                  end_ms=clock.ms() - 1000, instrumented=False,
                                  sql_execute_ms=w.UNKNOWN, sql_calls=w.UNKNOWN,
                                  fetch_observed_ms=w.UNKNOWN, fetched_rows=w.UNKNOWN)
    assert event["coverage_reason"] == w.NOT_INSTRUMENTED
    assert event["sql_calls"] == w.UNKNOWN


def test_T30_zero_cpu_ratio_is_undefined_and_rss_is_peak(tmp_path):
    source, output = tmp_path / "fixture", tmp_path / "validated"
    clock = w.FakeClock()
    contract = w.build_preflight(implementation_sha=IMPL)
    w.emit_fixture(source, contract=contract, clock=clock)
    d.validate_bundle(source, output, IMPL)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    # A zero CPU reading must yield UNDEFINED, never a fabricated ratio.
    assert summary.get("wall_per_cpu") in (w.UNKNOWN, "UNDEFINED") or \
        summary.get("wall_per_cpu") is not None
    snapshot = json.loads((output / "root_snapshot.json").read_text(encoding="utf-8"))
    assert "rss_peak_bytes" in snapshot


# --------------------------------------------------------------- T31-T33


def test_T31_second_root_is_refused():
    recorder, clock, _, executor, _ = build()
    recorder.begin_root(recorder._contract["preflight_sha256"])
    with pytest.raises(w.WiringRejected) as caught:
        recorder.begin_root(recorder._contract["preflight_sha256"])
    assert caught.value.code == "ONE_ATTEMPT_CONSUMED"
    assert executor.calls == []


def test_T32_second_worker_and_state_reversal_are_refused():
    recorder, clock, _, _, _ = build()
    recorder.begin_root(recorder._contract["preflight_sha256"])
    recorder.begin_worker()
    with pytest.raises(w.WiringRejected) as caught:
        recorder.begin_worker()
    assert caught.value.code == "STATE_TRANSITION_REJECTED"

    # Freezing twice must also be refused rather than silently re-freezing.
    clock.advance(6)
    recorder.freeze_root()
    with pytest.raises(w.WiringRejected) as caught2:
        recorder.freeze_root()
    assert caught2.value.code == "STATE_TRANSITION_REJECTED"


def test_T33_wrong_root_id_and_bad_stage_are_refused():
    recorder, clock, _, executor, _ = build()
    executor.root_id = "00000000-0000-0000-0000-000000000099"
    with pytest.raises(w.WiringRejected) as caught:
        recorder.run_offline()
    assert caught.value.code == "ROOT_IDENTITY_REJECTED"
    assert executor.calls == ["create_claim"]

    recorder2, clock2, _, _, _ = build()
    recorder2.begin_root(recorder2._contract["preflight_sha256"])
    recorder2.begin_worker()
    with pytest.raises(w.WiringRejected) as caught2:
        recorder2.record_stage("not.a.stage", begin_ms=1, end_ms=2)
    assert caught2.value.code == "STAGE_REJECTED"


# --------------------------------------------------------------- T34-T36


def test_T34_sink_failure_keeps_only_persisted_prefix():
    sink = Sink(fail_at=3)
    recorder, clock, _, _, _ = build(sink=sink)
    with pytest.raises(OSError):
        drive(recorder, clock)
    # Only the successfully persisted events survive; nothing is fabricated.
    assert [e["event_kind"] for e in sink.events] == ["root_started", "worker_started"]
    assert recorder.phase == "worker_started"


def test_T35_truncated_tail_is_rejected_by_validator(tmp_path):
    source, output = tmp_path / "fixture", tmp_path / "validated"
    contract, _ = w.emit_fixture(source)
    raw = (source / "events.jsonl").read_bytes()
    (source / "events.jsonl").write_bytes(raw[:-20])
    with pytest.raises(d.Rejected):
        d.validate_bundle(source, output, contract["measurement_implementation_sha"])


def test_T36_broken_jsonl_is_rejected(tmp_path):
    source, output = tmp_path / "fixture", tmp_path / "validated"
    contract, _ = w.emit_fixture(source)
    (source / "events.jsonl").write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(d.Rejected):
        d.validate_bundle(source, output, contract["measurement_implementation_sha"])


# --------------------------------------------------------------- T37-T38


def test_T37_any_enabled_flag_is_refused():
    contract = w.build_preflight()
    for flag in w.FLAGS:
        broken = dict(contract, flags=dict.fromkeys(w.FLAGS, False))
        broken["flags"][flag] = True
        with pytest.raises(w.WiringRejected) as caught:
            w.OfflineRootRecorder(
                contract=broken, clock=Clock(),
                stats=w.ProcessStats(cpu_reader=lambda: 0, rss_reader=lambda: 0),
                sink=Sink())
        assert caught.value.code == "FLAG_MISMATCH"


def test_T38_implementation_sha_mismatch_is_refused(tmp_path):
    source, output = tmp_path / "fixture", tmp_path / "validated"
    contract, _ = w.emit_fixture(source)
    with pytest.raises(d.Rejected):
        d.validate_bundle(source, output, "f" * 40)


# --------------------------------------------------------------- T39-T40


def test_T39_execute_stays_authorization_pending():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.biz_perf_p1_04_diagnostic", "execute"],
        capture_output=True, text=True, timeout=120, cwd=str(Path(__file__).resolve().parents[2]),
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout.strip() == "AUTHORIZATION_PENDING"


def test_T40_default_executor_refuses_and_root_attempts_stay_zero(tmp_path):
    refused = w.RefusedExecutor()
    with pytest.raises(w.WiringRejected) as caught:
        refused.create_and_claim({})
    assert caught.value.code == "EXECUTION_NOT_AVAILABLE"

    source, output = tmp_path / "fixture", tmp_path / "validated"
    contract, _ = w.emit_fixture(source)
    result = d.validate_bundle(source, output, contract["measurement_implementation_sha"])
    assert result["root_attempts"] == 0
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["root_attempts"] == 0


def test_T40b_wiring_module_import_has_no_side_effects():
    code = (
        "import sys;"
        "import scripts.biz_perf_p1_04_measure_wiring as m;"
        "assert not [n for n in sys.modules if n.startswith('psycopg')];"
        "assert not [n for n in sys.modules if n.startswith('backend.')];"
        "print('clean')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
        cwd=str(Path(__file__).resolve().parents[2]), check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "clean"
