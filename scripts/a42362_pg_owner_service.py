"""Owner planning and raw identity validation; target-session GUC method remains blocked."""

import os
from typing import Literal

from scripts.a4235_calibration_adapter_contract import Strict
from scripts.a42361_contract import checked
from scripts.a42362_contract import Fault, Lookup, Scope, require

INIT_STEPS = (
    "REVOKE_DATABASE_PUBLIC",
    "REVOKE_SCHEMA_PUBLIC",
    "CREATE_RESTRICTED_ROLE",
    "REVOKE_DEFAULT_FUNCTION_EXECUTE",
    "GRANT_CONNECT_ONLY",
    "CONFIGURE_READ_ONLY",
    "CONFIGURE_TIMEOUT",
    "AUDIT_ROLE_ACL",
)


class MethodDecision(Strict):
    status: Literal["METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION"] = (
        "METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION"
    )
    session_guc: Literal["CONFIGURED_NOT_INDEPENDENTLY_OBSERVED"] = (
        "CONFIGURED_NOT_INDEPENDENTLY_OBSERVED"
    )
    additional_probe_sql: Literal[0] = 0
    probe_sql_budget: Literal[16] = 16
    initialization_max_sql: Literal[8] = 8
    code_ready: Literal[False] = False


def require_session_method():
    # PQparameterStatus does not report statement_timeout. Another backend's SHOW
    # cannot prove the probe's session. No approved replacement template exists.
    raise Fault("A42362_METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION")


def verify_raw_owner_identity(value, scope):
    scope = checked(Scope, scope)
    require(
        type(value) is dict
        and set(value)
        == {
            "pg_major",
            "system_identifier_sha256",
            "image_digest",
            "namespace_sha256",
            "marker_sha256",
            "fixture_uuid",
            "nonce",
            "container_id",
            "volume_id",
            "role_audit",
            "initialization_sql",
            "initialization_commands",
            "initialization_ms",
        },
        "A42362_OWNER_RAW_PROOF_REQUIRED",
    )
    require(
        value["pg_major"] == 17
        and value["image_digest"] == scope.image_digest
        and value["namespace_sha256"] == scope.namespace_sha256
        and value["marker_sha256"] == scope.binding.marker_sha256
        and value["fixture_uuid"] == scope.binding.fixture_uuid
        and value["nonce"] == scope.binding.nonce,
        "A42362_OWNER_IDENTITY_MISMATCH",
    )
    require(
        all(
            type(value[k]) is int and 0 < value[k] <= limit
            for k, limit in (
                ("initialization_sql", 8),
                ("initialization_commands", 12),
                ("initialization_ms", 2000),
            )
        ),
        "A42362_INIT_BUDGET_INFEASIBLE",
    )
    expected = dict(
        superuser=False,
        createdb=False,
        createrole=False,
        inherit=False,
        bypassrls=False,
        replication=False,
        memberships=[],
        public_write=False,
        public_execute=False,
        business_read=False,
        maintain=False,
        ddl=False,
        dml=False,
    )
    require(value["role_audit"] == expected, "A42362_ROLE_PRIVILEGES_UNPROVEN")
    require(
        all(
            type(value[k]) is str and value[k]
            for k in ("system_identifier_sha256", "container_id", "volume_id")
        ),
        "A42362_OWNER_RAW_PROOF_REQUIRED",
    )
    return dict(
        identity=value, session_guc=MethodDecision().session_guc, execution_authorized=False
    )


class PgOwnerService:
    def __init__(self, installation=None, owner_backend=None):
        self.installation, self.owner_backend = installation, owner_backend

    def dispatch(self, peer_uid, method, body):
        from scripts.a42362_service_host import installation

        c = installation(self.installation)
        require(
            c.domain == "pg_owner" and os.getuid() == c.uid and peer_uid in c.read_uids,
            "A42362_PEER_REJECTED",
        )
        require(method in ("create", "receipt", "run"), "A42362_METHOD_REJECTED")
        if method == "run":
            # Before issuing a credential or opening any connection.
            require_session_method()
        q = checked(Lookup, body)
        require(self.owner_backend is not None, "A42362_OWNER_SERVICE_NOT_CONFIGURED")
        require(
            peer_uid == c.controller_uid if method == "create" else True, "A42362_PEER_REJECTED"
        )
        # A raw backend must provide real metadata/ACLs, not request JSON echoes.
        raw = (
            self.owner_backend.initialize(q.scope)
            if method == "create"
            else self.owner_backend.inspect(q.scope)
        )
        return verify_raw_owner_identity(raw, q.scope)
