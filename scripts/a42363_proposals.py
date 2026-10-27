"""Pure candidate specifications/parsers. No executor, credential or connection operations.

These are review artifacts. Neither a valid vector nor a budget proposal approves a
method. Existing live gates/SQL/limits are deliberately not configurable here.
"""

from dataclasses import dataclass

from scripts.a42361_contract import canonical, sha
from scripts.a42363_contract import require

TARGET_SQL = (
    b"SELECT current_setting('statement_timeout') AS statement_timeout, "
    b"current_setting('transaction_read_only')::boolean AS read_only, "
    b"p.name,p.parameter_types::oid[],p.from_sql,p.generic_plans,p.custom_plans "
    b"FROM (SELECT 1) AS singleton LEFT JOIN LATERAL "
    b"(SELECT name,parameter_types,from_sql,generic_plans,custom_plans "
    b"FROM pg_catalog.pg_prepared_statements ORDER BY name LIMIT 8) AS p ON true ORDER BY p.name"
)
TARGET_OIDS = (25, 16, 25, 1028, 16, 20, 20)
TARGET_SQL_SHA = "2f2f912b70ec0fe9c81c17c9098d8c2208a54e78ba69277bfe49c1bcf5986b56"
CANDIDATE_ALLOWLIST_SHA = "9b4a128a2cfb0c2c44d7eb70ab0e6d311162c902a53a3e96fb34eb0ca130d571"


def parse_target_projection(rows, output_oids, previous=None):
    """Validate offline candidate rows, never attest the origin of caller JSON.

    Physical same-session provenance would require a separately approved driver and
    signature-bound protocol. This parser always returns observed=False/qualified=False.
    """
    require(type(output_oids) is tuple and output_oids == TARGET_OIDS, "CANDIDATE_RESULT_OIDS")
    require(type(rows) is list and 1 <= len(rows) <= 8, "CANDIDATE_RESULT_ROWS")
    plans, names = [], []
    for row in rows:
        require(type(row) in (tuple, list) and len(row) == 7, "CANDIDATE_RESULT_SHAPE")
        timeout, readonly, name, oids, from_sql, generic, custom = row
        require(
            type(timeout) is str and timeout == "100ms" and readonly is True,
            "CANDIDATE_GUC_MISMATCH",
        )
        if name is None:
            require(len(rows) == 1 and all(v is None for v in row[2:]), "CANDIDATE_NULL_PLAN")
            continue
        require(
            type(name) is str and name.isascii() and 0 < len(name) <= 128, "CANDIDATE_PLAN_NAME"
        )
        require(
            type(oids) in (list, tuple)
            and all(type(o) is int and 0 < o <= 4294967295 for o in oids)
            and type(from_sql) is bool
            and type(generic) is int
            and generic >= 0
            and type(custom) is int
            and custom >= 0,
            "CANDIDATE_PLAN_FIELDS",
        )
        names.append(name)
        plans.append(
            dict(
                name_sha256=sha(name.encode()),
                parameter_oids=list(oids),
                from_sql=from_sql,
                generic_plans=generic,
                custom_plans=custom,
            )
        )
    require(names == sorted(set(names)), "CANDIDATE_PLAN_ORDER")
    from scripts.a42361_contract import Fault as PreviousFault
    from scripts.a42361_live_probe_worker import prepared_projection

    try:
        continuity = prepared_projection(
            [row[2:] for row in rows if row[2] is not None], {} if previous is None else previous
        )
    except PreviousFault:
        require(False, "CANDIDATE_PLAN_POLICY")
    return dict(
        candidate_vectors_valid=True,
        plans=plans,
        qualifies=False,
        target_session_settings_observed=False,
        protocol_decision="NOT_APPROVED",
        cached_plan_structure="CACHED_PLAN_STRUCTURE_NOT_VERIFIED",
        continuity=continuity,
    )


@dataclass(frozen=True)
class InitializationCost:
    sql: int
    commands: int
    window_ms: int = 0

    def __post_init__(self):
        require(
            all(type(v) is int and v >= 0 for v in (self.sql, self.commands, self.window_ms)),
            "INITIALIZATION_COST_SCHEMA",
        )

    def violations(self):
        return tuple(
            code
            for actual, limit, code in (
                (self.sql, 8, "INIT_BUDGET_INFEASIBLE"),
                (self.commands, 12, "INITIALIZATION_COMMAND_BUDGET"),
                (self.window_ms, 2000, "INITIALIZATION_TIMEOUT"),
            )
            if actual > limit
        )

    def enforce_current(self):
        failures = self.violations()
        require(not failures, failures[0] if failures else "INITIALIZATION_BUDGET")

    def as_record(self):
        return dict(
            sql=self.sql,
            commands=self.commands,
            window_ms=self.window_ms,
            limits=dict(sql=8, commands=12, window_ms=2000),
            violations=list(self.violations()),
            approved=False,
        )


@dataclass(frozen=True)
class BootstrapOperation:
    name: str
    phase: str
    kind: str
    template: str
    sql_cost: int
    command_cost: int
    worst_case_ms: int
    cost_counted: bool = True

    def as_record(self):
        return dict(
            name=self.name,
            phase=self.phase,
            kind=self.kind,
            template=self.template,
            sql_cost=self.sql_cost,
            command_cost=self.command_cost,
            worst_case_ms=self.worst_case_ms,
            cost_counted=True,
        )


@dataclass(frozen=True)
class BootstrapProposal:
    identity_sha256: str
    strategy: str
    operations: tuple
    cost: InitializationCost
    decision: str = "NOT_APPROVED"
    cold_start_p95: None = None

    @classmethod
    def fresh(cls, identity):
        identity.verify(identity.scope)
        # Explicit reviewed templates. Utility DDL requires psycopg Identifier/Literal
        # rendering inside a future trusted owner; never a caller string or fake $1 DDL.
        sql = (
            ("CREATE_DATABASE", "CREATE DATABASE {database} OWNER postgres"),
            ("REVOKE_DATABASE", "REVOKE ALL ON DATABASE {database} FROM PUBLIC"),
            ("REVOKE_SCHEMA", "REVOKE ALL ON SCHEMA public FROM PUBLIC"),
            (
                "CREATE_PROBE_ROLE",
                "CREATE ROLE {probe_role} LOGIN NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 1",
            ),
            ("SET_SCRAM_VERIFIER", "ALTER ROLE {probe_role} PASSWORD {scram_verifier_literal}"),
            (
                "REVOKE_DEFAULT_FUNCTION",
                "ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC",
            ),
            ("CONNECT_ONLY", "GRANT CONNECT ON DATABASE {database} TO {probe_role}"),
            ("READ_ONLY_DEFAULT", "ALTER ROLE {probe_role} SET default_transaction_read_only=on"),
            ("TIMEOUT_DEFAULT", "ALTER ROLE {probe_role} SET statement_timeout='100ms'"),
            (
                "RAW_OWNER_ROLE_AUDIT",
                "SELECT current_database(),current_user,"
                "current_setting('server_version_num'),system_identifier,"
                "p.rolsuper,p.rolcreatedb,p.rolcreaterole,p.rolinherit,p.rolreplication,p.rolbypassrls,"
                "p.rolconnlimit,ARRAY(SELECT roleid FROM pg_auth_members WHERE member=p.oid),"
                "has_database_privilege(p.oid,current_database(),'CREATE'),"
                "has_database_privilege(p.oid,current_database(),'TEMP'),"
                "has_schema_privilege(p.oid,'public','CREATE') "
                "FROM pg_control_system(),pg_roles p WHERE p.rolname=%s",
            ),
            (
                "AUTH_CONFIG_AUDIT",
                "SELECT rule_number,auth_method,error FROM pg_hba_file_rules ORDER BY rule_number",
            ),
            (
                "USER_OBJECT_PRIVILEGE_AUDIT",
                "SELECT c.oid,has_table_privilege(%s,c.oid,'SELECT'),"
                "has_table_privilege(%s,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,MAINTAIN') "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' ORDER BY c.oid",
            ),
        )
        operations = [
            BootstrapOperation(n, "OWNER_INITIALIZATION", "SQL", t, 1, 0, 100) for n, t in sql
        ]
        commands = (
            "C_VOLUME_CREATE",
            "C_VOLUME_INSPECT",
            "C_SECRET_CREATE",
            "C_SECRET_INSPECT",
            "C_CONTAINER_CREATE",
            "C_CONTAINER_INSPECT",
            "C_PREPARED_INSPECT",
            "C_BEFORE_START_INSPECT",
            "C_START",
            "C_RUNNING_INSPECT",
            "C_READINESS_INSPECT",
            "O_BEFORE_VOLUME_INSPECT",
            "O_BEFORE_SECRET_INSPECT",
            "O_BEFORE_CONTAINER_INSPECT",
            "O_AFTER_VOLUME_INSPECT",
            "O_AFTER_SECRET_INSPECT",
            "O_AFTER_CONTAINER_INSPECT",
            "ROOT_VERIFY_PINNED_IMAGE",
            "ROOT_CREATE_CGROUP_SCOPE",
            "ROOT_BIND_PRIVATE_SOCKET",
            "ROOT_SEAL_CREDENTIALS",
            "IMAGE_INITDB",
            "IMAGE_WRITE_PG_HBA",
            "IMAGE_POSTGRES_START",
            "OWNER_AUTH_CONNECT",
            "PROBE_AUTH_CONNECT",
        )
        operations += [
            BootstrapOperation(n, "BOOTSTRAP_RUNTIME", "OS_OR_AUTH", n, 0, 1, 1000)
            for n in commands
        ]
        cost = InitializationCost(
            sql=sum(o.sql_cost for o in operations),
            commands=sum(o.command_cost for o in operations),
            window_ms=sum(o.worst_case_ms for o in operations),
        )
        return cls(sha(canonical(identity.model_dump())), "FRESH_DYNAMIC", tuple(operations), cost)

    @classmethod
    def prebuilt(cls, identity):
        fresh = cls.fresh(identity)
        # Builder cost is retained, not erased as 'free image SQL'. Runtime still
        # requires new supply-chain/single-use template binding and independent audits.
        return cls(fresh.identity_sha256, "SINGLE_USE_PREBUILT", fresh.operations, fresh.cost)

    def as_record(self):
        return dict(
            strategy=self.strategy,
            identity_sha256=self.identity_sha256,
            operations=[o.as_record() for o in self.operations],
            cost=self.cost.as_record(),
            proposed_limits=dict(sql=12, commands=32, window_ms=30000),
            cold_start_p95=None,
            decision="NOT_APPROVED",
            qualifies=False,
            executable=False,
            version="g1.bootstrap.candidate.v2",
            measured=False,
            physical="NOT_RUN",
        )


def engineering_candidate_specifications(identity):
    """Independent cost/GUC proposals, never edits to the frozen contract."""
    from scripts.a42364_costs import cost_plan
    from scripts.a42364_session import candidate_specification

    return dict(dynamic=cost_plan(identity),
                prebuilt=cost_plan(identity, "SINGLE_USE_PREBUILT"),
                guc=candidate_specification(), approved=False, qualifies=False)
