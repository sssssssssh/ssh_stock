"""Relative checkpoints, path identity and read races; no production resources."""

import os
import subprocess

import pytest
from test_biz_perf_p1_04_e05_audit import a, assert_hold, d, s, saved_checkpoint
from test_biz_perf_p1_04_e05_audit import bundle as bundle
from test_biz_perf_p1_04_e05_audit import evidence as evidence
from test_biz_perf_p1_04_e05_audit import g as g
from test_biz_perf_p1_04_e05_audit import p as p
from test_biz_perf_p1_04_e05_audit import plan as plan


@pytest.mark.parametrize("field,value", [("seq", 5), ("chain_head", "0" * 64),
    ("implementation_sha", "b" * 40), ("run_uuid", "00000000-0000-0000-0000-000000000099"),
    ("manifest_sha256", "0" * 64), ("packet_sha256", "0" * 64),
    ("journal_marker_sha256", "0" * 64), ("output_sha256", "0" * 64),
    ("snapshot_sha256", "0" * 64)])
def test_external_relative_checkpoint_mismatch(evidence, field, value):
    checkpoint = saved_checkpoint(evidence)
    prior = dict(checkpoint["observation"], **{field: value})
    checkpoint = s.make_checkpoint(prior, check_time="2026-11-14T00:00:00Z")
    report = a.audit_bundle(**evidence, checkpoint=checkpoint)
    assert report["audit_status"] == "EVIDENCE_TAMPER_SUSPECTED"
    assert report["error_code"] == ("CHECKPOINT_ROLLBACK" if field == "seq"
                                    else "CHECKPOINT_MISMATCH")
    assert_hold(report)


@pytest.mark.parametrize("field,value", [("trust", "TRUSTED"), ("check_time", "yesterday"),
    ("scan_source", "LIVE_SIGNED"), ("canonical_sha256", "0" * 64),
    ("permit", True), ("evidence_kind", "LIVE_VERIFIED")])
def test_checkpoint_cannot_self_promote(evidence, field, value):
    checkpoint = saved_checkpoint(evidence)
    checkpoint[field] = value
    report = a.audit_bundle(**evidence, checkpoint=checkpoint)
    assert report["audit_status"] == "AUDIT_REFUSED"
    assert report["error_code"] == "CHECKPOINT_REJECTED"
    assert_hold(report)


@pytest.mark.parametrize("value", [True, -1, 7, "4", float("inf"), None])
def test_checkpoint_bounded_sequence(evidence, value):
    observation = a.audit_bundle(**evidence)["observation"]
    observation["seq"] = value
    with pytest.raises(s.Refused, match="CHECKPOINT_REJECTED"):
        s.make_checkpoint(observation, check_time="2026-11-14T00:00:00Z")


def test_old_log_reappearance_after_checkpoint_holds(evidence):
    checkpoint = saved_checkpoint(evidence)
    (evidence["journal_path"] / evidence["run_uuid"] / "04.json").unlink()
    report = a.audit_bundle(**evidence, checkpoint=checkpoint)
    assert report["journal_state"] == "UNKNOWN_ACK"
    assert report["error_code"] == "CHECKPOINT_ROLLBACK"
    assert_hold(report)


@pytest.mark.parametrize("target", ["raw", "journal", "marker", "bundle", "raw_root"])
def test_same_content_replacement_inode_is_relative_change(evidence, tmp_path, target):
    checkpoint = saved_checkpoint(evidence)
    if target == "raw":
        original = evidence["raw_dir"] / "events.jsonl"
    elif target == "journal":
        original = evidence["journal_path"] / evidence["run_uuid"] / "04.json"
    elif target == "marker":
        original = evidence["journal_path"] / "journal.json"
    elif target == "bundle":
        original = evidence["bundle"]
    else:
        original = evidence["raw_dir"]
    backup = tmp_path / "saved"
    original.rename(backup)
    if backup.is_dir():
        # Copy only this fixed offline fixture, not a repository or resource tree.
        original.mkdir(mode=0o700)
        for member in backup.iterdir():
            (original / member.name).write_bytes(member.read_bytes())
    else:
        original.write_bytes(backup.read_bytes())
        original.chmod(0o600)
    report = a.audit_bundle(**evidence, checkpoint=checkpoint)
    assert report["audit_status"] == "EVIDENCE_TAMPER_SUSPECTED"
    assert report["error_code"] == "CHECKPOINT_MISMATCH"
    assert_hold(report)


def test_entire_journal_swapped_with_identical_copy(evidence, tmp_path):
    checkpoint = saved_checkpoint(evidence)
    original = evidence["journal_path"]
    backup = tmp_path / "saved-journal"
    original.rename(backup)
    original.mkdir(mode=0o700)
    marker = original / "journal.json"
    marker.write_bytes((backup / "journal.json").read_bytes())
    marker.chmod(0o600)
    lease = original / evidence["run_uuid"]
    lease.mkdir(mode=0o700)
    for member in (backup / evidence["run_uuid"]).iterdir():
        new = lease / member.name
        new.write_bytes(member.read_bytes())
        new.chmod(0o600)
    report = a.audit_bundle(**evidence, checkpoint=checkpoint)
    assert report["error_code"] == "CHECKPOINT_MISMATCH"
    assert_hold(report)


@pytest.mark.parametrize("target", ["raw_dir", "journal_path", "bundle"])
def test_hardlink_fixed_member_refuses(evidence, tmp_path, target):
    name = {"raw_dir": "events.jsonl", "journal_path": "journal.json",
            "bundle": "ci.json"}[target]
    os.link(evidence[target] / name, tmp_path / "external-link")
    report = a.audit_bundle(**evidence)
    assert report["error_code"] == "PATH_REJECTED"
    assert_hold(report)


@pytest.mark.parametrize("target", ["raw_dir", "journal_path", "bundle"])
def test_directory_link_refuses(evidence, tmp_path, target):
    original = evidence[target]
    link = tmp_path / "linked-dir"
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(original)],
                                capture_output=True, check=False)
        assert result.returncode == 0
    else:
        link.symlink_to(original, target_is_directory=True)
    evidence[target] = link
    report = a.audit_bundle(**evidence)
    assert report["error_code"] == "PATH_REJECTED"
    assert_hold(report)


@pytest.mark.parametrize("fault", ["bytes", "same-bytes-inode", "mtime", "parent"])
def test_mutation_during_read_fails_closed(evidence, tmp_path, monkeypatch, fault):
    original_read = d.read_file
    fired = False

    def mutate(path, limit):
        nonlocal fired
        raw = original_read(path, limit)
        if path == evidence["raw_dir"] / "events.jsonl" and not fired:
            fired = True
            if fault == "bytes":
                path.write_bytes(raw + b" ")
            elif fault == "same-bytes-inode":
                path.rename(tmp_path / "old-events")
                path.write_bytes(raw)
            elif fault == "mtime":
                info = path.stat()
                os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000))
            else:
                parent = evidence["raw_dir"]
                parent.rename(tmp_path / "old-raw")
                parent.mkdir()
                for member in (tmp_path / "old-raw").iterdir():
                    (parent / member.name).write_bytes(member.read_bytes())
        return raw

    monkeypatch.setattr(d, "read_file", mutate)
    report = a.audit_bundle(**evidence)
    assert fired
    assert report["audit_status"] == "EVIDENCE_TAMPER_SUSPECTED"
    assert_hold(report)


def test_checkpoint_unbounded_cycle_refused(evidence):
    cycle = {}
    cycle["cycle"] = cycle
    report = a.audit_bundle(**evidence, checkpoint=cycle)
    assert report["error_code"] == "CHECKPOINT_REJECTED"
    assert_hold(report)


@pytest.mark.parametrize("checkpoint", [[], True, "signed", 42])
def test_checkpoint_non_objects_refuse(evidence, checkpoint):
    report = a.audit_bundle(**evidence, checkpoint=checkpoint)
    assert report["error_code"] == "CHECKPOINT_REJECTED"
    assert_hold(report)


def test_same_seq_different_chain_head_is_relative_change(evidence):
    checkpoint = saved_checkpoint(evidence)
    path = evidence["journal_path"] / evidence["run_uuid"] / "04.json"
    event = d.decode(path.read_bytes())
    event.pop("canonical_sha256")
    event["elapsed_ms"] += 1
    path.write_bytes(d.encode(a.p.seal(event)))
    report = a.audit_bundle(**evidence, checkpoint=checkpoint)
    assert report["observation"]["seq"] == checkpoint["observation"]["seq"]
    assert report["error_code"] == "CHECKPOINT_MISMATCH"
    assert report["checkpoint_sha256"] == checkpoint["canonical_sha256"]
    assert_hold(report)
