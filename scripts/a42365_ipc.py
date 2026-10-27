"""Fixed inherited Unix channels; peer credentials checked before framed decoding."""

import socket
import time

from scripts.a42361_contract import checked
from scripts.a42363_contract import Receipt, require, verify_receipt
from scripts.a42364_manager import peer_uid, read_frame, send_frame
from scripts.a42365_contract import RuntimeReceipt, message, runtime_receipt

METHODS = dict(
    consumer=("consume", "stop", "receipt", "journal-append", "journal-read", "budget"),
    pg_owner=("create", "receipt", "candidate-session-v3"),
    controller=("create", "reconcile", "receipt"),
    supervisor=("run", "terminate", "receipt"),
    absence_auditor=("absent", "receipt"),
    writer_broker=("status", "receipt"),
)


class DomainClient:
    def __init__(self, fd, uid, domain, scope, source, budget):
        require(domain in METHODS, "RUNTIME_DOMAIN")
        self.channel = socket.fromfd(fd, socket.AF_UNIX, socket.SOCK_STREAM)
        self.uid, self.domain, self.scope, self.source, self.budget = (
            uid,
            domain,
            scope,
            source,
            budget,
        )
        require(peer_uid(self.channel) == uid, "RUNTIME_PEER_UID")

    def call(self, method, body=None):
        require(method in METHODS[self.domain], "RUNTIME_METHOD")
        require(peer_uid(self.channel) == self.uid, "RUNTIME_PEER_UID")
        send_frame(
            self.channel,
            message(
                self.scope,
                self.source,
                self.budget,
                self.domain,
                method,
                {} if body is None else body,
            ).model_dump(),
        )
        result = read_frame(self.channel, time.monotonic_ns() + 200000000)
        require(peer_uid(self.channel) == self.uid, "RUNTIME_PEER_UID")
        return result

    def close(self):
        self.channel.close()


class PeerJournal:
    def __init__(self, client):
        self.client, self.domain = client, client.domain

    def _receipt(self, scope, event, raw):
        require(scope == self.client.scope, "JOURNAL_SCOPE")
        if self.domain == "writer_broker":
            r = checked(RuntimeReceipt, raw)
            require(
                r == runtime_receipt(self.domain, scope, event, r.sequence, r.record),
                "RUNTIME_RECEIPT_BINDING",
            )
            return r
        return verify_receipt(checked(Receipt, raw), self.domain, scope, event)

    def append(self, scope, event, record):
        require(self.domain == "consumer", "REMOTE_APPEND_DOMAIN")
        raw = self.client.call("journal-append", dict(event=event, record=record))
        return self._receipt(scope, event, raw)

    def read(self, scope, event):
        raw = self.client.call(
            "journal-read" if self.domain == "consumer" else "receipt", dict(event=event)
        )
        return self._receipt(scope, event, raw)

    def maybe_read(self, scope, event):
        raw = self.client.call(
            "journal-read" if self.domain == "consumer" else "receipt", dict(event=event)
        )
        require(type(raw) is dict, "JOURNAL_REPLY")
        if raw == {"event": event, "missing": True}:
            return None
        return self._receipt(scope, event, raw)
