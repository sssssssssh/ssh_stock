"""Dedicated PostgreSQL domain journals. Never application DSNs or auto-provisioning."""

import sys
from contextlib import contextmanager

from scripts.a42361_contract import canonical, checked
from scripts.a42362_contract import close_receipt
from scripts.a42363_contract import DOMAINS, Fault, Receipt, receipt, require, scope_hash


class DomainStore:
    def __init__(self, domain, repository):
        require(domain in DOMAINS, "DOMAIN")
        self.domain, self.repository = domain, repository

    def append(self, scope, event, record):
        require(type(event) is str and event.isascii() and 0 < len(event) <= 64, "EVENT")
        writer, sent = self.repository.connect(self.domain), False
        try:
            self.repository.verify(writer, self.domain)
            # Fixed SQL; DB derives domain from session_user, rejects cross-domain writes.
            row = writer.execute(
                "SELECT sequence FROM g1_control.append_domain_event(%s,%s,%s,%s::jsonb)",
                (scope_hash(scope), scope.epoch, event, canonical(record).decode()),
            ).fetchone()
            require(row is not None and type(row[0]) is int, "JOURNAL_INSERT")
            sent = True
            writer.commit()
            fresh = self.read(scope, event, previous=writer)
            require(
                fresh.sequence == row[0] and canonical(fresh.record) == canonical(record),
                "JOURNAL_ACK_UNKNOWN",
            )
            return fresh
        except BaseException as error:
            try:
                writer.rollback()
            except BaseException:
                pass
            if sent:
                raise Fault("A42363_JOURNAL_COMMIT_UNKNOWN_NO_RETRY") from None
            if isinstance(error, Fault):
                raise
            raise Fault("A42363_JOURNAL_REJECTED") from None
        finally:
            close_receipt(writer)

    def read(self, scope, event, previous=None):
        reader = self.repository.connect("receipt_reader")
        try:
            require(reader is not previous, "WRITER_CONNECTION_REUSED")
            self.repository.verify(reader, "receipt_reader")
            row = reader.execute(
                "SELECT sequence,record FROM g1_control.domain_events WHERE domain=%s "
                "AND scope_sha256=%s AND epoch=%s::uuid AND event=%s "
                "ORDER BY sequence DESC LIMIT 1",
                (self.domain, scope_hash(scope), scope.epoch, event),
            ).fetchone()
            require(row is not None and len(row) == 2, "COMMITTED_RECEIPT_MISSING")
            return receipt(self.domain, scope, event, row[0], row[1])
        finally:
            close_receipt(reader)

    def maybe_read(self, scope, event):
        try:
            return self.read(scope, event)
        except Fault as error:
            if error.code == "A42363_COMMITTED_RECEIPT_MISSING":
                return None
            raise

    @contextmanager
    def lock(self, scope):
        require(self.domain == "controller", "SCOPE_LOCK_DOMAIN")
        connection = self.repository.connect(self.domain)
        try:
            self.repository.verify(connection, self.domain)
            row = connection.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s,42363))", (scope_hash(scope),)
            ).fetchone()
            require(row == (True,), "SCOPE_ALREADY_ACTIVE")
            yield
        finally:
            first = sys.exception()
            try:
                # Close releases this session's advisory lock; never retry an operation.
                close_receipt(connection)
            except BaseException:
                if first is None:
                    raise


class ReceiptSet:
    """References are fetched independently from each domain; never trust bundle JSON."""

    def __init__(self, sources):
        require(set(sources) == set(DOMAINS) - {"registry"}, "SIX_SOURCES_REQUIRED")
        self.sources = dict(sources)

    def fetch(self, scope, references):
        require(set(references) == set(self.sources), "SIX_REFERENCES_REQUIRED")
        result = {}
        for domain, source in self.sources.items():
            ref = checked(Receipt, references[domain])
            actual = source.read(scope, ref.event)
            require(actual == ref, "INDEPENDENT_RECEIPT_MISMATCH")
            result[domain] = actual
        return result
