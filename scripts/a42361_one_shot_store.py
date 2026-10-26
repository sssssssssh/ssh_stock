"""Deployable dedicated PostgreSQL transaction adapter. Never uses application settings."""

import os
import time
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field

from scripts.a4235_calibration_adapter_contract import Hash, Sha, Strict
from scripts.a4236_g1_harness_contract import UUID
from scripts.a42361_contract import Binding, Fault, canonical, checked, require, sha
from scripts.a42361_deployment import LocalReceiver, LocalService, installed
from scripts.a42361_trust_verifier import TrustVerifier, verified


class ReceiptLookup(Strict):
    token_id: UUID
    payload_sha256: Hash


class ConsumptionReceipt(ReceiptLookup):
    nonce: UUID
    approval_id: UUID
    head_sha: Sha
    run_id: Annotated[str, Field(pattern=r"^(local|[1-9][0-9]{0,23})$")]
    attempt: Annotated[int, Field(strict=True, ge=1, le=999999)]
    event: Literal["CONSUMED"]
    committed: Literal[True]
    control_instance_sha256: Hash


class ConsumeRequest(Strict):
    # Hex wrapping is only transport, never an alternative signature representation.
    envelope_hex: Annotated[str, Field(pattern=r"^(?:[0-9a-f]{2})+$", max_length=60000)]
    payload_sha256: Hash
    binding: Binding


class JournalRequest(ReceiptLookup):
    event: Literal["CREATE_REQUESTED", "SECRET_CREATED", "INCOMPLETE"]
    names: tuple[str, str, str]
    secret_id: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")] | None = None


def checked_journal(body):
    value = checked(JournalRequest, body)
    base, volume, secret = value.names
    require(
        base.startswith("a42361-")
        and len(base) == 39
        and all(c in "0123456789abcdef" for c in base[7:])
        and volume == base + "-data"
        and secret == base + "-owner-init"
        and (
            set(body) == {"event", "token_id", "payload_sha256", "names", "secret_id"}
            if value.event == "SECRET_CREATED"
            else set(body) == {"event", "token_id", "payload_sha256", "names"}
        )
        and (
            value.secret_id is not None
            if value.event == "SECRET_CREATED"
            else value.secret_id is None
        ),
        "A42361_JOURNAL_REJECTED",
    )
    return value


CONSUME_SQL = """
INSERT INTO g1_control.g1_consumptions
 (token_id, nonce, fixture_uuid, approval_id, payload_sha256,
  head_sha, run_id, attempt, committed_at)
SELECT %s::uuid, %s::uuid, %s::uuid, a.approval_id, a.payload_sha256,
 a.head_sha, a.run_id, a.attempt, clock_timestamp()
FROM g1_control.g1_approvals AS a
WHERE a.approval_id=%s::uuid AND a.payload_sha256=%s AND a.status='APPROVED'
 AND a.head_sha=%s AND a.run_id=%s AND a.attempt=%s AND a.expires_at>clock_timestamp()
ON CONFLICT DO NOTHING
RETURNING token_id::text, nonce::text, approval_id::text, payload_sha256,
 head_sha, run_id, attempt, committed_at::text
"""

_COMMITTED = object()


@dataclass(frozen=True)
class CommittedConsumption:
    grant: object
    receipt_sha256: str
    record: tuple
    independent_receipt: dict
    _seal: object


def committed(value):
    require(
        type(value) is CommittedConsumption and value._seal is _COMMITTED,
        "A42361_COMMITTED_CONSUMPTION_REQUIRED",
    )
    verified(value.grant)
    return value


def expected_receipt(grant, config):
    grant = verified(grant)
    p, identity = grant.payload, grant.payload.binding.identity
    return dict(
        event="CONSUMED",
        token_id=p.token_id,
        nonce=p.binding.nonce,
        approval_id=p.approval_id,
        payload_sha256=grant.payload_sha256,
        head_sha=identity.head_sha,
        run_id=identity.run_id,
        attempt=identity.attempt,
        control_instance_sha256=config.control_instance_sha256,
        committed=True,
    )


class PostgresConsumer:
    def __init__(self, deployment=None):
        self.deployment = deployment

    def _connect(self):
        config = installed(self.deployment)
        require(
            config.control_database.startswith("a42361_control_")
            and config.control_role == "g1_consumer"
            and os.getuid() == config.consumer.peer_uid
            and not any(
                k.startswith("PG") or k in ("DATABASE_URL", "TEST_DATABASE_URL") for k in os.environ
            ),
            "A42361_CONTROL_DATABASE_REJECTED",
        )
        # An independent owner attests isolation BEFORE any libpq connection attempt.
        attestation = LocalService(self.deployment, "pg_owner").call(
            "receipt",
            dict(purpose="CONTROL_PLANE_ISOLATION", instance_sha256=config.control_instance_sha256),
        )
        require(
            attestation
            == dict(
                purpose="CONTROL_PLANE_ISOLATION",
                instance_sha256=config.control_instance_sha256,
                pg_major=17,
                dedicated=True,
                business_databases=False,
                database=config.control_database,
            ),
            "A42361_CONTROL_DATABASE_REJECTED",
        )
        import psycopg

        return psycopg.connect(
            host=config.root_directory + "/" + config.control_socket_name,
            dbname=config.control_database,
            user=config.control_role,
            port=5432,
            password="",
            passfile="",
            sslmode="disable",
            connect_timeout=1,
            application_name="a42361-one-shot-consumer",
            options=(
                "-c statement_timeout=200 -c lock_timeout=100 -c search_path=g1_control,pg_catalog"
            ),
            autocommit=False,
        )

    def consume_once(self, grant):
        installed(self.deployment)  # Missing storage rejects before validation/connection.
        grant = verified(grant)
        connection = None
        try:
            connection = self._connect()
            return self.consume_transaction(grant, connection)
        except Fault:
            raise
        except Exception:
            raise Fault("A42361_PERSISTENT_CONSUMER_UNAVAILABLE") from None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    # Closing does not refund, invalidate or repeat a committed consumption.
                    pass

    def consume_transaction(self, grant, connection):
        """Protocol injection point: test connections prove ordering, not persistence.

        Production caller is consume_once(), whose connection comes only from _connect().
        This method never retries, returns on unknown commit, or creates a fixture.
        """
        config = installed(self.deployment)
        grant = verified(grant)
        p, identity = grant.payload, grant.payload.binding.identity
        commit_sent = False
        try:
            require(int(time.time()) < p.expires_at, "A42361_GRANT_EXPIRED")
            self._verify_connection(connection)
            # Lock the approval row against revocation until the consumption commits.
            connection.execute("SELECT g1_control.lock_approval(%s::uuid)", (p.approval_id,))
            parameters = (
                p.token_id,
                p.binding.nonce,
                p.binding.fixture_uuid,
                p.approval_id,
                grant.payload_sha256,
                identity.head_sha,
                identity.run_id,
                identity.attempt,
            )
            row = connection.execute(CONSUME_SQL, parameters).fetchone()
            require(row is not None and len(row) == 8, "A42361_GRANT_ALREADY_CONSUMED")
            require(
                tuple(row[:7])
                == (
                    p.token_id,
                    p.binding.nonce,
                    p.approval_id,
                    grant.payload_sha256,
                    identity.head_sha,
                    identity.run_id,
                    identity.attempt,
                ),
                "A42361_CONSUMPTION_IDENTITY_MISMATCH",
            )
            connection.execute(
                "INSERT INTO g1_control.g1_audit_events "
                "(token_id,event,payload_sha256) VALUES (%s::uuid,%s,%s)",
                (p.token_id, "CONSUMED", grant.payload_sha256),
            )
            # Immutable full payload for later resource reservations; control SQL, not probe SQL.
            connection.execute(
                "INSERT INTO g1_control.consumed_payloads(token_id,payload,payload_sha256) "
                "VALUES (%s::uuid,%s::jsonb,%s)",
                (p.token_id, canonical(p.model_dump()).decode(), grant.payload_sha256),
            )
            commit_sent = True
            connection.commit()  # No fixture may be constructed before this returns.
            # Fresh connection on B reads committed state. Never call our own RPC:
            # that deadlocks a single-request receiver. No reader sees writer state.
            receipt = self._fresh_receipt(
                ReceiptLookup(token_id=p.token_id, payload_sha256=grant.payload_sha256), connection
            )
            require(
                receipt == expected_receipt(grant, config),
                "A42361_COMMIT_ACK_UNTRUSTED",
            )
            require(int(time.time()) < p.expires_at, "A42361_GRANT_EXPIRED")
            return CommittedConsumption(
                grant, sha(canonical(receipt)), tuple(row), receipt, _COMMITTED
            )
        except BaseException as error:
            try:
                connection.rollback()
            except Exception:
                pass  # Unknown state remains consumed/unknown: NEVER retry or create.
            if commit_sent:
                raise Fault("A42361_COMMIT_UNKNOWN_NO_RETRY") from None
            raise Fault(
                error.code if isinstance(error, Fault) else "A42361_CONSUME_FAILED_NO_RETRY"
            ) from None

    def _verify_connection(self, connection):
        config = installed(self.deployment)
        actual = connection.execute(
            "SELECT current_database(), current_user, "
            "current_setting('server_version_num')::int, "
            "instance_sha256, purpose FROM g1_control.instance_identity WHERE singleton"
        ).fetchone()
        require(
            type(actual) in (tuple, list)
            and len(actual) == 5
            and type(actual[2]) is int
            and 170000 <= actual[2] < 180000
            and tuple(actual)
            == (
                config.control_database,
                config.control_role,
                actual[2],
                config.control_instance_sha256,
                "G1_CONTROL_PLANE_ONLY",
            ),
            "A42361_CONTROL_DATABASE_REJECTED",
        )

    def read_receipt(self, token_id, payload_sha256):
        """Each read gets its own re-attested connection, never an in-memory success."""
        installed(self.deployment)
        lookup = checked(ReceiptLookup, dict(token_id=token_id, payload_sha256=payload_sha256))
        return self._fresh_receipt(lookup)

    def _fresh_receipt(self, lookup, previous=None):
        connection = None
        try:
            connection = self._connect()
            require(connection is not previous, "A42361_COMMIT_ACK_UNTRUSTED")
            self._verify_connection(connection)
            row = connection.execute(
                "SELECT token_id::text, nonce::text, approval_id::text, payload_sha256, "
                "head_sha, run_id, attempt FROM g1_control.g1_consumptions "
                "WHERE token_id=%s::uuid AND payload_sha256=%s",
                (lookup.token_id, lookup.payload_sha256),
            ).fetchone()
            require(
                type(row) in (tuple, list)
                and len(row) == 7
                and row[0] == lookup.token_id
                and row[3] == lookup.payload_sha256,
                "A42361_COMMIT_ACK_UNTRUSTED",
            )
            result = dict(
                zip(
                    (
                        "token_id",
                        "nonce",
                        "approval_id",
                        "payload_sha256",
                        "head_sha",
                        "run_id",
                        "attempt",
                    ),
                    row,
                    strict=True,
                ),
                event="CONSUMED",
                committed=True,
                control_instance_sha256=installed(self.deployment).control_instance_sha256,
            )
            return checked(ConsumptionReceipt, result).model_dump()
        except Fault:
            raise
        except Exception:
            raise Fault("A42361_COMMIT_ACK_UNTRUSTED") from None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    raise Fault("A42361_COMMIT_ACK_UNTRUSTED") from None

    def append_journal(self, body):
        installed(self.deployment)
        checked_journal(body)  # Before connecting to any database.
        connection = None
        try:
            connection = self._connect()
            return self.journal_transaction(body, connection)
        except Fault:
            raise
        except Exception:
            raise Fault("A42361_JOURNAL_REJECTED") from None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass  # Cannot uncommit an audit stage or grant another attempt.

    def _fresh_journal(self, body, previous):
        connection = None
        try:
            connection = self._connect()
            require(connection is not previous, "A42361_COMMIT_ACK_UNTRUSTED")
            self._verify_connection(connection)
            row = connection.execute(
                "SELECT details FROM g1_control.g1_audit_events "
                "WHERE token_id=%s::uuid AND payload_sha256=%s AND event=%s",
                (body["token_id"], body["payload_sha256"], body["event"]),
            ).fetchone()
            require(
                type(row) in (tuple, list)
                and len(row) == 1
                and canonical(row[0]) == canonical(body),
                "A42361_COMMIT_ACK_UNTRUSTED",
            )
            return dict(event=body["event"], request_sha256=sha(canonical(body)), committed=True)
        finally:
            if connection is not None:
                connection.close()

    def journal_transaction(self, body, connection):
        """Atomic per-token stage reservation, append-only; NEVER authorizes a retry."""
        installed(self.deployment)
        checked_journal(body)
        allowed = {
            "CREATE_REQUESTED": "CONSUMED",
            "SECRET_CREATED": "CREATE_REQUESTED",
            "INCOMPLETE": "CREATE_REQUESTED",
        }
        require(
            type(body) is dict
            and body.get("event") in allowed
            and set(body)
            in (
                {"event", "token_id", "payload_sha256", "names"},
                {"event", "token_id", "payload_sha256", "names", "secret_id"},
            ),
            "A42361_JOURNAL_REJECTED",
        )
        raw = canonical(body)
        sent = False
        try:
            self._verify_connection(connection)
            row = connection.execute(
                "INSERT INTO g1_control.g1_audit_events(token_id,event,payload_sha256,details) "
                "SELECT c.token_id,%s,c.payload_sha256,%s::jsonb FROM g1_control.g1_consumptions c "
                "WHERE c.token_id=%s::uuid AND c.payload_sha256=%s AND EXISTS "
                "(SELECT 1 FROM g1_control.g1_audit_events e WHERE e.token_id=c.token_id "
                "AND e.event=%s) AND %s='a42361-' || replace(c.fixture_uuid::text,'-','') "
                "ON CONFLICT DO NOTHING RETURNING event_id",
                (
                    body["event"],
                    raw.decode(),
                    body["token_id"],
                    body["payload_sha256"],
                    allowed[body["event"]],
                    body["names"][0],
                ),
            ).fetchone()
            require(row is not None, "A42361_RESOURCE_ALREADY_RESERVED")
            sent = True
            connection.commit()
            return self._fresh_journal(body, connection)
        except BaseException as error:
            try:
                connection.rollback()
            except Exception:
                pass
            raise Fault(
                "A42361_COMMIT_UNKNOWN_NO_RETRY"
                if sent
                else error.code
                if isinstance(error, Fault)
                else "A42361_JOURNAL_REJECTED"
            ) from None


class ConsumerService(LocalReceiver):
    """B-side receiver implementation; no public CLI or automatic service activation.

    Only D may consume. C may reserve resources; C/owner/E/D may read receipts.
    Peer UID comes from SO_PEERCRED in serve_once, never from request JSON.
    """

    domain = "consumer"

    def __init__(self, deployment=None, policy=None):
        super().__init__(deployment)
        self.policy = policy

    def allowed_uids(self, config):
        return {
            getattr(config, k).peer_uid
            for k in ("supervisor", "controller", "pg_owner", "absence_auditor")
        }

    def dispatch(self, peer_uid, method, body):
        config = installed(self.deployment)
        require(os.getuid() == config.consumer.peer_uid, "A42361_SERVICE_PRINCIPAL_MISMATCH")
        require(type(peer_uid) is int, "A42361_PEER_IDENTITY_MISMATCH")
        require(method in ("consume", "receipt", "journal", "resource-append", "resource-scan"),
                "A42361_RPC_METHOD_REJECTED")
        allowed = (
            {config.supervisor.peer_uid}
            if method == "consume"
            else {config.controller.peer_uid}
            if method in ("journal", "resource-append")
            else self.allowed_uids(config)
        )
        require(peer_uid in allowed, "A42361_PEER_IDENTITY_MISMATCH")
        if method in ("resource-append", "resource-scan"):
            from scripts.a42362_ledger import ResourceLedger
            from scripts.a42362_service_host import ControlRepository, installation

            installation(self.policy)  # No repository/connection from an uninstalled receiver.
            ledger = ResourceLedger(ControlRepository(self.policy))
            return ledger.append(body) if method == "resource-append" else ledger.scan(body)
        consumer = PostgresConsumer(self.deployment)
        if method == "consume":
            request = checked(ConsumeRequest, body)
            from scripts.a42361_source_guard import independent_binding

            b = request.binding
            expected = independent_binding(
                b.identity.run_id, b.identity.attempt, b.fixture_uuid, b.nonce, b.marker_sha256
            )
            require(b == expected, "A42361_SOURCE_DRIFT")
            grant = TrustVerifier(self.deployment).verify_signature(
                bytes.fromhex(request.envelope_hex), expected
            )
            require(grant.payload_sha256 == request.payload_sha256, "A42361_BINDING_MISMATCH")
            result = consumer.consume_once(grant)
            return dict(receipt_sha256=result.receipt_sha256, committed=True)
        if method == "receipt":
            request = checked(ReceiptLookup, body)
            return consumer.read_receipt(request.token_id, request.payload_sha256)
        checked_journal(body)
        return consumer.append_journal(body)
