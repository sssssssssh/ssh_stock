"""Fixed sixteen-statement psycopg executor, callable only by the installed supervisor.

No CLI, DSN, SQL argument, pool, retries, forced preparation or business imports.
Private-driver observations are pinned to 3.3.4; absence is NOT_PROVEN, never inferred.
"""

import gc
import os
import resource
import time
from dataclasses import dataclass

from scripts.a4236_g1_probe import ALLOWLIST_SHA, TEMPLATES, request, validate_request
from scripts.a42361_contract import Fault, canonical, require, sha
from scripts.a42361_deployment import LocalService, installed
from scripts.a42361_fixture_controller import created

SCHEDULE = (
    ("I4",) * 5
    + ("PROJECTION", "I4", "PROJECTION")
    + ("I8",) * 5
    + ("PROJECTION", "I8", "PROJECTION")
)


@dataclass
class SqlBudget:
    count: int = 0
    first_ns: int | None = None
    last_ns: int | None = None
    stopped: bool = False

    def reserve(self, now):
        require(type(now) is int and now > 0, "A42361_CLOCK_INVALID")
        if self.first_ns is None:
            self.first_ns = now
        if (
            self.stopped
            or self.count >= 16
            or now - self.first_ns >= 2_000_000_000
            or self.last_ns is not None
            and now < self.last_ns
        ):
            self.stopped = True
            raise Fault("A42361_SQL_BUDGET_EXCEEDED")
        self.count += 1  # Includes failures and projections. Never refunded.
        self.last_ns = now
        return now

    def finish(self, start, end, rows):
        if (
            type(end) is not int
            or end < start
            or end - start > 100_000_000
            or end - self.first_ns > 2_000_000_000
            or type(rows) is not int
            or not 0 <= rows <= 8
        ):
            self.stopped = True
            raise Fault("A42361_SQL_BUDGET_EXCEEDED")
        self.last_ns = end


def validate_wire(template, driver, protocol, oids, parameter_count, allowlist=ALLOWLIST_SHA):
    try:
        validate_request(request(template), allowlist)
        d, p, types, _ = TEMPLATES[template]
        require(
            (driver, protocol, tuple(oids), parameter_count) == (d, p, types, len(types)),
            "A42361_SQL_NOT_ALLOWLISTED",
        )
    except Exception:
        raise Fault("A42361_SQL_NOT_ALLOWLISTED") from None


def prepared_projection(rows, previous):
    """Strict same-session projection, only hashed names in export; no plan claim."""
    require(type(rows) is list and len(rows) <= 8, "A42361_PREPARED_NOT_PROVEN")
    result = {}
    for row in rows:
        require(len(row) == 5, "A42361_PREPARED_NOT_PROVEN")
        name, oids, from_sql, generic, custom = row
        require(
            type(name) is str
            and name.startswith("_pg3_")
            and tuple(oids) in ((23,), (20,), ())
            and from_sql is False
            and type(generic) is int
            and type(custom) is int
            and min(generic, custom) >= 0,
            "A42361_PREPARED_NOT_PROVEN",
        )
        require(
            generic + custom <= 6 and not (generic > 0 and custom > 0), "A42361_PREPARED_NOT_PROVEN"
        )
        key = sha(name.encode())
        require(key not in result, "A42361_PREPARED_NOT_PROVEN")
        result[key] = dict(oids=list(oids), generic=generic, custom=custom)
    for key, old in previous.items():
        new = result.get(key)
        require(
            new is not None
            and new["oids"] == old["oids"]
            and new["generic"] >= old["generic"]
            and new["custom"] >= old["custom"],
            "A42361_PREPARED_NOT_PROVEN",
        )
    return result


class ProbeWorker:
    def __init__(self, deployment=None):
        self.deployment = deployment

    def run_owned(self, fixture):
        config = installed(self.deployment)
        fixture = created(fixture)
        require(os.getuid() == config.worker_uid, "A42361_WORKER_PRINCIPAL_MISMATCH")
        require(
            not any(
                k.startswith("PG") or k in ("DATABASE_URL", "TEST_DATABASE_URL") for k in os.environ
            ),
            "A42361_AMBIENT_CONNECTION_REJECTED",
        )
        # This independent service must attest this precise worker PID, fixture and
        # hard deadline BEFORE it releases a short-lived probe-only credential.
        body = dict(
            payload_sha256=fixture.consumption.grant.payload_sha256,
            creation_sha256=fixture.receipt_sha256,
            worker_pid=os.getpid(),
            allowlist_sha256=ALLOWLIST_SHA,
            schedule=list(SCHEDULE),
        )
        lease = LocalService(self.deployment, "pg_owner").call("run", body)
        require(
            type(lease) is dict
            and set(lease)
            == {
                "socket_directory",
                "database",
                "password",
                "backend_start_sha256",
                "creation_sha256",
                "supervised",
                "statement_timeout_ms",
                "read_only",
                "probe_role_sha256",
                "lease_expires_at",
            },
            "A42361_PROBE_LEASE_UNTRUSTED",
        )
        require(
            lease["socket_directory"] == fixture.socket_directory
            and lease["database"]
            == "a42361_" + fixture.consumption.grant.payload.binding.fixture_uuid.replace("-", "")
            and lease["creation_sha256"] == fixture.receipt_sha256
            and lease["probe_role_sha256"] == fixture.pg_identity["probe_role_sha256"]
            and lease["supervised"] is True
            and lease["read_only"] is True
            and type(lease["statement_timeout_ms"]) is int
            and lease["statement_timeout_ms"] == 100
            and type(lease["lease_expires_at"]) is int
            and int(time.time()) < lease["lease_expires_at"]
            and type(lease["password"]) is str
            and 32 <= len(lease["password"]) <= 128,
            "A42361_PROBE_LEASE_UNTRUSTED",
        )
        import psycopg

        require(psycopg.__version__ == "3.3.4", "A42361_DRIVER_VERSION_MISMATCH")
        connection = None
        try:
            connection = psycopg.connect(
                host=fixture.socket_directory,
                port=5432,
                dbname=lease["database"],
                user="g1_probe",
                password=lease.pop("password"),
                passfile="",
                sslmode="disable",
                connect_timeout=1,
                autocommit=True,
                prepare_threshold=5,
                application_name="a42361-g1-probe",
                options=(
                    "-c statement_timeout=100 -c default_transaction_read_only=on "
                    "-c search_path=pg_catalog"
                ),
            )
            # Owner verifies actual backend_start/role/session identity using its own
            # separately budgeted connection. No identity SQL hidden in probe budget.
            identity = LocalService(self.deployment, "pg_owner").call(
                "receipt",
                dict(purpose="PROBE_SESSION", backend_pid=connection.info.backend_pid, **body),
            )
            require(
                identity
                == dict(
                    backend_pid=connection.info.backend_pid,
                    backend_start_sha256=lease["backend_start_sha256"],
                    creation_sha256=fixture.receipt_sha256,
                    read_only=True,
                    statement_timeout_ms=100,
                    pg_major=17,
                    driver_version="3.3.4",
                ),
                "A42361_SESSION_IDENTITY_UNPROVEN",
            )
            return self._execute_fixed(connection, identity)
        except Fault:
            raise
        except Exception:
            raise Fault("A42361_PROBE_INCOMPLETE") from None
        finally:
            if connection is not None:
                connection.close()

    def _execute_fixed(self, connection, identity):
        """Internal protocol boundary; tests may inject a driver, not attest a real PG."""
        from psycopg._queries import PostgresQuery
        from psycopg.adapt import Transformer
        from psycopg.types.numeric import Int4, Int8

        budget, events, snapshots, previous = SqlBudget(), [], [], {}
        initial_pid = connection.info.backend_pid
        require(
            connection.prepare_threshold == 5 and gc.isenabled(), "A42361_SESSION_IDENTITY_UNPROVEN"
        )
        thresholds = gc.get_threshold()
        cpu, started = time.process_time_ns(), time.monotonic_ns()
        gc_events = []

        def natural_gc(phase, info):
            if len(gc_events) < 32:
                gc_events.append(
                    dict(phase=phase, generation=info["generation"], at_ns=time.monotonic_ns())
                )

        gc.callbacks.append(natural_gc)
        first = None
        try:
            with connection.cursor() as cursor:
                for index, template in enumerate(SCHEDULE):
                    driver, protocol, oids, max_rows = TEMPLATES[template]
                    parameters = (
                        (Int4(1),) if template == "I4" else (Int8(1),) if template == "I8" else None
                    )
                    converted = PostgresQuery(Transformer.from_context(connection))
                    converted.convert(driver, parameters)
                    validate_wire(
                        template, driver, converted.query, converted.types, len(parameters or ())
                    )
                    require(
                        connection.info.backend_pid == initial_pid
                        and not connection.closed
                        and connection.prepare_threshold == 5,
                        "A42361_SESSION_IDENTITY_DRIFT",
                    )
                    start = budget.reserve(time.monotonic_ns())
                    event = dict(
                        index=index,
                        template=template,
                        started_ns=start,
                        finished_ns=None,
                        rows=None,
                        failure_code=None,
                        protocol_sha256=sha(protocol),
                        driver_sha256=sha(driver),
                        parameter_oids=list(oids),
                    )
                    events.append(event)
                    try:
                        cursor.execute(driver, parameters)  # Never prepare=True.
                        actual = cursor._query
                        validate_wire(
                            template, driver, actual.query, actual.types, len(parameters or ())
                        )
                        rows = cursor.fetchmany(9)
                        end = time.monotonic_ns()
                        event.update(finished_ns=end, rows=len(rows))
                        budget.finish(start, end, len(rows))
                        require(len(rows) <= max_rows, "A42361_ROW_BUDGET_EXCEEDED")
                        if template == "PROJECTION":
                            previous = prepared_projection(rows, previous)
                            snapshots.append(dict(index=index, rows=previous))
                        # Read cached metadata ONLY. Calling PrepareManager.get() here
                        # would mutate its name counter; it is deliberately not called.
                        event["cache_sha256"] = sha(
                            canonical(
                                sorted(
                                    [
                                        dict(
                                            protocol_sha256=sha(k[0]),
                                            parameter_oids=list(k[1]),
                                            name_sha256=sha(v),
                                        )
                                        for k, v in connection._prepared._names.items()
                                    ],
                                    key=lambda v: v["name_sha256"],
                                )
                            )
                        )
                    except BaseException as error:
                        budget.stopped = True
                        first = (
                            error.code if isinstance(error, Fault) else "A42361_SQL_FAILED_NO_RETRY"
                        )
                        event["failure_code"] = first
                        break
        except BaseException as error:
            budget.stopped = True
            if first is None:
                first = error.code if isinstance(error, Fault) else "A42361_PROBE_INCOMPLETE"
        finally:
            gc.callbacks.remove(natural_gc)
        require(gc.isenabled() and gc.get_threshold() == thresholds, "A42361_GC_CHANGED")
        finished = time.monotonic_ns()
        prepared = (
            first is None
            and len(snapshots) == 4
            and {(23,), (20,)} <= {tuple(v["oids"]) for v in previous.values()}
        )
        return dict(
            evidence_kind="WORKER_UNATTESTED",
            first_error=first,
            collection_status="INCOMPLETE" if first else "COLLECTED_PENDING_INDEPENDENT_REVIEW",
            sql_count=budget.count,
            events=events,
            snapshots=snapshots,
            session=identity,
            checkout_generation=1,
            prepared_status="OBSERVED_PENDING_REVIEW" if prepared else "NOT_PROVEN",
            cached_plan_structure="CACHED_PLAN_STRUCTURE_NOT_VERIFIED",
            backend_cpu=dict(
                availability="METRIC_UNAVAILABLE",
                value=None,
                scope="SAME_BACKEND_USER_PLUS_SYSTEM_INTERVAL",
            ),
            observer=dict(
                status="BRACKET_UNCOVERED", joined=False, thread_cpu_ns=None, elapsed_ns=None
            ),
            business_environment=dict(
                statistics="NOT_PROVEN", mvcc="NOT_PROVEN", maintenance="UNKNOWN"
            ),
            process=dict(
                cpu_ns=time.process_time_ns() - cpu,
                elapsed_ns=finished - started,
                lifetime_rss_high_water_raw=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                rss_unit="PLATFORM_NATIVE_NOT_NORMALIZED",
                gc_events=gc_events,
                gc_subtracted=False,
            ),
        )
