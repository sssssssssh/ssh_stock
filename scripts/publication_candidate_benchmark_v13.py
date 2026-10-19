"""Explicit loopback PG17 experiment; never imports business settings before validation."""

import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

BASELINE = "9a377e410516d6bf53e6d1363ec5094af88478df"
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]


def isolated_url():
    from sqlalchemy.engine import make_url

    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw:
        raise SystemExit("EXPLICIT_LOOPBACK_SYNTHETIC_TEST_DATABASE_REQUIRED")
    url = make_url(raw)
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in {"127.0.0.1", "localhost"}
        or not (url.database or "").endswith("_test")
    ):
        raise SystemExit("EXPLICIT_LOOPBACK_SYNTHETIC_TEST_DATABASE_REQUIRED")
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    os.environ["TUSHARE_TOKEN"] = "synthetic-v13"
    os.environ["LLM_ENABLED"] = "false"
    return url


def rss_bytes():
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                *[
                    (n, ctypes.c_size_t)
                    for n in (
                        "PeakWorkingSetSize",
                        "WorkingSetSize",
                        "QuotaPeakPagedPoolUsage",
                        "QuotaPagedPoolUsage",
                        "QuotaPeakNonPagedPoolUsage",
                        "QuotaNonPagedPoolUsage",
                        "PagefileUsage",
                        "PeakPagefileUsage",
                    )
                ],
            ]

        value = Counters()
        value.cb = ctypes.sizeof(value)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        memory_info = ctypes.WinDLL("psapi").GetProcessMemoryInfo
        memory_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        memory_info.restype = wintypes.BOOL
        if not memory_info(kernel.GetCurrentProcess(), ctypes.byref(value), value.cb):
            raise OSError("PROCESS_MEMORY_MEASUREMENT_FAILED")
        return value.PeakWorkingSetSize
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
        1 if sys.platform == "darwin" else 1024
    )


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "seconds": 0}
    quantiles = (
        statistics.quantiles(ordered, n=100, method="inclusive")
        if len(ordered) > 1
        else [ordered[0]] * 99
    )
    return {
        "count": len(values),
        "seconds": sum(values),
        "median": statistics.median(values),
        **{f"p{p}": quantiles[p - 1] for p in (50, 95, 99)},
    }


def baseline_class():
    source = subprocess.check_output(
        ["git", "show", f"{BASELINE}:backend/app/services/data_publication.py"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_loader("publication_v13_frozen_baseline", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, "<frozen-publication-baseline>", "exec"), module.__dict__)
    return module.PublicationWorkspace


class ReaderProbe:
    """Independent public RR readers; their SQL is excluded from Writer counts."""

    def __init__(self, engine, amount):
        from sqlalchemy import create_engine

        self.engine = create_engine(engine.url)
        self.amount = amount
        self.stop = threading.Event()
        self.measuring = False
        self.latencies, self.errors, self.threads = [], [], []
        self.writer_pid = None
        self.waits = defaultdict(int)
        self.max_blockers = 0

    def __enter__(self):
        for _ in range(self.amount):
            thread = threading.Thread(target=self.read, daemon=True)
            self.threads.append(thread)
            thread.start()
        return self

    def read(self):
        from sqlalchemy import text

        while not self.stop.is_set():
            started = time.perf_counter()
            measured = self.measuring
            try:
                with self.engine.connect().execution_options(
                    isolation_level="REPEATABLE READ"
                ) as connection:
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                    connection.execute(text("SET LOCAL statement_timeout='5s'"))
                    first = connection.execute(
                        text(
                            "SELECT count(*),min(calc_run_id::text),"
                            "max(calc_run_id::text) FROM public.stock_trade_status_daily"
                        )
                    ).one()
                    rows = connection.execute(
                        text(
                            "SELECT calc_run_id::text FROM "
                            "public.stock_trade_status_daily ORDER BY trade_date,ts_code LIMIT 20"
                        )
                    ).all()
                    assert first[1] == first[2]
                    assert all(r[0] == first[1] for r in rows)
                    if measured and self.writer_pid is not None:
                        activity = (
                            connection.execute(
                                text(
                                    "SELECT wait_event_type,wait_event,"
                                    "cardinality(pg_blocking_pids(pid)) AS blockers "
                                    "FROM pg_stat_activity "
                                    "WHERE pid=:pid"
                                ),
                                dict(pid=self.writer_pid),
                            )
                            .mappings()
                            .one_or_none()
                        )
                        if activity:
                            label = (
                                f"{activity['wait_event_type'] or 'CPU/client'}/"
                                f"{activity['wait_event'] or 'none'}"
                            )
                            self.waits[label] += 1
                            self.max_blockers = max(self.max_blockers, activity["blockers"])
                if measured:
                    self.latencies.append(time.perf_counter() - started)
            except Exception as error:
                self.errors.append(type(error).__name__)
            self.stop.wait(0.25)

    def finish(self):
        self.measuring = False
        self.stop.set()
        for thread in self.threads:
            thread.join(timeout=15)
        if any(thread.is_alive() for thread in self.threads):
            raise RuntimeError("SYNTHETIC_READER_DID_NOT_EXIT")
        self.engine.dispose()

    def __exit__(self, *args):
        self.finish()


def run(args, rows, repeat):
    from datetime import UTC, date, datetime, timedelta

    import pytest
    from app.models.data_publication import DataPublicationRow
    from app.models.job import JobRun
    from app.models.market_data import StockTradeStatusDaily as Model
    from app.services import data_publication as publication
    from app.services.data_publication import KEYS
    from sqlalchemy import event, func, select, text

    from tests.integration import test_data_publication as support
    from tests.integration.m16_6_support import isolated_contract_database

    timers = defaultdict(list)
    sql_times = []
    plans = {}
    patch = pytest.MonkeyPatch()
    cls = (
        baseline_class() if args.implementation == "baseline" else publication.PublicationWorkspace
    )
    patch.setattr(support, "PublicationWorkspace", cls)
    day = date(2026, 1, 1)
    fixed_time = datetime(2026, 1, 1, tzinfo=UTC)
    try:
        with isolated_contract_database(patch) as (factory, engine):
            with factory() as db:
                version = db.scalar(text("SHOW server_version"))
                settings = dict(
                    db.execute(
                        text(
                            "SELECT name,setting FROM pg_settings WHERE name IN "
                            "('shared_buffers','work_mem','max_connections','fsync','synchronous_commit')"
                        )
                    ).all()
                )
                source = JobRun(job_type="recalculate", status="SUCCESS", job_metadata={})
                db.add(source)
                db.flush()
                base = support.sample_row(Model, source.id, day=day)
                base["calculated_at"] = fixed_time
                if args.public:
                    columns = list(base)
                    names = ",".join(f'"{c}"' for c in columns)
                    expressions = [
                        "d.day"
                        if c == "trade_date"
                        else "'V' || lpad(e.n::text,6,'0') || '.SZ'"
                        if c == "ts_code"
                        else f'r."{c}"'
                        for c in columns
                    ]
                    db.execute(
                        text(
                            f"INSERT INTO public.stock_trade_status_daily ({names}) "
                            f"SELECT {','.join(expressions)} FROM generate_series(1,:stocks) e(n) "
                            "CROSS JOIN generate_series(CAST(:day AS date), "
                            "CAST(:day AS date)+(:days-1),interval '1 day') d(day) "
                            "CROSS JOIN LATERAL jsonb_populate_record("
                            "NULL::public.stock_trade_status_daily,CAST(:base AS jsonb)) r"
                        ),
                        dict(
                            stocks=min(rows, 5000),
                            day=day,
                            days=(rows + 4999) // 5000,
                            base=json.dumps(base, default=str),
                        ),
                    )
                db.commit()
            with (
                support.candidate(
                    factory, engine, start=day, end=day + timedelta(days=(rows + 4999) // 5000)
                ) as (db, job),
                ReaderProbe(engine, args.readers) as readers,
            ):
                ws = db.info["publication_workspace"]
                if args.existing:
                    base = support.sample_row(Model, job.id, day=day)
                    base["calculated_at"] = fixed_time
                    db.execute(
                        text("""INSERT INTO public.data_publication_row
                        (publication_id,table_name,row_key,row_data,base_row,source_id,is_deleted,
                         trade_date,entity_key)
                        SELECT :job,'stock_trade_status_daily',jsonb_build_array(d.day::date,code),
                        CAST(:base AS jsonb)||
                          jsonb_build_object('trade_date',d.day::date,'ts_code',code),
                        to_jsonb(p),:job,false,d.day::date,code
                        FROM generate_series(1,:stocks) e(n)
                        CROSS JOIN generate_series(CAST(:day AS date),
                          CAST(:day AS date)+(:days-1),interval '1 day') d(day)
                        CROSS JOIN LATERAL (SELECT 'V'||lpad(e.n::text,6,'0')||'.SZ' AS code) k
                        LEFT JOIN public.stock_trade_status_daily p
                          ON p.trade_date=d.day::date AND p.ts_code=code"""),
                        dict(
                            job=job.id,
                            stocks=min(args.existing, 5000),
                            day=day,
                            days=(args.existing + 4999) // 5000,
                            base=json.dumps(base, default=str),
                        ),
                    )
                    db.commit()
                db.execute(text("ANALYZE public.data_publication_row"))
                db.execute(text("ANALYZE public.stock_trade_status_daily"))
                db.commit()
                io_before = db.scalar(text("SELECT jsonb_agg(to_jsonb(i)) FROM pg_stat_io i"))
                rtt = []
                for _ in range(5):
                    rtt_started = time.perf_counter()
                    db.scalar(text("SELECT 1"))
                    rtt.append(time.perf_counter() - rtt_started)
                db.commit()
                before = db.execute(
                    text(
                        "SELECT pg_current_wal_insert_lsn()::text, "
                        "pg_database_size(current_database())"
                    )
                ).one()
                db.commit()

                def begin(conn, cursor, statement, parameters, context, many):
                    context._v13_started = time.perf_counter()

                def end(conn, cursor, statement, parameters, context, many):
                    sql_times.append(time.perf_counter() - context._v13_started)

                readers.writer_pid = db.scalar(text("SELECT pg_backend_pid()"))
                db.commit()
                event.listen(engine, "before_cursor_execute", begin)
                event.listen(engine, "after_cursor_execute", end)
                for name in ("_lookup", "_lookup_batch", "_store_batch"):
                    if not hasattr(ws, name):
                        continue
                    original = getattr(ws, name)

                    def measured(*a, _fn=original, _name=name, **kw):
                        label = (
                            ("public_lookup" if kw.get("public") else "candidate_lookup")
                            if _name == "_lookup"
                            else _name
                        )
                        started = time.perf_counter()
                        try:
                            return _fn(*a, **kw)
                        finally:
                            timers[label].append(time.perf_counter() - started)

                    patch.setattr(ws, name, measured)
                started = time.perf_counter()
                readers.measuring = True
                prepare_seconds = payload_build_seconds = 0.0
                prototype = support.sample_row(Model, job.id, day=day)
                for offset in range(0, rows, 5000):
                    build_started = time.perf_counter()
                    payload = []
                    for n in range(offset, min(rows, offset + 5000)):
                        item = {
                            **prototype,
                            "trade_date": day + timedelta(days=n // 5000),
                            "ts_code": f"V{n % 5000 + 1:06d}.SZ",
                            "calculated_at": fixed_time,
                        }
                        payload.append(item)
                    payload_build_seconds += time.perf_counter() - build_started
                    batch_started = time.perf_counter()
                    ws.upsert(Model, payload, KEYS[Model.__tablename__])
                    prepare_seconds += time.perf_counter() - batch_started
                elapsed_seconds = time.perf_counter() - started
                readers.finish()
                operation_stats = {key: distribution(value) for key, value in timers.items()}
                sql_stats = distribution(sql_times)
                event.remove(engine, "before_cursor_execute", begin)
                event.remove(engine, "after_cursor_execute", end)
                staged = db.scalar(
                    select(func.count())
                    .select_from(DataPublicationRow)
                    .where(DataPublicationRow.publication_id == job.id)
                )
                digest = db.scalar(
                    text("""SELECT md5(string_agg(md5(jsonb_build_array(
                    table_name,row_key,row_data-'calc_run_id',base_row-'calc_run_id',is_deleted)::text),
                    '' ORDER BY table_name,row_key)) FROM public.data_publication_row
                    WHERE publication_id=:job"""),
                    dict(job=job.id),
                )
                scope = None
                if args.scope_probe:
                    scope_started = time.perf_counter()
                    rss_before = rss_bytes()
                    end_day = day + timedelta(days=(max(rows, args.existing) + 4999) // 5000 - 1)
                    existing_keys = set(
                        db.execute(
                            select(Model.trade_date, Model.ts_code).where(
                                Model.trade_date >= day, Model.trade_date <= end_day
                            )
                        ).all()
                    )
                    existing_seconds = time.perf_counter() - scope_started
                    current_keys = {
                        (day + timedelta(days=n // 5000), f"V{n % 5000 + 1:06d}.SZ")
                        for n in range(rows)
                    }
                    stale = existing_keys - current_keys
                    difference_seconds = time.perf_counter() - scope_started - existing_seconds
                    masks = sorted(stale)[:500]
                    mask_started = time.perf_counter()
                    event.listen(engine, "before_cursor_execute", begin)
                    event.listen(engine, "after_cursor_execute", end)
                    sql_before = len(sql_times)
                    ws.delete_keys(Model, masks)
                    event.remove(engine, "before_cursor_execute", begin)
                    event.remove(engine, "after_cursor_execute", end)
                    scope = dict(
                        existing_keys=len(existing_keys),
                        current_keys=len(current_keys),
                        stale_keys=len(stale),
                        existing_key_seconds=existing_seconds,
                        difference_seconds=difference_seconds,
                        mask_sample_rows=len(masks),
                        mask_sample_seconds=time.perf_counter() - mask_started,
                        mask_sql_count=len(sql_times) - sql_before,
                        peak_rss_before_bytes=rss_before,
                        peak_rss_after_bytes=rss_bytes(),
                        full_mask_write_measured=False,
                    )
                # Capture the actual generated lookup, only with synthetic parameters.
                captured = []

                def capture(conn, cursor, statement, parameters, context, many):
                    if statement.lstrip().upper().startswith(("SELECT", "WITH")):
                        captured.append((statement, parameters))

                event.listen(engine, "before_cursor_execute", capture)
                ws._lookup(Model, payload[:500])
                ws._lookup(Model, payload[:500], public=True)
                event.remove(engine, "before_cursor_execute", capture)
                for i, (statement, parameters) in enumerate(captured):
                    with db.connection().connection.cursor() as cursor:
                        cursor.execute(
                            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters
                        )
                        plans[str(i)] = cursor.fetchone()[0]
                after = db.execute(
                    text(
                        "SELECT pg_current_wal_insert_lsn()::text, "
                        "pg_database_size(current_database())"
                    )
                ).one()
                wal = db.scalar(
                    text("SELECT pg_wal_lsn_diff(:end,:start)"), dict(end=after[0], start=before[0])
                )
                relation = dict(
                    db.execute(
                        text("""SELECT pg_table_size('public.data_publication_row')
                    AS table_bytes,pg_indexes_size('public.data_publication_row') AS index_bytes,
                    pg_total_relation_size('public.data_publication_row') AS total_bytes,
                    (SELECT CASE WHEN reltoastrelid=0 THEN 0 ELSE
                        pg_total_relation_size(reltoastrelid) END FROM pg_class
                        WHERE oid='public.data_publication_row'::regclass) AS toast_bytes""")
                    )
                    .mappings()
                    .one()
                )
                result = dict(
                    rows=rows,
                    repeat=repeat,
                    implementation=args.implementation,
                    public_a=args.public,
                    existing_candidates=args.existing,
                    staged=staged,
                    prepare_seconds=prepare_seconds,
                    input_build_seconds=payload_build_seconds,
                    elapsed_seconds=elapsed_seconds,
                    publish_seconds=None,
                    sql_count=sql_stats["count"],
                    sql=sql_stats,
                    operations=operation_stats,
                    scope=scope,
                    candidate_digest=digest,
                    peak_process_rss_bytes=rss_bytes(),
                    wal_bytes=int(wal),
                    relation=relation,
                    database_growth_bytes=after[1] - before[1],
                    postgres=version,
                    database_settings=settings,
                    roundtrip=distribution(rtt),
                    pg_stat_io_before=io_before,
                    pg_stat_io_after=db.scalar(
                        text("SELECT jsonb_agg(to_jsonb(i)) FROM pg_stat_io i")
                    ),
                    counter_scope="PG instance; concurrent load may contribute to IO/WAL",
                    reader_count=args.readers,
                    reader_latency=distribution(list(readers.latencies)),
                    reader_errors=list(readers.errors),
                    writer_wait_samples=dict(readers.waits),
                    max_writer_blockers=readers.max_blockers,
                    network_wait_seconds=None,
                    timing_scope="Driver SQL time includes execution, transfer and decoding",
                    plans=plans,
                    cache_condition="OS cache uncontrolled",
                    cold_cache_claim=False,
                    synthetic=True,
                    production_validation="UNPROVEN",
                )
                db.rollback()
                return result
    finally:
        patch.undo()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-synthetic", action="store_true", required=True)
    parser.add_argument("--implementation", choices=["baseline", "current"], default="current")
    parser.add_argument("--rows", type=int, nargs="+", default=[1000, 100000, 500000])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--public", action="store_true")
    parser.add_argument("--existing", type=int, default=0)
    parser.add_argument("--scope-probe", action="store_true")
    parser.add_argument("--readers", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    isolated_url()
    if (
        any(n < 1 or n > 1000000 for n in args.rows)
        or not 1 <= args.repeats <= 10
        or not 0 <= args.existing <= 1000000
        or not 0 <= args.readers <= 4
    ):
        raise SystemExit("BOUNDED_SYNTHETIC_MEASUREMENT_REQUIRED")
    from loguru import logger

    logger.remove()
    receipt = dict(
        schema_version="publication-candidate-v13",
        measurement_version="v13-2-excludes-input-build",
        baseline_sha=BASELINE,
        head_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        working_tree_dirty=bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
        ),
        environment=dict(
            platform=platform.platform(),
            python=platform.python_version(),
            logical_cpus=os.cpu_count(),
            processor=platform.processor(),
            disk_free_bytes=shutil.disk_usage(ROOT).free,
            packages={
                name: importlib.metadata.version(name)
                for name in ("pandas", "psycopg", "SQLAlchemy")
            },
        ),
        results=[],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for rows in args.rows:
        for repeat in range(args.repeats):
            result = run(args, rows, repeat)
            receipt["results"].append(result)
            args.output.write_text(
                json.dumps(receipt, default=str, allow_nan=False, indent=2) + "\n", encoding="utf-8"
            )
            print(
                json.dumps(
                    {k: v for k, v in result.items() if k not in {"plans", "database_settings"}}
                ),
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
