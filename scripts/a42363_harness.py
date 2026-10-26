"""Fixed PG fixture lifecycle. No installer, CLI, runtime flag or physical authorization.

The fresh dynamic database needs nine visible SQL statements. Preflight refuses the
eight-statement protocol BEFORE resource creation; deployment must not hide entrypoint SQL.
"""

import os
import stat
import time
from dataclasses import dataclass

from scripts.a42361_contract import canonical, sha
from scripts.a42362_contract import resources
from scripts.a42363_contract import require, scope_hash, session_method


@dataclass(frozen=True)
class InitializationPlan:
    identity: object
    statements: tuple
    allowed_sql: int = 8

    @classmethod
    def build(cls, identity):
        identity.verify(identity.scope)
        from scripts.a42363_owner import INIT_SQL

        # Derived identifiers contain only ASCII letters/digits/underscore; no caller SQL.
        statements = tuple(
            s.replace("a42363_fixture", identity.database).replace(
                "a42363_probe", identity.probe_role
            )
            for s in INIT_SQL
        )
        return cls(identity, ("CREATE DATABASE " + identity.database, *statements))

    def preflight(self):
        self.identity.verify(self.identity.scope)
        require(
            self.allowed_sql == 8 and self.statements == self.build(self.identity).statements,
            "INIT_PLAN_CHANGED",
        )
        require(len(self.statements) <= self.allowed_sql, "INIT_BUDGET_INFEASIBLE")

    def initialize_database(self, connection_factory):
        """Explicit autocommit CREATE DATABASE then a distinct fixture connection.

        Unreachable under the current eight-SQL contract. No CREATE ACK retry, no
        initial connection to a not-yet-created database, no entrypoint SQL exemption.
        """
        self.preflight()
        c = connection_factory(self.identity.scope, database="postgres", autocommit=True)
        try:
            require(
                c.info.dbname == "postgres"
                and c.info.user == self.identity.owner_role
                and c.info.host == self.identity.socket_host,
                "OWNER_BOOTSTRAP_TARGET",
            )
            c.execute(self.statements[0])
        finally:
            c.close()
        return connection_factory(
            self.identity.scope, database=self.identity.database, autocommit=False
        )


class PgFixtureRuntime:
    """Actual driver/store adapter, with explicit prepare/start/ready/stopping states.

    lifecycle records are independent domain commits, not C's create JSON. Fixed pinned
    image must implement the reviewed mount/peer-auth bootstrap. That image and UID maps
    remain PLATFORM_NOT_VERIFIED; no request can provide a 'ready' boolean.
    """

    def __init__(self, identity, driver, engine, store, owner_store=None):
        self.identity, self.driver, self.engine, self.store = identity, driver, engine, store
        self.state, self.ready, self.first_error = "NEW", False, None
        self.container_id, self.runtime_identity = None, None
        self.started_ns = None
        self.owner_store = owner_store

    def preflight(self):
        self.identity.verify(self.identity.scope)
        InitializationPlan.build(self.identity).preflight()
        session_method()
        require(
            self.driver is not None and self.engine is not None and self.store is not None,
            "FIXTURE_CAPABILITIES_REQUIRED",
        )

    def prepare(self):
        self.preflight()  # Budget/method decisions before first irreversible side effect.
        require(self.state == "NEW", "PG_NO_SECOND_PREPARE")
        self.started_ns = time.monotonic_ns()
        self.state = "PREPARE_ATTEMPTED"
        self.store.append(
            self.identity.scope, self.state, dict(identity=self.identity.model_dump())
        )
        try:
            self.engine.create(self.identity.scope)
            raw = self.driver.inspect(resources(self.identity.scope)[3])
            self.driver.verify(resources(self.identity.scope)[3], raw)
            self.container_id = raw.get("ID", raw.get("Id"))
            require(
                type(self.container_id) is str and len(self.container_id) == 64,
                "CONTAINER_IMMUTABLE_ID",
            )
            self.runtime_identity = self._stable(raw)
            self._record("PREPARED", raw)
        except BaseException as error:
            self._fail(error)
            raise

    def _stable(self, raw):
        return sha(
            canonical(
                {
                    k: raw.get(k)
                    for k in (
                        "ID",
                        "Id",
                        "Created",
                        "Config",
                        "HostConfig",
                        "Mounts",
                        "ImageDigest",
                    )
                }
            )
        )

    def _record(self, state, raw):
        self.store.append(
            self.identity.scope,
            "PG_" + state,
            dict(
                container_id=self.container_id,
                raw=raw,
                identity_sha256=sha(canonical(self.identity.model_dump())),
                qualifies=False,
            ),
        )
        self.state = state

    def _fail(self, error):
        self.first_error = self.first_error or getattr(error, "code", "A42363_PG_ACK_UNKNOWN")
        self.state, self.ready = "UNKNOWN", False

    def _time(self):
        require(
            self.started_ns is not None and time.monotonic_ns() - self.started_ns < 2_000_000_000,
            "INITIALIZATION_TIMEOUT",
        )

    def _inspect(self):
        self.identity.verify(self.identity.scope)
        item = resources(self.identity.scope)[3]
        raw = self.driver.inspect(item)
        self.driver.verify(item, raw)
        require(self._stable(raw) == self.runtime_identity, "PG_CONTAINER_REPLACED")
        return raw

    def start(self):
        require(self.state == "PREPARED", "PG_NOT_PREPARED")
        self._time()
        self._inspect()
        # Durable attempt before start; an ACK loss never grants a second start.
        self._record("START_ATTEMPTED", {})
        try:
            code, _ = self.driver.commands.run(("container", "start", self.container_id))
            require(code == 0, "PG_START_ACK_UNKNOWN")
            raw = self._inspect()
            require(raw.get("State", {}).get("Running") is True, "PG_NOT_RUNNING")
            self._record("RUNNING", raw)
        except BaseException as error:
            self._fail(error)
            raise

    def readiness(self):
        require(self.state == "RUNNING", "PG_NOT_RUNNING")
        try:
            self._time()
            raw = self._inspect()
            require(raw.get("State", {}).get("Running") is True, "PG_NOT_RUNNING")
            require(
                raw.get("State", {}).get("Health", {}).get("Status") == "healthy", "PG_NOT_READY"
            )
            self.driver.verify_socket_mount(raw, self.identity)
            fd = self.driver.socket_directory.open_fixture()
            try:
                meta = os.stat(".s.PGSQL.5432", dir_fd=fd, follow_symlinks=False)
            finally:
                os.close(fd)
            require(stat.S_ISSOCK(meta.st_mode), "PG_SOCKET_NOT_READY")
            self._record("READY_FOR_OWNER_AUDIT", raw)
            # Socket health is not an authenticated Owner/role/ACL certificate.
            return dict(status=self.state, owner_audited=False, qualifies=False)
        except BaseException as error:
            self._fail(error)
            raise

    def owner_audited(self, raw_receipt):
        from scripts.a42363_contract import verify_receipt

        require(self.state == "READY_FOR_OWNER_AUDIT", "PG_NOT_READY")
        r = verify_receipt(raw_receipt, "pg_owner", self.identity.scope, "OWNER_RAW")
        require(
            self.owner_store is not None
            and self.owner_store.read(self.identity.scope, "OWNER_RAW") == r,
            "INDEPENDENT_OWNER_REQUIRED",
        )
        require(
            r.record.get("fixture_identity") == self.identity.model_dump(), "OWNER_TARGET_UNPROVEN"
        )
        self._record("OWNER_AUDITED", dict(receipt_digest=r.digest))
        self.ready = True

    def restore(self):
        """Only original committed creation facts, never a new same-name inspect.

        Lost START/STOP ACK stays UNKNOWN. A receiver restart must not repeat either
        side effect. C's ledger separately retains the original observed identity.
        """
        require(self.state == "NEW", "PG_NO_SECOND_RESTORE")
        original = self.store.read(self.identity.scope, "PG_PREPARED")
        require(
            original.record["identity_sha256"] == sha(canonical(self.identity.model_dump())),
            "FIXTURE_IDENTITY",
        )
        self.container_id = original.record["container_id"]
        self.runtime_identity = self._stable(original.record["raw"])
        last, sequence = "PREPARED", original.sequence
        for stage in (
            "START_ATTEMPTED",
            "RUNNING",
            "READY_FOR_OWNER_AUDIT",
            "OWNER_AUDITED",
            "STOP_ATTEMPTED",
            "STOPPED",
        ):
            r = self.store.maybe_read(self.identity.scope, "PG_" + stage)
            if r is not None:
                require(
                    r.sequence > sequence
                    and r.record["container_id"] == self.container_id
                    and r.record["identity_sha256"] == original.record["identity_sha256"],
                    "PG_HISTORY_DRIFT",
                )
                last, sequence = stage, r.sequence
        self.state = "UNKNOWN" if last.endswith("ATTEMPTED") else last
        self.ready = False  # A restart never reissues a credential from remembered readiness.
        self.started_ns = None  # Initialization budget cannot be reset by a restart.
        return self.state

    def stop(self):
        require(self.container_id is not None, "PG_OWNERSHIP_UNKNOWN")
        self.ready = False
        self.driver.begin_cleanup()
        raw = self._inspect()
        if raw.get("State", {}).get("Running") is True:
            require(
                self.store.maybe_read(self.identity.scope, "PG_STOP_ATTEMPTED") is None,
                "PG_STOP_ACK_UNKNOWN",
            )
            self._record("STOP_ATTEMPTED", {})
            try:
                code, _ = self.driver.commands.run(
                    ("container", "stop", "--time=1", self.container_id)
                )
                require(code == 0, "PG_STOP_ACK_UNKNOWN")
            except BaseException as error:
                self._fail(error)
                raise
        stopped = self._inspect()
        require(stopped.get("State", {}).get("Running") is False, "PG_STOP_UNPROVEN")
        self._record("STOPPED", stopped)
        return dict(scope_sha256=scope_hash(self.identity.scope), qualifies=False)

    def inspect(self):
        return self._inspect()
