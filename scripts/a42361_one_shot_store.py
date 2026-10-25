"""Deployable dedicated PostgreSQL transaction adapter. Never uses application settings."""

import os
import time
from dataclasses import dataclass

from scripts.a42361_contract import Fault, canonical, require, sha
from scripts.a42361_deployment import LocalService, installed
from scripts.a42361_trust_verifier import verified

CONSUME_SQL = """
INSERT INTO g1_control.g1_consumptions
 (token_id, nonce, approval_id, payload_sha256, head_sha, run_id, attempt, committed_at)
SELECT %s::uuid, %s::uuid, a.approval_id, a.payload_sha256, a.head_sha, a.run_id, a.attempt,
 clock_timestamp()
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
            actual = connection.execute(
                "SELECT current_database(), current_user, "
                "current_setting('server_version_num')::int, "
                "instance_sha256, purpose FROM g1_control.instance_identity WHERE singleton"
            ).fetchone()
            require(
                actual
                == (
                    config.control_database,
                    config.control_role,
                    actual[2],
                    config.control_instance_sha256,
                    "G1_CONTROL_PLANE_ONLY",
                )
                and 170000 <= actual[2] < 180000,
                "A42361_CONTROL_DATABASE_REJECTED",
            )
            # Lock the approval row against revocation until the consumption commits.
            connection.execute("SELECT g1_control.lock_approval(%s::uuid)", (p.approval_id,))
            parameters = (
                p.token_id,
                p.binding.nonce,
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
            commit_sent = True
            connection.commit()  # No fixture may be constructed before this returns.
            # Independent consumer RPC reads COMMITTED state, not this connection's row.
            receipt = LocalService(self.deployment, "consumer").call(
                "receipt", dict(token_id=p.token_id, payload_sha256=grant.payload_sha256)
            )
            require(
                receipt
                == dict(
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
                ),
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

    def read_receipt(self, token_id, payload_sha256):
        """Fresh committed-state read. Hosted separately from transaction RPC workers."""
        installed(self.deployment)
        connection = None
        try:
            connection = self._connect()
            row = connection.execute(
                "SELECT token_id::text, nonce::text, approval_id::text, payload_sha256, "
                "head_sha, run_id, attempt FROM g1_control.g1_consumptions "
                "WHERE token_id=%s::uuid AND payload_sha256=%s",
                (token_id, payload_sha256),
            ).fetchone()
            require(row is not None and len(row) == 7, "A42361_COMMIT_ACK_UNTRUSTED")
            return dict(
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
        except Fault:
            raise
        except Exception:
            raise Fault("A42361_COMMIT_ACK_UNTRUSTED") from None
        finally:
            if connection is not None:
                connection.close()

    def journal_transaction(self, body, connection):
        """Atomic per-token stage reservation, append-only; NEVER authorizes a retry."""
        installed(self.deployment)
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
            row = connection.execute(
                "INSERT INTO g1_control.g1_audit_events(token_id,event,payload_sha256,details) "
                "SELECT c.token_id,%s,c.payload_sha256,%s::jsonb FROM g1_control.g1_consumptions c "
                "WHERE c.token_id=%s::uuid AND c.payload_sha256=%s AND EXISTS "
                "(SELECT 1 FROM g1_control.g1_audit_events e WHERE e.token_id=c.token_id "
                "AND e.event=%s) ON CONFLICT DO NOTHING RETURNING event_id",
                (
                    body["event"],
                    raw.decode(),
                    body["token_id"],
                    body["payload_sha256"],
                    allowed[body["event"]],
                ),
            ).fetchone()
            require(row is not None, "A42361_RESOURCE_ALREADY_RESERVED")
            sent = True
            connection.commit()
            return dict(event=body["event"], request_sha256=sha(raw), committed=True)
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
