"""Bounded synthetic-only instrumentation of actual candidate calls, not replay SQL."""

import functools
import hashlib
import json
from collections import Counter
from contextlib import contextmanager
from time import monotonic

PLAN_FIELDS = frozenset(
    {
        "Plan",
        "Plans",
        "Node Type",
        "Relation Name",
        "Index Name",
        "Actual Rows",
        "Actual Loops",
        "Execution Time",
        "Planning Time",
        "Shared Hit Blocks",
        "Shared Read Blocks",
        "Temp Read Blocks",
        "Temp Written Blocks",
        "Plan Rows",
    }
)


def safe_plan(value):
    if isinstance(value, dict):
        return {k: safe_plan(v) for k, v in value.items() if k in PLAN_FIELDS}
    if isinstance(value, list):
        return [safe_plan(v) for v in value]
    return value


class CandidateObserver:
    """Installed only after the measurement harness verifies its UUID-owned PG17."""

    def __init__(self, engine, patch, rss):
        from app.services import data_publication as publication
        from app.services import recalculation
        from sqlalchemy import event

        self.stack, self.timeline, self.plans = [], [], []
        self.metrics, self.rows, self.seen = {}, {}, set()
        self.connections, self.plan_tables = {}, set()
        self.plan_target, self.plan_error = None, None
        self.control_sql_calls = 0
        self.rss, self.started = rss, monotonic()
        self.engine, self.event = engine, event
        self.handlers = []

        def wrap(owner, name, label, table=False):
            original = getattr(owner, name)

            @functools.wraps(original)
            def observed(*args, **kwargs):
                model = args[1] if table else None
                table_name = model.__tablename__ if model else None
                payload_rows = len(args[2]) if table else len(args[1]) if label == "store" else None
                with self.stage(label, table_name, payload_rows):
                    if label == "lookup" and table_name not in self.plan_tables:
                        return self.first_lookup(original, args, kwargs, table_name)
                    if label == "store":
                        payload = args[1]
                        result = original(*args, **kwargs)
                        for row in payload:
                            key = (
                                str(row["publication_id"]),
                                row["table_name"],
                                json.dumps(row["row_key"], sort_keys=True),
                            )
                            counts = self.rows.setdefault(row["table_name"], Counter())
                            counts["accepted_patch_rows"] += 1
                            counts["update" if key in self.seen else "insert"] += 1
                            self.seen.add(key)
                            if len(self.seen) > 250_000:
                                raise RuntimeError("BIZ02_OBSERVER_KEY_BUDGET")
                        return result
                    return original(*args, **kwargs)

            patch.setattr(owner, name, observed)

        wrap(recalculation, "validate_cross_table_range", "cross_table_quality")
        wrap(publication.PublicationWorkspace, "upsert", "upsert", True)
        wrap(publication.PublicationWorkspace, "_lookup_batch", "lookup", True)
        wrap(publication.PublicationWorkspace, "_store_batch", "store")
        for name, callback in (
            ("before_cursor_execute", self.before),
            ("after_cursor_execute", self.after),
        ):
            event.listen(engine, name, callback)
            self.handlers.append((name, callback))

        import psycopg

        for cls in (psycopg.Cursor, psycopg.ServerCursor):
            for name in ("fetchone", "fetchmany", "fetchall"):
                original = getattr(cls, name)

                def fetch_wrapper(method, operation):
                    @functools.wraps(method)
                    def fetch(cursor, *args, **kwargs):
                        result = method(cursor, *args, **kwargs)
                        item = self.metric()
                        item["fetch_calls"] += 1
                        item["fetched_rows"] += (
                            int(result is not None) if operation == "fetchone" else len(result)
                        )
                        return result

                    return fetch

                patch.setattr(cls, name, fetch_wrapper(original, name))

    def metric(self):
        label = "/".join(f"{a}:{b or '-'}" for a, b in self.stack) or "orchestration"
        return self.metrics.setdefault(label, Counter())

    @contextmanager
    def stage(self, label, table, payload_rows=None):
        began = monotonic()
        self.stack.append((label, table))
        metric = self.metric()
        metric["calls"] += 1
        if payload_rows is not None:
            metric["attempted_rows"] += payload_rows
            metric["max_payload_rows"] = max(metric["max_payload_rows"], payload_rows)
        try:
            yield
        except BaseException:
            metric["failed_calls"] += 1
            raise
        finally:
            elapsed = monotonic() - began
            metric["wall_seconds"] += elapsed
            metric["peak_process_rss_bytes"] = max(metric["peak_process_rss_bytes"], self.rss())
            self.timeline.append(
                dict(
                    stage=label,
                    table=table,
                    payload_rows=payload_rows,
                    start_seconds=began - self.started,
                    end_seconds=monotonic() - self.started,
                )
            )
            self.stack.pop()
            if len(self.timeline) > 30_000:
                raise RuntimeError("BIZ02_OBSERVER_TIMELINE_BUDGET")

    def before(self, conn, cursor, sql, params, context, many):
        context.biz02_began, context.biz02_metric = monotonic(), self.metric()
        context.biz02_metric["sql_calls"] += 1
        operation = sql.lstrip().split(None, 1)[0].upper()
        context.biz02_metric["sql_" + operation] += 1

    def after(self, conn, cursor, sql, params, context, many):
        context.biz02_metric["sql_driver_seconds"] += monotonic() - context.biz02_began

    def control(self, cursor, sql):
        began = monotonic()
        cursor.execute(sql)
        self.control_sql_calls += 1
        self.metric()["observer_control_sql_calls"] += 1
        self.metric()["observer_control_sql_seconds"] += monotonic() - began

    def notice(self, diagnostic):
        if self.plan_target is None or "plan:" not in diagnostic.message_primary:
            return
        try:
            duration, payload = diagnostic.message_primary.split("plan:", 1)
            value = json.loads(payload)
            self.plans.append(
                dict(
                    table=self.plan_target,
                    capture="ACTUAL_TIMED_LOOKUP",
                    query_sha256=hashlib.sha256(value["Query Text"].encode()).hexdigest(),
                    server_duration_ms=float(duration.split("duration:")[1].split("ms")[0]),
                    plan=safe_plan(value),
                    parameters_exported=False,
                )
            )
        except (ValueError, KeyError, TypeError):
            self.plan_error = "BIZ02_ACTUAL_PLAN_INVALID"

    def first_lookup(self, method, args, kwargs, table):
        raw = args[0].db.connection().connection.driver_connection
        if id(raw) not in self.connections:
            with raw.cursor() as cursor:
                for sql in (
                    "LOAD 'auto_explain'",
                    "SET client_min_messages=notice",
                    "SET auto_explain.log_format=json",
                    "SET auto_explain.log_level=notice",
                    "SET auto_explain.log_parameter_max_length=0",
                    "SET auto_explain.log_timing=off",
                    "SET auto_explain.log_buffers=on",
                ):
                    self.control(cursor, sql)
            raw.add_notice_handler(self.notice)
            self.connections[id(raw)] = raw
        before = len(self.plans)
        self.plan_target = table
        try:
            with raw.cursor() as cursor:
                self.control(cursor, "SET auto_explain.log_analyze=on")
                self.control(cursor, "SET auto_explain.log_min_duration=0")
            result = method(*args, **kwargs)
        finally:
            from psycopg.pq import TransactionStatus

            try:
                if not raw.closed and raw.info.transaction_status != TransactionStatus.INERROR:
                    # Extended-protocol notices may arrive on the next command's
                    # Sync, after the result rows were delivered to SQLAlchemy.
                    with raw.cursor() as cursor:
                        self.control(cursor, "SET auto_explain.log_min_duration=-1")
                        self.control(cursor, "SET auto_explain.log_analyze=off")
            finally:
                self.plan_target = None
        if self.plan_error or len(self.plans) != before + 1:
            raise RuntimeError(self.plan_error or "BIZ02_ACTUAL_PLAN_MISSING")
        self.plan_tables.add(table)
        return result

    def close(self):
        for name, callback in self.handlers:
            self.event.remove(self.engine, name, callback)
        for raw in self.connections.values():
            raw.remove_notice_handler(self.notice)
        return dict(
            schema="biz-perf-02.observer.v1",
            inclusive_stages_overlap=True,
            timing_includes_observer=True,
            direct_plan_control_sql_count=self.control_sql_calls,
            note="auto_explain is enabled only for first timed lookup per table; no replay; "
            "RSS is process lifetime high-water, not per-stage exclusive memory; "
            "insert/update counts describe acknowledged B patch stores, not publication",
            stages={k: dict(v) for k, v in self.metrics.items()},
            timeline=self.timeline,
            plans=self.plans,
            writes={k: dict(v) for k, v in self.rows.items()},
        )
