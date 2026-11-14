"""Bounded offline evidence and one-shot mock lifecycle; no cleanup executor.

Only FileJsonlSink writes local fixture events. Original diagnostic Replay is
applied before each append; no arbitrary log/error text crosses this boundary.
An inspectable prefix is not a completed bundle. validate_bundle remains the
only completion validator, with its OFFLINE_FIXTURE classification unchanged.
"""

import copy
import uuid

from scripts import biz_perf_p1_04_diagnostic as d
from scripts import biz_perf_p1_04_measure_wiring as w
from scripts.biz_perf_p1_04_e03_guard import GATES, RefusedExecutor, validate_plan

FAILURES = frozenset({
    "CREATE_FAILED", "CLAIM_FAILED", "UNKNOWN_ACK", "WORKER_FAILED", "TIMEOUT",
    "BUDGET_EXCEEDED", "COLLECTOR_FAILED", "SINK_FAILED", "EXECUTION_NOT_AVAILABLE",
    "EVIDENCE_INCOMPLETE", "ONE_ATTEMPT_CONSUMED",
})


class OfflineFailure(ValueError):
    def __init__(self, code):
        self.code = code if type(code) is str and code in FAILURES else "WORKER_FAILED"
        super().__init__(self.code)


class BoundedEvidenceSink:
    """Validator-backed, bounded FileJsonlSink. Failure poisons further writes.

    Replay state advances only after the entire line has been fsynced. This does
    not claim crash durability of directory entries on Windows or hostile paths.
    Ancestors must be trusted and stable, as required by FileJsonlSink.
    """

    def __init__(self, path, contract):
        d.preflight(contract, contract["measurement_implementation_sha"])
        self._replay = d.Replay(copy.deepcopy(contract))
        self._sink = w.FileJsonlSink(path)
        self._bytes = 0
        self._failed = False

    def append(self, event):
        if self._failed:
            raise w.SinkRejected("SINK_FAILED")
        try:
            raw = d.encode(event)
            if len(raw) > d.MAX_LINE_BYTES or self._bytes + len(raw) > d.MAX_RAW_BYTES:
                raise ValueError
            candidate = copy.deepcopy(self._replay)
            candidate.accept(event)
            self._sink.append(event)
            self._replay = candidate
            self._bytes += len(raw)
        except Exception:
            self._failed = True
            raise w.SinkRejected("SINK_FAILED") from None

    @property
    def count(self):
        return self._sink.count

    def close(self):
        self._sink.close()


class _CheckedExecutor:
    def __init__(self, port, root_id):
        self.port, self.root_id = port, root_id
        self.failure = None

    def _call(self, name, value, fallback):
        try:
            result = getattr(self.port, name)(value)
            if name == "create_and_claim":
                if result != self.root_id:
                    raise OfflineFailure("UNKNOWN_ACK")
            elif (type(result) is not dict or set(result) != {"root_job_id", "status"}
                  or result["root_job_id"] != self.root_id or result["status"] != "SUCCESS"):
                raise OfflineFailure("UNKNOWN_ACK")
            return result
        except Exception as exc:
            code = getattr(exc, "code", fallback)
            self.failure = code if type(code) is str and code in FAILURES else fallback
            raise OfflineFailure(self.failure) from None

    def create_and_claim(self, identity):
        return self._call("create_and_claim", identity, "CREATE_FAILED")

    def execute_claimed_job(self, root_job_id):
        return self._call("execute_claimed_job", root_job_id, "WORKER_FAILED")


class MockLifecycle:
    """One-shot offline simulation around R2's run/capture/freeze path.

    Injected Python ports are trusted test code, not a security sandbox. There
    is no resource creator, cleanup/drop method, retry or production adapter.
    This class does not accept an execution token or issue one. No proof from
    OfflineGuard can make execute available.
    """

    def __init__(self, *, plan, expected_sha, clock, collectors, sink, executor=None,
                 root_id_factory=None):
        validate_plan(plan, expected_sha)
        self.contract = copy.deepcopy(plan["preflight"])
        self.contract["preflight_sha256"] = d.preflight_digest(self.contract)
        root_id = (root_id_factory or (lambda: str(uuid.uuid4())))()
        if not d.uuid_value(root_id):
            raise OfflineFailure("EVIDENCE_INCOMPLETE")
        self._executor = _CheckedExecutor(executor or RefusedExecutor(),
                                          root_id)
        # Use R2's public injection instead of modifying its private state.
        self.recorder = w.OfflineRootRecorder(
            contract=self.contract, clock=clock, stats=collectors.stats, sink=sink,
            fetch_reader=collectors.fetch, executor=self._executor,
            root_id_factory=lambda: self._executor.root_id,
        )
        self._consumed = False
        self.failure_code = None

    def run_offline(self, *, stages=()):
        if self._consumed:
            raise OfflineFailure("ONE_ATTEMPT_CONSUMED")
        self._consumed = True  # Includes failed create/claim and unknown ACK.
        try:
            self.recorder.run_offline(stages=stages)
            self.recorder.freeze_root()
        except Exception as exc:
            code = self._executor.failure
            if code is None:
                code = "SINK_FAILED" if isinstance(exc, w.SinkRejected) else "COLLECTOR_FAILED"
            self.failure_code = code
            # Failed create/claim has no Worker-return boundary. Seal SQL and
            # preserve a schema-valid terminal failure prefix where possible.
            if self.recorder.phase not in {"failure", "cleanup"}:
                try:
                    self.recorder.counts().freeze()
                except ValueError:
                    pass  # Already frozen; no retry or successful snapshot follows.
                try:
                    original_code = {
                        "UNKNOWN_ACK": "ROOT_UNKNOWN", "TIMEOUT": "TIMEOUT",
                        "BUDGET_EXCEEDED": "TIMEOUT",
                    }.get(code, "ROOT_FAILED")
                    self.recorder.fail(original_code)
                except Exception:
                    self.failure_code = "SINK_FAILED"
            raise OfflineFailure(self.failure_code) from None
        return dict(status="OFFLINE_ROOT_FROZEN_ONLY", **GATES)
