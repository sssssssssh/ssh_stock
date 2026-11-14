"""Actual local processes and filesystem fault injection; no resource adapters."""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

from scripts import biz_perf_p1_04_diagnostic as d
from scripts import biz_perf_p1_04_e04_journal as j
from scripts.biz_perf_p1_04_e04_packet import Refused, digest

RUN = str(UUID(int=5))
ARGS = ("a" * 40, RUN, "b" * 64, "c" * 64)


@pytest.fixture
def journal(tmp_path):
    return j.OfflineLeaseJournal.create(tmp_path / "journal")


def test_permanent_reservation_reopen_and_legal_states(journal):
    lease = journal.reserve(*ARGS)
    lease.transition("UNKNOWN_ACK", code="UNKNOWN_ACK", elapsed_ms=1)
    report = j.OfflineLeaseJournal(journal.path).inspect(*ARGS, elapsed_ms=2**63 - 1)
    assert report["state"] == "UNKNOWN_ACK"
    assert report["decision"] == "MANUAL_REVIEW_REQUIRED"
    assert report["lease_expired"] is True
    assert [e["state"] for e in report["transitions"]] == ["PLANNED", "RESERVED", "UNKNOWN_ACK"]
    with pytest.raises(Refused, match="RUN_UUID_REUSED"):
        j.OfflineLeaseJournal(journal.path).reserve(*ARGS)
    assert not hasattr(journal, "release") and not hasattr(journal, "resume")
    lease.transition("MANUAL_REVIEW_REQUIRED", code="UNKNOWN_ACK", elapsed_ms=2)
    with pytest.raises(Refused):
        lease.transition("MOCK_RETURNED", code="MOCK_ONLY", elapsed_ms=3, evidence_sha256="d" * 64)
    assert journal.inspect(*ARGS)["state"] == "MANUAL_REVIEW_REQUIRED"


def test_two_spawned_processes_only_one_reserves(journal):
    code = """
import sys
from scripts.biz_perf_p1_04_e04_journal import OfflineLeaseJournal
from scripts.biz_perf_p1_04_e04_packet import Refused
try:
    OfflineLeaseJournal(sys.argv[1]).reserve(*sys.argv[2:])
    print('RESERVED')
except Refused as exc:
    print(exc.code)
"""
    command = [sys.executable, "-B", "-c", code, str(journal.path), *ARGS]
    children = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True) for _ in range(2)]
    outputs = [child.communicate(timeout=20) for child in children]
    assert [child.returncode for child in children] == [0, 0]
    assert all(not err for _, err in outputs)
    assert sorted(out.strip() for out, _ in outputs) == ["RESERVED", "RUN_UUID_REUSED"]
    assert journal.inspect(*ARGS)["state"] == "RESERVED"


def test_process_crash_after_unknown_ack_cannot_resume(journal):
    code = """
import os, sys
from scripts.biz_perf_p1_04_e04_journal import OfflineLeaseJournal
lease = OfflineLeaseJournal(sys.argv[1]).reserve(*sys.argv[2:])
lease.transition('UNKNOWN_ACK', code='UNKNOWN_ACK', elapsed_ms=1)
os._exit(17)
"""
    child = subprocess.run([sys.executable, "-B", "-c", code, str(journal.path), *ARGS],
                           capture_output=True, text=True, check=False, timeout=20)
    assert child.returncode == 17 and child.stderr == child.stdout == ""
    assert journal.inspect(*ARGS, elapsed_ms=1_200_001)["decision"] == "MANUAL_REVIEW_REQUIRED"
    with pytest.raises(Refused, match="RUN_UUID_REUSED"):
        journal.reserve(*ARGS)


@pytest.mark.parametrize("fault", ["short", "file_fsync", "directory_fsync"])
def test_partial_reservation_and_fsync_faults_never_release(journal, monkeypatch, fault):
    original_write, original_sync = d.sync_write, d.sync_directory
    if fault == "short":
        def partial(stream, raw):
            stream.write(raw[:5])
            stream.flush()
            raise OSError("SECRET_DSN")

        monkeypatch.setattr(d, "sync_write", partial)
    elif fault == "file_fsync":
        monkeypatch.setattr(d.os, "fsync", lambda *_: (_ for _ in ()).throw(OSError("SECRET")))
    else:
        def directory_sync(path):
            if Path(path).name == RUN:
                raise OSError("SECRET")
            return original_sync(path)

        monkeypatch.setattr(d, "sync_directory", directory_sync)
    with pytest.raises(Refused, match="JOURNAL_IO_FAILED") as exc:
        journal.reserve(*ARGS)
    assert "SECRET" not in str(exc.value)
    monkeypatch.undo()
    assert d.sync_write is original_write
    assert (journal.path / RUN).is_dir()
    assert journal.inspect(*ARGS)["decision"] == "MANUAL_REVIEW_REQUIRED"
    with pytest.raises(Refused, match="RUN_UUID_REUSED"):
        journal.reserve(*ARGS)


def test_append_failure_is_sticky_and_lock_is_evidence(journal, monkeypatch):
    lease = journal.reserve(*ARGS)
    original = j._write_new

    def fails(path, value):
        if path.name == "03.json":
            path.write_bytes(b'{"broken":')
            raise OSError("PRIVATE")
        return original(path, value)

    monkeypatch.setattr(j, "_write_new", fails)
    with pytest.raises(Refused, match="JOURNAL_IO_FAILED"):
        lease.transition("UNKNOWN_ACK", code="UNKNOWN_ACK", elapsed_ms=1)
    monkeypatch.undo()
    assert (journal.path / RUN / "writer.lock").is_file()
    with pytest.raises(Refused, match="MANUAL_REVIEW_REQUIRED"):
        lease.transition("UNKNOWN_ACK", code="UNKNOWN_ACK", elapsed_ms=1)
    assert journal.inspect(*ARGS)["error_code"] == "JOURNAL_CORRUPT"


@pytest.mark.parametrize("change", ["tail", "duplicate", "nonfinite", "digest", "extra",
                                    "missing", "identity", "sequence", "transition", "hardlink"])
def test_corrupt_records_are_manual_and_occupied(journal, tmp_path, change):
    journal.reserve(*ARGS)
    file = journal.path / RUN / "02.json"
    value = json.loads(file.read_bytes())
    if change == "tail":
        file.write_bytes(file.read_bytes()[:-4])
    elif change == "duplicate":
        file.write_bytes(b'{"state":"RESERVED","state":"MOCK_RETURNED"}\n')
    elif change == "nonfinite":
        file.write_bytes(b'{"elapsed_ms":NaN}\n')
    elif change == "extra":
        (file.parent / "07.json").write_bytes(b"{}\n")
    elif change == "missing":
        file.unlink()
    elif change == "hardlink":
        os.link(file, tmp_path / "linked.json")
    else:
        if change == "digest":
            value["canonical_sha256"] = "0" * 64
        else:
            if change == "identity":
                value["binding"]["packet_sha256"] = "d" * 64
            if change == "sequence":
                value["seq"] = True
            if change == "transition":
                value["state"] = "MOCK_RETURNED"
            value.pop("canonical_sha256")
            value["canonical_sha256"] = digest(value)
        file.write_bytes(d.encode(value))
    report = journal.inspect(*ARGS)
    assert report["error_code"] == "JOURNAL_CORRUPT"
    assert report["state"] == "MANUAL_REVIEW_REQUIRED"
    with pytest.raises(Refused, match="RUN_UUID_REUSED"):
        journal.reserve(*ARGS)


def test_wrong_binding_and_replaced_directory(journal):
    lease = journal.reserve(*ARGS)
    assert journal.inspect("a" * 40, RUN, "d" * 64, "c" * 64)["error_code"] == "JOURNAL_CORRUPT"
    old = journal.path / RUN
    old.rename(journal.path / "retained")
    old.mkdir()
    with pytest.raises(Refused):
        lease.transition("UNKNOWN_ACK", code="UNKNOWN_ACK", elapsed_ms=1)
    with pytest.raises(Refused, match="RUN_UUID_REUSED"):
        journal.reserve(*ARGS)


def test_new_directory_only_and_platform_permissions(journal):
    with pytest.raises(Refused):
        j.OfflineLeaseJournal.create(journal.path)
    if os.name == "posix":
        assert journal.path.stat().st_mode & 0o077 == 0
        assert (journal.path / "journal.json").stat().st_mode & 0o077 == 0
        journal.path.chmod(0o777)
        with pytest.raises(Refused, match="PATH_REJECTED"):
            j.OfflineLeaseJournal(journal.path)
    else:
        assert os.name == "nt"  # ACL policy/parent trust is external; no POSIX mode claim.


def test_directory_symlink_or_junction_rejected(journal, tmp_path):
    link = tmp_path / "linked"
    if os.name == "nt":
        # Native directory junction needs no symlink privilege. Pure local test paths only.
        command = ['cmd', '/c', 'mklink', '/J', str(link), str(journal.path)]
        result = subprocess.run(command, capture_output=True, check=False)
        assert result.returncode == 0
    else:
        link.symlink_to(journal.path, target_is_directory=True)
    try:
        with pytest.raises(Refused):
            j.OfflineLeaseJournal(link)
    finally:
        if os.name == "nt":
            assert link.is_junction()
            os.rmdir(link)  # Remove junction entry only; never recurse into target.
        else:
            link.unlink()
    assert journal.path.is_dir()


@pytest.mark.parametrize("state,code,elapsed", [
    ("MOCK_RETURNED", "MOCK_ONLY", 1), ("RESERVED", "MOCK_ONLY", 1),
    ("UNKNOWN_ACK", "PRIVATE_LOG", 1), ("UNKNOWN_ACK", "UNKNOWN_ACK", True),
    ("UNKNOWN_ACK", "UNKNOWN_ACK", -1), ("UNKNOWN_ACK", "UNKNOWN_ACK", 2**100),
])
def test_illegal_transitions_poison_handle(journal, state, code, elapsed):
    lease = journal.reserve(*ARGS)
    with pytest.raises(Refused):
        lease.transition(state, code=code, elapsed_ms=elapsed)
    with pytest.raises(Refused, match="MANUAL_REVIEW_REQUIRED"):
        lease.transition("UNKNOWN_ACK", code="UNKNOWN_ACK", elapsed_ms=1)
    assert journal.inspect(*ARGS)["decision"] == "MANUAL_REVIEW_REQUIRED"


def test_return_record_without_confirmed_unlock_cannot_be_success(journal, monkeypatch):
    lease = journal.reserve(*ARGS)
    lease.transition("UNKNOWN_ACK", code="UNKNOWN_ACK", elapsed_ms=1)
    original = d.sync_directory
    count = [0]

    def fails(path):
        count[0] += 1
        if count[0] == 2:  # Lock persisted, full return file written, directory fsync fails.
            raise OSError("PRIVATE")
        return original(path)

    monkeypatch.setattr(d, "sync_directory", fails)
    with pytest.raises(Refused, match="JOURNAL_IO_FAILED"):
        lease.transition("MOCK_RETURNED", code="MOCK_ONLY", elapsed_ms=2,
                         evidence_sha256="d" * 64)
    monkeypatch.undo()
    report = journal.inspect(*ARGS)
    assert report["state"] == "MOCK_RETURNED"
    assert report["decision"] == "MANUAL_REVIEW_REQUIRED"
    with pytest.raises(Refused, match="RUN_UUID_REUSED"):
        journal.reserve(*ARGS)


def test_process_crash_during_first_event_preserves_directory(journal):
    code = """
import os, sys
from scripts import biz_perf_p1_04_e04_journal as j
original = j._write_new
def interrupted(path, value):
    if path.name == '01.json':
        os._exit(19)
    return original(path, value)
j._write_new = interrupted
j.OfflineLeaseJournal(sys.argv[1]).reserve(*sys.argv[2:])
"""
    child = subprocess.run([sys.executable, "-B", "-c", code, str(journal.path), *ARGS],
                           capture_output=True, text=True, check=False, timeout=20)
    assert child.returncode == 19 and child.stderr == child.stdout == ""
    assert journal.inspect(*ARGS)["state"] == "MANUAL_REVIEW_REQUIRED"
    with pytest.raises(Refused, match="RUN_UUID_REUSED"):
        journal.reserve(*ARGS)
