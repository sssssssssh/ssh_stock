"""One-root business signature bridge, supported execution is fake-only.

No CLI, session/engine factory, environment discovery, resource lifecycle or live
assembler exists here. LiveBusinessPort is deliberately non-instantiable. Its
lazy mappings document future wiring and share the argument adapters tested with
fakes. Python injections are trusted code, not an isolation/security boundary.
Bridge events are in-memory call-boundary evidence, NOT E03 Replay bundles.
"""

from __future__ import annotations

import copy
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from scripts import biz_perf_p1_04_measure_wiring as w
from scripts.biz_perf_p1_04_e03_collectors import CollectorPorts
from scripts.business_sql_snapshot import RootCounts, build

WORKER_ID = "biz-perf-w05-isolated"
CODES = frozenset({
    "EXECUTION_NOT_AVAILABLE", "IDENTITY_REJECTED", "PORT_REJECTED",
    "ONE_ATTEMPT_CONSUMED", "CREATED_ROOT_REJECTED", "CLAIM_IDENTITY_REJECTED",
    "CLAIM_OWNER_REJECTED", "CREATE_CLAIM_FAILED", "WORKER_FAILED", "UNKNOWN_ACK",
    "POST_FAILED", "POST_IDENTITY_REJECTED", "CLOCK_REJECTED", "CLOCK_REGRESSION",
    "ELAPSED_LIMIT", "ROOT_FREEZE_FAILED", "STAGE_REJECTED", "SINK_FAILED",
})
GATES = dict(root_attempts=0, HOTSPOT="NONE_PROVEN", REAL_PG17="NOT_RUN",
             REAL_WORKER="NOT_RUN", B_GATE="NOT_APPROVED",
             TARGETED_PG17_GATE="NOT_APPROVED", AUTHORIZATION="AUTHORIZATION_PENDING",
             BUDGET="DRAFT_NOT_APPROVED")


class BridgeRejected(ValueError):
    def __init__(self, code):
        self.code = code if type(code) is str and code in CODES else "WORKER_FAILED"
        super().__init__(self.code)


def _require(condition, code):
    if not condition:
        raise BridgeRejected(code)


def _uuid(value):
    try:
        return type(value) is str and str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


@dataclass(frozen=True)
class Claim:
    root_id: uuid.UUID
    worker_id: str
    token: uuid.UUID


@dataclass(frozen=True)
class PostRead:
    """Reader assertions, not certified provenance or actual DB verification.

    Future independent reader must prove scope/source/rows/no candidate leak;
    this module has no implementation of that real reader. Missing proof fails.
    """

    root_id: uuid.UUID
    publication_job_id: uuid.UUID
    run_uuid: str
    implementation_sha: str
    publication_token: uuid.UUID
    job_status: str | None = None
    publication_state: str | None = None
    ack: str = "UNKNOWN_ACK"
    public_scope_verified: bool = False
    source_verified: bool = False
    row_counts_verified: bool = False
    no_b_leak: bool = False


class BusinessPorts(Protocol):
    def create_claim(self, emit) -> Claim: ...
    def execute_claimed_job(self, claim: Claim) -> None: ...
    def post_validate(self, claim: Claim, *, run_uuid: str,
                      implementation_sha: str) -> PostRead: ...


class RefusedPorts:
    def create_claim(self, emit):
        raise BridgeRejected("EXECUTION_NOT_AVAILABLE")

    def execute_claimed_job(self, claim):
        raise BridgeRejected("EXECUTION_NOT_AVAILABLE")

    def post_validate(self, claim, **identity):
        raise BridgeRejected("EXECUTION_NOT_AVAILABLE")


def _create_claim(db, create, claim_next, emit):
    """Native signatures; never retry, cancel, recover or supply a fake target filter.

    Production create commits/refreshes via create_queued_ingestion_job, and can
    deduplicate. claim_next commits a FIFO claim, with NO target ID argument.
    An empty dedicated queue is therefore a still-unverified external prerequisite.
    """
    job = create(db, start=date(2025, 1, 1), end=date(2025, 1, 31),
                 evaluate_signals=False, mode="manual")
    _require(type(job.id) is uuid.UUID and job.parent_job_id is None
             and getattr(job, "_queue_deduplicated", None) is False,
             "CREATED_ROOT_REJECTED")
    created = job.id
    emit("create", created)
    identity = claim_next(db, WORKER_ID)
    _require(type(identity) is uuid.UUID and identity == created, "CLAIM_IDENTITY_REJECTED")
    db.refresh(job)
    _require(job.id == created and job.parent_job_id is None
             and job.worker_id == WORKER_ID and type(job.execution_token) is uuid.UUID,
             "CLAIM_OWNER_REJECTED")
    emit("claim", identity)
    return Claim(identity, job.worker_id, job.execution_token)


def _execute(db, execute, claim):
    _require(type(claim) is Claim and type(claim.root_id) is uuid.UUID
             and type(claim.token) is uuid.UUID and claim.worker_id == WORKER_ID,
             "CLAIM_OWNER_REJECTED")
    return execute(db, claim.root_id, expected_worker=claim.worker_id,
                   expected_token=claim.token)


class LiveBusinessPort:
    """Unassembled future mappings, intentionally impossible to instantiate.

    No approved=True, URI, Session or Factory can activate this class. A future
    approved coordinator requires separately reviewed code and external hard
    termination/resource proofs. Deliberate Python object construction bypasses
    are outside this contract; these methods are not a security sandbox.
    """

    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        raise BridgeRejected("EXECUTION_NOT_AVAILABLE")

    def _session(self):
        raise BridgeRejected("EXECUTION_NOT_AVAILABLE")

    def create_claim(self, emit):
        _require(type(self) is LiveBusinessPort, "EXECUTION_NOT_AVAILABLE")
        db = self._session()  # Fixed refusal before importing any production module.
        from app.services.job_worker import claim_next_job
        from app.services.recalculation import create_recalculation_job

        return _create_claim(db, create_recalculation_job, claim_next_job, emit)

    def execute_claimed_job(self, claim):
        _require(type(self) is LiveBusinessPort, "EXECUTION_NOT_AVAILABLE")
        db = self._session()
        from app.services.job_worker import execute_claimed_job

        return _execute(db, execute_claimed_job, claim)

    def post_validate(self, claim, **identity):
        raise BridgeRejected("EXECUTION_NOT_AVAILABLE")


class RootBridge:
    """Synchronous, one-use fake lifecycle; timers do not enforce hard budgets.

    Clocks use integer monotonic ms, CPU is cumulative process ms. RootCounts
    uses existing SQLAlchemy attempt semantics. No SQL/FETCH/stage hooks are
    installed; collectors and ports are trusted test injections only. Sink owns
    persistence if any; no files are opened by the bridge.
    """

    def __init__(self, *, run_uuid, implementation_sha, ports: BusinessPorts | None = None,
                 monotonic_ms=None, cpu_ms=None, rss_reader=None, fetch_reader=None,
                 sql_counts=None, sink=None):
        _require(_uuid(run_uuid) and type(implementation_sha) is str
                 and re.fullmatch(r"[0-9a-f]{40}", implementation_sha) is not None,
                 "IDENTITY_REJECTED")
        _require(ports is None or (not isinstance(ports, (LiveBusinessPort, str, dict))
                 and all(callable(getattr(ports, n, None)) for n in (
                     "create_claim", "execute_claimed_job", "post_validate"))), "PORT_REJECTED")
        self._run, self._sha = run_uuid, implementation_sha
        self._ports = ports if ports is not None else RefusedPorts()
        self._clock = monotonic_ms or (lambda: time.monotonic_ns() // 1_000_000)
        self._cpu = cpu_ms
        self._collectors = CollectorPorts(
            cpu_reader=(lambda: self._cpu()) if cpu_ms is not None else None,
            rss_reader=rss_reader, fetch_reader=fetch_reader)
        self._sql_instrumented = sql_counts is not None
        self._counts = sql_counts if sql_counts is not None else RootCounts()
        self._sink = sink
        self._sink_failed = False
        self._seq = 0
        self._root = None
        self._snapshot = None
        self._stages = []
        self._phase = "initial"
        self._origin = self._last = None
        self._attempt_consumed = False
        self.failure_code = None

    @property
    def attempt_consumed(self):
        return self._attempt_consumed

    @property
    def snapshot(self):
        return copy.deepcopy(self._snapshot)

    def _tick(self):
        value = self._clock()
        _require(type(value) is int and 0 <= value < 2**63, "CLOCK_REJECTED")
        if self._last is not None:
            _require(value >= self._last, "CLOCK_REGRESSION")
            _require(value - self._origin <= w.MAX_ELAPSED_MS, "ELAPSED_LIMIT")
        self._last = value
        return value

    def _cpu_read(self):
        # Reuse E03's sticky validation for both cumulative CPU samples.
        return self._collectors.stats.cpu_ms()

    def _emit(self, kind, *, at=None, error_code=None):
        event = dict(seq=self._seq + 1, event_kind=kind, run_uuid=self._run,
                     implementation_sha=self._sha,
                     root_job_id=str(self._root) if self._root is not None else None,
                     utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     elapsed_ms=(at if at is not None else self._last) - self._origin)
        if error_code is not None:
            event["error_code"] = error_code
        _require(not self._sink_failed, "SINK_FAILED")
        try:
            if self._sink is not None:
                self._sink(copy.deepcopy(event))
        except BaseException:
            self._sink_failed = True
            raise BridgeRejected("SINK_FAILED") from None
        self._seq += 1

    def _boundary(self, kind, root_id):
        _require(type(root_id) is uuid.UUID, "CLAIM_IDENTITY_REJECTED")
        _require((kind, self._phase) in {("create", "create_claim"), ("claim", "create")},
                 "CLAIM_IDENTITY_REJECTED")
        _require(self._root is None or root_id == self._root, "CLAIM_IDENTITY_REJECTED")
        self._root = root_id
        self._tick()
        self._emit(kind)
        self._phase = kind

    def record_stage(self, name, *, begin_ms, end_ms):
        """Wall-only injected observations; missing SQL/FETCH are never zero-filled."""
        _require(type(name) is str and name in w.STAGES and self._phase == "worker"
                 and len(self._stages) < w.MAX_EVENTS
                 and all(type(v) is int for v in (begin_ms, end_ms))
                 and 0 <= begin_ms <= end_ms <= w.MAX_STAGE_MS, "STAGE_REJECTED")
        self._stages.append((name, begin_ms, end_ms))

    def _freeze(self, claim, worker_start, ended, cpu_start):
        self._phase = "freeze"
        _require(ended > self._origin, "ROOT_FREEZE_FAILED")
        try:
            counts = self._counts.freeze()  # Before any reader, sink, or post work.
        except Exception:
            raise BridgeRejected("ROOT_FREEZE_FAILED") from None
        cpu_end = self._cpu_read()
        cpu = (cpu_end - cpu_start if type(cpu_start) is int and type(cpu_end) is int
               and cpu_end >= cpu_start else w.UNKNOWN)
        stages = {n: dict(status=w.NOT_INSTRUMENTED, stage_inclusive_ms=w.UNKNOWN,
                          sql_execute_ms=w.UNKNOWN, fetched_rows=w.UNKNOWN,
                          fetch_observed_ms=w.UNKNOWN, sql_calls=w.UNKNOWN) for n in w.STAGES}
        for name, start, end in self._stages:
            _require(worker_start - self._origin <= start <= end <= ended - self._origin,
                     "STAGE_REJECTED")
            prior = stages[name]
            elapsed = prior["stage_inclusive_ms"] if prior["status"] == w.RECORDED else 0
            prior.update(status=w.RECORDED, stage_inclusive_ms=elapsed + end - start)
        fetch = self._collectors.fetch()
        rss = self._collectors.stats.rss_peak_bytes()
        sql = build(counts, head_sha=self._sha, root_job_id=str(claim.root_id),
                    started=self._origin / 1000, ended=ended / 1000)
        self._snapshot = dict(
            root_job_id=str(claim.root_id), run_uuid=self._run, implementation_sha=self._sha,
            root_elapsed_ms=ended - self._origin, execute_claimed_job_ms=ended - worker_start,
            process_cpu_ms=cpu, wall_per_cpu=(ended - self._origin) / cpu
            if type(cpu) is int and cpu > 0 else "UNDEFINED",
            rss_peak_bytes=rss, sql_counts=counts if self._sql_instrumented else w.UNKNOWN,
            sql_snapshot=sql if self._sql_instrumented else w.UNKNOWN,
            sql_execute_ms=w.UNKNOWN, fetch_observed_ms=fetch["observed_ms"],
            fetched_rows=fetch["rows"], stages=stages, interval_semantics="INCLUSIVE_DO_NOT_SUM",
            coverage={**self._collectors.coverage,
                      "sql": w.RECORDED if self._sql_instrumented else w.NOT_INSTRUMENTED})

    def run_offline(self):
        _require(not self._attempt_consumed and self._phase == "initial", "ONE_ATTEMPT_CONSUMED")
        self._attempt_consumed = True  # Failed create and unknown acknowledgement consume it too.
        fallback = "CREATE_CLAIM_FAILED"
        try:
            self._origin = self._tick()
            cpu_start = self._cpu_read()
            self._emit("begin", at=self._origin)
            self._phase = "create_claim"
            claim = self._ports.create_claim(self._boundary)
            _require(type(claim) is Claim and self._phase == "claim"
                     and claim.root_id == self._root, "CLAIM_IDENTITY_REJECTED")
            _require(type(claim.token) is uuid.UUID and claim.worker_id == WORKER_ID,
                     "CLAIM_OWNER_REJECTED")
            fallback = "WORKER_FAILED"
            self._phase = "worker"
            worker_start = self._tick()
            self._ports.execute_claimed_job(claim)
            ended = self._tick()  # First boundary after synchronous Worker finally returned.
            self._freeze(claim, worker_start, ended, cpu_start)
            self._emit("worker_return", at=ended)
            self._emit("root_freeze", at=ended)
            self._phase = "post"
            fallback = "POST_FAILED"
            post = self._ports.post_validate(claim, run_uuid=self._run,
                                            implementation_sha=self._sha)
            post_end = self._tick()
            _require(type(post) is PostRead, "POST_IDENTITY_REJECTED")
            _require(post.ack == "KNOWN_RETURN", "UNKNOWN_ACK")
            _require((post.root_id, post.publication_job_id, post.publication_token,
                      post.run_uuid, post.implementation_sha) ==
                     (claim.root_id, claim.root_id, claim.token, self._run, self._sha),
                     "POST_IDENTITY_REJECTED")
            valid = (post.job_status == "SUCCESS" and post.publication_state == "PUBLISHED"
                     and all(v is True for v in (post.public_scope_verified, post.source_verified,
                                                post.row_counts_verified, post.no_b_leak)))
            self._emit("post_read")
            self._phase = "done"
            return dict(GATES, evidence_kind="OFFLINE_FIXTURE", attempt_consumed=True,
                        status="FAKE_VALIDATED" if valid else "INCONCLUSIVE",
                        root=self.snapshot, post_root_validation_ms=post_end - ended)
        except BaseException as exc:
            code = exc.code if type(exc) is BridgeRejected else fallback
            self.failure_code = code
            self._phase = "failed"
            try:
                self._counts.freeze()  # Seal failure prefix; never fabricate a complete snapshot.
            except Exception:
                pass
            if self._origin is not None and not self._sink_failed:
                try:
                    self._emit("failure", error_code=code)
                except BridgeRejected:
                    pass
            raise BridgeRejected(code) from None
