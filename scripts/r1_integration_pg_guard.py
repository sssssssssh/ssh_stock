"""Explicit DB-API connector boundary. Never reads environment or builds an engine.

The external verifier MUST establish a dedicated, local, non-tunnel, non-RDS
instance out of band. Server observations alone cannot prove physical isolation.
Receipts are local capabilities bound to this guard object, not signed approvals.
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from scripts.r1_business_snapshot_contract import typed
from scripts.r1_integration_evidence import label, sha
from scripts.r1_real_root_protocol import Refused, require

BEGIN_SQL = "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY"
IDENTITY_SQL = """SELECT current_setting('server_version_num')::integer,
 (SELECT system_identifier::text FROM pg_control_system()),
 current_setting('r1.lab_marker', true),
 (SELECT oid::bigint FROM pg_database WHERE datname=current_database()),
 pg_postmaster_start_time(), current_database(), current_user,
 r.rolsuper, r.rolcreatedb, r.rolcreaterole, r.rolreplication, r.rolbypassrls,
 pg_is_in_recovery(),
 ARRAY(SELECT p.rolname FROM pg_auth_members m JOIN pg_roles p ON p.oid=m.roleid
       WHERE m.member=r.oid ORDER BY p.rolname),
 current_setting('r1.lab_environment', true),
 (NOT has_database_privilege(current_user,current_database(),'CREATE')
  AND NOT has_database_privilege(current_user,current_database(),'TEMP')
  AND NOT has_schema_privilege(current_user,'public','CREATE')
  AND NOT EXISTS (SELECT 1 FROM information_schema.role_table_grants
    WHERE grantee=current_user AND privilege_type <> 'SELECT'))
 FROM pg_roles r WHERE r.rolname=current_user"""


@dataclass(frozen=True)
class ReviewedTarget:
    config_ref: str = field(repr=False)
    system_identifier: str = field(repr=False)
    marker: UUID = field(repr=False)
    database_oid: int = field(repr=False)
    postmaster_start: datetime = field(repr=False)
    database_name: str = field(repr=False)
    role: str = field(repr=False)
    environment: UUID = field(repr=False)
    owner_scope: str


def review_binding(target):
    """Expected external attestation payload; computing it is not approval."""
    return sha({k: getattr(target, k) for k in target.__dataclass_fields__})


def validate_target(t):
    require(type(t) is ReviewedTarget, "PG_EXPLICIT_CONFIG_REQUIRED")
    for item in (t.config_ref, t.owner_scope, t.database_name, t.role):
        label(item)
    require(
        t.database_name.startswith("r1_") and t.database_name.endswith("_test"),
        "PG_EXPERIMENT_DATABASE_REQUIRED",
    )
    require(
        type(t.system_identifier) is str
        and t.system_identifier.isdecimal()
        and len(t.system_identifier) >= 10,
        "PG_PHYSICAL_ID_REQUIRED",
    )
    require(
        type(t.marker) is UUID
        and type(t.environment) is UUID
        and type(t.database_oid) is int
        and t.database_oid > 0,
        "PG_IDENTITY_UNKNOWN",
    )
    require(type(t.postmaster_start) is datetime, "PG_IDENTITY_UNKNOWN")
    typed(t.postmaster_start)


@dataclass(frozen=True)
class GuardReceipt:
    target_digest: str
    physical_digest: str
    owner_scope: str
    evidence_kind: str
    isolation_proven: bool = False


class Pg17ResourceGuard:
    def __init__(self, external_verifier, *, evidence_kind="UNVERIFIED"):
        require(callable(external_verifier), "PG_EXTERNAL_REVIEW_REQUIRED")
        require(evidence_kind in ("FAKE", "UNVERIFIED"), "PG_EVIDENCE_KIND")
        self.verify, self.evidence_kind, self.issued = external_verifier, evidence_kind, []

    def preconnect(self, target):
        validate_target(target)
        # Verifier is supplied by a future independent operator. No production
        # verifier/token implementation is shipped in this development slice.
        require(self.verify(target) == review_binding(target), "PG_EXTERNAL_REVIEW_REQUIRED")

    def check_connection(self, connection, target):
        """Caller owns the transaction. Each new connection must be checked."""
        self.preconnect(target)
        cur = connection.cursor()
        try:
            cur.execute(IDENTITY_SQL)
            row = cur.fetchone()
            expected = (
                170000,
                target.system_identifier,
                str(target.marker),
                target.database_oid,
                target.postmaster_start,
                target.database_name,
                target.role,
                False,
                False,
                False,
                False,
                False,
                False,
                [],
                str(target.environment),
                True,
            )
            require(type(row) in (tuple, list) and len(row) == len(expected), "PG_IDENTITY_UNKNOWN")
            require(type(row[0]) is int and row[0] // 10000 == 17, "PG_IDENTITY_MISMATCH")
            for actual, want in zip(row[1:], expected[1:], strict=True):
                require(type(actual) is type(want) and actual == want, "PG_IDENTITY_MISMATCH")
            return sha(tuple(row))
        finally:
            cur.close()

    def inspect(self, connector, expected_identity, *, readonly=True):
        self.preconnect(expected_identity)
        require(readonly is True and callable(connector), "PG_READONLY_REQUIRED")
        connection = None
        try:
            connection = connector(expected_identity.config_ref)
            cur = connection.cursor()
            try:
                cur.execute(BEGIN_SQL)
            finally:
                cur.close()
            observed = self.check_connection(connection, expected_identity)
            result = GuardReceipt(
                review_binding(expected_identity),
                sha(
                    (
                        expected_identity.system_identifier,
                        expected_identity.database_oid,
                        expected_identity.postmaster_start,
                        observed,
                    )
                ),
                expected_identity.owner_scope,
                self.evidence_kind,
            )
            # A receipt is issued only after all close/rollback acknowledgements.
            connection.rollback()
            connection.close()
            connection = None
            self.issued.append(result)
            return result
        except Refused:
            raise
        except Exception:
            raise Refused("PG_INSPECTION_INCOMPLETE") from None
        finally:
            if connection is not None:
                try:
                    connection.rollback()
                    connection.close()
                except Exception:
                    raise Refused("PG_CLEANUP_UNCERTAIN") from None

    def require_ready(self, receipt, owner_scope):
        require(
            any(receipt is r for r in self.issued) and receipt.owner_scope == owner_scope,
            "PG_RECEIPT_NOT_OWNED",
        )
        return receipt
