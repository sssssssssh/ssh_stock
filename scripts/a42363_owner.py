"""Raw PG17 Owner adapter and deliberately unapproved target-session method."""

import os
import time

from scripts.a42361_contract import canonical, checked, sha
from scripts.a42362_contract import Scope
from scripts.a42362_pg_owner_service import verify_raw_owner_identity
from scripts.a42363_contract import require, session_method

# Only a future installed owner connection can execute these fixed initialization steps.
# No application connection, provider data or caller SQL is accepted.
INIT_SQL = (
    "REVOKE ALL ON DATABASE a42363_fixture FROM PUBLIC",
    "REVOKE ALL ON SCHEMA public FROM PUBLIC",
    "CREATE ROLE a42363_probe LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
    "NOINHERIT NOBYPASSRLS NOREPLICATION",
    "ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC",
    "GRANT CONNECT ON DATABASE a42363_fixture TO a42363_probe",
    "ALTER ROLE a42363_probe SET default_transaction_read_only=on",
    "ALTER ROLE a42363_probe SET statement_timeout='100ms'",
    "SELECT current_setting('server_version_num')::int,system_identifier::text,"
    "rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolbypassrls,rolreplication,"
    "ARRAY(SELECT r.rolname FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid "
    "WHERE m.member=p.oid),has_database_privilege(p.oid,current_database(),'CREATE'),"
    "has_schema_privilege(p.oid,'public','CREATE'),"
    "EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
    "WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' "
    "AND (has_table_privilege(p.oid,c.oid,'SELECT') OR has_table_privilege(p.oid,c.oid,'INSERT') "
    "OR has_table_privilege(p.oid,c.oid,'UPDATE') OR has_table_privilege(p.oid,c.oid,'DELETE'))),"
    "EXISTS(SELECT 1 FROM pg_proc f JOIN pg_namespace n ON n.oid=f.pronamespace "
    "WHERE n.nspname='public' AND has_function_privilege(p.oid,f.oid,'EXECUTE')) "
    "FROM pg_control_system(),pg_roles p WHERE p.rolname='a42363_probe'",
)


class OwnerRuntime:
    """Raw runtime inspector and dedicated control-plane isolation receiver backend."""

    def __init__(self, driver, control_connection, control_database, control_instance_sha256):
        self.driver, self.control_connection = driver, control_connection
        self.control_database, self.control_instance_sha256 = (
            control_database,
            control_instance_sha256,
        )

    def inspect_control(self):
        connection = self.control_connection()
        try:
            row = connection.execute(
                "SELECT current_database(),current_setting('server_version_num')::int,"
                "instance_sha256,purpose,ARRAY(SELECT datname FROM pg_database "
                "WHERE datallowconn AND NOT datistemplate ORDER BY datname) "
                "FROM g1_control.instance_identity WHERE singleton"
            ).fetchone()
            require(
                row is not None
                and len(row) == 5
                and row[0] == self.control_database
                and 170000 <= row[1] < 180000
                and row[2] == self.control_instance_sha256
                and row[3] == "G1_CONTROL_PLANE_ONLY"
                and set(row[4]) <= {self.control_database, "postgres"},
                "CONTROL_ISOLATION_UNPROVEN",
            )
            return dict(
                purpose="CONTROL_PLANE_ISOLATION",
                instance_sha256=row[2],
                pg_major=17,
                dedicated=True,
                business_databases=False,
                database=row[0],
            )
        finally:
            connection.close()

    def verify_owner_connection(self, connection, scope):
        require(
            connection.info.dbname == "a42363_fixture"
            and connection.info.user == "postgres"
            and connection.info.host.startswith("/")
            and connection.info.port == 5432,
            "OWNER_CONNECTION_IDENTITY",
        )
        self.inspect_owner(scope)

    def inspect_owner(self, scope):
        from scripts.a42362_contract import resources

        values = {item.kind: self.driver.inspect(item) for item in resources(scope)}
        for item in resources(scope):
            self.driver.verify(item, values[item.kind])
        container, volume = values["CONTAINER"], values["VOLUME"]
        return dict(
            image_digest=scope.image_digest,
            namespace_sha256=scope.namespace_sha256,
            marker_sha256=scope.binding.marker_sha256,
            fixture_uuid=scope.binding.fixture_uuid,
            nonce=scope.binding.nonce,
            container_id=container.get("ID", container.get("Id")),
            volume_id=sha(canonical(volume)),
            initialization_commands=self.driver.commands.count,
        )


class RawOwnerBackend:
    """Concrete transformation of connection/Podman raw facts, never request JSON echoes.

    connection_factory and runtime are manager-installed capabilities. Tests inject a
    DB_MODEL_ONLY driver; that does not constitute an actual PG identity proof.
    """

    def __init__(self, connection_factory, runtime, store):
        self.connection_factory, self.runtime, self.store = connection_factory, runtime, store

    def initialize(self, scope):
        scope = checked(Scope, scope)
        started = time.monotonic_ns()
        connection = self.connection_factory(scope)
        try:
            self.runtime.verify_owner_connection(connection, scope)
            for statement in INIT_SQL:
                cursor = connection.execute(statement)
            row = cursor.fetchone()
            connection.commit()
        finally:
            connection.close()
        require(row is not None and len(row) == 13, "OWNER_RAW_ROW")
        version, system_id, *flags = row
        require(type(version) is int and 170000 <= version < 180000, "PG17_REQUIRED")
        require(
            all(v is False for v in flags[:6])
            and flags[6] == []
            and all(v is False for v in flags[7:]),
            "OWNER_ROLE_ACL",
        )
        runtime = self.runtime.inspect_owner(scope)
        require(
            set(runtime)
            == {
                "image_digest",
                "namespace_sha256",
                "marker_sha256",
                "fixture_uuid",
                "nonce",
                "container_id",
                "volume_id",
                "initialization_commands",
            },
            "OWNER_RUNTIME_RAW",
        )
        elapsed = max(1, (time.monotonic_ns() - started) // 1_000_000)
        raw = dict(
            runtime,
            pg_major=17,
            system_identifier_sha256=sha(str(system_id).encode()),
            initialization_sql=len(INIT_SQL),
            initialization_ms=elapsed,
            role_audit=dict(
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
            ),
        )
        verify_raw_owner_identity(raw, scope)
        return self.store.append(
            scope,
            "OWNER_RAW",
            dict(
                raw=raw,
                provenance=dict(
                    server="pg_control_system/server_version_num",
                    acl="pg_roles/pg_auth_members/has_*_privilege",
                    runtime="independent pinned runtime inspect",
                    timing="monotonic_ns",
                ),
                session_guc="CONFIGURED_NOT_INDEPENDENTLY_OBSERVED",
                qualifies=False,
            ),
        ).model_dump()

    def inspect(self, scope):
        return self.store.read(scope, "OWNER_RAW").model_dump()

    def lease(self, scope, worker_identity):
        # Before calling the credential factory, socket access or worker launch.
        session_method()


def validate_lease_v2(lease, scope, worker_pid, now):
    require(
        type(lease) is dict
        and set(lease) == {"scope_sha256", "worker_pid", "expires_at", "credential_fd", "version"},
        "LEASE_SCHEMA",
    )
    require(
        lease["version"] == 2
        and lease["scope_sha256"] == sha(canonical(scope.model_dump()))
        and type(worker_pid) is int
        and worker_pid > 1
        and lease["worker_pid"] == worker_pid
        and now < lease["expires_at"] <= now + 1,
        "LEASE_BINDING",
    )
    require(type(lease["credential_fd"]) is int and lease["credential_fd"] >= 0, "CREDENTIAL_FD")
    # No backend_start field in a pre-connect lease.
    os.fstat(lease["credential_fd"])
    return lease


def validate_session_v2(session, scope, lease):
    require(
        type(session) is dict
        and set(session)
        == {
            "scope_sha256",
            "worker_pid",
            "backend_pid",
            "backend_start",
            "role",
            "namespace_sha256",
            "connection_generation",
            "guc_source",
        },
        "SESSION_SCHEMA",
    )
    require(
        session["scope_sha256"] == lease["scope_sha256"]
        and session["worker_pid"] == lease["worker_pid"]
        and session["namespace_sha256"] == scope.namespace_sha256
        and type(session["backend_pid"]) is int
        and session["backend_pid"] > 1
        and bool(session["backend_start"])
        and session["role"] == "a42363_probe"
        and type(session["connection_generation"]) is int
        and session["connection_generation"] > 0,
        "SESSION_IDENTITY",
    )
    # Neither role defaults, requested libpq options nor another backend's SHOW prove GUCs.
    session_method()
