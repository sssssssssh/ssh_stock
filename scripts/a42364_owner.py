"""Versioned fixed Owner/SCRAM adapter. Default routes remain on the blocked v1 API."""

import base64
import hashlib
import hmac
import os
import secrets
import time

from psycopg import sql

from scripts.a42361_contract import sha
from scripts.a42363_contract import Fault, require, scope_hash
from scripts.a42363_proposals import BootstrapProposal


def scram_verifier(password):
    """RFC5803/PG SCRAM verifier for manager-generated printable ASCII credentials."""
    require(
        type(password) is bytes
        and 32 <= len(password) <= 128
        and all(33 <= b <= 126 for b in password),
        "SCRAM_CREDENTIAL",
    )
    salt = secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", password, salt, 4096)
    client = hmac.digest(salted, b"Client Key", "sha256")
    stored = hashlib.sha256(client).digest()
    server = hmac.digest(salted, b"Server Key", "sha256")

    def b64(value):
        return base64.b64encode(value).decode("ascii")

    return "SCRAM-SHA-256$4096:" + b64(salt) + "$" + b64(stored) + ":" + b64(server)


def statements(identity, verifier):
    identity.verify(identity.scope)
    require(type(verifier) is str and verifier.startswith("SCRAM-SHA-256$4096:"), "SCRAM_VERIFIER")
    d, p, o = map(sql.Identifier, (identity.database, identity.probe_role, identity.owner_role))
    proposal = BootstrapProposal.fresh(identity)
    templates = {op.name: op.template for op in proposal.operations if op.kind == "SQL"}
    # The only dynamic SQL parts are closed FixtureIdentity identifiers and a secret
    # Literal. Never use f-strings/format with raw caller identifiers or passwords.
    return (
        ("CREATE_DATABASE", sql.SQL("CREATE DATABASE {} OWNER {}").format(d, o), None),
        ("REVOKE_DATABASE", sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(d), None),
        ("REVOKE_SCHEMA", sql.SQL("REVOKE ALL ON SCHEMA public FROM PUBLIC"), None),
        (
            "CREATE_PROBE_ROLE",
            sql.SQL(
                "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 1"
            ).format(p),
            None,
        ),
        (
            "SET_SCRAM_VERIFIER",
            sql.SQL("ALTER ROLE {} PASSWORD {}").format(p, sql.Literal(verifier)),
            None,
        ),
        ("REVOKE_DEFAULT_FUNCTION", sql.SQL(templates["REVOKE_DEFAULT_FUNCTION"]), None),
        ("CONNECT_ONLY", sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(d, p), None),
        (
            "READ_ONLY_DEFAULT",
            sql.SQL("ALTER ROLE {} SET default_transaction_read_only=on").format(p),
            None,
        ),
        ("TIMEOUT_DEFAULT", sql.SQL("ALTER ROLE {} SET statement_timeout='100ms'").format(p), None),
        (
            "RAW_OWNER_ROLE_AUDIT",
            sql.SQL(templates["RAW_OWNER_ROLE_AUDIT"]),
            (identity.probe_role,),
        ),
        ("AUTH_CONFIG_AUDIT", sql.SQL(templates["AUTH_CONFIG_AUDIT"]), None),
        (
            "USER_OBJECT_PRIVILEGE_AUDIT",
            sql.SQL(templates["USER_OBJECT_PRIVILEGE_AUDIT"]),
            (identity.probe_role, identity.probe_role),
        ),
    )


def verify_owner_metadata(identity, raw, hba, objects):
    require(type(raw) in (tuple, list) and len(raw) == 15, "OWNER_RAW_METADATA")
    require(type(raw[2]) is str and raw[2].isdigit(), "OWNER_RAW_TARGET")
    require(
        raw[0] == identity.database
        and raw[1] == identity.owner_role
        and 170000 <= int(raw[2]) < 180000
        and str(raw[3]).isdigit(),
        "OWNER_RAW_TARGET",
    )
    require(
        all(v is False for v in raw[4:10])
        and raw[10] == 1
        and raw[11] == []
        and all(v is False for v in raw[12:]),
        "OWNER_RAW_PRIVILEGES",
    )
    require(
        type(hba) is list
        and len(hba) == 4
        and all(type(r) in (tuple, list) and len(r) == 3 for r in hba)
        and [r[1] for r in hba] == ["scram-sha-256", "scram-sha-256", "reject", "reject"]
        and all(len(r) == 3 and type(r[0]) is int and r[0] > 0 and r[2] is None for r in hba),
        "OWNER_HBA_RULES",
    )
    require(type(objects) is list and objects == [], "OWNER_USER_OBJECTS_UNEXPECTED")
    return dict(
        database=raw[0],
        role=raw[1],
        pg_major=17,
        system_identifier_sha256=sha(str(raw[3]).encode()),
        privilege_audit="RAW_METADATA_VERIFIED",
        target_session_settings_observed=False,
        qualifies=False,
    )


class OwnerConnections:
    def __init__(self, identity, authority, credential_source, budget=None):
        self.identity, self.authority, self.credential_source = (
            identity,
            authority,
            credential_source,
        )
        self.budget = budget

    def open(self, *, bootstrap=False, probe=False):
        self.authority.require("BOOTSTRAP_AND_BUDGET")
        i = self.identity.verify(self.identity.scope)
        require(not (bootstrap and probe), "OWNER_CONNECTION_PHASE")
        require(self.budget is not None, "SHARED_BOOTSTRAP_BUDGET_REQUIRED")
        step = (
            "OWNER_AUTH_CONNECT"
            if bootstrap
            else "PROBE_AUTH_CONNECT"
            if probe
            else "OWNER_FIXTURE_AUTH_CONNECT"
        )
        self.budget.reserve_named(step, time.monotonic_ns())
        require(
            not any(
                k.startswith("PG") or k in ("DATABASE_URL", "TEST_DATABASE_URL") for k in os.environ
            ),
            "OWNER_AMBIENT_CONNECTION",
        )
        # credential_source is an installed sealed-FD reader, never an RPC/environment value.
        secret = self.credential_source.read("PROBE" if probe else "OWNER", i)
        import psycopg

        require(psycopg.__version__ == "3.3.4", "DRIVER_VERSION")
        c = psycopg.connect(
            host=i.socket_host,
            port=5432,
            dbname="postgres" if bootstrap else i.database,
            user=i.probe_role if probe else i.owner_role,
            password=secret,
            passfile="",
            sslmode="disable",
            connect_timeout=1,
            autocommit=bootstrap or probe,
            options="-c statement_timeout=100 -c search_path=pg_catalog",
        )
        try:
            verify_connection(c, i, bootstrap=bootstrap, probe=probe)
        except BaseException:
            c.close()
            raise
        return c


def verify_connection(c, identity, *, bootstrap=False, probe=False):
    require(
        c.info.dbname == ("postgres" if bootstrap else identity.database)
        and c.info.user == (identity.probe_role if probe else identity.owner_role)
        and c.info.host == identity.socket_host
        and c.info.port == 5432
        and 170000 <= c.info.server_version < 180000
        and not c.closed,
        "OWNER_CONNECTION_TARGET",
    )
    require(not bootstrap or c.autocommit is True, "CREATE_DATABASE_AUTOCOMMIT")


class OwnerInitializer:
    def __init__(self, identity, authority, connections, journal, credential_source, budget=None):
        self.identity, self.authority, self.connections = identity, authority, connections
        self.journal, self.credential_source = journal, credential_source
        self.budget = budget

    def initialize(self):
        i = self.identity.verify(self.identity.scope)
        self.authority.require("BOOTSTRAP_AND_BUDGET")
        require(self.budget is not None, "SHARED_BOOTSTRAP_BUDGET_REQUIRED")
        require(
            self.journal.maybe_read(i.scope, "OWNER_V3_ATTEMPTED") is None,
            "OWNER_NO_SECOND_INITIALIZATION",
        )
        self.journal.append(
            i.scope, "OWNER_V3_ATTEMPTED", dict(scope_sha256=scope_hash(i.scope), qualifies=False)
        )
        private = self.credential_source.read("PROBE", i).encode("ascii")
        plan = statements(i, scram_verifier(private))
        metadata, hba, objects = None, None, None
        c = None
        cleanup_codes = []
        try:
            for index, (name, statement, params) in enumerate(plan):
                # The independent domain store commits and freshly reads every attempt.
                event = "OWNER_SQL_" + str(index + 1).zfill(2)
                self.journal.append(i.scope, event, dict(operation=name, qualifies=False))
                if index == 0:
                    c = self.connections.open(bootstrap=True)
                    try:
                        verify_connection(c, i, bootstrap=True)
                        self.budget.reserve_named(name, time.monotonic_ns())
                        c.execute(statement, params)
                    finally:
                        try:
                            c.close()
                        finally:
                            c = None
                    c = self.connections.open()
                else:
                    self.budget.reserve_named(name, time.monotonic_ns())
                    cursor = c.execute(statement, params)
                    if name == "RAW_OWNER_ROLE_AUDIT":
                        metadata = cursor.fetchone()
                    elif name == "AUTH_CONFIG_AUDIT":
                        hba = cursor.fetchall()
                    elif name == "USER_OBJECT_PRIVILEGE_AUDIT":
                        objects = cursor.fetchall()
            result = verify_owner_metadata(i, metadata, hba, objects)
            c.commit()
            c.close()
            c = None
            probe = self.connections.open(probe=True)
            try:
                verify_connection(probe, i, probe=True)
            finally:
                probe.close()
            result.update(
                scope_sha256=scope_hash(i.scope),
                authentication="ACTUAL_SCRAM_LOGIN_COMPLETED",
                sql_count=len(plan),
                configured_only=True,
            )
            return self.journal.append(i.scope, "OWNER_V3_RAW", result)
        except BaseException:
            # Never expose a driver error/Composed Literal containing the SCRAM verifier.
            if c is not None:
                try:
                    c.close()
                except BaseException:
                    cleanup_codes.append("A42363_OWNER_CONNECTION_CLOSE_UNKNOWN")
                c = None
            try:
                self.journal.append(
                    i.scope,
                    "OWNER_V3_FAILED",
                    dict(
                        first_error="A42363_OWNER_ACK_UNKNOWN_NO_RETRY",
                        cleanup_codes=list(cleanup_codes),
                        qualifies=False,
                    ),
                )
            except BaseException:
                cleanup_codes.append("A42363_OWNER_FAILURE_JOURNAL_UNKNOWN")
            fault = Fault("A42363_OWNER_ACK_UNKNOWN_NO_RETRY")
            fault.cleanup_codes = cleanup_codes
            raise fault from None


class SealedCredentialSource:
    """Root-created sealed material, explicitly passed by manager; never discovered in env."""

    def __init__(self, fd, authority):
        self.fd, self.authority = fd, authority

    def read(self, role, identity):
        import fcntl
        import stat

        from scripts.a42361_contract import decode

        self.authority.require("BOOTSTRAP_AND_BUDGET")
        require(role in ("OWNER", "PROBE"), "CREDENTIAL_ROLE")
        meta = os.fstat(self.fd)
        seals = fcntl.F_SEAL_SEAL | fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK
        require(
            stat.S_ISREG(meta.st_mode)
            and meta.st_uid == 0
            and stat.S_IMODE(meta.st_mode) == 0o400
            and 0 < meta.st_size <= 65536
            and fcntl.fcntl(self.fd, fcntl.F_GET_SEALS) & seals == seals,
            "CREDENTIAL_FD",
        )
        body = decode(os.pread(self.fd, 65537, 0))
        require(
            type(body) is dict
            and set(body) == {"version", "scope_sha256", "OWNER", "PROBE"}
            and body["version"] == "a42364.secret.v3"
            and body["scope_sha256"] == scope_hash(identity.scope),
            "CREDENTIAL_SCOPE",
        )
        value = body[role]
        require(
            type(value) is str
            and 64 <= len(value) <= 128
            and value.isascii()
            and all(33 <= ord(c) <= 126 for c in value),
            "CREDENTIAL_ASCII",
        )
        return value


class WorkerCredentialFactory:
    def __init__(self, package, identity, authority, credentials, owner_journal):
        self.package, self.identity, self.authority = package, identity, authority
        self.credentials, self.owner_journal = credentials, owner_journal

    def __call__(self, pid):
        from scripts.a42361_contract import canonical
        from scripts.a42364_installation_verify import installed_package
        from scripts.a42364_manager import sealed_capsule

        package = installed_package(self.package)
        require(os.getuid() == 0 and type(pid) is int and pid > 1, "ROOT_WORKER_LEASE")
        i = self.identity.verify(package.document.scope)
        for kind in ("BOOTSTRAP_AND_BUDGET", "SAFE_VOLUME_DISPOSAL", "TARGET_SESSION_GUC"):
            self.authority.require(kind)
        raw = self.owner_journal.read(i.scope, "OWNER_V3_RAW")
        require(
            raw.record.get("scope_sha256") == scope_hash(i.scope)
            and raw.record.get("authentication") == "ACTUAL_SCRAM_LOGIN_COMPLETED",
            "OWNER_RAW_REQUIRED",
        )
        now = int(time.time())
        credentials = dict(
            host=i.socket_host,
            database=i.database,
            user=i.probe_role,
            password=self.credentials.read("PROBE", i),
        )
        capsule = dict(
            version="a42364.worker-capsule.v3",
            scope=i.scope.model_dump(),
            fixture_identity=i.model_dump(),
            worker_pid=pid,
            worker_uid=package.document.principals["worker"],
            owner_uid=package.document.principals["pg_owner"],
            owner_socket="/run/space-g1/" + i.scope.binding.fixture_uuid + "/owner.sock",
            lease_not_after=now + 1,
            run_not_after=now + 3,
            decision_digests={
                **{k: v.digest for k, v in self.authority.decisions.items()},
                "G1_L2_EXECUTION": self.authority.execution.digest,
            },
            source_archive_sha256=package.document.code_archive_sha256,
            credentials=credentials,
        )
        return sealed_capsule(canonical(capsule))
