"""Six real private processes/Unix SCM_RIGHTS + SQLite MODEL stores, never real G1.

All processes use the runner's UID. This proves IPC/persistence/reviewer logic, NOT
physical multi-UID independence, PostgreSQL durability, SCRAM or Podman absence.
"""

import array
import json
import os
import socket
import sqlite3
import time

import pytest

from scripts.a42361_contract import canonical
from scripts.a42363_contract import Fault, receipt, scope_hash
from scripts.a42364_evidence_gate import EvidenceGate
from scripts.a42364_manager import peer_uid, read_frame, receive_fds, send_frame
from scripts.a42364_volume_exclusion import OperationJournal
from tests.unit.test_a42364_evidence import chain
from tests.unit.test_a42364_owner import identity


class SQLiteModelStore:
    def __init__(self, path, domain):
        self.path, self.domain = path, domain
        c = sqlite3.connect(path)
        try:
            c.execute(
                "CREATE TABLE IF NOT EXISTS events (event TEXT PRIMARY KEY, body TEXT NOT NULL)"
            )
            c.commit()
        finally:
            c.close()

    def append(self, scope, event, record):
        c = sqlite3.connect(self.path)
        try:
            c.execute("BEGIN IMMEDIATE")
            sequence = c.execute("SELECT count(*) FROM events").fetchone()[0] + 1
            value = receipt(self.domain, scope, event, sequence, record)
            c.execute(
                "INSERT INTO events VALUES (?,?)", (event, canonical(value.model_dump()).decode())
            )
            c.commit()
        finally:
            c.close()
        return self.read(scope, event)  # new physical SQLite connection, not writer.

    def read(self, scope, event):
        from scripts.a42363_contract import verify_receipt

        c = sqlite3.connect(self.path)
        try:
            row = c.execute("SELECT body FROM events WHERE event=?", (event,)).fetchone()
        finally:
            c.close()
        if row is None:
            return None
        return verify_receipt(json.loads(row[0]), self.domain, scope, event)

    def maybe_read(self, scope, event):
        return self.read(scope, event)


def model_server(channel, path, domain, scope):
    fds = receive_fds(channel, 1)
    try:
        assert os.pread(fds[0], 4096, 0) == scope_hash(scope).encode()
        send_frame(channel, dict(model=True, uid=os.getuid(), pid=os.getpid(), qualifies=False))
        store = SQLiteModelStore(path, domain)
        while True:
            request = read_frame(channel, time.monotonic_ns() + 30_000_000_000)
            if request["method"] == "stop":
                return
            assert request["scope_sha256"] == scope_hash(scope)
            if request["method"] == "append":
                r = store.append(scope, request["event"], request["record"])
            else:
                assert request["method"] == "read"
                r = store.read(scope, request["event"])
            send_frame(channel, r.model_dump())
    finally:
        os.close(fds[0])
        channel.close()


class ModelClient:
    def __init__(self, channel):
        self.channel = channel

    def call(self, method, scope, event, record=None):
        require_record = dict(method=method, scope_sha256=scope_hash(scope), event=event)
        if record is not None:
            require_record["record"] = record
        send_frame(self.channel, require_record)
        from scripts.a42363_contract import verify_receipt

        return verify_receipt(
            read_frame(self.channel, time.monotonic_ns() + 3_000_000_000), self.domain, scope, event
        )

    def read(self, scope, event):
        return self.call("read", scope, event)


def test_AT36_AT38_six_process_fd_handoff_and_independent_persistent_receipts(tmp_path):
    scope, _, original = chain()
    model = tmp_path / "scope.model"
    model.write_text(scope_hash(scope))
    fd = os.open(model, os.O_RDONLY)
    children = []
    clients = {}
    references = {}
    pids = []
    try:
        for domain in original:
            parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
            pid = os.fork()
            if pid == 0:
                parent.close()
                for client in clients.values():
                    client.channel.close()
                try:
                    model_server(child, tmp_path / (domain + ".sqlite"), domain, scope)
                    os._exit(0)
                except BaseException:
                    os._exit(1)
            child.close()
            children.append(pid)
            assert peer_uid(parent) == os.getuid()
            parent.sendmsg([b"F"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))])
            ack = read_frame(parent, time.monotonic_ns() + 3_000_000_000)
            assert ack["model"] and ack["qualifies"] is False
            pids.append(ack["pid"])
            client = ModelClient(parent)
            client.domain = domain
            clients[domain] = client
            r = original[domain]
            references[domain] = client.call("append", scope, r.event, r.record)
        assert len(set(pids)) == 6
        result = EvidenceGate(clients).review(scope, references)
        assert result["status"] == "OFFLINE_CROSS_DOMAIN_VERIFIED" and result["qualifies"] is False
        assert result["real_probe_sql_executed"] == 0
    finally:
        os.close(fd)
        for client in clients.values():
            try:
                send_frame(client.channel, dict(method="stop"))
            finally:
                client.channel.close()
        for pid in children:
            observed, status = os.waitpid(pid, 0)
            assert observed == pid and status == 0


@pytest.mark.parametrize("kind", ["SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER"])
def test_AT25_AT29_private_persistence_blocks_second_remove_after_process_restart(tmp_path, kind):
    scope = identity().scope
    path = tmp_path / "model.sqlite"
    writer = SQLiteModelStore(path, "controller")
    calls = []

    def remove():
        calls.append(kind)
        raise RuntimeError("OFFLINE_ACK_UNKNOWN")

    with pytest.raises(Fault):
        OperationJournal(writer).perform(scope, kind, "REMOVE", "original", remove)
    restarted = SQLiteModelStore(path, "controller")
    with pytest.raises(Fault, match="NO_REPLAY"):
        OperationJournal(restarted).perform(scope, kind, "REMOVE", "original", remove)
    assert calls == [kind]
