"""A4-1 diagnostic ONLY: unchanged Q0/Q1/Q2 on a physically marked PG17.

No alternate SQL, planner hints, persistent cache, publication or business DB.
All patches are process-local observers and restored even on BaseException.
"""

import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import threading
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter, process_time
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
REVIEW_SHA = "4b158c10f22119374c2e0891308ba935ff91d4ca"
FROZEN_FILES = (
    "backend/app/repositories/ab_merge_read.py",
    "backend/app/repositories/calculation_frame.py",
    "backend/app/services/factors/service.py",
    "backend/app/services/data_publication.py",
    "backend/app/services/job_execution.py",
    "backend/app/services/job_worker.py",
    "backend/app/services/trading_calendar_guard.py",
)
_VERIFIED_RESOURCE_CONTAINERS = set()


def source_receipt():
    result = {}
    for filename in FROZEN_FILES:
        frozen = subprocess.check_output(["git", "show", f"{REVIEW_SHA}:{filename}"], cwd=ROOT)
        current = (ROOT / filename).read_bytes()
        if current != frozen:
            raise ValueError("A4_DIAGNOSTIC_REQUIRES_UNCHANGED_PRODUCTION_SOURCE")
        result[filename] = hashlib.sha256(current).hexdigest()
    return result


def alternating_orders(repeats):
    variants = ("q0", "q1", "q2")
    return [variants[i % 3:] + variants[:i % 3] for i in range(repeats)]


def sql_phase(statement):
    sql = " ".join(statement.lower().split())
    if sql.startswith("lock table"):
        return "T2_lock_acquire"
    if "string_agg(encode(sha256" in sql:
        return "T3_fingerprint_sql"
    if "select exists(select 1 from public.data_publication_row" in sql:
        return "T4_candidate_validation_sql"
    if "trade_calendar" in sql:
        return "T1_calendar_sql"
    if sql.startswith("select") and "stock_trade_status_daily" in sql:
        return "T5_declare"
    return "other_sql"


class Profile:
    """Nested timers are labelled, not added as independent wall-clock costs."""

    def __init__(self, db, engine):
        self.db, self.engine = db, engine
        self.events, self.cursors, self.statements = [], [], {}
        self.started = perf_counter()
        self.lock_started = None

    @contextmanager
    def timing(self, phase, **details):
        started = perf_counter()
        item = {"phase": phase, "offset_seconds": started - self.started, **details}
        try:
            yield item
        except BaseException as error:
            item["failure_type"] = type(error).__name__
            raise
        finally:
            item["seconds"] = perf_counter() - started
            self.events.append(item)

    @contextmanager
    def observe(self):
        import pandas as pd
        import psycopg
        import pytest
        from app.repositories import ab_merge_read as ab
        from app.repositories import calculation_frame as cf
        from sqlalchemy import event

        patch = pytest.MonkeyPatch()
        driver = self.db.connection().connection.driver_connection
        original_factory = driver.server_cursor_factory
        profile = self

        class TracedCursor(psycopg.ServerCursor):
            def execute(self, query, params=None, **kwargs):
                item = {"name": self.name, "declare_sql": str(query), "fetches": []}
                profile.cursors.append(item)
                self._a4_item = item
                started = perf_counter()
                self._a4_started, self._a4_returned = started, 0
                try:
                    return super().execute(query, params, **kwargs)
                finally:
                    item["declare_seconds"] = perf_counter() - started

            def fetchmany(self, size=0):
                started = perf_counter()
                item = {"operation": "FETCH", "requested": size or self.arraysize}
                try:
                    rows = super().fetchmany(size)
                    item["rows"] = len(rows)
                    return rows
                except BaseException as error:
                    item["failure_type"] = type(error).__name__
                    raise
                finally:
                    item["seconds"] = perf_counter() - started
                    item["cursor_until_return_seconds"] = perf_counter() - self._a4_started
                    if item.get("rows", 0):
                        self._a4_item.setdefault("first_row_seconds",
                            item["cursor_until_return_seconds"])
                        self._a4_returned += item["rows"]
                        if self._a4_returned >= 5000:
                            self._a4_item.setdefault("first_5000_seconds",
                                item["cursor_until_return_seconds"])
                    elif item.get("rows") == 0:
                        self._a4_item["until_eof_seconds"] = item["cursor_until_return_seconds"]
                    self._a4_item["fetches"].append(item)

            def close(self):
                try:
                    return super().close()
                finally:
                    if hasattr(self, "_a4_item"):
                        self._a4_item["closed"] = self.closed

        def before(connection, cursor, statement, parameters, context, executemany):
            context._a4_started = perf_counter()

        def after(connection, cursor, statement, parameters, context, executemany):
            phase = sql_phase(statement)
            started = context._a4_started
            self.events.append({"phase": phase, "seconds": perf_counter() - started,
                                "offset_seconds": started - self.started})
            if phase == "T2_lock_acquire" and self.lock_started is None:
                self.lock_started = perf_counter()
            if phase not in {"other_sql", "T2_lock_acquire"}:
                values = dict(context.compiled_parameters[0]) if context.compiled_parameters else {}
                # Internal only: used for EXPLAIN later, never log parameter values.
                self.statements.setdefault(phase, []).append(
                    (str(context.compiled.statement), values))

        def transaction_end(connection):
            if connection is self.db.get_bind() and self.lock_started is not None:
                self.events.append({"phase": "T2_lock_hold", "seconds":
                                    perf_counter() - self.lock_started})
                self.lock_started = None

        def wrap(module, name, phase):
            original = getattr(module, name)

            def measured(*args, **kwargs):
                details = {}
                if name == "_public_fingerprints":
                    details = {"lo": str(args[1]), "hi": str(args[2])}
                with self.timing(phase, **details):
                    return original(*args, **kwargs)

            patch.setattr(module, name, measured)

        for module in (ab, cf):
            wrap(module, "checkpoint", "checkpoint")
        wrap(ab, "_prepare_candidate_read", "T2_T4_prepare_inclusive")
        wrap(ab, "_public_fingerprints", "T3_fingerprint_inclusive")
        wrap(ab, "calendar_windows", "T1_calendar_inclusive")
        wrap(ab, "verify_public_read_evidence", "T8_verify_inclusive")
        original_frame, original_sort, original_reset = (
            pd.DataFrame, pd.DataFrame.sort_values, pd.DataFrame.reset_index)

        def frame(*args, **kwargs):
            with self.timing("T6_frame"):
                return original_frame(*args, **kwargs)

        def sort(frame, *args, **kwargs):
            with self.timing("T6_sort"):
                return original_sort(frame, *args, **kwargs)

        def reset(frame, *args, **kwargs):
            with self.timing("T6_reset_index"):
                return original_reset(frame, *args, **kwargs)

        patch.setattr(cf, "pd", SimpleNamespace(DataFrame=frame))
        patch.setattr(pd.DataFrame, "sort_values", sort)
        patch.setattr(pd.DataFrame, "reset_index", reset)
        driver.server_cursor_factory = TracedCursor
        event.listen(self.engine, "before_cursor_execute", before)
        event.listen(self.engine, "after_cursor_execute", after)
        event.listen(self.engine, "commit", transaction_end)
        event.listen(self.engine, "rollback", transaction_end)
        try:
            yield frame
        finally:
            driver.server_cursor_factory = original_factory
            event.remove(self.engine, "before_cursor_execute", before)
            event.remove(self.engine, "after_cursor_execute", after)
            event.remove(self.engine, "commit", transaction_end)
            event.remove(self.engine, "rollback", transaction_end)
            patch.undo()

    def receipt(self):
        from scripts.publication_candidate_benchmark_v13 import distribution

        phases = sorted({item["phase"] for item in self.events})
        return {"events": self.events, "phase_distributions": {
            phase: distribution([e["seconds"] for e in self.events if e["phase"] == phase])
            for phase in phases}, "cursors": self.cursors,
            "driver_fetch": distribution([f["seconds"] for c in self.cursors
                                            for f in c["fetches"]]),
            "timing_caveat": "inclusive/nested timers overlap; never sum all phases",
            "network_vs_server_vs_decode": "UNPROVEN"}


def resource_snapshot(container):
    """Whole isolated container CPU (including WAL/checkpointer), not backend CPU."""
    if not container:
        return {"container_resources": "UNPROVEN"}
    info = json.loads(subprocess.check_output(["docker", "inspect", container], text=True))[0]
    if info["Config"]["Labels"].get("purpose") != "ssh-stock-a4-physical-test":
        raise ValueError("A4_RESOURCE_CONTAINER_NOT_MARKED")
    if "v14.test_instance=" + os.environ["V14_TEST_INSTANCE"] not in info["Config"]["Cmd"]:
        raise ValueError("A4_RESOURCE_CONTAINER_MARKER_MISMATCH")
    if info["Id"] not in _VERIFIED_RESOURCE_CONTAINERS:
        from sqlalchemy.engine import make_url

        url = make_url(os.environ["TEST_DATABASE_URL"])
        system_id = subprocess.check_output(["docker", "exec", container, "psql",
            "-U", url.username, "-d", url.database, "-Atc",
            "SELECT system_identifier FROM pg_control_system()"], text=True, timeout=15).strip()
        if system_id != os.environ["V14_TEST_SYSTEM_IDENTIFIER"]:
            raise ValueError("A4_RESOURCE_CONTAINER_PHYSICAL_ID_MISMATCH")
        _VERIFIED_RESOURCE_CONTAINERS.add(info["Id"])
    output = subprocess.check_output(["docker", "exec", container, "sh", "-c",
        "cat /sys/fs/cgroup/cpu.stat /sys/fs/cgroup/memory.current "
        "/sys/fs/cgroup/memory.peak /sys/fs/cgroup/io.stat"], text=True, timeout=15)
    return {"cgroup_raw": output, "cpu_limit_nano": info["HostConfig"]["NanoCpus"],
            "memory_limit_bytes": info["HostConfig"]["Memory"]}


def database_snapshot(db):
    from sqlalchemy import text

    # This connection's cumulative counters are flushed before a separate stats
    # snapshot. No reset of cluster statistics and no concurrent load generator.
    db.execute(text("SELECT pg_stat_force_next_flush()"))
    db.execute(text("SELECT pg_stat_clear_snapshot()"))
    return {"database": dict(db.execute(text("""SELECT blks_read,blks_hit,
        temp_files,temp_bytes,blk_read_time,blk_write_time FROM pg_stat_database
        WHERE datname=current_database()""")).mappings().one()),
        "statements": [dict(r) for r in db.execute(text("""SELECT query,calls,rows,
        total_exec_time,shared_blks_hit,shared_blks_read,temp_blks_read,temp_blks_written,
        shared_blk_read_time,shared_blk_write_time,wal_bytes FROM pg_stat_statements
        WHERE dbid=(SELECT oid FROM pg_database WHERE datname=current_database())
        AND (query LIKE '%stock_trade_status_daily%' OR query LIKE 'FETCH%%')""")).mappings()],
        "maintenance": [dict(r) for r in db.execute(text("""SELECT relname,
        last_autovacuum,last_autoanalyze,vacuum_count,autovacuum_count,n_live_tup,n_dead_tup
        FROM pg_stat_user_tables WHERE relname IN
        ('stock_trade_status_daily','stock_factor_daily','data_publication_row')""")).mappings()],
        "autovacuum_workers": [dict(r) for r in db.execute(text("""SELECT pid,
        wait_event_type,wait_event FROM pg_stat_activity
        WHERE datname=current_database() AND backend_type='autovacuum worker'""")).mappings()]}


class ResidentMemory:
    """Sampled RSS lower bound, separate from process-lifetime ru_maxrss."""

    def __init__(self):
        self.stop = threading.Event()
        self.values = []
        self.errors = []

    def sample(self):
        try:
            if sys.platform == "linux":
                # Resident pages of this process, not the PostgreSQL container.
                pages = int(Path("/proc/self/statm").read_text().split()[1])
                self.values.append(pages * os.sysconf("SC_PAGE_SIZE"))
            else:
                rss = subprocess.check_output(
                    ["ps", "-o", "rss=", "-p", str(os.getpid())], text=True, timeout=5)
                self.values.append(int(rss.strip()) * 1024)
        except Exception as error:
            self.errors.append(type(error).__name__)

    def loop(self):
        while not self.stop.wait(0.5):
            self.sample()

    def __enter__(self):
        self.sample()
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.sample()
        self.stop.set()
        self.thread.join(timeout=6)

    def receipt(self):
        return {"samples": len(self.values), "interval_seconds": 0.5,
                "start_bytes": self.values[0] if self.values else None,
                "sampled_peak_bytes": max(self.values) if self.values else None,
                "errors": self.errors, "scope": "read plus T8; sampled peak is a lower bound"}


def seed_multitable(db, root, source, amount, *, preimage_percent=0):
    """Other root: full native 55-column Factor rows + actual first preimages.

    Not padding: the factor values, identities and timestamps follow the model.
    Existing keys retain real first preimages. The percentage is explicit so
    the generic table can be calibrated, not hidden by arbitrary text padding.
    """
    from app.models.market_data import StockFactorDaily as Model
    from app.services.analysis_identity import FACTOR_CALC_VERSION
    from app.services.job_guard import data_queue_identity
    from sqlalchemy import Boolean, Date, DateTime, Float, text

    columns, expressions = [], []
    for index, col in enumerate(Model.__table__.c):
        columns.append('"' + col.name + '"')
        if col.name == "ts_code":
            value = "lpad((g/257+20000)::text,6,'0')||'.SZ'"
        elif isinstance(col.type, DateTime):
            value = "'2026-01-01'::timestamptz"
        elif isinstance(col.type, Date):
            value = "d.cal_date"
        elif col.name == "calc_run_id":
            value = ":source"
        elif col.name == "calc_version":
            value = ":factor_version"
        elif col.name == "config_hash":
            value = ":hash"
        elif col.name == "exclusion_reason":
            value = "'SYNTHETIC_INELIGIBLE'"
        elif isinstance(col.type, Boolean):
            value = f"g%{index+2}<>0"
        elif isinstance(col.type, Float):
            # Typed but incomplete synthetic histories: named rolling horizons
            # are not fully populated on their early dates. This is fixture
            # distribution, NOT a new implementation of any factor formula.
            horizon = max([1] + [int(n) for n in re.findall(r"\d+", col.name)])
            value = (f"CASE WHEN g%257<{horizon} OR g%2={index%2} OR g%31=0 THEN NULL ELSE "
                     f"((g%100003+{index})/137.0)::double precision END")
        else:
            raise ValueError("A4_UNEXPECTED_FACTOR_COLUMN")
        expressions.append(value)
    params = {"n": amount, "existing": amount*preimage_percent//100,
              "source": source, "root": root, "factor_version": FACTOR_CALC_VERSION,
              "hash": data_queue_identity()["analysis"]}
    prefix = """WITH days AS (SELECT cal_date,row_number() OVER (ORDER BY cal_date)-1 AS i
        FROM trade_calendar WHERE is_open ORDER BY cal_date LIMIT 257) """
    db.execute(text(prefix + "INSERT INTO public.stock_factor_daily (" + ",".join(columns)
        + ") SELECT " + ",".join(expressions) + " FROM generate_series(0,:existing-1) g "
        "JOIN days d ON d.i=g%257"), params)
    # Candidates for existing keys use their actual A; new keys use a native
    # populated record of the same schema, never fabricated base_row evidence.
    db.execute(text(prefix + ", native AS (SELECT " + ",".join(
        f"{value} AS {column}" for column, value in zip(columns, expressions, strict=True))
        + " FROM generate_series(0,:n-1) g JOIN days d ON d.i=g%257) "
        """INSERT INTO public.data_publication_row
        (publication_id,table_name,row_key,row_data,base_row,source_id,
         is_deleted,trade_date,entity_key)
        SELECT :root,'stock_factor_daily',jsonb_build_array(n.trade_date,n.ts_code),
          to_jsonb(n),to_jsonb(a),:source,false,n.trade_date,n.ts_code
        FROM native n LEFT JOIN public.stock_factor_daily a USING(trade_date,ts_code)"""), params)
    db.commit()


def measure(db, engine, variant, params, *, container=None, carry_evidence=False):
    from app.repositories import ab_merge_read as ab
    from app.repositories.calculation_frame import read_calculation_frame
    from app.services.data_publication import workspace
    from sqlalchemy import text

    from scripts.ab_read_benchmark_v14 import frame_digest, q0_statement
    from scripts.publication_candidate_benchmark_v13 import rss_bytes

    current = workspace(db)
    if not carry_evidence:
        # Independent read trials start with identical empty root-local evidence.
        # No publication is attempted. T7 explicitly keeps it across commits.
        current.ab_public_read_evidence = {}
    gc.collect()
    before = {"database": database_snapshot(db), "resource": resource_snapshot(container)}
    db.commit()
    profile, metrics = Profile(db, engine), []
    started, cpu = perf_counter(), process_time()
    try:
        with ResidentMemory() as memory, profile.observe() as frame_constructor:
            if variant == "q0":
                # Freeze the prior reported benchmark INCLUDING its absence of
                # per-FETCH owner checkpoints. q0_service measures that asymmetry.
                rows = []
                with db.execute(q0_statement().execution_options(yield_per=5000), params) as result:
                    for batch in result.mappings().partitions(5000):
                        rows.extend(batch)
                frame = frame_constructor(rows)
                del rows
            elif variant == "q0_service":
                frame = read_calculation_frame(db, q0_statement().bindparams(**params),
                                               name="test.a4_q0")
            else:
                frame = ab.ABMergeReadRepository(db, observer=metrics.append).read_trade_status(
                    window=ab.ReadWindow(params["lo"], params["hi"]),
                    calc_version=params["version"], config_hash=params["hash"],
                    window_days=5 if variant == "q2" else None)
            seconds, client_cpu = perf_counter() - started, process_time() - cpu
            db.commit()  # release T2 before verification/digest, as chunked jobs do
            if variant in {"q1", "q2"}:
                db.execute(text("LOCK TABLE public.stock_trade_status_daily IN SHARE MODE"))
                ab.verify_public_read_evidence(db, current)
                db.commit()
        after = {"database": database_snapshot(db), "resource": resource_snapshot(container)}
        frame_bytes = int(frame.memory_usage(index=True, deep=True).sum())
        # Canonicalization is ONLY the golden oracle, excluded from read timing.
        # Q1/Q2's own global sort remains INCLUDED in their measured path.
        record = {"variant": variant, "seconds": seconds, "rows": len(frame),
            "hash": frame_digest(frame), "dtypes": frame.dtypes.astype(str).to_dict(),
            "frame_deep_bytes": frame_bytes, "client_cpu_seconds": client_cpu,
            "process_lifetime_peak_rss_bytes": rss_bytes(), "metrics": metrics,
            "resident_memory": memory.receipt(),
            **profile.receipt(), "before": before, "after": after}
        # Disjoint observables inside the timed read. Residual includes Python
        # mapping/list/progress/bookkeeping and observer setup, NOT pure network.
        read_events = [e for e in profile.events if e.get("offset_seconds", seconds+1) < seconds]

        def total(phase):
            return sum(e["seconds"] for e in read_events if e["phase"] == phase)

        components = {phase: total(phase) for phase in (
            "T1_calendar_inclusive", "T2_lock_acquire", "T3_fingerprint_inclusive",
            "T4_candidate_validation_sql", "T5_declare", "T6_frame", "T6_sort",
            "T6_reset_index", "checkpoint")}
        components["T5_driver_fetch_inclusive"] = record["driver_fetch"]["seconds"]
        components["python_sqlalchemy_progress_observer_residual"] = (
            seconds-sum(components.values()))
        record["read_wall_components_seconds"] = components
        record["final_verify_seconds"] = total_verify = sum(
            e["seconds"] for e in profile.events if e["phase"] == "T8_verify_inclusive")
        record["read_plus_final_verify_seconds"] = seconds+total_verify
        del frame
        return record, profile.statements
    except BaseException as error:
        # Outer caller persists this receipt even if SQL timeout/cancel is a BaseException.
        error.a4_receipt = {"variant": variant, "seconds": perf_counter() - started,
                            "failure_type": type(error).__name__, **profile.receipt()}
        raise


def capture_plans(db, statements):
    from sqlalchemy import text

    plans = {}
    for phase, queries in statements.items():
        indexes = sorted({0, len(queries)//2, len(queries)-1}) if phase == "T5_declare" else [0]
        plans[phase] = []
        for index in indexes:
            sql, values = queries[index]
            entry = {"sql": sql, "ordinal": index+1,
                     "dates": {k: str(v) for k, v in values.items() if k in {"lo", "hi"}}}
            # Ordinary SELECT ANALYZE is explanatory, NOT the measured FETCH.
            for name, prefix in (("select_actual", "EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) "),
                ("cursor_estimated", "EXPLAIN (FORMAT JSON) DECLARE a4_plan CURSOR FOR ")):
                entry[name] = db.scalar(text(prefix + sql), values)
            plans[phase].append(entry)
    return plans


def cursor_actual_plans(db, statements):
    """Separate, untimed full FETCH with auto_explain, not SELECT substituted
    for a cursor plan. Instrumentation is NEVER enabled during timed trials.
    Node timing is off to reduce perturbation; actual rows/loops/buffers remain.
    """
    from sqlalchemy import text

    driver = db.connection().connection.driver_connection
    plans = []

    def notice(diagnostic):
        message = diagnostic.message_primary or ""
        if "plan:" in message and "{" in message:
            plans.append(json.loads(message[message.index("{"):]))

    driver.add_notice_handler(notice)
    try:
        db.execute(text("LOAD 'auto_explain'"))
        db.execute(text("SET client_min_messages=log"))
        for setting, value in (("log_min_duration", "0"), ("log_analyze", "on"),
                               ("log_buffers", "on"), ("log_timing", "off"),
                               ("log_format", "json")):
            db.execute(text(f"SET auto_explain.{setting}='{value}'"))
        queries = statements.get("T5_declare", [])
        for index in sorted({0, len(queries)//2, len(queries)-1}):
            sql, values = queries[index]
            with db.execute(text(sql).execution_options(yield_per=5000), values) as result:
                for _ in result.partitions(5000):
                    pass  # full FETCH, bounded memory, no DataFrame or engine
        if not plans or not any("DECLARE" in p.get("Query Text", "").upper() for p in plans):
            raise ValueError("A4_ACTUAL_CURSOR_PLAN_NOT_CAPTURED")
        return plans
    finally:
        try:
            db.rollback()  # a failed probe must not mask its error with SET in an aborted txn
            db.execute(text("SET auto_explain.log_min_duration='-1'"))
            db.execute(text("RESET client_min_messages"))
        finally:
            driver.remove_notice_handler(notice)


def lock_probe(db, engine):
    """Separate from timed reads; exact DML is a zero-row test-only statement."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    results = {}
    for table, column in (("stock_trade_status_daily", "is_st"),
                          ("data_publication_row", "table_name")):
        result = {}
        lock = text(f"LOCK TABLE public.{table} IN SHARE MODE")
        dml = text(f"UPDATE public.{table} SET {column}={column} WHERE false")
        db.commit()
        db.execute(lock)
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as outsider:
            outsider.execute(text("SET TRANSACTION READ ONLY"))
            started = perf_counter()
            outsider.execute(text("SELECT * FROM public.stock_trade_status_daily LIMIT 1")).all()
            result["rr_reader_seconds"] = perf_counter() - started
        with engine.connect() as outsider:
            outsider.execute(text("SET LOCAL lock_timeout='200ms'"))
            started = perf_counter()
            try:
                outsider.execute(dml)
            except DBAPIError as error:
                result.update(dml_wait_seconds=perf_counter()-started,
                              dml_sqlstate=error.orig.sqlstate)
            else:
                raise AssertionError("A4_SHARE_LOCK_DID_NOT_BLOCK_DML")
            finally:
                outsider.rollback()
        db.commit()
        with engine.begin() as outsider:
            outsider.execute(dml)
            db.execute(text("SET LOCAL lock_timeout='200ms'"))
            started = perf_counter()
            try:
                db.execute(lock)
            except DBAPIError as error:
                result.update(acquire_wait_seconds=perf_counter()-started,
                              acquire_sqlstate=error.orig.sqlstate)
            else:
                raise AssertionError("A4_SHARE_LOCK_DID_NOT_WAIT_FOR_DML")
            finally:
                db.rollback()
        assert result["dml_sqlstate"] == result["acquire_sqlstate"] == "55P03"
        results[table] = result
    return results


def run(args, output):
    from scripts.v14_test_database import isolated_v14_database, verified_test_url

    target = verified_test_url()  # BEFORE any business/settings import
    os.environ.update(DATABASE_URL=target.render_as_string(hide_password=False),
                      TUSHARE_TOKEN="synthetic-a4", LLM_ENABLED="false")
    import pytest
    from app.models.data_publication import DataPublication
    from app.services.job_guard import data_queue_identity
    from loguru import logger
    from sqlalchemy import text

    from scripts.ab_read_benchmark_v14 import compare_runs, frozen_q0, seed, stage
    from tests.integration import test_data_publication as support

    logger.remove()  # progress reporting still executes; don't flood diagnostic stdout
    output.update(schema="v14-a4-1-profile-v1", review_sha=REVIEW_SHA,
        head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
        production_source_hashes=source_receipt(), python=platform.python_version(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        versions={n: importlib.metadata.version(n) for n in ("sqlalchemy", "psycopg", "pandas")},
        cache_control="UNCONTROLLED; serial alternating trials, no cache eviction",
        cold_cache="UNPROVEN", cloud_validation="NOT_AUTHORIZED_NOT_PERFORMED",
        orders=alternating_orders(args.repeats), runs=[], plans={}, monthly=[],
        resource_scope="whole isolated cgroup incl WAL/checkpointer; no other test load",
        snapshot_safety="real regressions in JUnit; profiling never publishes",
        read_performance="OPEN", stage="A4-1 ONLY; no optimization")
    patch = pytest.MonkeyPatch()
    try:
        with isolated_v14_database(patch) as (factory, engine):
            with factory() as db:
                db.execute(text("CREATE EXTENSION pg_stat_statements"))
                _, other = seed(db, public_rows=args.public_rows, candidate_rows=0, other_rows=0)
                db.add(DataPublication(job_id=other, execution_token=uuid4(), state="PREPARING",
                                       identity=data_queue_identity(), row_counts={}))
                db.commit()
                if args.multitable:
                    seed_multitable(db, other, other, args.other_rows,
                                    preimage_percent=args.other_preimage_percent)
                else:
                    stage(db, other, other, args.other_rows, other=True)
                # Actual monthly FactorService history uses start - 430 days.
                db.execute(text("""INSERT INTO trade_calendar(cal_date,is_open,exchange)
                    SELECT d::date,extract(isodow FROM d)<6,'SSE'
                    FROM generate_series('2023-01-01'::date,'2025-12-31'::date,'1 day') d
                    ON CONFLICT DO NOTHING"""))
                db.commit()
            frozen, output["q0_source_sha256"] = frozen_q0()
            patch.setattr(support, "PublicationWorkspace", frozen)
            with support.candidate(factory, engine, start=date(2024, 1, 1),
                                   end=date(2024, 12, 31)) as (db, job):
                # Seed helper uses the first 257 dates: keep its original 2024
                # stock-major distribution even though T7 needs wider calendar.
                db.execute(text("DELETE FROM trade_calendar WHERE cal_date<'2024-01-01'"))
                db.commit()
                stage(db, job.id, job.id, args.candidate_rows,
                      offset=args.public_rows//257//4 if args.public_rows < 100000
                      else args.public_rows//257*3//4)
                db.execute(text("""INSERT INTO trade_calendar(cal_date,is_open,exchange)
                    SELECT d::date,extract(isodow FROM d)<6,'SSE'
                    FROM generate_series('2023-01-01'::date,'2023-12-31'::date,'1 day') d"""))
                for table in (
                        "stock_trade_status_daily", "stock_factor_daily", "data_publication_row"):
                    db.execute(text(f'ANALYZE public."{table}"'))
                db.commit()
                db.execute(text("SET statement_timeout='300s'"))
                db.execute(text("SET lock_timeout='5s'"))
                output["pg_version"] = db.scalar(text("SHOW server_version"))
                output["migration"] = db.scalar(text("SELECT version_num FROM alembic_version"))
                output["physical_system_identifier"] = db.scalar(
                    text("SELECT system_identifier::text FROM pg_control_system()"))
                output["settings"] = {key: db.scalar(text(f"SHOW {key}")) for key in (
                    "cursor_tuple_fraction", "work_mem", "shared_buffers", "effective_cache_size",
                    "max_parallel_workers_per_gather", "statement_timeout", "lock_timeout",
                    "track_io_timing", "pg_stat_statements.track", "pg_stat_statements.max",
                    "autovacuum", "default_statistics_target", "random_page_cost",
                    "seq_page_cost", "effective_io_concurrency")}
                output["fixture"] = {"layout": "stock-major; 257 weekdays in 2024",
                    "requested_a": args.public_rows, "requested_current_b": args.candidate_rows,
                    "requested_other_b": args.other_rows, "multitable": args.multitable,
                    "other_preimage_percent": args.other_preimage_percent,
                    "factor_nulls": "horizon + alternating-field + every31 nulls; synthetic",
                    "candidate_groups": [dict(r) for r in db.execute(text("""SELECT
                    table_name,publication_id=:root AS current_root,count(*) AS rows,
                    count(base_row) AS preimages,count(*) FILTER(WHERE is_deleted) AS tombstones,
                    avg(pg_column_size(s)) AS average_stored_row_bytes
                    FROM public.data_publication_row s GROUP BY 1,2"""),
                        {"root": job.id}).mappings()],
                    "sizes": [dict(r) for r in db.execute(text("""SELECT relname,
                    pg_table_size(relid) AS table_bytes,pg_indexes_size(relid) AS index_bytes,
                    last_analyze FROM pg_stat_user_tables WHERE relname IN
                    ('stock_trade_status_daily','stock_factor_daily','data_publication_row')""")).mappings()],
                    "indexes": [dict(r) for r in db.execute(text("""SELECT tablename,indexdef
                    FROM pg_indexes WHERE schemaname='public' AND tablename IN
                    ('stock_trade_status_daily','stock_factor_daily','data_publication_row')""")).mappings()],
                    "public_rows_by_day": [dict(r) for r in db.execute(text("""SELECT trade_date,
                    count(*) AS rows FROM public.stock_trade_status_daily GROUP BY 1 ORDER BY 1"""))
                    .mappings()]}
                db.commit()
                save(args.output, output)
                for round_number, order in enumerate(output["orders"], 1):
                    for variant in order:
                        params = dict(lo=date(2024, 1, 1), hi=date(2024, 12, 31),
                            version="trade_status_v1", hash=data_queue_identity()["analysis"])
                        record, statements = measure(db, engine, variant, params,
                                                     container=args.container)
                        record["round"] = round_number
                        output["runs"].append(record)
                        # Plans captured AFTER all timed trials to avoid extra
                        # warm-up differences between the alternating reads.
                        if round_number == 1:
                            output["plans"][variant] = statements
                        save(args.output, output, omit_plans=True)
                        print(json.dumps({"variant": variant, "round": round_number,
                            "seconds": record["seconds"], "rows": record["rows"]}), flush=True)
                output["comparison"] = compare_runs(output)
                if args.service_control:
                    record, _ = measure(db, engine, "q0_service", params, container=args.container)
                    output["q0_service_control"] = record
                    if (record["hash"], record["dtypes"]) != (
                            output["runs"][0]["hash"], output["runs"][0]["dtypes"]):
                        raise ValueError("A4_Q0_SERVICE_GOLDEN_MISMATCH")
                if args.monthly:
                    from app.services.recalculation import _month_chunks

                    for variant in ("q0", "q1", "q2"):
                        for index, (lo, hi) in enumerate(_month_chunks(
                                date(2025, 1, 1), date(2025, 3, 31))):
                            record, _ = measure(db, engine, variant,
                                {**params, "lo": lo-timedelta(days=430), "hi": hi},
                                container=args.container, carry_evidence=index > 0)
                            record.update(chunk_start=str(lo), chunk_end=str(hi),
                                input_start=str(lo-timedelta(days=430)), input_end=str(hi))
                            output["monthly"].append(record)
                            save(args.output, output, omit_plans=True)
                    output["monthly_scope"] = (
                        "actual month/430-day input bounds, read-only replay; no factors/writes; "
                        "final verification per chunk is reported separately, not hidden")
                    from scripts.ab_read_profile_summary_v14_a4 import verify_monthly

                    output["monthly_comparison"] = verify_monthly(output["monthly"])
                statements_by_variant = output["plans"]
                output["plans"] = {variant: capture_plans(db, statements)
                                   for variant, statements in statements_by_variant.items()}
                output["actual_cursor_plans_untimed"] = {
                    variant: cursor_actual_plans(db, statements)
                    for variant, statements in statements_by_variant.items()}
                db.commit()
                output["lock_probe_separate_from_trials"] = lock_probe(db, engine)
    except BaseException as error:
        # Don't log params/DSN/traceback of SQL errors to synthetic receipt.
        output["failure"] = getattr(error, "a4_receipt", {"failure_type": type(error).__name__})
        output["failure"]["sqlstate"] = getattr(getattr(error, "orig", error), "sqlstate", None)
        raise
    finally:
        patch.undo()
        save(args.output, output, omit_plans=bool(output.get("failure")))


def save(path, output, *, omit_plans=False):
    # Output is generated synthetic evidence, not a source edit.
    payload = {**output, "plans": "PENDING_CAPTURE"} if omit_plans else output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, default=str, indent=2)+"\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-rows", type=int, default=10000)
    parser.add_argument("--candidate-rows", type=int, default=5253)
    parser.add_argument("--other-rows", type=int, default=10894)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--multitable", action="store_true")
    parser.add_argument("--other-preimage-percent", type=int, choices=range(101), default=0)
    parser.add_argument("--monthly", action="store_true")
    parser.add_argument("--service-control", action="store_true")
    parser.add_argument("--container")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.public_rows, args.candidate_rows, args.other_rows) < 1 or args.repeats < 3:
        parser.error("positive fixtures and at least three alternating repetitions required")
    output = {}
    try:
        run(args, output)
    except BaseException as error:
        output.setdefault("failure", {"failure_type": type(error).__name__})
        save(args.output, output, omit_plans=True)
        print(json.dumps({"complete": False, "failure": output["failure"]["failure_type"]}))
        raise SystemExit(1) from None
    print(json.dumps({"complete": True, "read_performance": "OPEN",
                      "runs": len(output["runs"])}))


if __name__ == "__main__":
    main()
