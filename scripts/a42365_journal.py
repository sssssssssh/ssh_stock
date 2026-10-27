"""Private FD-bound operational journal. No PG/business DSN or user-selected path.

The runtime and controlled L1 use this same durable implementation. A live domain
must receive its own correctly owned directory from the root provisioner; SQLite
does not establish multi-UID isolation or a physical G1 qualification.
"""

import os
import sqlite3
import stat
from contextlib import contextmanager

from scripts.a42363_contract import DOMAINS, receipt, require, scope_hash, verify_receipt
from scripts.a42365_contract import canonical, decode, runtime_receipt


class DurableJournal:
    def __init__(self, directory_fd, domain, *, owner=None):
        require(domain in (*DOMAINS, "root_manager", "writer_broker"), "JOURNAL_DOMAIN")
        m = os.fstat(directory_fd)
        require(
            stat.S_ISDIR(m.st_mode)
            and stat.S_IMODE(m.st_mode) == 0o700
            and m.st_uid == (os.getuid() if owner is None else owner),
            "JOURNAL_DIRECTORY",
        )
        self.fd, self.domain, self.identity = directory_fd, domain, self.directory_identity(m)
        self.filename = "events.sqlite"
        # O_EXCL/NOFOLLOW custody first; SQLite can never open an arbitrary caller path.
        try:
            fd = os.open(
                self.filename,
                os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW,
                0o600,
                dir_fd=self.fd,
            )
            os.fsync(fd)
            os.close(fd)
            os.fsync(self.fd)
        except FileExistsError:
            pass
        m = os.stat(self.filename, dir_fd=self.fd, follow_symlinks=False)
        require(
            stat.S_ISREG(m.st_mode)
            and m.st_nlink == 1
            and stat.S_IMODE(m.st_mode) == 0o600
            and m.st_uid == os.fstat(self.fd).st_uid,
            "JOURNAL_FILE",
        )
        self.file_id = (m.st_dev, m.st_ino)
        with self.connection() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS runtime_events (sequence INTEGER PRIMARY KEY, "
                "scope TEXT NOT NULL, epoch TEXT NOT NULL, event TEXT NOT NULL, "
                "body BLOB NOT NULL, UNIQUE(scope,epoch,event))"
            )
            c.commit()

    def verify(self):
        require(
            self.directory_identity(os.fstat(self.fd)) == self.identity, "JOURNAL_DIRECTORY_CHANGED"
        )
        m = os.stat(self.filename, dir_fd=self.fd, follow_symlinks=False)
        require(
            stat.S_ISREG(m.st_mode)
            and m.st_nlink == 1
            and (m.st_dev, m.st_ino) == self.file_id
            and stat.S_IMODE(m.st_mode) == 0o600,
            "JOURNAL_FILE_CHANGED",
        )

    @contextmanager
    def connection(self):
        self.verify()
        if os.path.isdir("/proc/self/fd"):
            path = "/proc/self/fd/" + str(self.fd) + "/" + self.filename
        else:
            # Controlled macOS L1 only. Kernel F_GETPATH derives the held object's
            # path; no CLI/network path is accepted. Live installation is Linux-only.
            import fcntl
            import sys

            require(sys.platform == "darwin", "JOURNAL_FD_FILESYSTEM_REQUIRED")
            directory = fcntl.fcntl(self.fd, 50, b"\0" * 1024).split(b"\0", 1)[0]
            require(
                self.directory_identity(os.stat(directory)) == self.identity,
                "JOURNAL_DIRECTORY_CHANGED",
            )
            path = os.fsdecode(directory) + "/" + self.filename
        c = sqlite3.connect(path, timeout=1)
        try:
            c.execute("PRAGMA synchronous=FULL")
            c.execute("PRAGMA busy_timeout=1000")
            yield c
            self.verify()
        finally:
            c.close()

    @staticmethod
    def directory_identity(value):
        # APFS directory link counts change when SQLite adds/removes journal files.
        return tuple(getattr(value, k) for k in ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid"))

    def _receipt(self, scope, event, sequence, record):
        # Legacy domain receipts remain exact; root/broker have independent records.
        if self.domain in DOMAINS:
            return receipt(self.domain, scope, event, sequence, record)
        return runtime_receipt(self.domain, scope, event, sequence, record)

    def append(self, scope, event, record):
        require(type(event) is str and event.isascii() and 0 < len(event) <= 64, "JOURNAL_EVENT")
        raw = canonical(record)
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                cur = c.execute(
                    "INSERT INTO runtime_events(scope,epoch,event,body) VALUES(?,?,?,?)",
                    (scope_hash(scope), scope.epoch, event, raw),
                )
                sequence = cur.lastrowid
                c.commit()  # An ACK after this point may be unknown; never INSERT again.
            except sqlite3.IntegrityError:
                require(False, "JOURNAL_DUPLICATE_NO_REPLAY")
        result = self.read(scope, event)  # separate physical connection
        require(
            result.sequence == sequence and canonical(result.record) == raw, "JOURNAL_ACK_UNKNOWN"
        )
        return result

    def maybe_read(self, scope, event):
        with self.connection() as c:
            row = c.execute(
                "SELECT sequence,body FROM runtime_events WHERE scope=? AND epoch=? AND event=?",
                (scope_hash(scope), scope.epoch, event),
            ).fetchone()
        return None if row is None else self._receipt(scope, event, row[0], decode(bytes(row[1])))

    def read(self, scope, event, previous=None):
        require(previous is None, "JOURNAL_WRITER_REUSE")
        result = self.maybe_read(scope, event)
        require(result is not None, "COMMITTED_RECEIPT_MISSING")
        if self.domain in DOMAINS:
            return verify_receipt(result, result.domain, scope, event)
        require(
            result == runtime_receipt(self.domain, scope, event, result.sequence, result.record),
            "RUNTIME_RECEIPT_BINDING",
        )
        return result

    def events(self, scope):
        with self.connection() as c:
            rows = c.execute(
                "SELECT sequence,event,body FROM runtime_events "
                "WHERE scope=? AND epoch=? ORDER BY sequence",
                (scope_hash(scope), scope.epoch),
            ).fetchall()
        return [self._receipt(scope, event, seq, decode(bytes(raw))) for seq, event, raw in rows]

    def reserve(self, scope, event, record, limits):
        """Serialize global costs with the insert, not a racy read/count/write.

        Every process uses the B directory. A committed reservation is spent even
        if the reply is lost. Costs are never refunded or reset on restart.
        """
        require(self.domain == "consumer", "BUDGET_WRITER_DOMAIN")
        require(
            type(event) is str and event.startswith("RESERVE_") and len(event) <= 64,
            "BUDGET_RESERVATION_KEY",
        )
        costs = record["costs"]
        require(
            set(costs) == set(limits) and all(type(v) is int and v >= 0 for v in costs.values()),
            "BUDGET_COSTS",
        )
        raw = canonical(record)
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            require(
                c.execute(
                    "SELECT 1 FROM runtime_events WHERE scope=? AND epoch=? AND event=?",
                    (scope_hash(scope), scope.epoch, event),
                ).fetchone()
                is None,
                "BUDGET_ACK_UNKNOWN_NO_RETRY",
            )
            rows = c.execute(
                "SELECT body FROM runtime_events WHERE scope=? AND epoch=? "
                "AND event LIKE 'RESERVE_%'",
                (scope_hash(scope), scope.epoch),
            ).fetchall()
            totals = dict.fromkeys(limits, 0)
            for (body,) in rows:
                old = decode(bytes(body))
                require(set(old["costs"]) == set(limits), "BUDGET_PLAN_DRIFT")
                for k in totals:
                    totals[k] += old["costs"][k]
            require(
                all(totals[k] + costs[k] <= limits[k] for k in totals), "GLOBAL_BUDGET_EXHAUSTED"
            )
            try:
                cur = c.execute(
                    "INSERT INTO runtime_events(scope,epoch,event,body) VALUES(?,?,?,?)",
                    (scope_hash(scope), scope.epoch, event, raw),
                )
                sequence = cur.lastrowid
                c.commit()
            except sqlite3.IntegrityError:
                require(False, "BUDGET_ACK_UNKNOWN_NO_RETRY")
        result = self.read(scope, event)
        require(result.sequence == sequence, "JOURNAL_ACK_UNKNOWN")
        return result

    @contextmanager
    def exclusive(self, scope, event):
        # Persisted single-use ownership. A process death never resets this claim.
        self.append(scope, event, dict(qualifies=False))
        yield
