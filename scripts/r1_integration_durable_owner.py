"""Append-only local owner journal, exclusive reservation, fail closed on restart.

Local fsync is NOT cross-machine fencing. The filesystem must be private, local
and owned; network filesystems and hostile same-UID writers are not proven safe.
No crash recovery or automatic lock stealing is provided by this task.
"""

import json
import os
import stat
import threading
from pathlib import Path
from time import monotonic
from uuid import uuid4

from scripts.r1_integration_evidence import finite_time, label, sha
from scripts.r1_real_root_protocol import Refused, parse_json, require


def sync_directory(path):
    require(os.name == "posix", "OWNER_DIRECTORY_FSYNC_UNAVAILABLE")
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class DurableOwner:
    external_fencing_proven = False

    def __init__(self, directory, *, clock=monotonic, directory_sync=sync_directory):
        self.path = Path(directory).absolute()
        require(
            self.path.is_dir() and not self.path.is_symlink() and not self.path.is_junction(),
            "OWNER_PRIVATE_DIRECTORY_REQUIRED",
        )
        for parent in [self.path, *self.path.parents]:
            require(not parent.is_symlink() and not parent.is_junction(), "OWNER_PATH_LINK")
        mode = self.path.stat()
        if os.name == "posix":
            require(
                mode.st_uid == os.getuid() and stat.S_IMODE(mode.st_mode) & 0o077 == 0,
                "OWNER_PRIVATE_DIRECTORY_REQUIRED",
            )
        self.clock, self.sync = clock, directory_sync
        self.nonce = uuid4().hex
        self.binding, self.state, self.handle = None, "NEW", None
        self.chain, self.count, self.poisoned = "0" * 64, 0, False
        self.lock = threading.Lock()
        self.started = self.deadline = None

    def _write(self, path, payload):
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        try:
            raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
            require(len(raw) <= 65536, "OWNER_EVENT_BUDGET")
            offset = 0
            while offset < len(raw):
                size = os.write(fd, raw[offset:])
                require(size > 0, "OWNER_SHORT_WRITE")
                offset += size
            os.fsync(fd)
        finally:
            os.close(fd)
        self.sync(self.path)

    def _append(self, event, details=None):
        try:
            if self.count:
                self._validate_disk()
            value = {
                "index": self.count,
                "previous": self.chain,
                "session": self.nonce,
                "binding": self.binding,
                "event": event,
                "at": finite_time(self.clock()),
                "details": details or {},
            }
            digest = sha(value)
            self._write(self.path / f"{self.count:06d}.json", {"value": value, "sha256": digest})
            self.chain, self.count = digest, self.count + 1
        except Exception:
            self.poisoned = True
            raise Refused("OWNER_DURABILITY_UNKNOWN") from None

    def read_events(self):
        try:
            chain, events = "0" * 64, []
            paths = sorted(self.path.glob("*.json"))
            require(len(paths) <= 128, "OWNER_EVENT_BUDGET")
            for index, path in enumerate(paths):
                require(
                    path.name == f"{index:06d}.json"
                    and not path.is_symlink()
                    and path.stat().st_size <= 65536,
                    "OWNER_JOURNAL_INVALID",
                )
                fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                try:
                    raw = os.read(fd, 65537)
                finally:
                    os.close(fd)
                entry = parse_json(raw)
                require(set(entry) == {"value", "sha256"}, "OWNER_JOURNAL_INVALID")
                value = entry["value"]
                require(
                    value["index"] == index
                    and value["previous"] == chain
                    and entry["sha256"] == sha(value),
                    "OWNER_JOURNAL_INVALID",
                )
                chain = entry["sha256"]
                events.append(value)
            return events
        except Exception:
            raise Refused("OWNER_JOURNAL_INVALID") from None

    def _validate_disk(self):
        events = self.read_events()
        require(
            len(events) == self.count
            and events[-1]["session"] == self.nonce
            and sha(events[-1]) == self.chain,
            "OWNER_JOURNAL_CHANGED",
        )
        reserve = self.path / "reservation"
        require(
            not reserve.is_symlink() and reserve.read_text("ascii") == self.nonce,
            "OWNER_RESERVATION_CHANGED",
        )

    def reserve(self, binding):
        label(binding)
        with self.lock:
            require(self.state == "NEW" and not self.poisoned, "OWNER_REPLAY")
            try:
                fd = os.open(
                    self.path / "reservation",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
                try:
                    require(
                        os.write(fd, self.nonce.encode("ascii")) == len(self.nonce),
                        "OWNER_SHORT_WRITE",
                    )
                    os.fsync(fd)
                finally:
                    os.close(fd)
                self.sync(self.path)
                self.binding = binding
                self.started = finite_time(self.clock())
                self.deadline = self.started + 390
                self._append("RESERVED", {"absolute_expiry": self.deadline})
                self.state = "RESERVED"
                return "LOCAL_RESERVED"
            except Exception:
                self.poisoned = True
                raise Refused("OWNER_RESERVATION_UNKNOWN") from None

    def confirm(self, binding):
        require(
            not self.poisoned
            and binding == self.binding
            and self.state in ("RESERVED", "INTENT", "BOUND"),
            "OWNER_UNCONFIRMED",
        )
        self._validate_disk()
        require(finite_time(self.clock()) < self.deadline, "OWNER_LEASE_EXPIRED")
        return "CONFIRMED"

    def record_intent_before_first_spawn(self, binding):
        with self.lock:
            self.confirm(binding)
            require(self.state == "RESERVED", "OWNER_SPAWN_REPLAY")
            self._append("SPAWN_INTENT")
            self.state = "INTENT"
            return "LOCAL_INTENT_DURABLE"

    def bind_handle(self, binding, facts):
        with self.lock:
            self.confirm(binding)
            require(
                self.state == "INTENT" and type(facts) is dict and bool(facts),
                "OWNER_HANDLE_BEFORE_INTENT",
            )
            self._append("HANDLE_BOUND", {"handle_digest": sha(facts)})
            self.handle, self.state = sha(facts), "BOUND"
            return "LOCAL_HANDLE_BOUND"

    def confirm_handle(self, binding, facts):
        self.confirm(binding)
        require(self.state == "BOUND" and sha(facts) == self.handle, "OWNER_HANDLE_MISMATCH")
        return "CONFIRMED"

    def suspend(self, binding):
        self._stop(binding, "SUSPENDED")

    def fence(self, binding, reason):
        label(reason)
        self._stop(binding, "FENCED")

    def _stop(self, binding, state):
        with self.lock:
            require(not self.poisoned and self.binding == binding, "OWNER_UNCONFIRMED")
            self._append(state)
            self.state = state

    def cleanup_ack(self, binding, facts, *, exited, teardown):
        with self.lock:
            require(
                not self.poisoned
                and binding == self.binding
                and self.handle == sha(facts)
                and exited is True
                and teardown is True,
                "OWNER_CLEANUP_UNKNOWN",
            )
            self._append("CLEANUP_ACK", {"handle_digest": self.handle})
            # Cleanup does not resurrect an expired/fenced lease or permit ON.
            self.state = "CLEANED"
            return "LOCAL_CLEANUP_ACK"
