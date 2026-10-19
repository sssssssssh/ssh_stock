"""Explicit loopback PG17 experiment; never imports business settings before validation."""

import argparse
import importlib.util
import json
import os
import platform
import statistics
import subprocess
import sys
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
    os.environ["AGENT_CHAT_ENABLED"] = "false"
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
    return {
        "count": len(values),
        "seconds": sum(values),
        "median": statistics.median(values),
        **{f"p{p}": ordered[int((len(ordered) - 1) * p / 100)] for p in (50, 95, 99)},
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
            with support.candidate(
                factory, engine, start=day, end=day + timedelta(days=(rows + 4999) // 5000)
            ) as (db, job):
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
                for offset in range(0, rows, 5000):
                    payload = []
                    for n in range(offset, min(rows, offset + 5000)):
                        item = support.sample_row(
                            Model, job.id, day=day + timedelta(days=n // 5000)
                        )
                        item.update(ts_code=f"V{n % 5000 + 1:06d}.SZ", calculated_at=fixed_time)
                        payload.append(item)
                    ws.upsert(Model, payload, KEYS[Model.__tablename__])
                prepare_seconds = time.perf_counter() - started
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
                # Capture the actual generated lookup, only with synthetic parameters.
                captured = []

                def capture(conn, cursor, statement, parameters, context, many):
                    if statement.lstrip().upper().startswith("SELECT"):
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
                    pg_total_relation_size('public.data_publication_row') AS total_bytes""")
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
                    publish_seconds=None,
                    sql_count=len(sql_times),
                    sql=distribution(sql_times),
                    operations={k: distribution(v) for k, v in timers.items()},
                    candidate_digest=digest,
                    peak_process_rss_bytes=rss_bytes(),
                    wal_bytes=int(wal),
                    relation=relation,
                    database_growth_bytes=after[1] - before[1],
                    postgres=version,
                    database_settings=settings,
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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    isolated_url()
    if (
        any(n < 1 or n > 1000000 for n in args.rows)
        or not 1 <= args.repeats <= 10
        or not 0 <= args.existing <= 1000000
    ):
        raise SystemExit("BOUNDED_SYNTHETIC_MEASUREMENT_REQUIRED")
    from loguru import logger

    logger.remove()
    receipt = dict(
        schema_version="publication-candidate-v13",
        baseline_sha=BASELINE,
        head_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        working_tree_dirty=bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
        ),
        environment=dict(
            platform=platform.platform(),
            python=platform.python_version(),
            logical_cpus=os.cpu_count(),
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
