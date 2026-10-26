"""Append-only PostgreSQL resource ledger; fresh reads after commit, no create retry."""

import json

from scripts.a42361_contract import canonical, checked, sha
from scripts.a42362_contract import (
    Fault,
    LedgerRequest,
    Lookup,
    close_receipt,
    receipt,
    require,
    resource,
    transition,
    validate_receipt,
)


class ResourceLedger:
    def __init__(self, repository=None):
        self.repository = repository

    def _repository(self):
        require(self.repository is not None, "A42362_LEDGER_NOT_CONFIGURED")
        return self.repository

    def append(self, body):
        request = checked(LedgerRequest, body)
        resource(request.resource)
        repo = self._repository()
        repo.verify_scope(request.resource.scope)
        connection, sent = None, False
        try:
            connection = repo.connect("consumer")
            repo.verify(connection, "consumer")
            s = request.resource.scope
            row = connection.execute(
                "SELECT payload_sha256,fixture_uuid::text,nonce::text,head_sha,run_id,attempt "
                "FROM g1_control.g1_consumptions WHERE token_id=%s::uuid FOR UPDATE",
                (s.token_id,),
            ).fetchone()
            i = s.binding.identity
            require(
                row is not None
                and tuple(row)
                == (
                    s.payload_sha256,
                    s.binding.fixture_uuid,
                    s.binding.nonce,
                    i.head_sha,
                    i.run_id,
                    i.attempt,
                ),
                "A42362_CONSUMPTION_REQUIRED",
            )
            previous = connection.execute(
                "SELECT request FROM g1_control.resource_events WHERE token_id=%s::uuid "
                "AND resource_kind=%s AND resource_name=%s ORDER BY sequence DESC LIMIT 1",
                (s.token_id, request.resource.kind, request.resource.name),
            ).fetchone()
            if previous:
                old = checked(LedgerRequest, previous[0])
                require(old.resource == request.resource, "A42362_IMMUTABLE_OWNERSHIP_CHANGED")
            transition(old.event if previous else None, request)
            row = connection.execute(
                "INSERT INTO g1_control.resource_events "
                "(event_id,token_id,resource_kind,resource_name,event,request,request_sha256) "
                "VALUES (%s::uuid,%s::uuid,%s,%s,%s,%s::jsonb,%s) ON CONFLICT DO NOTHING "
                "RETURNING sequence,committed_at::text",
                (
                    request.event_id,
                    s.token_id,
                    request.resource.kind,
                    request.resource.name,
                    request.event,
                    canonical(request.model_dump()).decode(),
                    sha(canonical(request.model_dump())),
                ),
            ).fetchone()
            require(row is not None, "A42362_RESOURCE_EVENT_REPLAY")
            sent = True
            connection.commit()
            result = self.read_event(request, previous=connection)
            require(result.sequence == row[0], "A42362_COMMIT_RECEIPT_UNTRUSTED")
            return result.model_dump()
        except BaseException as error:
            if connection is not None:
                try:
                    connection.rollback()
                except Exception:
                    pass
            if sent:
                raise Fault("A42362_COMMIT_UNKNOWN_NO_RETRY") from None
            if isinstance(error, Fault):
                raise
            raise Fault("A42362_LEDGER_REJECTED") from None
        finally:
            if connection is not None:
                close_receipt(connection)

    def read_event(self, request, previous=None):
        request = checked(LedgerRequest, request)
        repo = self._repository()
        c = repo.connect("receipt_reader")
        try:
            require(c is not previous, "A42362_WRITER_CONNECTION_REUSED")
            repo.verify(c, "receipt_reader")
            row = c.execute(
                "SELECT request,sequence,committed_at::text FROM g1_control.resource_events "
                "WHERE event_id=%s::uuid AND token_id=%s::uuid",
                (request.event_id, request.resource.scope.token_id),
            ).fetchone()
            require(row is not None and len(row) == 3, "A42362_COMMIT_RECEIPT_MISSING")
            result = receipt(row[0], row[1], row[2], repo.instance_sha256)
            return validate_receipt(result, request)
        finally:
            close_receipt(c)

    def scan(self, body):
        value = checked(Lookup, body)
        repo = self._repository()
        repo.verify_scope(value.scope)
        c = repo.connect("receipt_reader")
        try:
            repo.verify(c, "receipt_reader")
            rows = c.execute(
                "SELECT request,sequence,committed_at::text FROM g1_control.resource_events "
                "WHERE token_id=%s::uuid ORDER BY sequence LIMIT 25",
                (value.scope.token_id,),
            ).fetchall()
            require(len(rows) <= 24, "A42362_LEDGER_LIMIT")
            result = []
            for row in rows:
                r = receipt(row[0], row[1], row[2], repo.instance_sha256)
                require(r.request.resource.scope == value.scope, "A42362_LEDGER_BINDING_MISMATCH")
                result.append(r.model_dump())
            return dict(events=result, snapshot_sha256=sha(canonical(result)))
        finally:
            close_receipt(c)


def parse_rows(raw):
    """Driver JSONB is structured data; never accept caller-supplied SQL or DSN."""
    return json.loads(raw) if isinstance(raw, str) else raw
