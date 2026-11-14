"""Permanent one-shot UUID reservations in a NEW, trusted offline directory.

mkdir is the cross-process exclusive reservation. A UUID directory is never
removed, even if its first write fails. A writer lock is left on failure/crash.
Reopening permits inspection only: no resume, release, expiry or retry method.
An existing/new journal is NOT a production lease, authority or hostile-FS sandbox.
The caller must preserve this directory and its trusted, stable ancestors. A new
journal elsewhere cannot establish global uniqueness. POSIX fsyncs files and
parent directories; Windows does not prove directory-entry power-loss durability.
"""

from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path

from scripts import biz_perf_p1_04_diagnostic as d
from scripts.biz_perf_p1_04_e04_packet import (
    GATES,
    SCHEMA,
    Refused,
    decode,
    execute,
    fields,
    require,
    seal,
    unseal,
)

MAX_RECORD = 4096
MAX_RECORDS = 6
NEXT = {
    None: {"PLANNED"}, "PLANNED": {"RESERVED"},
    "RESERVED": {"UNKNOWN_ACK", "BLOCKED", "MANUAL_REVIEW_REQUIRED"},
    "UNKNOWN_ACK": {"MOCK_RETURNED", "BLOCKED", "MANUAL_REVIEW_REQUIRED"},
    "MOCK_RETURNED": set(), "BLOCKED": set(), "MANUAL_REVIEW_REQUIRED": set(),
}
STATE_CODES = {
    "PLANNED": {"MOCK_ONLY"}, "RESERVED": {"MOCK_ONLY"},
    "UNKNOWN_ACK": {"UNKNOWN_ACK"}, "MOCK_RETURNED": {"MOCK_ONLY"},
    "BLOCKED": {"CLEANUP_BLOCKED", "BUDGET_REJECTED", "MOCK_FAILED", "EVIDENCE_INCOMPLETE"},
    "MANUAL_REVIEW_REQUIRED": {"UNKNOWN_ACK", "MOCK_FAILED", "EVIDENCE_INCOMPLETE"},
}


def _private(path):
    info = path.lstat()
    require(not path.is_symlink() and not path.is_junction(), "PATH_REJECTED")
    if os.name == "posix":
        require(info.st_uid == os.getuid() and info.st_mode & 0o077 == 0, "PATH_REJECTED")
    return info


def _write_new(path, value):
    """Never unlink a partial record: failure is permanent uncertainty evidence."""
    raw = d.encode(value)
    require(len(raw) <= MAX_RECORD, "JOURNAL_REJECTED")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        d.sync_write(stream, raw)
    d.sync_directory(path.parent)


def _binding(sha, run_uuid, packet_sha256, manifest_sha256):
    require(d.hex_value(sha, 40) and d.uuid_value(run_uuid)
            and d.hex_value(packet_sha256, 64) and d.hex_value(manifest_sha256, 64),
            "IDENTITY_MISMATCH")
    return dict(implementation_sha=sha, run_uuid=run_uuid, packet_sha256=packet_sha256,
                manifest_sha256=manifest_sha256)


class OfflineLeaseJournal:
    def __init__(self, path):
        try:
            self.path = d.directory(Path(path))
            self._inode = _private(self.path)
            self._marker_raw = d.read_file(self.path / "journal.json", MAX_RECORD)
            marker = decode(self._marker_raw)
            fields(marker, {"schema", "evidence_kind", "journal_uuid"}, "JOURNAL_REJECTED")
            require(marker["schema"] == SCHEMA and marker["evidence_kind"] == "OFFLINE_FIXTURE"
                    and d.uuid_value(marker["journal_uuid"]), "JOURNAL_REJECTED")
            _private(self.path / "journal.json")
        except Refused:
            raise
        except (OSError, d.Rejected):
            raise Refused("PATH_REJECTED") from None

    @classmethod
    def create(cls, path):
        """The only initializer. Existing directories are always refused."""
        import uuid

        try:
            path = Path(path)
            parent = d.directory(path.parent)
            require(path.name not in {"", ".", ".."}, "PATH_REJECTED")
            path = parent / path.name
            path.mkdir(mode=0o700)  # Never exist_ok. No unrelated directory is adopted.
            d.sync_directory(parent)
            _write_new(path / "journal.json", dict(schema=SCHEMA,
                       evidence_kind="OFFLINE_FIXTURE", journal_uuid=str(uuid.uuid4())))
            return cls(path)
        except Refused:
            raise
        except (OSError, d.Rejected):
            raise Refused("JOURNAL_IO_FAILED") from None

    def _check(self):
        d.directory(self.path)
        require(os.path.samestat(_private(self.path), self._inode), "PATH_REJECTED")
        require(d.read_file(self.path / "journal.json", MAX_RECORD) == self._marker_raw,
                "PATH_REJECTED")

    def reserve(self, sha, run_uuid, packet_sha256, manifest_sha256):
        binding = _binding(sha, run_uuid, packet_sha256, manifest_sha256)
        try:
            self._check()
            path = self.path / run_uuid
            path.mkdir(mode=0o700)
            # The directory itself is the permanent reservation, even before events exist.
            d.sync_directory(self.path)
            lease = _Lease(self, path, binding)
            lease._append("PLANNED", "MOCK_ONLY", 0)
            lease._append("RESERVED", "MOCK_ONLY", 0)
            return lease
        except FileExistsError:
            raise Refused("RUN_UUID_REUSED") from None
        except Refused:
            raise
        except (OSError, d.Rejected):
            raise Refused("JOURNAL_IO_FAILED") from None

    def _read(self, binding):
        self._check()
        path = self.path / binding["run_uuid"]
        d.directory(path)
        inode = _private(path)
        names = {p.name for p in path.iterdir()}
        locked = "writer.lock" in names
        names.discard("writer.lock")
        require(2 <= len(names) <= MAX_RECORDS
                and names == {f"{i:02}.json" for i in range(1, len(names) + 1)},
                "JOURNAL_CORRUPT")
        events, raws, inodes, previous, state, elapsed = [], {}, {}, "0" * 64, None, 0
        for seq in range(1, len(names) + 1):
            name = f"{seq:02}.json"
            inodes[name] = _private(path / name)
            raw = d.read_file(path / name, MAX_RECORD)
            value = decode(raw)
            body = unseal(value, {"schema", "evidence_kind", "binding", "seq", "state",
                                  "code", "elapsed_ms", "previous_sha256", "evidence_sha256"},
                          "JOURNAL_CORRUPT")
            require(body["schema"] == SCHEMA and body["evidence_kind"] == "OFFLINE_FIXTURE"
                    and body["binding"] == binding, "IDENTITY_MISMATCH")
            require(type(body["seq"]) is int and body["seq"] == seq
                    and type(body["state"]) is str and body["state"] in NEXT[state]
                    and type(body["code"]) is str
                    and body["code"] in STATE_CODES[body["state"]]
                    and d.uint(body["elapsed_ms"], 1_200_000)
                    and body["elapsed_ms"] >= elapsed
                    and body["previous_sha256"] == previous, "JOURNAL_CORRUPT")
            require(d.hex_value(body["evidence_sha256"], 64) if body["state"] == "MOCK_RETURNED"
                    else body["evidence_sha256"] is None, "JOURNAL_CORRUPT")
            state, elapsed, previous = body["state"], body["elapsed_ms"], value["canonical_sha256"]
            events.append(value)
            raws[name] = raw
        self._check()
        d.directory(path)
        require(os.path.samestat(inode, _private(path)), "PATH_REJECTED")
        require({p.name for p in path.iterdir()} == names | ({"writer.lock"} if locked else set())
                and all(os.path.samestat(inodes[name], _private(path / name))
                        and d.read_file(path / name, MAX_RECORD) == raw
                        for name, raw in raws.items()), "JOURNAL_CORRUPT")
        return events, {name: hashlib.sha256(raw).hexdigest() for name, raw in raws.items()}, locked

    def inspect(self, sha, run_uuid, packet_sha256, manifest_sha256, *, elapsed_ms=0):
        binding = _binding(sha, run_uuid, packet_sha256, manifest_sha256)
        require(d.uint(elapsed_ms), "BUDGET_REJECTED")
        try:
            events, files, locked = self._read(binding)
            state = events[-1]["state"]
            decision = ("OFFLINE_RETURN_RECORDED_ONLY" if state == "MOCK_RETURNED" and not locked
                        else "MANUAL_REVIEW_REQUIRED")
            if state == "BLOCKED" and not locked:
                decision = "CLEANUP_BLOCKED"
            return dict(schema=SCHEMA, evidence_kind="OBSERVED_OFFLINE", binding=binding,
                        state=state, decision=decision, transitions=events, files=files,
                        lease_expired=elapsed_ms >= 1_200_000, error_code=None, **GATES)
        except (Refused, OSError, d.Rejected, ValueError, TypeError, KeyError):
            return dict(schema=SCHEMA, evidence_kind="OBSERVED_OFFLINE", binding=binding,
                        state="MANUAL_REVIEW_REQUIRED", decision="MANUAL_REVIEW_REQUIRED",
                        transitions=[], files={}, lease_expired=elapsed_ms >= 1_200_000,
                        error_code="JOURNAL_CORRUPT", **GATES)


class _Lease:
    """Process-local continuation only. No method to reconstruct this on reopen."""

    def __init__(self, journal, path, binding):
        self._journal, self._path = journal, path
        self._binding = copy.deepcopy(binding)
        self._inode = _private(path)
        self._events = []
        self._failed = False
        self._pid = os.getpid()

    def _append(self, state, code, elapsed_ms, evidence_sha256=None):
        require(not self._failed and os.getpid() == self._pid, "MANUAL_REVIEW_REQUIRED")
        try:
            previous = self._events[-1] if self._events else None
            require(type(state) is str and state in NEXT[previous["state"] if previous else None]
                    and type(code) is str and code in STATE_CODES[state]
                    and d.uint(elapsed_ms, 1_200_000)
                    and elapsed_ms >= (previous["elapsed_ms"] if previous else 0),
                    "TRANSITION_REJECTED")
            require(d.hex_value(evidence_sha256, 64) if state == "MOCK_RETURNED"
                    else evidence_sha256 is None, "TRANSITION_REJECTED")
            self._journal._check()
            d.directory(self._path)
            require(os.path.samestat(self._inode, _private(self._path)), "PATH_REJECTED")
            lock = self._path / "writer.lock"
            _write_new(lock, dict(schema=SCHEMA, evidence_kind="OFFLINE_FIXTURE"))
            # Compare every prior byte; a replaced/corrupted event cannot be extended.
            wanted = {f"{i:02}.json" for i in range(1, len(self._events) + 1)} | {"writer.lock"}
            require({p.name for p in self._path.iterdir()} == wanted, "JOURNAL_CORRUPT")
            for seq, event in enumerate(self._events, 1):
                require(d.read_file(self._path / f"{seq:02}.json", MAX_RECORD) == d.encode(event),
                        "JOURNAL_CORRUPT")
            event = seal(dict(schema=SCHEMA, evidence_kind="OFFLINE_FIXTURE",
                              binding=self._binding, seq=len(self._events) + 1, state=state,
                              code=code, elapsed_ms=elapsed_ms,
                              evidence_sha256=evidence_sha256,
                              previous_sha256=(previous["canonical_sha256"] if previous
                                               else "0" * 64)))
            _write_new(self._path / f"{event['seq']:02}.json", event)
            self._journal._check()
            require(os.path.samestat(self._inode, _private(self._path)), "PATH_REJECTED")
            saved = d.read_file(self._path / f"{event['seq']:02}.json", MAX_RECORD)
            require(saved == d.encode(event),
                    "JOURNAL_CORRUPT")
            lock.unlink()  # Only this local operation lock; UUID reservation is never removed.
            d.sync_directory(self._path)
            self._events.append(event)
        except BaseException:
            self._failed = True
            raise Refused("JOURNAL_IO_FAILED") from None

    def transition(self, state, *, code, elapsed_ms, evidence_sha256=None):
        self._append(state, code, elapsed_ms, evidence_sha256)

    @property
    def binding(self):
        return copy.deepcopy(self._binding)


if __name__ == "__main__":
    raise SystemExit(execute())
