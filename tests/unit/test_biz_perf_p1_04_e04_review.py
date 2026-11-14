"""Resource decisions and receipts are mock/file-only, with original validator QA."""

import copy
import json
import os
from uuid import UUID

import pytest
from test_biz_perf_p1_04_e04_packet import SHA, MockVerifier
from test_biz_perf_p1_04_e04_packet import bundle as bundle
from test_biz_perf_p1_04_e04_packet import g as g
from test_biz_perf_p1_04_e04_packet import p as p
from test_biz_perf_p1_04_e04_packet import plan as plan

from scripts import biz_perf_p1_04_diagnostic as d
from scripts import biz_perf_p1_04_e04_review as r
from scripts import biz_perf_p1_04_measure_wiring as w
from scripts.biz_perf_p1_04_e04_journal import OfflineLeaseJournal
from scripts.biz_perf_p1_04_e04_packet import Refused, digest

ROOT = str(UUID(int=22))


def usage():
    return dict.fromkeys(("cpu_millis", "worker_bytes", "pg_bytes", "volume_bytes",
                          "output_bytes", "elapsed_ms"), 0)


def checkpoint(plan, **kw):
    return dict(ack="KNOWN_MOCK_RETURN", ownership="OFFLINE_KNOWN",
                limits=plan["expected"]["resources"]["limits"], usage=usage(), phase="root", **kw)


def test_resource_reader_refuses_by_default_and_matching_is_not_cleanup_authority(plan):
    assert r.inspect_resources(plan["expected"], **checkpoint(plan)) == "CLEANUP_BLOCKED"
    assert r.resource_decision(plan["expected"], plan["observed"], **checkpoint(plan)) == (
        "OFFLINE_OWNERSHIP_MATCH_ONLY")

    class Reader:
        def read(self):
            return copy.deepcopy(plan["observed"])

    assert r.inspect_resources(plan["expected"], reader=Reader(), **checkpoint(plan)) == (
        "OFFLINE_OWNERSHIP_MATCH_ONLY")
    assert not hasattr(Reader(), "cleanup") and not hasattr(r, "drop")


@pytest.mark.parametrize("key,value", [
    ("platform", "Windows"), ("architecture", "aarch64"), ("pgdata_new", False),
    ("database_new", False), ("pgdata_exclusive", False), ("lease_exclusive", False),
    ("volume_sha256", "9" * 64), ("database_owner_sha256", "0" * 64),
    ("offline_system_identifier", "42"), ("online_system_identifier", "42"),
    ("lease_uuid", str(UUID(int=99))),
])
def test_resource_drift_blocks_cleanup(plan, key, value):
    plan["observed"]["resources"][key] = value
    assert r.resource_decision(plan["expected"], plan["observed"], **checkpoint(plan)) == (
        "CLEANUP_BLOCKED")


@pytest.mark.parametrize("key,value", [("pg_major", 16), ("marker", str(UUID(int=33))),
    ("system_identifier", "42"), ("network_sha256", "0" * 64), ("owner_sha256", "0" * 64),
    ("pgdata_sha256", "0" * 64), ("database", "unowned"), ("host", "private.example")])
def test_instance_drift_blocks_cleanup(plan, key, value):
    plan["observed"]["resources"]["instance"][key] = value
    assert r.resource_decision(plan["expected"], plan["observed"], **checkpoint(plan)) == (
        "CLEANUP_BLOCKED")


@pytest.mark.parametrize("ack,ownership,expected", [
    ("UNKNOWN_ACK", "OFFLINE_KNOWN", "MANUAL_REVIEW_REQUIRED"),
    (None, "OFFLINE_KNOWN", "MANUAL_REVIEW_REQUIRED"),
    ("KNOWN_MOCK_RETURN", "UNKNOWN", "CLEANUP_BLOCKED"),
    (True, True, "MANUAL_REVIEW_REQUIRED"),
])
def test_unknown_ack_or_ownership_cannot_be_cleaned(plan, ack, ownership, expected):
    args = checkpoint(plan)
    args.update(ack=ack, ownership=ownership)
    assert r.resource_decision(plan["expected"], plan["observed"], **args) == expected


@pytest.mark.parametrize("key", ["cpu_millis", "worker_bytes", "pg_bytes", "volume_bytes",
                                  "output_bytes"])
def test_fixed_budget_caps_and_overflow(plan, key):
    limits = plan["expected"]["resources"]["limits"]
    sample = usage()
    sample[key] = limits[key]
    assert r.check_budget(limits, sample, phase="root") == "OFFLINE_BUDGET_CHECK_ONLY"
    for value in (limits[key] + 1, 2**100, True, -1, None, "UNKNOWN", float("inf"), float("nan")):
        sample[key] = value
        with pytest.raises(Refused, match="BUDGET_REJECTED"):
            r.check_budget(limits, sample, phase="root")


def test_budget_deadlines_and_draft_limits_cannot_expand(plan):
    limits = plan["expected"]["resources"]["limits"]
    sample = usage()
    for phase, elapsed, accept in [("root", 899999, True), ("root", 900000, False),
                                   ("cleanup", 900000, True), ("cleanup", 1199999, True),
                                   ("cleanup", 1200000, False), ("other", 0, False)]:
        sample["elapsed_ms"] = elapsed
        if accept:
            assert r.check_budget(limits, sample, phase=phase)
        else:
            with pytest.raises(Refused, match="BUDGET_REJECTED"):
                r.check_budget(limits, sample, phase=phase)
    sample["elapsed_ms"] = 0
    for key in limits:
        changed = dict(limits)
        changed[key] = 2**63
        with pytest.raises(Refused, match="BUDGET_REJECTED"):
            r.check_budget(changed, sample, phase="root")
    del sample["cpu_millis"]
    with pytest.raises(Refused, match="BUDGET_REJECTED"):
        r.check_budget(limits, sample, phase="root")


@pytest.mark.parametrize("bad_kind", ["OBSERVED_LIVE", "LIVE_VERIFIED", "EXPECTED"])
def test_live_evidence_refused(plan, bad_kind):
    plan["observed"]["kind"] = bad_kind
    assert r.resource_decision(plan["expected"], plan["observed"], **checkpoint(plan)) == (
        "CLEANUP_BLOCKED")


def run(bundle, tmp_path, *, fault=None, at="create", complete=False):
    path, packet, _ = bundle
    run_uuid = packet["run_uuid"]
    journal = OfflineLeaseJournal.create(tmp_path / "journal")
    executor = r.OfflineMockExecutor(w.FakeClock(), ROOT, fault=fault, at=at)
    output = tmp_path / "raw"
    return path, packet, run_uuid, journal, executor, output, dict(
        verifier=MockVerifier(), executor=executor, complete_evidence=complete)


def test_closed_mock_full_loop_independent_receipt_and_original_validator(bundle, tmp_path):
    path, packet, run_uuid, journal, executor, output, kwargs = run(bundle, tmp_path, complete=True)
    result = r.run_mock(path, journal, output, SHA, run_uuid, **kwargs)
    assert result["status"] == "OFFLINE_MOCK_RETURN_ONLY"
    assert executor.calls == ["mock_create_claim", "mock_worker"]
    receipt = r.review_receipt(path, OfflineLeaseJournal(journal.path), output, SHA, run_uuid)
    assert receipt["status"] == "OFFLINE_EVIDENCE_REVIEWED_ONLY"
    assert receipt["error_code"] is None
    assert receipt["root_attempts"] == 0
    assert receipt["journal"]["state"] == "MOCK_RETURNED"
    assert receipt["manifest_sha256"] == packet["manifest_sha256"]
    assert "LIVE_RESOURCE_OWNERSHIP" in receipt["unverified"]
    assert "LIVE_VERIFIED" not in str(receipt)
    assert "integrity" not in receipt and "completed" not in receipt
    body = dict(receipt)
    claimed = body.pop("canonical_sha256")
    assert claimed == digest(body)
    # Cross-check with the frozen full validator, without modifying a compatibility layer.
    summary = d.validate_bundle(output, tmp_path / "validated", SHA)
    assert summary["status"] == "OFFLINE_VALIDATED" and summary["root_attempts"] == 0
    assert (tmp_path / "validated" / "integrity.json").is_file()
    with pytest.raises(Refused, match="RUN_UUID_REUSED"):
        r.run_mock(path, OfflineLeaseJournal(journal.path), tmp_path / "second", SHA, run_uuid,
                   **kwargs)
    assert executor.calls == ["mock_create_claim", "mock_worker"]


@pytest.mark.parametrize("fault,at", [("CREATE_FAILED", "create"), ("CLAIM_FAILED", "create"),
    ("UNKNOWN_ACK", "create"), ("UNKNOWN_ACK", "worker"), ("WORKER_FAILED", "worker"),
    ("TIMEOUT", "worker"), ("BUDGET_EXCEEDED", "worker")])
def test_failure_keeps_reservation_and_never_root_success(bundle, tmp_path, fault, at):
    values = run(bundle, tmp_path, fault=fault, at=at)
    path, packet, run_uuid, journal, executor, output, kwargs = values
    with pytest.raises(Refused, match="UNKNOWN_ACK" if fault == "UNKNOWN_ACK" else "MOCK_FAILED"):
        r.run_mock(path, journal, output, SHA, run_uuid, **kwargs)
    report = journal.inspect(SHA, run_uuid, packet["canonical_sha256"], packet["manifest_sha256"],
                              elapsed_ms=1_200_001)
    assert report["decision"] in {"MANUAL_REVIEW_REQUIRED", "CLEANUP_BLOCKED"}
    states = [e["state"] for e in report["transitions"]]
    assert states[:3] == ["PLANNED", "RESERVED", "UNKNOWN_ACK"]
    assert "MOCK_RETURNED" not in states
    receipt = r.review_receipt(path, journal, output, SHA, run_uuid)
    assert receipt["error_code"] == "EVIDENCE_INCOMPLETE"
    assert receipt["status"] == "MANUAL_REVIEW_REQUIRED"
    with pytest.raises(d.Rejected):
        d.validate_bundle(output, tmp_path / "rejected", SHA)
    assert not (tmp_path / "rejected" / "summary.json").exists()
    with pytest.raises(Refused, match="RUN_UUID_REUSED"):
        r.run_mock(path, journal, tmp_path / "retry", SHA, run_uuid, **kwargs)
    assert executor.calls.count("mock_create_claim") == 1
    assert executor.calls.count("mock_worker") == (at == "worker")


def test_default_and_real_executor_ports_never_called(bundle, tmp_path):
    path, _packet, run_uuid, journal, _executor, output, _kwargs = run(bundle, tmp_path)

    class Real:
        def create_and_claim(self, *_):
            pytest.fail("must not call any unsealed executor")

    for port in (None, Real(), r.g.RefusedExecutor()):
        with pytest.raises(Refused, match="MOCK_ONLY"):
            r.run_mock(path, journal, output, SHA, run_uuid, executor=port)
    assert not (journal.path / run_uuid).exists()


def test_no_self_approval_can_replace_default_refused_verifier(bundle, tmp_path):
    path, _packet, run_uuid, journal, executor, output, _kwargs = run(bundle, tmp_path)
    with pytest.raises(Refused, match="ATTESTATION_REFUSED"):
        r.run_mock(path, journal, output, SHA, run_uuid, executor=executor)
    assert executor.calls == [] and not (journal.path / run_uuid).exists()


@pytest.mark.parametrize("change", ["missing", "tail", "duplicate", "nonfinite", "substitute"])
def test_receipt_cannot_complete_corrupt_or_missing_evidence(bundle, tmp_path, change):
    values = run(bundle, tmp_path, complete=True)
    path, packet, run_uuid, journal, _executor, output, kwargs = values
    r.run_mock(path, journal, output, SHA, run_uuid, **kwargs)
    rawfile = output / "events.jsonl"
    if change == "missing":
        rawfile.unlink()
    elif change == "tail":
        rawfile.write_bytes(rawfile.read_bytes()[:-2])
    elif change in {"duplicate", "nonfinite"}:
        with rawfile.open("ab") as stream:
            stream.write(b'{"seq":1,"seq":1}\n' if change == "duplicate" else b'{"seq":NaN}\n')
    else:
        # Schema-valid altered raw evidence still fails the journal's immutable digest binding.
        events = [json.loads(line) for line in rawfile.read_bytes().splitlines()]
        events[-2]["tables_sha256"] = dict.fromkeys(d.TABLES, "8" * 64)
        rawfile.write_bytes(b"".join(d.encode(event) for event in events))
    receipt = r.review_receipt(path, journal, output, SHA, run_uuid)
    assert receipt["status"] == "MANUAL_REVIEW_REQUIRED"
    assert receipt["error_code"] == "EVIDENCE_INCOMPLETE"


@pytest.mark.parametrize("fault", ["short", "fsync"])
def test_sink_fault_stops_before_mock_call_and_preserves_uuid(bundle, tmp_path, monkeypatch, fault):
    path, _packet, run_uuid, journal, executor, output, kwargs = run(bundle, tmp_path)
    original = r.BoundedEvidenceSink

    def fail_sink(path, contract):
        sink = original(path, contract)
        if fault == "fsync":
            append = sink._sink.append

            def broken(event):
                with monkeypatch.context() as scope:
                    def fsync(_fd):
                        raise OSError("PRIVATE")

                    scope.setattr(w.os, "fsync", fsync)
                    append(event)

            sink._sink.append = broken
        else:
            handle = sink._sink._fh

            class Short:
                closed = False

                def write(self, raw):
                    return handle.write(raw[:-1])

                def close(self):
                    handle.close()

            sink._sink._fh = Short()
        return sink

    monkeypatch.setattr(r, "BoundedEvidenceSink", fail_sink)
    with pytest.raises(Refused, match="MOCK_FAILED"):
        r.run_mock(path, journal, output, SHA, run_uuid, **kwargs)
    assert executor.calls == []
    with pytest.raises(Refused, match="RUN_UUID_REUSED"):
        journal.reserve(SHA, run_uuid, "b" * 64, "c" * 64)
    assert not (output / "integrity.json").exists()


def test_directory_fsync_platform_contract(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(d.os, "fsync", lambda fd: calls.append(fd))
    d.sync_directory(tmp_path)
    assert len(calls) == (1 if os.name == "posix" else 0)


def test_published_receipt_fresh_reader_and_no_overwrite(bundle, tmp_path):
    values = run(bundle, tmp_path, complete=True)
    path, _packet, run_uuid, journal, _executor, output, kwargs = values
    r.run_mock(path, journal, output, SHA, run_uuid, **kwargs)
    receipt_dir = tmp_path / "receipt"
    receipt_dir.mkdir()
    receipt = r.publish_review(path, journal, output, SHA, run_uuid, receipt_dir)
    reopened = OfflineLeaseJournal(journal.path)
    assert r.read_review(path, reopened, output, SHA, run_uuid, receipt_dir) == receipt
    saved = (receipt_dir / "review_receipt.json").read_bytes()
    with pytest.raises(Refused, match="EVIDENCE_INCOMPLETE"):
        r.publish_review(path, journal, output, SHA, run_uuid, receipt_dir)
    assert (receipt_dir / "review_receipt.json").read_bytes() == saved
    value = json.loads(saved)
    value["root_attempts"] = 1
    (receipt_dir / "review_receipt.json").write_bytes(d.encode(value))
    with pytest.raises(Refused, match="EVIDENCE_INCOMPLETE"):
        r.read_review(path, reopened, output, SHA, run_uuid, receipt_dir)


def test_root_prefix_alone_cannot_produce_reviewed_or_integrity(bundle, tmp_path):
    path, _packet, run_uuid, journal, _executor, output, kwargs = run(bundle, tmp_path)
    r.run_mock(path, journal, output, SHA, run_uuid, **kwargs)
    receipt = r.review_receipt(path, journal, output, SHA, run_uuid)
    assert receipt["status"] == "MANUAL_REVIEW_REQUIRED"
    assert not (output / "integrity.json").exists()
