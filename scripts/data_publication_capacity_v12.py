"""Explicit isolated PG17 synthetic capacity experiment; never accepts a business DB.

Full publication protocol uses real candidate upserts/preimages/commit, but the
performance fixture certifies structural samples, NOT real financial calculations.
Real calculator + quality + Worker coverage lives in test_data_publication.py.
"""

import argparse
import json
import os
import resource
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from app.models import market_data as m  # noqa: E402
from app.models.data_publication import DataPublicationRow  # noqa: E402
from app.models.job import JobRun  # noqa: E402
from app.repositories.job_run import update_job  # noqa: E402
from app.services.data_publication import KEYS, MODELS, record_validation  # noqa: E402

from tests.integration.m16_6_support import isolated_contract_database  # noqa: E402
from tests.integration.test_data_publication import candidate, sample_row  # noqa: E402


def payload(model, source, day, entity, value):
    if model is m.SignalForwardEval:
        return dict(
            trade_date=day,
            ts_code=f"S{entity:06d}.SZ",
            signal_type="RIGHT_SIDE_NEW",
            algo_version="v1.0",
            eval_version="eval_v3",
            entry_basis="NEXT_OPEN",
            horizon_basis="MARKET_TRADING_DAY",
            ret5=value / 1000,
        )
    if model is m.DataQualityDaily:
        return dict(
            trade_date=day,
            dataset="capacity_synthetic",
            status="PASS",
            job_id=source,
            expected_rows=entity,
            actual_rows=entity,
        )
    result = sample_row(model, source, value, day)
    for col in model.__table__.columns:
        if col.name not in result and col.default is not None and col.default.is_scalar:
            result[col.name] = col.default.arg
    if "ts_code" in result:
        result["ts_code"] = f"S{entity:06d}.SZ"
    if "sector_id" in result:
        result["sector_id"] = entity
    if "theme_code" in result:
        result["theme_code"] = f"T{entity:04d}"
    return result


def entities(model, stocks):
    return (
        1
        if model in (m.MarketDaily, m.DataQualityDaily)
        else min(50, stocks)
        if model is m.SectorFactorDaily
        else min(100, stocks)
        if model is m.ThemeFactorDaily
        else stocks
    )


def seed(factory, stocks, days):
    with factory() as db:
        old = JobRun(job_type="recalculate", status="SUCCESS", job_metadata={})
        db.add(old)
        db.add_all(m.TradeCalendar(cal_date=day, is_open=True) for day in days)
        db.add_all(
            m.Sector(sector_id=i, source="SW", source_code=str(i), name="synthetic", level="L1")
            for i in range(1, min(stocks, 50) + 1)
        )
        db.add_all(
            m.Theme(theme_code=f"T{i:04d}", source="THS", name="synthetic", theme_type="N")
            for i in range(1, min(stocks, 100) + 1)
        )
        db.flush()
        for model in MODELS:
            if model is m.SignalForwardEval:
                db.execute(
                    text("""INSERT INTO signal_forward_eval
                    (signal_id,trade_date,ts_code,signal_type,algo_version,eval_version,
                     entry_basis,horizon_basis,ret5)
                    SELECT id,trade_date,ts_code,signal_type,algo_version,'eval_v3',
                     'NEXT_OPEN','MARKET_TRADING_DAY',0.01 FROM strategy_signal""")
                )
                continue
            base = payload(model, old.id, days[0], 1, 10)
            columns = list(base)
            expressions = []
            for column in columns:
                if column == "trade_date":
                    expressions.append("d.day")
                elif column == "ts_code":
                    expressions.append("'S' || lpad(e.n::text,6,'0') || '.SZ'")
                elif column == "sector_id":
                    expressions.append("e.n")
                elif column == "theme_code":
                    expressions.append("'T' || lpad(e.n::text,4,'0')")
                else:
                    expressions.append(f'r."{column}"')
            names = ",".join(f'"{c}"' for c in columns)
            db.execute(
                text(f"""INSERT INTO "{model.__tablename__}" ({names})
                SELECT {",".join(expressions)} FROM unnest(CAST(:days AS date[])) d(day)
                CROSS JOIN generate_series(1,:entities) e(n)
                CROSS JOIN LATERAL jsonb_populate_record(
                  NULL::public."{model.__tablename__}", CAST(:base AS jsonb)) r"""),
                dict(
                    days=days,
                    entities=entities(model, stocks),
                    base=json.dumps(base, default=str, allow_nan=False),
                ),
            )
        db.commit()
        return old.id


def stats(db):
    return dict(
        db.execute(
            text("""SELECT
        pg_database_size(current_database()) AS database_bytes,
        (SELECT coalesce(sum(pg_total_relation_size(c.oid)),0)::bigint
         FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE n.nspname='public' AND c.relkind='r') AS table_and_index_bytes,
        (SELECT pg_current_wal_insert_lsn()::text) AS wal_lsn""")
        )
        .mappings()
        .one()
    )


def run_level(stocks, count, label):
    days = list(pd.bdate_range("2026-01-01", periods=count).date)
    with (
        pytest.MonkeyPatch.context() as patch,
        isolated_contract_database(patch) as (factory, engine),
    ):
        old = seed(factory, stocks, days)
        with factory() as db:
            before = stats(db)
            pg_version = db.scalar(text("SHOW server_version"))
        stop = threading.Event()
        latencies, failures, observations, locks = [], [], [], []

        def reader():
            while not stop.is_set():
                started = time.perf_counter()
                try:
                    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as c:
                        c.execute(text("SET TRANSACTION READ ONLY"))
                        first = c.execute(
                            text("""SELECT max(trade_date),count(*),
                           min(calc_run_id::text),max(calc_run_id::text) FROM stock_factor_daily""")
                        ).one()
                        assert first[2] == first[3]
                        # Same request includes latest, JOIN, count and ordered pagination.
                        rows = c.execute(
                            text("""SELECT f.calc_run_id::text,s.calc_run_id::text,
                            o.calc_run_id::text FROM stock_factor_daily f
                            JOIN stock_state_daily s USING(trade_date,ts_code)
                            JOIN stock_opportunity_daily o USING(trade_date,ts_code)
                            WHERE f.trade_date=:day ORDER BY f.ts_code LIMIT 20 OFFSET 1"""),
                            dict(day=first[0]),
                        ).all()
                        assert all(set(row) == {first[2]} for row in rows)
                        eval_count = c.scalar(text("SELECT count(*) FROM signal_forward_eval"))
                        assert eval_count == stocks * count
                        for model in MODELS[:8]:
                            sources = c.execute(
                                text(
                                    "SELECT min(calc_run_id::text),max(calc_run_id::text) "
                                    f'FROM public."{model.__tablename__}" WHERE trade_date=:day'
                                ),
                                dict(day=first[0]),
                            ).one()
                            assert sources == (first[2], first[2])
                        returns = c.execute(
                            text(
                                "SELECT min(e.ret5),max(e.ret5) FROM strategy_signal s "
                                "JOIN signal_forward_eval e ON e.signal_id=s.id "
                                "WHERE s.trade_date=:day"
                            ),
                            dict(day=first[0]),
                        ).one()
                        expected_return = 0.01 if first[2] == str(old) else 0.02
                        assert returns == (expected_return, expected_return)
                        observations.append(first[2])
                    latencies.append((time.perf_counter() - started) * 1000)
                except Exception as exc:
                    failures.append(type(exc).__name__ + ":" + str(exc))
                    stop.set()
                stop.wait(0.15)

        def lock_sampler():
            while not stop.wait(0.2):
                with engine.connect() as c:
                    locks.append(
                        dict(
                            c.execute(
                                text("""SELECT
                       count(*) FILTER (WHERE wait_event_type='Lock') AS waiting,
                       (SELECT count(*) FROM job_run WHERE status='RUNNING'
                        AND parent_job_id IS NULL) AS running
                       FROM pg_stat_activity WHERE datname=current_database()""")
                            )
                            .mappings()
                            .one()
                        )
                    )

        threads = [threading.Thread(target=reader) for _ in range(3)]
        threads.append(threading.Thread(target=lock_sampler))
        for thread in threads:
            thread.start()
        try:
            # Existing candidate context fixes its target to DAY; keep protocol,
            # replace only this isolated Job's requested synthetic date range.
            with candidate(factory, engine) as (db, job):
                job.job_metadata = {
                    **job.job_metadata,
                    "start": days[0].isoformat(),
                    "end": days[-1].isoformat(),
                }
                db.commit()
                ws = db.info["publication_workspace"]
                staged, stage_seconds = 0, {}
                stage_peak_rss = {}
                started = time.perf_counter()
                for model in MODELS:
                    stage_start = time.perf_counter()
                    ws.record_scope(
                        model, [model.trade_date >= days[0], model.trade_date <= days[-1]]
                    )
                    n = entities(model, stocks)
                    for day in days:
                        for start in range(1, n + 1, 500):
                            rows = [
                                payload(model, job.id, day, i, 20)
                                for i in range(start, min(n + 1, start + 500))
                            ]
                            if model is m.SignalForwardEval:
                                ids = dict(
                                    db.execute(
                                        select(m.StrategySignal.ts_code, m.StrategySignal.id).where(
                                            m.StrategySignal.trade_date == day,
                                            m.StrategySignal.ts_code.in_(
                                                [r["ts_code"] for r in rows]
                                            ),
                                        )
                                    ).all()
                                )
                                for row in rows:
                                    row["signal_id"] = ids[row["ts_code"]]
                            ws.upsert(model, rows, KEYS[model.__tablename__])
                            staged += len(rows)
                        db.commit()
                    stage_seconds[model.__tablename__] = time.perf_counter() - stage_start
                    stage_peak_rss[model.__tablename__] = resource.getrusage(
                        resource.RUSAGE_SELF
                    ).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
                    print(
                        json.dumps(dict(level=label, stage=model.__tablename__, rows=staged)),
                        flush=True,
                    )
                write_seconds = time.perf_counter() - started
                # Structural perf fixture only. Real CrossTableQuality is exercised
                # by the actual cold-start Worker regression, never mocked there.
                from types import SimpleNamespace

                for day in days:
                    record_validation(db, job.id, day, SimpleNamespace(has_error=False))
                db.commit()
                plan = db.execute(
                    text("""EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                    SELECT row_data FROM data_publication_row
                    WHERE publication_id=:root AND table_name='stock_factor_daily'
                    AND trade_date=:day AND entity_key='S000001.SZ'"""),
                    dict(root=job.id, day=days[-1]),
                ).scalar()
                candidate_stats = dict(
                    db.execute(
                        text("""SELECT count(*) AS rows,
                    sum(pg_column_size(row_data)+coalesce(pg_column_size(base_row),0))
                      AS json_bytes,
                    avg(pg_column_size(row_data)) AS average_candidate_json_bytes
                    FROM public.data_publication_row WHERE publication_id=:root"""),
                        dict(root=job.id),
                    )
                    .mappings()
                    .one()
                )
                public_plan = db.execute(
                    text("""EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                    SELECT f.ts_code,f.adj_close,s.state,o.opportunity_score
                    FROM public.stock_factor_daily f JOIN public.stock_state_daily s
                    USING(trade_date,ts_code) JOIN public.stock_opportunity_daily o
                    USING(trade_date,ts_code) WHERE f.trade_date=:day
                    ORDER BY f.ts_code LIMIT 20 OFFSET 1"""),
                    dict(day=days[-1]),
                ).scalar()
                from app.services.data_publication import _publishable_sql

                publication_plan = db.execute(
                    text(
                        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                        "SELECT count(*) FROM public.data_publication_row s WHERE "
                        + _publishable_sql("stock_factor_daily")
                    ),
                    dict(root=job.id),
                ).scalar()
                assert db.scalar(select(func.count()).select_from(DataPublicationRow)) == staged
                started = time.perf_counter()
                update_job(db, job, status="SUCCESS")
                publish_seconds = time.perf_counter() - started
                root_id = str(job.id)
            time.sleep(0.4)
            with factory() as db:
                after = stats(db)
                wal_bytes = db.scalar(
                    text("SELECT pg_wal_lsn_diff(:end,:start)"),
                    dict(end=after["wal_lsn"], start=before["wal_lsn"]),
                )
                preimage = dict(
                    db.execute(
                        text("""SELECT count(*) AS rows,
                    coalesce(sum(pg_column_size(row_data)),0) AS json_bytes
                    FROM data_publication_preimage""")
                    )
                    .mappings()
                    .one()
                )
                relations = [
                    dict(row)
                    for row in db.execute(
                        text("""SELECT relname,
                    pg_table_size(oid) AS table_bytes, pg_indexes_size(oid) AS index_bytes
                    FROM pg_class WHERE relname IN
                    ('data_publication_row','data_publication_preimage')
                    AND relnamespace='public'::regnamespace""")
                    ).mappings()
                ]
            assert not failures, failures
            assert str(old) in observations and root_id in observations
            assert all(x["running"] <= 1 for x in locks)
            ordered = sorted(latencies)
            return dict(
                level=label,
                stocks=stocks,
                days=count,
                postgres=pg_version,
                rows=staged,
                write_seconds=write_seconds,
                rows_per_second=staged / write_seconds,
                stage_seconds=stage_seconds,
                stage_peak_process_rss_bytes=stage_peak_rss,
                publish_seconds=publish_seconds,
                peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                * (1 if sys.platform == "darwin" else 1024),
                candidate=candidate_stats,
                preimage=preimage,
                relations=relations,
                database_before=before,
                database_after=after,
                wal_bytes=int(wal_bytes),
                reader_samples=len(ordered),
                reader_p95_ms=ordered[int((len(ordered) - 1) * 0.95)],
                reader_median_ms=statistics.median(ordered),
                reader_errors=failures,
                max_running=max([x["running"] for x in locks], default=0),
                max_lock_waiters=max([x["waiting"] for x in locks], default=0),
                plan=plan,
                public_plan=public_plan,
                publication_plan=publication_plan,
                production_capacity="UNPROVEN",
                synthetic_quality_fixture=True,
                row_budget=10000000,
                merge_timeout_ms=300000,
            )
        finally:
            stop.set()
            for thread in threads:
                thread.join(timeout=30)
            assert not any(thread.is_alive() for thread in threads)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-synthetic", action="store_true", required=True)
    parser.add_argument("--levels", choices=["smoke", "all"], default="all")
    parser.add_argument("--output", type=Path, default=Path(".codex_tmp/cold-start-capacity.json"))
    args = parser.parse_args()
    url = make_url(os.environ["TEST_DATABASE_URL"])
    allowed_database = (url.database or "").endswith("_test") or (
        os.environ.get("CI") == "true" and url.database == "stock_db"
    )
    if url.host not in {"127.0.0.1", "localhost"} or not allowed_database:
        raise SystemExit("EXPLICIT_LOOPBACK_SYNTHETIC_TEST_DATABASE_REQUIRED")
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    # Imports above never connect; clear Settings cache before any DB work.
    from app.core.config import get_settings

    get_settings.cache_clear()
    from loguru import logger

    logger.remove()
    levels = (
        [(10, 2, "L1")]
        if args.levels == "smoke"
        else [
            (10, 2, "L1"),
            (5000, 20, "L2"),
            (500, 120, "L3-scaled-10pct"),
        ]
    )
    result = dict(
        head_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        working_tree_dirty=bool(subprocess.check_output(["git", "status", "--porcelain"])),
        results=[],
    )
    for stocks, days, level in levels:
        result["results"].append(run_level(stocks, days, level))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, default=str, allow_nan=False, indent=2) + "\n")
    print(json.dumps(dict(output=str(args.output), levels=len(result["results"]))))
