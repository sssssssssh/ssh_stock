"""Offline-only measurement wiring for the P1-04 E-02 single-root protocol.

This module is a *recording and state-machine adapter*. It never creates a job,
opens a database connection, starts a worker, spawns a thread or touches the
network. Everything that could execute is injected through an executor port that
defaults to a refusal, so importing this module and instantiating the recorder
are side-effect free.

Timing and counter contract (authoritative table lives in
docs/acceptance/BIZ_PERF_P1_04_E02_CLOSEOUT.md):

* root_elapsed_ms        -- from before create/claim to the single worker
  returning with its own finally done; excludes post-root reads.
* execute_claimed_job_ms -- from before the single worker call to its return.
  A child interval of root; never added to root.
* post_root_validation_ms -- from root_frozen to verification finished. Strictly
  separated from root; post queries never enter the root SQL snapshot.
* stage_inclusive_ms     -- real stage begin to stage end. Stages may nest or
  overlap and are never summed into root.
* sql_execute_ms/calls   -- attributed execute call to return or exception.
  SQLAlchemy execute time is not PG server CPU.
* fetch_observed_ms/rows -- driver FETCH begin to return and rows received.
  May overlap SQL latency; delivered progress rows are not FETCH return rows.
* process_cpu_ms         -- process_time delta over the root window. The ratio
  is UNDEFINED when zero.
* rss_peak_bytes         -- peak over the root window, not per-stage allocation.

All durations come from an injected monotonic clock. UTC timestamps are audit
metadata only and are never used to compute durations.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path

from scripts.business_sql_snapshot import RootCounts

SCHEMA_VERSION = "biz-perf-p1-04.root.v1"
EVIDENCE_KIND = "OFFLINE_FIXTURE"
BOUNDARY = "create_claim_execute_then_independent_validation"
MEASUREMENT_VERSION = "biz-perf-p1-04.e02.measure-wiring.v1"

UNKNOWN = "UNKNOWN"
NOT_INSTRUMENTED = "NOT_INSTRUMENTED"
NOT_APPLICABLE = "NOT_APPLICABLE"
RECORDED = "RECORDED"

FAILURE_CODES = frozenset({
    "ROOT_FAILED", "ROOT_CANCELLED", "ROOT_UNKNOWN", "TIMEOUT", "OOM",
})

FLAGS = frozenset({
    "factor_input_reuse_enabled", "raw_preflight_batch_enabled",
    "factor_cpu_optimization_enabled", "ab_merge_read_enabled", "perf_diagnostics_enabled",
})

STAGES = frozenset({
    "recalculation.raw_prerequisites", "factors.stock_daily", "factors.adj_factor",
    "factors.stock_basic", "factors.trade_status", "factors.index_daily", "factors.compute",
    "candidate_lookup_batch", "candidate_store_batch", "publication.verify",
    "publish_inclusive",
})

MAX_EVENTS = 4096
MAX_ELAPSED_MS = 1_200_000
MAX_STAGE_MS = 1_200_000

# Fixed stop codes. Only these strings may leave the module.
_CODE = re.compile(r"[A-Z][A-Z0-9_]{1,60}")


class WiringRejected(Exception):
    """Fixed-code rejection; the message is always a whitelisted code token."""

    def __init__(self, code):
        if not isinstance(code, str) or _CODE.fullmatch(code) is None:
            code = "WIRING_REJECTED"
        super().__init__(code)
        self.code = code


def _require(condition, code):
    if not condition:
        raise WiringRejected(code)


def _duration(value):
    return type(value) is int and 0 <= value <= MAX_ELAPSED_MS


def _uuid(value):
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def _hex64(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


class MonotonicClock:
    """Injected monotonic clock; the only source of duration arithmetic."""

    def __init__(self, source=None):
        self._source = source

    def ms(self):
        if self._source is None:
            import time

            return time.monotonic_ns() // 1_000_000
        return self._source()


class ProcessStats:
    """Injected process CPU and peak RSS reader."""

    def __init__(self, cpu_reader=None, rss_reader=None):
        self._cpu = cpu_reader
        self._rss = rss_reader

    def cpu_ms(self):
        if self._cpu is None:
            return UNKNOWN
        return self._cpu()

    def rss_peak_bytes(self):
        if self._rss is None:
            return UNKNOWN
        return self._rss()


class RefusedExecutor:
    """Default executor port: refuses every call.

    The offline adapter must never gain a way to start real work by accident, so
    the default implementation refuses rather than no-ops.
    """

    def create_and_claim(self, identity):  # pragma: no cover - refusal path
        raise WiringRejected("EXECUTION_NOT_AVAILABLE")

    def execute_claimed_job(self, root_job_id):  # pragma: no cover - refusal path
        raise WiringRejected("EXECUTION_NOT_AVAILABLE")


class OfflineRootRecorder:
    """Records the P1-04 single-root lifecycle without performing it.

    The recorder owns the event sequence, the state machine and root SQL
    counting. Execution is delegated to the injected `executor`, which must be
    an offline double in every supported use of this module.
    """

    def __init__(self, *, contract, clock, stats, sink, root_id_factory=None,
                 utc_factory=None, executor=None):
        _require(isinstance(contract, dict), "CONTRACT_REJECTED")
        _require(contract.get("schema_version") == SCHEMA_VERSION, "CONTRACT_REJECTED")
        _require(contract.get("evidence_kind") == EVIDENCE_KIND, "CONTRACT_REJECTED")
        _require(_uuid(contract.get("run_uuid")), "CONTRACT_REJECTED")
        _require(_uuid(contract.get("expected_instance", {}).get("marker"))
                 if isinstance(contract.get("expected_instance"), dict) else False,
                 "CONTRACT_REJECTED")
        _require(all(flag is False for flag in contract.get("flags", {}).values())
                 and set(contract.get("flags", {})) == FLAGS, "FLAG_MISMATCH")
        self._contract = dict(contract)
        self._clock = clock
        self._stats = stats
        self._sink = sink
        self._root_id_factory = root_id_factory or (lambda: str(uuid.uuid4()))
        self._utc_factory = utc_factory
        self._executor = executor or RefusedExecutor()

        self._seq = 0
        self._phase = "INITIAL"
        self._root_id = None
        self._run_uuid = contract["run_uuid"]
        self._origin = None
        self._last_elapsed = 0
        self._last_utc = None
        self._frozen = False
        self._counts = RootCounts()
        self._cpu_start = None
        self._rss_peak = 0
        self._fetch_ms = 0
        self._fetched_rows = 0
        self._root_started_ms = 0
        self._worker_started_ms = 0
        self._root_frozen_ms = None
        self._stage_ends = []

    # ---------------------------------------------------------------- helpers
    def _now_ms(self):
        value = self._clock.ms()
        _require(type(value) is int and value >= 0, "CLOCK_REJECTED")
        return value

    def _stamp(self):
        if self._utc_factory is None:
            from datetime import UTC, datetime

            return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return self._utc_factory()

    def _elapsed(self):
        value = self._now_ms() - self._origin
        _require(0 <= value <= MAX_ELAPSED_MS, "ELAPSED_LIMIT")
        _require(value >= self._last_elapsed, "CLOCK_REGRESSION")
        return value

    def _emit(self, kind, **fields):
        _require(self._root_id is not None or kind == "root_started", "ROOT_NOT_OPENED")
        event = {
            "seq": self._seq + 1,
            "event_kind": kind,
            "run_uuid": self._run_uuid,
            "root_job_id": self._root_id,
            "utc": self._stamp(),
            "elapsed_ms": self._elapsed(),
            **fields,
        }
        _require(self._seq < MAX_EVENTS, "EVENT_LIMIT")
        self._sink.append(event)  # persisted before anything derived
        self._seq = event["seq"]
        self._last_elapsed = event["elapsed_ms"]
        self._last_utc = event["utc"]
        self._phase = kind
        return event

    def _expect(self, *kinds):
        _require(self._phase in kinds, "STATE_TRANSITION_REJECTED")

    # ------------------------------------------------------------- lifecycle
    def begin_root(self, preflight_sha256):
        """Open the single root. Second call on the same recorder is refused."""
        _require(self._phase == "INITIAL", "ONE_ATTEMPT_CONSUMED")
        _require(_hex64(preflight_sha256), "IDENTITY_REJECTED")
        self._origin = self._now_ms()
        if self._root_id is None:
            self._root_id = self._root_id_factory()
        _require(_uuid(self._root_id), "IDENTITY_REJECTED")
        self._cpu_start = self._stats.cpu_ms()
        event = self._emit("root_started", preflight_sha256=preflight_sha256)
        return event

    def begin_worker(self):
        self._expect("root_started")
        event = self._emit("worker_started")
        self._worker_started_ms = event["elapsed_ms"]
        return event

    def record_stage(self, stage_name, *, begin_ms, end_ms, sql_execute_ms=0,
                     sql_calls=0, fetch_observed_ms=0, fetched_rows=0,
                     instrumented=True):
        """Record one stage interval.

        `begin_ms` / `end_ms` are offsets from the recorder origin (the same
        clock as `elapsed_ms`). Stages may overlap; they never sum to root.
        """
        self._expect("worker_started", "stage")
        _require(stage_name in STAGES, "STAGE_REJECTED")
        _require(_duration(begin_ms) and _duration(end_ms) and end_ms >= begin_ms,
                 "STAGE_INTERVAL_REJECTED")
        _require(begin_ms >= self._worker_started_ms, "STAGE_INTERVAL_REJECTED")
        _require(begin_ms >= self._last_elapsed, "CLOCK_REGRESSION")

        if instrumented:
            for value in (sql_execute_ms, sql_calls, fetch_observed_ms, fetched_rows):
                _require(type(value) is int and value >= 0, "STAGE_METRIC_REJECTED")
            coverage = RECORDED
        else:
            _require(all(v == UNKNOWN for v in (
                sql_execute_ms, sql_calls, fetch_observed_ms, fetched_rows)),
                "STAGE_METRIC_REJECTED")
            coverage = NOT_INSTRUMENTED

        event = self._emit(
            "stage", stage_name=stage_name, started_ms=begin_ms,
            instrumented=bool(instrumented), coverage_reason=coverage,
            sql_execute_ms=sql_execute_ms, sql_calls=sql_calls,
            fetch_observed_ms=fetch_observed_ms, fetched_rows=fetched_rows,
        )
        self._stage_ends.append(end_ms)
        return event

    def freeze_root(self, *, cpu_ms=None, rss_peak_bytes=None):
        """Freeze root counters and emit root_frozen.

        Root SQL counts are frozen here; any later counter attempt is refused by
        RootCounts itself. Post-root reads must never reach this counter.
        """
        self._expect("worker_started", "stage")
        _require(not self._frozen, "ALREADY_FROZEN")
        counts = self._counts.freeze()
        self._frozen = True
        cpu = self._stats.cpu_ms() if cpu_ms is None else cpu_ms
        rss = self._stats.rss_peak_bytes() if rss_peak_bytes is None else rss_peak_bytes
        _require(cpu == UNKNOWN or (type(cpu) is int and cpu >= 0), "METRIC_REJECTED")
        _require(rss == UNKNOWN or (type(rss) is int and rss >= 0), "METRIC_REJECTED")
        event = self._emit(
            "root_frozen", sql_counts=counts, process_cpu_ms=cpu,
            rss_peak_bytes=rss, fetch_observed_ms=self._fetch_ms,
            fetched_rows=self._fetched_rows,
        )
        _require(event["elapsed_ms"] > self._root_started_ms, "ROOT_INTERVAL_REJECTED")
        self._root_frozen_ms = event["elapsed_ms"]
        return event

    def record_post_validation(self, *, job_status, publication_state, quality_verified,
                               no_candidate_leak, atomic_publication_verified,
                               tables_sha256, source_mismatches=UNKNOWN):
        """Post-root verification. Deliberately outside the frozen root window."""
        self._expect("root_frozen")
        _require(job_status in {"SUCCESS", "FAILED", "CANCELLED", "UNKNOWN"},
                 "POST_REJECTED")
        _require(publication_state in {"PUBLISHED", "PREPARING", "ABORTED", "UNKNOWN"},
                 "POST_REJECTED")
        _require(all(type(v) is bool for v in (
            quality_verified, no_candidate_leak, atomic_publication_verified)),
            "POST_REJECTED")
        _require(isinstance(tables_sha256, dict)
                 and all(type(k) is str and _hex64(v) for k, v in tables_sha256.items()),
                 "POST_REJECTED")
        _require(source_mismatches == UNKNOWN
                 or (type(source_mismatches) is int and source_mismatches >= 0),
                 "POST_REJECTED")
        return self._emit(
            "post_root_validation", job_status=job_status,
            publication_state=publication_state, quality_verified=quality_verified,
            no_candidate_leak=no_candidate_leak,
            atomic_publication_verified=atomic_publication_verified,
            tables_sha256=tables_sha256, source_mismatches=source_mismatches,
        )

    def record_cleanup(self, *, cleanup_status, instance):
        self._expect("post_root_validation")
        _require(cleanup_status in {"COMPLETE", "BLOCKED"}, "CLEANUP_REJECTED")
        _require(isinstance(instance, dict), "CLEANUP_REJECTED")
        # The cleanup identity must be the full reviewed instance shape so a
        # reviewer can prove the cleanup targeted the same instance as the root.
        _require(set(instance) == set(self._contract["expected_instance"]),
                 "CLEANUP_REJECTED")
        return self._emit("cleanup", cleanup_status=cleanup_status, instance=instance)

    def fail(self, failure_code):
        """Terminal failure on any non-terminal phase."""
        _require(self._phase != "cleanup" and self._phase != "failure",
                 "STATE_TRANSITION_REJECTED")
        _require(failure_code in FAILURE_CODES, "FAILURE_CODE_REJECTED")
        return self._emit("failure", failure_code=failure_code)

    # ------------------------------------------------------------ injection
    def run_offline(self, *, stages=()):
        """Drive one fully simulated root through the injected executor port.

        Real execution is impossible here: the default executor refuses, and
        every supported caller injects an offline double.
        """
        preflight = self._contract.get("preflight_sha256")
        _require(_hex64(preflight), "IDENTITY_REJECTED")
        self.begin_root(preflight)
        root = self._executor.create_and_claim(self._contract)
        _require(root == self._root_id, "ROOT_IDENTITY_REJECTED")
        self.begin_worker()
        cursor = self._worker_started_ms
        for stage in stages:
            begin = cursor
            end = begin + int(stage.get("stage_ms", 0))
            self._advance_to(end)
            self.record_stage(
                stage["stage_name"], begin_ms=begin, end_ms=end,
                sql_execute_ms=stage.get("sql_execute_ms", 0),
                sql_calls=stage.get("sql_calls", 0),
                fetch_observed_ms=stage.get("fetch_observed_ms", 0),
                fetched_rows=stage.get("fetched_rows", 0),
            )
            cursor = end
        self._executor.execute_claimed_job(root)
        return self

    def _advance_to(self, target_ms):
        """Advance the clock so the next emitted event reads `target_ms`.

        Used by the fixture driver only; it never fabricates a duration because
        the value still comes from the injected clock.
        """
        if hasattr(self._clock, "advance_to"):
            self._clock.advance_to(target_ms)

    # -------------------------------------------------------------- accessors
    def root_id_factory(self):
        """Return the single root id this recorder will use."""
        if self._root_id is None:
            self._root_id = self._root_id_factory()
        return self._root_id

    def frozen_after_ms(self):
        """Milliseconds the offline driver should advance before freezing."""
        return 6

    @property
    def phase(self):
        return self._phase

    @property
    def seq(self):
        return self._seq

    @property
    def root_id(self):
        return self._root_id

    def counts(self):
        """Root SQL counter handle (freeze is performed by freeze_root)."""
        return self._counts


# ------------------------------------------------------------------ fixtures


class ListSink:
    """In-memory append-only sink used by the offline contract tests."""

    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append(dict(event))

    def write_jsonl(self, path, *, fsync=True):
        raw = "".join(
            json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
            for event in self.events
        ).encode()
        with open(path, "wb") as stream:
            stream.write(raw)
            stream.flush()
            if fsync:
                os.fsync(stream.fileno())
        return hashlib.sha256(raw).hexdigest()


def build_preflight(*, preflight_sha256=None, run_uuid=None, dataset="0" * 64,
                    strategy="1" * 64, env_digest="2" * 64, budget="3" * 64,
                    implementation_sha="4" * 40):
    """Assemble a schema-valid OFFLINE_FIXTURE preflight contract.

    Values are fixed/derived only: no SQL, no connection string, no environment
    dump. The design baseline and business-source digest are the reviewed
    constants enforced by scripts.biz_perf_p1_04_diagnostic.
    """
    from scripts import biz_perf_p1_04_diagnostic as diagnostic

    run_uuid = run_uuid or str(uuid.uuid4())
    instance = {
        "scope": "ISOLATED_SYNTHETIC",
        "host": "127.0.0.1",
        "database": f"v14_{uuid.uuid4().hex}_test",
        "pg_major": 17,
        "marker": str(uuid.uuid4()),
        "system_identifier": "7400000000000000001",
        "pgdata_sha256": "5" * 64,
        "network_sha256": "6" * 64,
        "owner_sha256": "7" * 64,
    }
    contract = {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "design_baseline_sha": diagnostic.BASELINE,
        "measurement_implementation_sha": implementation_sha,
        "business_source_sha256": diagnostic.BUSINESS_SOURCE_SHA256,
        "worktree": "CLEAN",
        "run_uuid": run_uuid,
        "run_attempt": 1,
        "stocks": 8,
        "months": 1,
        "dataset_sha256": dataset,
        "strategy_sha256": strategy,
        "env_identity_digest": env_digest,
        "resource_budget_id": budget,
        "flags": dict.fromkeys(sorted(FLAGS), False),
        "expected_instance": instance,
        "observed_instance": dict(instance),
    }
    contract["preflight_sha256"] = preflight_sha256 or diagnostic.preflight_digest(
        contract)
    return contract


class FakeClock:
    """Controllable monotonic clock for offline fixtures (milliseconds)."""

    def __init__(self, start=1000):
        self._value = start
        self._start = start

    def ms(self):
        return self._value

    def advance(self, delta):
        self._value += int(delta)

    def advance_to(self, absolute_offset_ms):
        target = self._start + int(absolute_offset_ms)
        if target > self._value:
            self._value = target


class OfflineExecutor:
    """Offline executor double. Never touches a database or a worker."""

    def __init__(self, *, calls=None, spawn_ms=5, run_ms=40):
        self.calls = calls if calls is not None else []
        self.spawn_ms = spawn_ms
        self.run_ms = run_ms

    def create_and_claim(self, identity):  # noqa: ARG002 - offline double
        self.calls.append("create_claim")
        return self.current_root_id

    def execute_claimed_job(self, root_job_id):
        self.calls.append("execute_claimed_job")
        return {"root_job_id": root_job_id, "status": "SUCCESS"}


DEFAULT_STAGES = (
    {"stage_name": "factors.compute", "stage_ms": 20, "sql_execute_ms": 3,
     "sql_calls": 2, "fetch_observed_ms": 2, "fetched_rows": 10},
)


def emit_fixture(directory, *, contract=None, stages=None, clock=None):
    """Write preflight.json + events.jsonl compatible with validate_bundle.

    Returns (contract, events). The caller passes the two directories to
    `scripts.biz_perf_p1_04_diagnostic.validate_bundle` for end-to-end checking.
    A non-empty default stage set is required because the reviewed validator
    rejects evidence with no instrumented stage (EVIDENCE_INCOMPLETE).
    """
    directory = Path(directory)
    contract = contract or build_preflight()
    stages = DEFAULT_STAGES if stages is None else stages
    clock = clock or FakeClock()
    sink = ListSink()
    calls = []
    executor = OfflineExecutor(calls=calls)

    recorder = OfflineRootRecorder(
        contract=contract, clock=clock,
        stats=ProcessStats(cpu_reader=lambda: 10, rss_reader=lambda: 1024), sink=sink,
        executor=executor,
    )
    executor.current_root_id = recorder.root_id_factory()
    recorder.run_offline(stages=stages)

    # Root SQL attempts are counted before the freeze; the summary requires a
    # non-zero root total plus at least one instrumented stage, otherwise the
    # evidence is INCOMPLETE by contract.
    counts = recorder.counts()
    for operation, repeat in (("SELECT", 9), ("WITH", 2)):
        for _ in range(repeat):
            counts.begin(operation)
            counts.end()

    clock.advance(recorder.frozen_after_ms())
    recorder.freeze_root()

    clock.advance(7)  # independent post-root read window
    recorder.record_post_validation(
        job_status="SUCCESS", publication_state="PUBLISHED", quality_verified=True,
        no_candidate_leak=True, atomic_publication_verified=True,
        tables_sha256={name: "9" * 64 for name in sorted(TRACKED_TABLES)},
        source_mismatches=0,
    )
    clock.advance(3)
    recorder.record_cleanup(cleanup_status="COMPLETE",
                            instance=dict(contract["expected_instance"]))
    directory.mkdir(parents=True, exist_ok=True)
    # preflight.json must contain EXACTLY the reviewed field set; the digest is
    # carried in the root_started event, not stored alongside the contract.
    on_disk = {k: v for k, v in contract.items() if k != "preflight_sha256"}
    (directory / "preflight.json").write_text(
        json.dumps(on_disk, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8")
    sink.write_jsonl(directory / "events.jsonl")
    executor.calls.clear()
    return contract, sink.events


# Tables tracked by the post-root validation event.
TRACKED_TABLES = frozenset({
    "stock_trade_status_daily", "stock_factor_daily", "market_daily",
    "sector_factor_daily", "theme_factor_daily", "stock_state_daily",
    "stock_opportunity_daily", "strategy_signal", "signal_forward_eval",
    "data_quality_daily",
})
