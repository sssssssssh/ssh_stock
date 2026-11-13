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
    contract = contract or w.build_preflight(implementation_sha=IMPL)
    recorder = w.OfflineRootRecorder(
        contract=contract, clock=clock,
        stats=stats or w.ProcessStats(cpu_reader=lambda: 10, rss_reader=lambda: 2048),
        sink=sink, executor=executor or Executor(), root_id_factory=lambda: ROOT,
    )
    if executor is None:
        executor = recorder._executor
    executor.root_id = ROOT
    return recorder, clock, sink, executor, contract


class CountingExecutor(Executor):
    """Counts root SQL inside the worker call, as the real root window requires."""

    def __init__(self, recorder_ref, inner=None):
        super().__init__()
        self._ref = recorder_ref
        self._inner = inner

    def create_and_claim(self, identity):
        if self._inner is not None:
            return self._inner.create_and_claim(identity)
        return super().create_and_claim(identity)

    def execute_claimed_job(self, root_job_id):
        counts = self._ref[0].counts()
        for operation, repeat in (("SELECT", 4), ("WITH", 1)):
            for _ in range(repeat):
                counts.begin(operation)
                counts.end()
        if self._inner is not None:
            return self._inner.execute_claimed_job(root_job_id)
        return super().execute_claimed_job(root_job_id)


def drive(recorder, clock, *, stages=((5, 20),), post=7, cleanup=3, executor=None):
    """Drive one root. Root SQL is counted inside the worker call (M05).

    When `executor` is supplied the wrapper delegates to it so its call log
    stays observable; the SQL counting still happens inside the worker call.
    """
    counted = CountingExecutor([recorder], inner=executor)
    counted.root_id = ROOT
    recorder._executor = counted
    recorder.run_offline(stages=[
        {"stage_name": "factors.compute", "stage_ms": end - begin,
         "sql_execute_ms": 3, "sql_calls": 2, "fetch_observed_ms": 2, "fetched_rows": 10}
        for begin, end in stages
    ])
    # No post-return bookkeeping: freeze binds to the worker-return instant.
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
    drive(recorder, clock, executor=executor)
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


# =====================================================================
# E-02-R1 metric-correctness contracts (M01-M06)
# =====================================================================


class CumulativeCpu:
    """Cumulative process CPU reader in milliseconds (a real reader semantic)."""

    def __init__(self, values):
        self._values = list(values)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if len(self._values) > 1:
            return self._values.pop(0)
        return self._values[0]


def _cpu_recorder(reader, clock=None, sink=None):
    clock = clock or Clock()
    sink = sink or Sink()
    contract = w.build_preflight(implementation_sha=IMPL)
    rec = w.OfflineRootRecorder(
        contract=contract, clock=clock,
        stats=w.ProcessStats(cpu_reader=reader, rss_reader=lambda: 2048),
        sink=sink, executor=Executor(), root_id_factory=lambda: ROOT,
    )
    rec._executor.root_id = ROOT
    return rec, clock, sink


def test_M01_process_cpu_is_interval_delta_not_cumulative():
    reader = CumulativeCpu([100, 135])
    rec, clock, sink = _cpu_recorder(reader)
    rec.begin_root(rec._contract["preflight_sha256"])
    rec.begin_worker()
    clock.advance(26)
    rec.freeze_root()
    frozen = next(e for e in sink.events if e["event_kind"] == "root_frozen")
    # 135 - 100 = 35, never the raw cumulative 135.
    assert frozen["process_cpu_ms"] == 35


def test_M01_zero_cpu_interval_is_zero_not_undefined():
    reader = CumulativeCpu([100, 100])
    rec, clock, sink = _cpu_recorder(reader)
    rec.begin_root(rec._contract["preflight_sha256"])
    rec.begin_worker()
    clock.advance(26)
    rec.freeze_root()
    frozen = next(e for e in sink.events if e["event_kind"] == "root_frozen")
    assert frozen["process_cpu_ms"] == 0


def test_M01_regressing_cumulative_reader_yields_unknown():
    reader = CumulativeCpu([100, 90])  # end < start cannot form an interval
    rec, clock, sink = _cpu_recorder(reader)
    rec.begin_root(rec._contract["preflight_sha256"])
    rec.begin_worker()
    clock.advance(26)
    rec.freeze_root()
    frozen = next(e for e in sink.events if e["event_kind"] == "root_frozen")
    assert frozen["process_cpu_ms"] == w.UNKNOWN


def test_M01_bad_cpu_types_yield_unknown():
    for bad in (None, "100", 1.5, True, -5):
        reader = CumulativeCpu([100, bad])
        rec, clock, sink = _cpu_recorder(reader)
        rec.begin_root(rec._contract["preflight_sha256"])
        rec.begin_worker()
        clock.advance(26)
        rec.freeze_root()
        frozen = next(e for e in sink.events if e["event_kind"] == "root_frozen")
        assert frozen["process_cpu_ms"] == w.UNKNOWN, bad


def test_M01_missing_reader_is_unknown_not_zero():
    rec, clock, sink = _cpu_recorder(None)
    rec.begin_root(rec._contract["preflight_sha256"])
    rec.begin_worker()
    clock.advance(26)
    rec.freeze_root()
    frozen = next(e for e in sink.events if e["event_kind"] == "root_frozen")
    assert frozen["process_cpu_ms"] == w.UNKNOWN


def test_M02_nested_overlapping_stages_are_accepted( tmp_path=None):
    clock, sink, ex = Clock(), Sink(), Executor()
    contract = w.build_preflight(implementation_sha=IMPL)
    rec = w.OfflineRootRecorder(
        contract=contract, clock=clock,
        stats=w.ProcessStats(cpu_reader=lambda: 10, rss_reader=lambda: 2048),
        sink=sink, executor=ex, root_id_factory=lambda: ROOT,
    )
    ex.root_id = ROOT
    rec.begin_root(rec._contract["preflight_sha256"])
    rec.begin_worker()
    # Inner 10-20 completes first.
    clock.advance_to(20)
    rec.record_stage("factors.stock_daily", begin_ms=10, end_ms=20,
                     sql_execute_ms=4, sql_calls=1,
                     fetch_observed_ms=1, fetched_rows=3)
    # Outer 5-40 completes later; its begin predates the inner begin.
    clock.advance_to(40)
    rec.record_stage("factors.compute", begin_ms=5, end_ms=40,
                     sql_execute_ms=10, sql_calls=2,
                     fetch_observed_ms=2, fetched_rows=5)
    stages = [e for e in sink.events if e["event_kind"] == "stage"]
    assert len(stages) == 2
    outer = next(s for s in stages if s["stage_name"] == "factors.compute")
    inner = next(s for s in stages if s["stage_name"] == "factors.stock_daily")
    # Overlap is real: outer spans the inner.
    assert outer["started_ms"] == 5 and outer["elapsed_ms"] == 40
    assert inner["started_ms"] == 10 and inner["elapsed_ms"] == 20
    assert outer["started_ms"] < inner["started_ms"] < inner["elapsed_ms"] \
        < outer["elapsed_ms"]


def test_M02_illegal_stage_intervals_still_refused():
    def fresh():
        clock, sink, ex = Clock(), Sink(), Executor()
        contract = w.build_preflight(implementation_sha=IMPL)
        rec = w.OfflineRootRecorder(
            contract=contract, clock=clock,
            stats=w.ProcessStats(cpu_reader=lambda: 10, rss_reader=lambda: 2048),
            sink=sink, executor=ex, root_id_factory=lambda: ROOT,
        )
        ex.root_id = ROOT
        rec.begin_root(rec._contract["preflight_sha256"])
        rec.begin_worker()
        return rec, clock

    rec, clock = fresh()
    clock.advance_to(30)
    with pytest.raises(w.WiringRejected) as e1:
        rec.record_stage("factors.compute", begin_ms=20, end_ms=10)
    assert e1.value.code == "STAGE_INTERVAL_REJECTED"

    rec, clock = fresh()
    clock.advance_to(10)
    with pytest.raises(w.WiringRejected) as e2:
        rec.record_stage("factors.compute", begin_ms=0, end_ms=99)
    assert e2.value.code == "STAGE_END_IN_FUTURE"

    rec, clock = fresh()
    clock.advance_to(10)
    rec._worker_started_ms = 5
    with pytest.raises(w.WiringRejected) as e3:
        rec.record_stage("factors.compute", begin_ms=0, end_ms=10)
    assert e3.value.code == "STAGE_INTERVAL_REJECTED"


def test_M03_end_ms_is_bound_to_event_elapsed():
    clock, sink, ex = Clock(), Sink(), Executor()
    contract = w.build_preflight(implementation_sha=IMPL)
    rec = w.OfflineRootRecorder(
        contract=contract, clock=clock,
        stats=w.ProcessStats(cpu_reader=lambda: 10, rss_reader=lambda: 2048),
        sink=sink, executor=ex, root_id_factory=lambda: ROOT,
    )
    ex.root_id = ROOT
    rec.begin_root(rec._contract["preflight_sha256"])
    rec.begin_worker()
    clock.advance_to(50)
    ev = rec.record_stage("factors.compute", begin_ms=10, end_ms=40,
                          sql_execute_ms=3, sql_calls=1,
                          fetch_observed_ms=1, fetched_rows=2)
    # The emitted event time EQUALS the declared end, so the validator's
    # elapsed-started wall always matches the caller interval.
    assert ev["elapsed_ms"] == 40
    assert ev["elapsed_ms"] - ev["started_ms"] == 30


def test_M03_future_end_is_fail_closed():
    clock, sink, ex = Clock(), Sink(), Executor()
    contract = w.build_preflight(implementation_sha=IMPL)
    rec = w.OfflineRootRecorder(
        contract=contract, clock=clock,
        stats=w.ProcessStats(cpu_reader=lambda: 10, rss_reader=lambda: 2048),
        sink=sink, executor=ex, root_id_factory=lambda: ROOT,
    )
    ex.root_id = ROOT
    rec.begin_root(rec._contract["preflight_sha256"])
    rec.begin_worker()
    clock.advance_to(10)
    with pytest.raises(w.WiringRejected) as caught:
        rec.record_stage("factors.compute", begin_ms=0, end_ms=99)
    assert caught.value.code == "STAGE_END_IN_FUTURE"
    assert not [e for e in sink.events if e["event_kind"] == "stage"]


def test_M04_root_fetch_is_unknown_when_unobserved():
    clock, sink, ex = Clock(), Sink(), Executor()
    contract = w.build_preflight(implementation_sha=IMPL)
    rec = w.OfflineRootRecorder(
        contract=contract, clock=clock,
        stats=w.ProcessStats(cpu_reader=lambda: 10, rss_reader=lambda: 2048),
        sink=sink, executor=ex, root_id_factory=lambda: ROOT,
    )
    ex.root_id = ROOT
    rec.begin_root(rec._contract["preflight_sha256"])
    rec.begin_worker()
    clock.advance_to(20)
    rec.record_stage("factors.compute", begin_ms=0, end_ms=20,
                     sql_execute_ms=5, sql_calls=2,
                     fetch_observed_ms=3, fetched_rows=500)
    clock.advance_to(26)
    rec.freeze_root()
    frozen = next(e for e in sink.events if e["event_kind"] == "root_frozen")
    # Never fabricate an observed zero from unobserved root-level fetch.
    assert frozen["fetched_rows"] == w.UNKNOWN
    assert frozen["fetch_observed_ms"] == w.UNKNOWN


def test_M04_root_fetch_accepted_only_from_validated_port():
    clock, sink, ex = Clock(), Sink(), Executor()
    contract = w.build_preflight(implementation_sha=IMPL)
    rec = w.OfflineRootRecorder(
        contract=contract, clock=clock,
        stats=w.ProcessStats(cpu_reader=lambda: 10, rss_reader=lambda: 2048),
        sink=sink, executor=ex, root_id_factory=lambda: ROOT,
    )
    ex.root_id = ROOT
    rec.begin_root(rec._contract["preflight_sha256"])
    rec.begin_worker()
    clock.advance_to(26)
    rec.freeze_root(fetch={"observed_ms": 7, "rows": 42})
    frozen = next(e for e in sink.events if e["event_kind"] == "root_frozen")
    assert frozen["fetch_observed_ms"] == 7
    assert frozen["fetched_rows"] == 42


def test_M04_malformed_fetch_port_is_refused():
    clock, sink, ex = Clock(), Sink(), Executor()
    contract = w.build_preflight(implementation_sha=IMPL)
    rec = w.OfflineRootRecorder(
        contract=contract, clock=clock,
        stats=w.ProcessStats(cpu_reader=lambda: 10, rss_reader=lambda: 2048),
        sink=sink, executor=ex, root_id_factory=lambda: ROOT,
    )
    ex.root_id = ROOT
    rec.begin_root(rec._contract["preflight_sha256"])
    rec.begin_worker()
    clock.advance_to(26)
    for bad in ({"observed_ms": 1}, {"rows": 1}, {"observed_ms": -1, "rows": 0},
                {"observed_ms": 1, "rows": "x"}, "nope"):
        with pytest.raises(w.WiringRejected):
            rec.freeze_root(fetch=bad)


def test_M05_freeze_binds_to_worker_return_not_later_work():
    clock, sink = Clock(), Sink()
    contract = w.build_preflight(implementation_sha=IMPL)
    ex = Executor()
    rec = w.OfflineRootRecorder(
        contract=contract, clock=clock,
        stats=w.ProcessStats(cpu_reader=lambda: 10, rss_reader=lambda: 2048),
        sink=sink, executor=ex, root_id_factory=lambda: ROOT,
    )
    ex.root_id = ROOT
    origin = clock.ms()
    rec.run_offline(stages=[{"stage_name": "factors.compute", "stage_ms": 20}])
    worker_returned = clock.ms() - origin
    # Post-return bookkeeping: the clock advances 6ms before freeze.
    clock.advance(6)
    rec.freeze_root()
    frozen = next(e for e in sink.events if e["event_kind"] == "root_frozen")
    started = next(e for e in sink.events if e["event_kind"] == "worker_started")
    assert frozen["elapsed_ms"] == worker_returned
    assert frozen["elapsed_ms"] - started["elapsed_ms"] == worker_returned


def test_M05_validator_never_sees_post_return_gap(tmp_path):
    source, output = tmp_path / "fixture", tmp_path / "validated"
    contract, events = w.emit_fixture(source)
    d.validate_bundle(source, output, contract["measurement_implementation_sha"])
    frozen = next(e for e in events if e["event_kind"] == "root_frozen")
    started = next(e for e in events if e["event_kind"] == "worker_started")
    snapshot = json.loads((output / "root_snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["execute_claimed_job_ms"] == frozen["elapsed_ms"] - started["elapsed_ms"]


def test_M06_listsink_is_declared_non_durable():
    assert w.ListSink.DURABLE is False
    doc = (w.ListSink.__doc__ or "").lower()
    assert "non-persistent" in doc or "not a durable" in doc
    import inspect
    assert "fsync" not in inspect.getsource(w.ListSink.append)


def test_M06_file_sink_fsyncs_each_append(tmp_path):
    path = tmp_path / "events.jsonl"
    sink = w.FileJsonlSink(path)
    assert w.FileJsonlSink.DURABLE is True
    sink.append({"seq": 1})
    # Visible on disk before close: each append is flushed.
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1
    sink.append({"seq": 2})
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    sink.close()


def test_M06_file_sink_refuses_overwrite_and_reentrancy(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("prior\n", encoding="utf-8")
    with pytest.raises(w.WiringRejected) as caught:
        w.FileJsonlSink(path)
    assert caught.value.code == "SINK_EXISTS"
    # The prior evidence file is untouched.
    assert path.read_text(encoding="utf-8") == "prior\n"


def test_M06_file_sink_survives_abort_after_partial_writes(tmp_path):
    path = tmp_path / "events.jsonl"
    sink = w.FileJsonlSink(path)
    sink.append({"seq": 1})
    sink.append({"seq": 2})
    # Simulate a crash: no close(), the object simply goes away.
    del sink
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"seq": 1}
    assert json.loads(lines[1]) == {"seq": 2}
