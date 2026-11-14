"""Offline resource decisions, sealed mock lifecycle and independent read receipts.

No real executor/cleanup adapter is accepted. E03 owns raw event collection and
the frozen diagnostic validator owns complete bundle semantics. A review receipt
records inspection scope, never execution authority, completion or live integrity.
"""

from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
from typing import Protocol

from scripts import biz_perf_p1_04_diagnostic as d
from scripts import biz_perf_p1_04_e03_guard as g
from scripts import biz_perf_p1_04_measure_wiring as w
from scripts.biz_perf_p1_04_e03_collectors import CollectorPorts
from scripts.biz_perf_p1_04_e03_evidence import BoundedEvidenceSink, MockLifecycle, OfflineFailure
from scripts.biz_perf_p1_04_e04_journal import OfflineLeaseJournal
from scripts.biz_perf_p1_04_e04_packet import (
    GATES,
    SCHEMA,
    Refused,
    RefusedVerifier,
    decode,
    digest,
    execute,
    fields,
    load_bundle,
    require,
    seal,
)


class ResourceReader(Protocol):
    def read(self) -> dict: ...


class RefusedResourceReader:
    def read(self):
        raise Refused("ATTESTATION_REFUSED")


def check_budget(limits, usage, *, phase):
    """Strict fixed DRAFT limits; milli-CPU allocation is not CPU time."""
    try:
        fields(limits, {*g.LIMITS, "cpu_millis"}, "BUDGET_REJECTED")
        require(all(type(limits[key]) is int and limits[key] == value
                    for key, value in g.LIMITS.items()), "BUDGET_REJECTED")
        require(type(limits["cpu_millis"]) is int and 1 <= limits["cpu_millis"] <= 64_000,
                "BUDGET_REJECTED")
        fields(usage, {"cpu_millis", "worker_bytes", "pg_bytes", "volume_bytes",
                       "output_bytes", "elapsed_ms"}, "BUDGET_REJECTED")
        require(all(d.uint(value) for value in usage.values()), "BUDGET_REJECTED")
        g.check_offline_usage(limits, usage, phase=phase)
        return "OFFLINE_BUDGET_CHECK_ONLY"
    except (g.Refused, Refused, ValueError, TypeError, KeyError, OverflowError):
        raise Refused("BUDGET_REJECTED") from None


def resource_decision(expected, observed, *, ack, ownership, limits, usage, phase):
    """Matching offline facts still cannot authorize cleanup or produce a permit."""
    try:
        if ack != "KNOWN_MOCK_RETURN" or ownership != "OFFLINE_KNOWN":
            return "MANUAL_REVIEW_REQUIRED" if ack != "KNOWN_MOCK_RETURN" else "CLEANUP_BLOCKED"
        check_budget(limits, usage, phase=phase)
        require(g.cleanup_status(expected, observed) == "OFFLINE_OWNERSHIP_MATCH_ONLY",
                "CLEANUP_BLOCKED")
        require(expected["resources"]["limits"] == limits, "CLEANUP_BLOCKED")
        return "OFFLINE_OWNERSHIP_MATCH_ONLY"
    except (Refused, g.Refused, ValueError, TypeError, KeyError):
        return "CLEANUP_BLOCKED"


def inspect_resources(expected, *, reader=None, **checkpoint):
    try:
        observed = (reader or RefusedResourceReader()).read()
        return resource_decision(copy.deepcopy(expected), observed, **checkpoint)
    except Exception:
        return "CLEANUP_BLOCKED"


class OfflineMockExecutor:
    """Closed test double. Fixed fake methods; no callback to real execution."""

    def __init__(self, clock, root_uuid, *, fault=None, at="create"):
        require(type(clock) is w.FakeClock and d.uuid_value(root_uuid), "MOCK_ONLY")
        require(fault is None or (type(fault) is str and fault in {
            "CREATE_FAILED", "CLAIM_FAILED", "UNKNOWN_ACK", "WORKER_FAILED", "TIMEOUT",
            "BUDGET_EXCEEDED"}),
                "MOCK_ONLY")
        require(type(at) is str and at in {"create", "worker"}, "MOCK_ONLY")
        self.clock, self.root_uuid, self.fault, self.at = clock, root_uuid, fault, at
        self.calls = []
        self.counts = None

    def create_and_claim(self, _identity):
        self.calls.append("mock_create_claim")
        self.clock.advance(5)
        if self.fault and self.at == "create":
            raise OfflineFailure(self.fault)
        return self.root_uuid

    def execute_claimed_job(self, _root):
        self.calls.append("mock_worker")
        self.clock.advance(20)
        if self.fault:
            raise OfflineFailure(self.fault)
        self.counts.begin("SELECT")
        self.counts.end()
        return dict(root_job_id=self.root_uuid, status="SUCCESS")


def run_mock(bundle, journal, output, sha, run_uuid, *, verifier=None, executor=None,
             complete_evidence=False):
    """One LOCAL mock call, durable uncertainty before create/claim. No retries.

    Exact built-in mock type only; arbitrary Python injection belongs to trusted
    tests, not a security boundary against monkeypatching or hostile code.
    """
    require(type(executor) is OfflineMockExecutor and type(journal) is OfflineLeaseJournal,
            "MOCK_ONLY")
    require(type(complete_evidence) is bool, "MOCK_ONLY")
    proof = load_bundle(bundle, sha, run_uuid, verifier=verifier or RefusedVerifier())
    try:
        packet = decode(d.read_file(d.directory(Path(bundle)) / "admission_packet.json", 64 * 1024))
    except (d.Rejected, OSError):
        raise Refused("PATH_REJECTED") from None
    require(packet["canonical_sha256"] == proof["packet_sha256"], "DIGEST_MISMATCH")
    # Require the exact byte digests accepted by the independent loader too.
    require(hashlib.sha256(d.encode(packet)).hexdigest()
            == proof["files"]["admission_packet.json"], "DIGEST_MISMATCH")
    plan = copy.deepcopy(packet["plan"])
    lease = journal.reserve(sha, run_uuid, proof["packet_sha256"], proof["manifest_sha256"])
    sink = None
    start = executor.clock.ms()
    try:
        # Filesystem-only fixture output, new directory, never a resource instance.
        output = Path(output)
        parent = d.directory(output.parent)
        require(output.name not in {"", ".", ".."}, "PATH_REJECTED")
        output = parent / output.name
        output.mkdir(mode=0o700)
        d.publish(output / "preflight.json", plan["preflight"])
        sink = BoundedEvidenceSink(output / "events.jsonl", plan["preflight"])
        session = MockLifecycle(plan=plan, expected_sha=sha, clock=executor.clock,
                                collectors=CollectorPorts(), sink=sink, executor=executor,
                                root_id_factory=lambda: executor.root_uuid)
        executor.counts = session.recorder.counts()
        # RESERVED alone can never be interpreted as permission to repeat a call.
        lease.transition("UNKNOWN_ACK", code="UNKNOWN_ACK", elapsed_ms=0)
        session.run_offline(stages=w.DEFAULT_STAGES)
        usage = dict.fromkeys(("cpu_millis", "worker_bytes", "pg_bytes", "volume_bytes",
                               "output_bytes", "elapsed_ms"), 0)
        usage["elapsed_ms"] = executor.clock.ms() - start
        check_budget(plan["expected"]["resources"]["limits"], usage, phase="root")
        if complete_evidence:
            executor.clock.advance(1)
            session.recorder.record_post_validation(
                job_status="SUCCESS", publication_state="PUBLISHED", quality_verified=True,
                no_candidate_leak=True, atomic_publication_verified=True,
                source_mismatches=0, tables_sha256=dict.fromkeys(d.TABLES, "9" * 64))
            session.recorder.record_cleanup(cleanup_status="COMPLETE",
                                           instance=plan["preflight"]["expected_instance"])
        sink.close()
        files = {name: hashlib.sha256(d.read_file(output / name, d.MAX_RAW_BYTES)).hexdigest()
                 for name in ("preflight.json", "events.jsonl")}
        require(load_bundle(bundle, sha, run_uuid, verifier=verifier) == proof, "PATH_REJECTED")
        lease.transition("MOCK_RETURNED", code="MOCK_ONLY", elapsed_ms=executor.clock.ms() - start,
                         evidence_sha256=digest(files))
        return dict(status="OFFLINE_MOCK_RETURN_ONLY", **GATES)
    except Exception as exc:
        unknown = isinstance(exc, OfflineFailure) and exc.code == "UNKNOWN_ACK"
        try:
            lease.transition("MANUAL_REVIEW_REQUIRED" if unknown else "BLOCKED",
                             code="UNKNOWN_ACK" if unknown else "MOCK_FAILED",
                             elapsed_ms=executor.clock.ms() - start)
        except Refused:
            pass  # Persistent reservation/uncertainty remains; never a retry.
        raise Refused("UNKNOWN_ACK" if unknown else "MOCK_FAILED") from None
    finally:
        if sink is not None:
            try:
                sink.close()
            except Exception:
                raise Refused("EVIDENCE_INCOMPLETE") from None


def review_receipt(bundle, journal, raw_dir, sha, run_uuid, *, elapsed_ms=0):
    """Independent read/replay; prefixes are reviewable, not completed bundles.

    Requires a MOCK_RETURNED journal and a complete original Replay to report
    OFFLINE_EVIDENCE_REVIEWED_ONLY. Any missing evidence yields an error receipt.
    No summary/integrity artifacts are synthesized here.
    """
    require(type(journal) is OfflineLeaseJournal, "JOURNAL_REJECTED")
    proof = load_bundle(bundle, sha, run_uuid)
    report = journal.inspect(sha, run_uuid, proof["packet_sha256"], proof["manifest_sha256"],
                             elapsed_ms=elapsed_ms)
    raw_files, error, review_state = {}, "EVIDENCE_INCOMPLETE", "MANUAL_REVIEW_REQUIRED"
    try:
        source = d.directory(Path(raw_dir))
        before = source.stat()
        inodes = {name: (source / name).lstat() for name in ("preflight.json", "events.jsonl")}
        require({p.name for p in source.iterdir()} == {"preflight.json", "events.jsonl"},
                "PATH_REJECTED")
        contract_raw = d.read_file(source / "preflight.json", d.MAX_LINE_BYTES)
        raw = d.read_file(source / "events.jsonl", d.MAX_RAW_BYTES)
        contract = d.preflight(d.decode(contract_raw), sha)
        packet = decode(d.read_file(d.directory(Path(bundle)) / "admission_packet.json", 64 * 1024))
        require(contract == packet["plan"]["preflight"] and contract["run_uuid"] == run_uuid,
                "IDENTITY_MISMATCH")
        require(packet["canonical_sha256"] == proof["packet_sha256"], "DIGEST_MISMATCH")
        replay = d.Replay(contract)
        for line in raw.splitlines(keepends=True):
            require(len(line) <= d.MAX_LINE_BYTES and line.endswith(b"\n"), "EVIDENCE_INCOMPLETE")
            replay.accept(d.decode(line))
        # Original Replay.summary enforces root/post/cleanup success and completeness.
        replay.summary()
        d.directory(source)
        require(os.path.samestat(before, source.stat())
                and all(os.path.samestat(info, (source / name).lstat())
                        for name, info in inodes.items())
                and d.read_file(source / "preflight.json", d.MAX_LINE_BYTES) == contract_raw
                and d.read_file(source / "events.jsonl", d.MAX_RAW_BYTES) == raw,
                "PATH_REJECTED")
        require(report["decision"] == "OFFLINE_RETURN_RECORDED_ONLY", "EVIDENCE_INCOMPLETE")
        raw_files = {"preflight.json": hashlib.sha256(contract_raw).hexdigest(),
                     "events.jsonl": hashlib.sha256(raw).hexdigest()}
        require(report["transitions"][-1]["evidence_sha256"] == digest(raw_files),
                "DIGEST_MISMATCH")
        review_state, error = "OFFLINE_EVIDENCE_REVIEWED_ONLY", None
    except (Refused, d.Rejected, OSError, ValueError, TypeError, KeyError):
        pass
    require(load_bundle(bundle, sha, run_uuid) == proof, "PATH_REJECTED")
    latest = journal.inspect(sha, run_uuid, proof["packet_sha256"], proof["manifest_sha256"],
                             elapsed_ms=elapsed_ms)
    require(latest == report, "JOURNAL_CORRUPT")
    return seal(dict(schema=SCHEMA, evidence_kind="OBSERVED_OFFLINE", status=review_state,
                     implementation_sha=sha, run_uuid=run_uuid,
                     packet_sha256=proof["packet_sha256"], manifest_sha256=proof["manifest_sha256"],
                     admission_files=proof["files"], journal=report, raw_files=raw_files,
                     error_code=error, unverified=["REMOTE_CI_AUTHENTICITY", "REVIEW_AUTHENTICITY",
                     "LIVE_RESOURCE_OWNERSHIP", "POWER_LOSS_DURABILITY", "REAL_EXECUTION"],
                     **GATES))


def publish_review(bundle, journal, raw_dir, sha, run_uuid, receipt_dir, *, elapsed_ms=0):
    """Append-only local review artifact; never overwrite an earlier receipt."""
    receipt = review_receipt(bundle, journal, raw_dir, sha, run_uuid, elapsed_ms=elapsed_ms)
    try:
        path = d.directory(Path(receipt_dir)) / "review_receipt.json"
        d.publish(path, receipt)
        require(d.read_file(path, 64 * 1024) == d.encode(receipt), "EVIDENCE_INCOMPLETE")
        return receipt
    except (d.Rejected, OSError):
        raise Refused("EVIDENCE_INCOMPLETE") from None


def read_review(bundle, journal, raw_dir, sha, run_uuid, receipt_dir, *, elapsed_ms=0):
    """Fresh reader replays original evidence and compares every receipt field."""
    try:
        path = d.directory(Path(receipt_dir)) / "review_receipt.json"
        saved = decode(d.read_file(path, 64 * 1024))
        expected = review_receipt(bundle, journal, raw_dir, sha, run_uuid, elapsed_ms=elapsed_ms)
        require(saved == expected, "EVIDENCE_INCOMPLETE")
        return expected
    except (d.Rejected, OSError):
        raise Refused("EVIDENCE_INCOMPLETE") from None


if __name__ == "__main__":
    raise SystemExit(execute())
