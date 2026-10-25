"""Closed synthetic SQL router and deterministic watchdog model; live always denies."""

from dataclasses import dataclass, field
from typing import Literal

from scripts.a4235_calibration_adapter_contract import Hash, Strict, digest
from scripts.a4236_g1_harness_contract import (
    Budget,
    Counter,
    FakeClock,
    Fault,
    Positive,
    checked,
    require,
)

# Driver bytes and protocol bytes are distinct; neither is an artifact payload.
TEMPLATES = {
    "I4": (b"SELECT %s::integer", b"SELECT $1::integer", (23,), 1),
    "I8": (b"SELECT %s::bigint + 1", b"SELECT $1::bigint + 1", (20,), 1),
    "PROJECTION": (
        b"SELECT name, parameter_types::oid[], from_sql, generic_plans, custom_plans "
        b"FROM pg_catalog.pg_prepared_statements ORDER BY name LIMIT 8",
        b"SELECT name, parameter_types::oid[], from_sql, generic_plans, custom_plans "
        b"FROM pg_catalog.pg_prepared_statements ORDER BY name LIMIT 8",
        (),
        8,
    ),
}
ALLOWLIST_SHA = digest(
    {
        k: dict(
            driver=v[0].hex(),
            protocol=v[1].hex(),
            parameter_oids=v[2],
            max_rows=v[3],
            stage="G1_SYNTHETIC_ONLY",
        )
        for k, v in TEMPLATES.items()
    }
)


class Request(Strict):
    template: Literal["I4", "I8", "PROJECTION"]
    driver_sql_sha256: Hash
    protocol_sql_sha256: Hash
    parameter_oids: tuple[Positive, ...]
    parameter_count: Counter
    stage: Literal["G1_SYNTHETIC_ONLY"] = "G1_SYNTHETIC_ONLY"


def request(template):
    import hashlib

    require(template in TEMPLATES, "A4236_SQL_NOT_ALLOWLISTED")
    driver, protocol, oids, _ = TEMPLATES[template]
    return Request(
        template=template,
        driver_sql_sha256=hashlib.sha256(driver).hexdigest(),
        protocol_sql_sha256=hashlib.sha256(protocol).hexdigest(),
        parameter_oids=oids,
        parameter_count=len(oids),
    )


def validate_request(value, harness_allowlist):
    value = checked(Request, value)
    require(
        value == request(value.template) and harness_allowlist == ALLOWLIST_SHA,
        "A4236_SQL_NOT_ALLOWLISTED",
    )
    return value


@dataclass
class SqlBudget:
    clock: FakeClock
    budget: Budget = field(default_factory=Budget)
    count: int = 0
    started_ns: int | None = None
    stopped: bool = False

    def reserve(self):
        require(type(self.clock) is FakeClock, "A4236_REAL_CLOCK_NOT_ALLOWED")
        require(type(self.clock.ns) is int and self.clock.ns > 0, "A4236_CLOCK_INVALID")
        require(not self.stopped, "A4236_PROBE_ALREADY_STOPPED")
        if self.started_ns is None:
            self.started_ns = self.clock.ns
        if self.count >= self.budget.max_sql or self.clock.ns - self.started_ns >= 2_000_000_000:
            self.stopped = True
            raise Fault("A4236_SQL_BUDGET_EXCEEDED")
        self.count += 1  # Includes failed executions and every projection, never refunds.

    def finish(self, started_ns, row_count):
        require(self.started_ns is not None, "A4236_PROBE_NOT_STARTED")
        if (
            self.clock.ns < started_ns
            or self.clock.ns - started_ns > 100_000_000
            or self.clock.ns - self.started_ns > 2_000_000_000
            or row_count > 8
        ):
            self.stopped = True
            raise Fault("A4236_SQL_BUDGET_EXCEEDED")


@dataclass(frozen=True)
class Reply:
    wall_ms: int = 1
    overhead_ms: int = 0
    rows: int = 1
    server_timeout_ms: int = 100
    terminable: bool = True
    failure_code: str | None = None


@dataclass
class FakeConnection:
    clock: FakeClock
    replies: tuple[Reply, ...] = ()
    calls: list = field(default_factory=list)
    statement_timeout_ms: int = 100
    read_only: bool = True

    def execute(self, value, budget, harness_allowlist=ALLOWLIST_SHA):
        require(
            type(self.clock) is FakeClock
            and type(budget) is SqlBudget
            and budget.clock is self.clock,
            "A4236_REAL_ADAPTER_NOT_ALLOWED",
        )
        record = None
        try:
            value = validate_request(value, harness_allowlist)
            require(
                self.read_only and 0 < self.statement_timeout_ms <= 100,
                "A4236_SERVER_TIMEOUT_UNPROVEN",
            )
            budget.reserve()
            reply = (
                self.replies[len(self.calls)] if len(self.calls) < len(self.replies) else Reply()
            )
            record = dict(
                request_sha256=digest(value.model_dump()),
                template=value.template,
                started_ns=self.clock.ns,
                finished_ns=None,
                row_count=None,
                failure_code=None,
            )
            self.calls.append(record)
            require(
                type(reply) is Reply
                and type(reply.wall_ms) is int
                and type(reply.overhead_ms) is int
                and type(reply.rows) is int
                and reply.wall_ms >= 0
                and reply.overhead_ms >= 0
                and reply.rows >= 0
                and 0 < reply.server_timeout_ms <= 100,
                "A4236_REPLY_INVALID",
            )
            started = self.clock.ns
            # This is a record of a fake route, not a driver or parameter execution.
            record["row_count"] = reply.rows
            self.clock.advance_ms(reply.wall_ms + reply.overhead_ms)
            record["finished_ns"] = self.clock.ns
            if not reply.terminable:
                raise Fault("A4236_TERMINATION_NOT_PROVEN")
            if reply.failure_code:
                raise Fault(reply.failure_code)
            budget.finish(started, reply.rows)
            require(reply.rows <= TEMPLATES[value.template][3], "A4236_ROW_BUDGET_EXCEEDED")
            return dict(row_count=reply.rows, status="MOCK_ONLY", real_sql_executed=0)
        except BaseException as error:
            budget.stopped = True
            code = error.code if isinstance(error, Fault) else "A4236_EXECUTION_MODEL_FAILED"
            if record is not None:
                record["failure_code"] = code
            raise Fault(code) from None


def run_mock_requests(connection, requests, harness_allowlist=ALLOWLIST_SHA):
    require(type(connection) is FakeConnection, "A4236_REAL_ADAPTER_NOT_ALLOWED")
    require(type(requests) in (list, tuple), "A4236_REQUEST_SEQUENCE_INVALID")
    budget = SqlBudget(connection.clock)
    first = None
    for value in requests:
        try:
            connection.execute(value, budget, harness_allowlist)
        except Fault as error:
            first = error.code
            break
    return dict(
        evidence_kind="MOCK_ONLY",
        mock_sql_count=budget.count,
        completed=first is None,
        first_error=first,
        real_sql_executed=0,
        capability_status="PARTIAL",
        cached_plan_structure="CACHED_PLAN_STRUCTURE_NOT_VERIFIED",
        events=connection.calls,
        termination_status="MODEL_ONLY_NOT_PROVEN",
    )


def run_live(*args, **kwargs):
    # FIRST branch: no token, callback, env, CLI, grant or config can reach an adapter.
    raise Fault("A4236_G1_NOT_RUN_NOT_AUTHORIZED")
