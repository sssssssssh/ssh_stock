"""Separately versioned candidate driver. Frozen v1 templates/entrypoints are untouched."""

import gc
import time

from scripts.a4236_g1_probe import TEMPLATES
from scripts.a42361_contract import sha
from scripts.a42363_contract import Fault, require, scope_hash
from scripts.a42363_proposals import (
    TARGET_OIDS,
    TARGET_SQL,
    TARGET_SQL_SHA,
    parse_target_projection,
)

OWNER_SESSION_SQL = (
    "SELECT pid,backend_start,usename,datname FROM pg_stat_activity WHERE pid=%s "
    "AND backend_type='client backend'"
)

# This independently versioned schedule has no platform imports or activation path.
SCHEDULE = ("I4",) * 5 + ("PROJECTION", "I4", "PROJECTION")
SCHEDULE += ("I8",) * 5 + ("PROJECTION", "I8", "PROJECTION")


def candidate_schedule():
    require(
        sha(TARGET_SQL) == TARGET_SQL_SHA and len(TARGET_SQL) == 406, "CANDIDATE_TEMPLATE_DRIFT"
    )
    result = []
    for index, kind in enumerate(SCHEDULE, 1):
        driver, wire, oids, rows = TEMPLATES[kind]
        if kind == "PROJECTION":
            driver, wire, oids, rows = TARGET_SQL, TARGET_SQL, (), 8
        result.append(
            dict(
                slot=index,
                kind=kind,
                driver=driver,
                wire=wire,
                parameter_oids=oids,
                driver_sha256=sha(driver),
                wire_sha256=sha(wire),
                max_rows=rows,
                budget_ms=100,
            )
        )
    return tuple(result)


def candidate_specification():
    return dict(
        version="a42364.target-session.v3",
        schedule=[
            {k: v for k, v in r.items() if k not in ("driver", "wire")}
            for r in candidate_schedule()
        ],
        output_oids=TARGET_OIDS,
        window_ms=2000,
        sql_count=16,
        effective_warmups_total=8,
        owner_identity_audit=dict(
            sql_sha256=sha(OWNER_SESSION_SQL.encode()),
            queries=2,
            phase="SEPARATE_AUTHENTICATION_AUDIT_NOT_PROBE",
            budget_ms=100,
        ),
        approved=False,
        qualifies=False,
    )


class PinnedSessionSource:
    """Independent Owner metadata for PID/start, never another session's GUC values."""

    def __init__(self, identity, connections, authority, generation):
        self.identity, self.connections, self.authority, self.generation = (
            identity,
            connections,
            authority,
            generation,
        )
        self.observations = 0

    def observe(self, pid):
        self.authority.require("TARGET_SESSION_GUC")
        require(
            type(pid) is int
            and pid > 1
            and self.observations < 2
            and type(self.generation) is int
            and self.generation > 0,
            "SESSION_AUDIT_BUDGET",
        )
        self.observations += 1
        c = self.connections.open()
        started = time.monotonic_ns()
        try:
            row = c.execute(OWNER_SESSION_SQL, (pid,)).fetchone()
        finally:
            c.close()
        require(time.monotonic_ns() - started <= 100_000_000, "SESSION_AUDIT_TIMEOUT")
        require(
            row is not None
            and len(row) == 4
            and row[0] == pid
            and row[1] is not None
            and row[2] == self.identity.probe_role
            and row[3] == self.identity.database,
            "SESSION_RAW_IDENTITY",
        )
        return dict(
            backend_pid=pid,
            backend_start=row[1].isoformat(),
            role=row[2],
            database=row[3],
            generation=self.generation,
            namespace_sha256=self.identity.scope.namespace_sha256,
            scope_sha256=scope_hash(self.identity.scope),
        )


class CandidateSessionExecutor:
    def __init__(self, identity, authority=None, session_source=None):
        self.identity, self.authority, self.session_source = identity, authority, session_source

    def execute(self, connection):
        require(self.authority is not None, "EXTERNAL_DECISION_REQUIRED")
        self.authority.require("TARGET_SESSION_GUC")
        require(self.session_source is not None, "INDEPENDENT_SESSION_SOURCE_REQUIRED")
        import psycopg
        from psycopg._queries import PostgresQuery
        from psycopg.adapt import Transformer
        from psycopg.types.numeric import Int4, Int8

        from scripts.a42361_live_probe_worker import SqlBudget

        require(
            psycopg.__version__ == "3.3.4" and type(connection) is psycopg.Connection,
            "CANDIDATE_REAL_DRIVER_REQUIRED",
        )
        i = self.identity.verify(self.identity.scope)
        require(
            connection.info.user == i.probe_role
            and connection.info.dbname == i.database
            and connection.info.host == i.socket_host
            and connection.info.port == 5432
            and connection.prepare_threshold == 5
            and gc.isenabled(),
            "CANDIDATE_SESSION_TARGET",
        )
        original = self.session_source.observe(connection.info.backend_pid)
        budget, events, plans = SqlBudget(), [], {}
        thresholds = gc.get_threshold()
        gc_events = []

        def observe_gc(phase, info):
            if len(gc_events) < 32:
                gc_events.append(dict(phase=phase, generation=info["generation"]))

        gc.callbacks.append(observe_gc)
        try:
            with connection.cursor() as cursor:
                for item in candidate_schedule():
                    require(
                        not connection.closed
                        and connection.info.backend_pid == original["backend_pid"]
                        and connection.prepare_threshold == 5,
                        "CANDIDATE_BACKEND_DRIFT",
                    )
                    params = (
                        (Int4(1),)
                        if item["kind"] == "I4"
                        else (Int8(1),)
                        if item["kind"] == "I8"
                        else None
                    )
                    query = PostgresQuery(Transformer.from_context(connection))
                    query.convert(item["driver"], params)
                    require(
                        query.query == item["wire"]
                        and tuple(query.types or ()) == item["parameter_oids"],
                        "CANDIDATE_WIRE_DRIFT",
                    )
                    start = budget.reserve(time.monotonic_ns())
                    cursor.execute(item["driver"], params)  # natural threshold5; no prepare=True.
                    require(
                        cursor._query.query == item["wire"]
                        and tuple(cursor._query.types or ()) == item["parameter_oids"],
                        "CANDIDATE_WIRE_DRIFT",
                    )
                    rows = cursor.fetchmany(9)
                    end = time.monotonic_ns()
                    budget.finish(start, end, len(rows))
                    require(len(rows) <= item["max_rows"], "CANDIDATE_ROW_LIMIT")
                    if item["kind"] == "PROJECTION":
                        output = tuple(column.type_code for column in cursor.description)
                        parsed = parse_target_projection(rows, output, plans)
                        plans = parsed["continuity"]
                    events.append(
                        dict(
                            slot=item["slot"],
                            wire_sha256=item["wire_sha256"],
                            rows=len(rows),
                            elapsed_ns=end - start,
                            kind=item["kind"],
                        )
                    )
            require(
                self.session_source.observe(connection.info.backend_pid) == original,
                "CANDIDATE_BACKEND_DRIFT",
            )
            require(
                len(events) == 16
                and [e["slot"] for e in events if e["kind"] == "PROJECTION"] == [6, 8, 14, 16],
                "CANDIDATE_SCHEDULE_INCOMPLETE",
            )
            require(gc.isenabled() and gc.get_threshold() == thresholds, "CANDIDATE_GC_DRIFT")
            return dict(
                version="a42364.target-session.v3",
                events=events,
                session=original,
                target_session_settings_observed=True,
                source="ACTUAL_APPROVED_PG_DRIVER",
                qualifies=False,
                backend_cpu_ns=None,
                gc_events=gc_events,
            )
        except BaseException:
            budget.stopped = True
            raise Fault("A42363_CANDIDATE_SESSION_INCOMPLETE_NO_RETRY") from None
        finally:
            gc.callbacks.remove(observe_gc)


def validate_offline_projection(rows, oids, previous=None):
    result = parse_target_projection(rows, oids, previous)
    require(result["target_session_settings_observed"] is False, "MODEL_CANNOT_OBSERVE_SESSION")
    return dict(result, source="OFFLINE_CANDIDATE_VECTOR", qualifies=False)
