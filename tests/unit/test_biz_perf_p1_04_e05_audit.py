"""Independent offline reader contracts; all evidence is temporary mock data."""

import hashlib
import importlib.util
import subprocess
import sys
from uuid import UUID

import pytest
from test_biz_perf_p1_04_e04_packet import SHA, rewrite
from test_biz_perf_p1_04_e04_packet import bundle as bundle
from test_biz_perf_p1_04_e04_packet import g as g
from test_biz_perf_p1_04_e04_packet import p as p
from test_biz_perf_p1_04_e04_packet import plan as plan
from test_biz_perf_p1_04_e04_review import r, run

from scripts import biz_perf_p1_04_diagnostic as d
from scripts import biz_perf_p1_04_e05_audit as a
from scripts import biz_perf_p1_04_e05_scan as s


def test_e05_read_only_entry_exists():
    assert importlib.util.find_spec("scripts.biz_perf_p1_04_e05_audit") is not None


def test_e05_execute_denies_even_force():
    result = subprocess.run(
        [sys.executable, "-B", "-m", "scripts.biz_perf_p1_04_e05_audit",
         "execute", "--allow", "--force", "--permit=MOCK"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert result.stdout.strip() == "AUTHORIZATION_PENDING"


@pytest.fixture
def evidence(bundle, tmp_path):
    path, packet, run_uuid, journal, executor, output, kw = run(bundle, tmp_path, complete=True)
    r.run_mock(path, journal, output, SHA, run_uuid, **kw)
    return dict(expected_sha=SHA, run_uuid=run_uuid, bundle=path,
                journal_path=journal.path, raw_dir=output)


def assert_hold(report):
    assert report["evidence_kind"] == "OFFLINE_ONLY"
    assert report["next_action"] == "HOLD_FOR_MANUAL_REVIEW"
    assert all(report[key] is True for key in ("no_replay", "no_retry", "no_cleanup", "no_release"))
    assert report["root_attempts"] == 0 and report["hotspot"] == "NONE_PROVEN"
    assert report["b_gate"] == report["targeted_pg17_gate"] == "NOT_APPROVED"
    assert report["authorization"] == "AUTHORIZATION_PENDING"
    assert report["budget"] == "DRAFT_NOT_APPROVED"
    assert set(a.UNVERIFIED) <= set(report["unverified"])
    assert report["error_code"] is None or report["error_code"] in a.ERROR_CODES


def saved_checkpoint(evidence):
    report = a.audit_bundle(**evidence)
    assert report["audit_status"] == "OFFLINE_EVIDENCE_CONSISTENT", report
    return s.make_checkpoint(report["observation"], check_time="2026-11-14T00:00:00Z")


def filesystem_snapshot(root):
    return {str(path.relative_to(root)): (path.stat().st_ino, path.stat().st_mtime_ns,
            path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())
            for path in root.rglob("*") if path.is_file()}


def test_complete_mock_is_read_only_not_trust(evidence, tmp_path, monkeypatch):
    before = filesystem_snapshot(tmp_path)

    def forbidden(*_args, **_kw):
        pytest.fail("write/execution port reached")

    monkeypatch.setattr(r, "run_mock", forbidden)
    monkeypatch.setattr(r, "publish_review", forbidden)
    monkeypatch.setattr(a.OfflineLeaseJournal, "create", forbidden)
    monkeypatch.setattr(a.OfflineLeaseJournal, "reserve", forbidden)
    report = a.audit_bundle(**evidence)
    assert report["audit_status"] == "OFFLINE_EVIDENCE_CONSISTENT", report
    assert report["journal_state"] == "MOCK_RETURNED"
    assert report["observation"]["seq"] == 4
    assert report["writer_lock"] == "ABSENT"
    assert report["implementation_sha"] == SHA
    assert report["run_uuid"] == evidence["run_uuid"]
    assert report["checkpoint_trust"] == "UNKNOWN"
    assert filesystem_snapshot(tmp_path) == before
    assert_hold(report)
    checkpoint = saved_checkpoint(evidence)
    checked = a.audit_bundle(**evidence, checkpoint=checkpoint)
    assert checked["checkpoint_comparison"] == "RELATIVE_MATCH_ONLY"
    assert checked["checkpoint_trust"] == "UNVERIFIED_EXTERNAL_CHECKPOINT"
    assert checked["checkpoint_sha256"] == checkpoint["canonical_sha256"]
    assert_hold(checked)


@pytest.mark.parametrize("state", sorted(a.STATES))
@pytest.mark.parametrize("elapsed", [0, 1_200_000, 2**63 - 1])
def test_state_taxonomy_never_releases(state, elapsed):
    value = a.classify_incident(state, complete=True, elapsed_ms=elapsed)
    assert value["next_action"] == "HOLD_FOR_MANUAL_REVIEW"
    assert all(value[key] for key in ("no_replay", "no_retry", "no_cleanup", "no_release"))
    assert value["audit_status"] == (
        "OFFLINE_EVIDENCE_CONSISTENT" if state == "MOCK_RETURNED" and elapsed == 0
        else "MANUAL_REVIEW_REQUIRED")


@pytest.mark.parametrize("change", [dict(ownership="UNKNOWN"), dict(resource_match=False),
                                  dict(locked=True), dict(elapsed_ms=1_200_000),
                                  dict(elapsed_ms=True), dict(complete=1),
                                  dict(error_code="PRIVATE_PAYLOAD"), dict(ownership={})])
def test_unknown_ownership_drift_or_invalid_classification(change):
    report = a.classify_incident("MOCK_RETURNED", **change)
    assert report["audit_status"] != "OFFLINE_EVIDENCE_CONSISTENT"
    assert report["no_cleanup"] and report["no_retry"]
    assert "PRIVATE_PAYLOAD" not in str(report)


@pytest.mark.parametrize("state", ["RESERVED", "UNKNOWN_ACK", "BLOCKED",
                                  "MANUAL_REVIEW_REQUIRED"])
def test_crash_or_unknown_ack_prefix_never_replays(bundle, tmp_path, state):
    path, packet, _ = bundle
    journal = a.OfflineLeaseJournal.create(tmp_path / "journal")
    lease = journal.reserve(SHA, packet["run_uuid"], packet["canonical_sha256"],
                            packet["manifest_sha256"])
    if state != "RESERVED":
        lease.transition("UNKNOWN_ACK", code="UNKNOWN_ACK", elapsed_ms=1)
    if state in {"BLOCKED", "MANUAL_REVIEW_REQUIRED"}:
        lease.transition(state, code="MOCK_FAILED", elapsed_ms=2)
    output = tmp_path / "raw"
    output.mkdir()
    report = a.audit_bundle(SHA, packet["run_uuid"], path, journal.path, output,
                            elapsed_ms=2_000_000)
    assert report["journal_state"] == state
    assert report["audit_status"] != "OFFLINE_EVIDENCE_CONSISTENT"
    assert_hold(report)
    with pytest.raises(a.p.Refused, match="RUN_UUID_REUSED"):
        journal.reserve(SHA, packet["run_uuid"], packet["canonical_sha256"],
                        packet["manifest_sha256"])


@pytest.mark.parametrize("raw", [b"", b"private payload", b'{"x":NaN}',
    d.encode(dict(schema=a.p.SCHEMA, evidence_kind="OFFLINE_FIXTURE"))],
                         ids=["empty", "corrupt", "nan", "valid-stale"])
def test_writer_lock_even_after_mock_success_holds(evidence, raw):
    lock = evidence["journal_path"] / evidence["run_uuid"] / "writer.lock"
    lock.write_bytes(raw)
    report = a.audit_bundle(**evidence)
    assert report["writer_lock"] == "PRESENT"
    assert report["error_code"] in {"WRITER_LOCK_CORRUPT", "WRITER_LOCK_PRESENT"}
    assert report["audit_status"] == "MANUAL_REVIEW_REQUIRED"
    assert "private payload" not in str(report)
    assert_hold(report)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}',
                                  b'{"x":-Infinity}', b'{"x":1e999}', b'\xff', b'{"x":',
                                  b" " * 65537],
                         ids=["dup", "nan", "inf", "neg-inf", "overflow", "utf8", "tail", "size"])
def test_invalid_admission_bytes_are_bounded(evidence, raw):
    (evidence["bundle"] / "admission_packet.json").write_bytes(raw)
    report = a.audit_bundle(**evidence)
    assert report["audit_status"] != "OFFLINE_EVIDENCE_CONSISTENT"
    assert_hold(report)


@pytest.mark.parametrize("member", list(a.p.FILES))
def test_missing_packet_manifest_or_source(evidence, member):
    (evidence["bundle"] / member).unlink()
    report = a.audit_bundle(**evidence)
    assert report["audit_status"] != "OFFLINE_EVIDENCE_CONSISTENT"
    assert_hold(report)


@pytest.mark.parametrize("kind", ["sha", "uuid", "manifest", "journal", "raw"])
def test_cross_binding_and_digests(evidence, kind):
    if kind == "sha":
        evidence["expected_sha"] = "b" * 40
    elif kind == "uuid":
        evidence["run_uuid"] = str(UUID(int=999))
    elif kind == "manifest":
        path = evidence["bundle"] / "evidence_manifest.json"
        value = d.decode(path.read_bytes())
        value["entries"]["ci.json"]["sha256"] = "0" * 64
        path.write_bytes(d.encode(value))
    elif kind == "journal":
        path = evidence["journal_path"] / evidence["run_uuid"] / "02.json"
        value = d.decode(path.read_bytes())
        value["binding"]["implementation_sha"] = "b" * 40
        value.pop("canonical_sha256")
        path.write_bytes(d.encode(a.p.seal(value)))
    else:
        path = evidence["raw_dir"] / "events.jsonl"
        path.write_bytes(path.read_bytes() + b" ")
    report = a.audit_bundle(**evidence)
    assert report["audit_status"] != "OFFLINE_EVIDENCE_CONSISTENT"
    assert_hold(report)


@pytest.mark.parametrize("field,value", [("seq", 7), ("state", "RELEASED"),
                                        ("previous_sha256", "0" * 64),
                                        ("elapsed_ms", 2_000_000)])
def test_rehashed_invalid_journal_semantics(evidence, field, value):
    path = evidence["journal_path"] / evidence["run_uuid"] / "03.json"
    event = d.decode(path.read_bytes())
    event[field] = value
    event.pop("canonical_sha256")
    path.write_bytes(d.encode(a.p.seal(event)))
    report = a.audit_bundle(**evidence)
    assert report["error_code"] == "JOURNAL_CORRUPT"
    assert_hold(report)


@pytest.mark.parametrize("fault", ["gap", "short", "partial", "duplicate", "nan", "empty"])
def test_journal_corruption_is_not_empty_success(evidence, fault):
    root = evidence["journal_path"] / evidence["run_uuid"]
    path = root / "03.json"
    if fault == "gap":
        path.rename(root / "06.json")
    elif fault == "empty":
        for member in root.iterdir():
            member.unlink()
    else:
        path.write_bytes({"short": b'{"schema":', "partial": b"",
                          "duplicate": b'{"seq":3,"seq":3}',
                          "nan": b'{"elapsed_ms":NaN}'}[fault])
    report = a.audit_bundle(**evidence)
    assert report["journal_state"] == "MANUAL_REVIEW_REQUIRED"
    assert report["error_code"] == "JOURNAL_CORRUPT"
    assert_hold(report)


@pytest.mark.parametrize("field,value", [("kind", "OBSERVED_LIVE"),
    ("resources.instance.owner_sha256", "0" * 64), ("resources.volume_sha256", "0" * 64),
    ("resources.lease_uuid", str(UUID(int=88)))])
def test_resource_drift_cannot_be_laundered_with_new_hashes(bundle, tmp_path, field, value):
    path, packet, _ = bundle
    payload = d.decode((path / "resources.json").read_bytes())
    target = payload["payload"]["observed"]
    keys = field.split(".")
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    rewrite(a.p, bundle, "resources.json", payload)
    journal = a.OfflineLeaseJournal.create(tmp_path / "journal")
    output = tmp_path / "raw"
    output.mkdir()
    report = a.audit_bundle(SHA, packet["run_uuid"], path, journal.path, output)
    assert report["audit_status"] != "OFFLINE_EVIDENCE_CONSISTENT"
    assert_hold(report)


def test_budget_expiry_does_not_release_success(evidence):
    report = a.audit_bundle(**evidence, elapsed_ms=1_200_000)
    assert report["audit_status"] == "MANUAL_REVIEW_REQUIRED"
    assert report["error_code"] == "BUDGET_EXPIRED"
    assert_hold(report)


def test_cli_dual_independent_process_readers(evidence, tmp_path):
    argv = [sys.executable, "-B", "-m", "scripts.biz_perf_p1_04_e05_audit", "audit",
            "--expected-implementation-sha", SHA, "--expected-run-uuid", evidence["run_uuid"],
            "--bundle", str(evidence["bundle"]), "--journal", str(evidence["journal_path"]),
            "--raw", str(evidence["raw_dir"])]
    before = filesystem_snapshot(tmp_path)
    processes = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for _ in range(2)]
    outputs = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, (stdout, stderr)
        assert stderr == b""
        report = d.decode(stdout)
        assert report["audit_status"] == "OFFLINE_EVIDENCE_CONSISTENT"
        assert_hold(report)
        outputs.append(report)
    assert outputs[0] == outputs[1]
    assert filesystem_snapshot(tmp_path) == before


@pytest.mark.parametrize("command", ["resume", "cleanup", "release", "--permit=private"])
def test_cli_unknown_commands_redact(command, capsys):
    assert a.main([command]) == 2
    report = d.decode(capsys.readouterr().out.encode())
    assert report["error_code"] == "INPUT_REJECTED"
    assert "private" not in str(report)
    assert_hold(report)


@pytest.mark.parametrize("module", ["audit", "scan"])
@pytest.mark.parametrize("flag", ["--allow", "--force", "--permit=MOCK"])
def test_every_module_execute_denies(module, flag, monkeypatch):
    monkeypatch.setenv("E05_PERMIT", "MOCK")
    result = subprocess.run([sys.executable, "-B", "-m", f"scripts.biz_perf_p1_04_e05_{module}",
                             "execute", flag], capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert result.stdout.strip() == "AUTHORIZATION_PENDING"


def test_no_file_identity_is_false_confidence(evidence, monkeypatch):
    def unknown(*_args, **_kw):
        raise s.Refused("FILE_IDENTITY_UNKNOWN")

    monkeypatch.setattr(s, "_identity", unknown)
    report = a.audit_bundle(**evidence)
    assert report["audit_status"] == "AUDIT_REFUSED"
    assert report["file_identity"] == "UNKNOWN"
    assert_hold(report)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}\n', b'{"x":NaN}\n', b'{"x":Infinity}\n',
                                  b'\xff\n', b'{"x":', b" " * 65537 + b"\n"],
                         ids=["dup", "nan", "inf", "utf8", "tail", "line-limit"])
def test_raw_rebound_digest_still_needs_original_replay(evidence, raw):
    (evidence["raw_dir"] / "events.jsonl").write_bytes(raw)
    output = {name: hashlib.sha256((evidence["raw_dir"] / name).read_bytes()).hexdigest()
              for name in ("preflight.json", "events.jsonl")}
    path = evidence["journal_path"] / evidence["run_uuid"] / "04.json"
    event = d.decode(path.read_bytes())
    event.pop("canonical_sha256")
    event["evidence_sha256"] = a.p.digest(output)
    path.write_bytes(d.encode(a.p.seal(event)))
    report = a.audit_bundle(**evidence)
    assert report["error_code"] == "EVIDENCE_INVALID"
    assert_hold(report)


@pytest.mark.parametrize("member", ["preflight.json", "events.jsonl"])
def test_raw_missing_is_incomplete(evidence, member):
    (evidence["raw_dir"] / member).unlink()
    report = a.audit_bundle(**evidence)
    assert report["audit_status"] == "OFFLINE_EVIDENCE_INCOMPLETE"
    assert_hold(report)


def test_root_expiry_never_renews_unknown_ack():
    report = a.classify_incident("UNKNOWN_ACK", elapsed_ms=900_000)
    assert report["audit_status"] == "MANUAL_REVIEW_REQUIRED"
    assert report["error_code"] == "BUDGET_EXPIRED"
    assert report["no_retry"] and report["no_release"]


def test_scan_detects_oversized_raw_without_reading_it(evidence):
    with (evidence["raw_dir"] / "events.jsonl").open("wb") as stream:
        stream.truncate(d.MAX_RAW_BYTES + 1)
    report = a.audit_bundle(**evidence)
    assert report["error_code"] == "SIZE_LIMIT"
    assert_hold(report)


def test_cli_checkpoint_and_redaction(evidence, tmp_path, capsys):
    checkpoint = saved_checkpoint(evidence)
    path = tmp_path / "checkpoint.json"
    path.write_bytes(d.encode(checkpoint))
    argv = ["audit", "--expected-implementation-sha", SHA,
            "--expected-run-uuid", evidence["run_uuid"], "--bundle", str(evidence["bundle"]),
            "--journal", str(evidence["journal_path"]), "--raw", str(evidence["raw_dir"]),
            "--checkpoint", str(path)]
    assert a.main(argv) == 0
    report = d.decode(capsys.readouterr().out.encode())
    assert report["checkpoint_comparison"] == "RELATIVE_MATCH_ONLY"
    assert_hold(report)
    path.write_bytes(b'{"PRIVATE_SQL_AND_CREDENTIALS":NaN}')
    assert a.main(argv) == 2
    output = capsys.readouterr().out
    assert "PRIVATE_SQL" not in output and str(tmp_path) not in output
    assert d.decode(output.encode())["audit_status"] == "AUDIT_REFUSED"
    assert_hold(d.decode(output.encode()))
