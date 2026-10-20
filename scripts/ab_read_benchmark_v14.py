"""Frozen Q0 and marked PG17 read experiment. Outputs synthetic evidence only."""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import date
from pathlib import Path
from time import perf_counter, process_time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
BASELINE = "c9f3b1a977c56698436d0ec4b29b6b154ed0fe55"
COLUMNS = "trade_date,ts_code,is_active,is_suspended,is_st,st_status_unknown"


def frozen_q0():
    # The view definition at BASELINE is frozen too, rather than trusting that
    # a future edit of PublicationWorkspace.open still represents the old SQL.
    source = subprocess.check_output(
        ["git", "show", f"{BASELINE}:backend/app/services/data_publication.py"],
        cwd=ROOT, text=True,
    )
    import types

    module = types.ModuleType("v14_frozen_publication")
    exec(compile(source, "<v14-frozen-q0>", "exec"), module.__dict__)
    return module.PublicationWorkspace, hashlib.sha256(source.encode()).hexdigest()


def q0_statement():
    from sqlalchemy import text

    return text(f"SELECT {COLUMNS} FROM stock_trade_status_daily "
                "WHERE trade_date BETWEEN :lo AND :hi "
                "AND calc_version=:version AND config_hash=:hash")


def frame_digest(frame):
    if not frame.empty:
        frame = frame.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    payload = frame.to_json(orient="split", date_format="iso", double_precision=15)
    return hashlib.sha256(payload.encode()).hexdigest()


def compare_runs(evidence):
    import statistics

    runs = evidence["runs"]
    if not runs:
        raise ValueError("V14_NO_COMPLETE_FETCH_RECEIPT")
    golden = (runs[0]["rows"], runs[0]["hash"], runs[0]["dtypes"])
    if any((r["rows"], r["hash"], r["dtypes"]) != golden for r in runs):
        raise ValueError("V14_GOLDEN_MISMATCH")
    medians = {name: statistics.median(r["seconds"] for r in runs if r["variant"] == name)
               for name in {r["variant"] for r in runs}}
    return {"full_fetch_golden": "PASS", "median_seconds": medians,
            "suggested_50pct_target_met": (
                medians["q2"] <= medians["q0"] * 0.5 if {"q0", "q2"} <= medians.keys() else None),
            # This script alone cannot certify width/resource/Windows/network,
            # final SHA CI, all safety regressions or approved production budgets.
            "read_performance": "OPEN", "production_acceptance": "UNPROVEN"}


def seed(db, *, public_rows, candidate_rows, other_rows):
    """Distributed over 257 weekdays; typed full-width state rows, real FK/trigger paths."""
    from app.models.job import JobRun
    from app.services.job_guard import data_queue_identity
    from sqlalchemy import text

    old = JobRun(job_type="recalculate", status="SUCCESS", job_metadata={})
    other = JobRun(job_type="recalculate", status="SUCCESS", job_metadata={})
    db.add_all([old, other])
    db.flush()
    db.execute(text("""INSERT INTO trade_calendar(cal_date,is_open,exchange)
        SELECT d::date,extract(isodow FROM d)<6,'SSE'
        FROM generate_series('2024-01-01'::date,'2024-12-31'::date,'1 day') d"""))
    params = {"n": public_rows, "old": old.id, "hash": data_queue_identity()["analysis"]}
    db.execute(text("""WITH days AS (
        SELECT cal_date,row_number() OVER (ORDER BY cal_date)-1 AS i
        FROM trade_calendar WHERE is_open ORDER BY cal_date LIMIT 257)
        INSERT INTO stock_trade_status_daily
        (trade_date,ts_code,is_active,is_suspended,is_st,st_status_unknown,
         up_limit,down_limit,is_limit_up_close,is_limit_down_close,tradable,strategy_eligible,
         status_reason,calc_version,config_hash,calc_run_id,calculated_at)
        SELECT d.cal_date,lpad((g/257)::text,6,'0')||'.SZ',true,false,
          CASE WHEN g%13=0 THEN NULL ELSE g%17=0 END,false,11.5,9.5,NULL,false,true,true,
          repeat('synthetic-status-',4),CASE WHEN g%19=0 THEN 'legacy' ELSE 'trade_status_v1' END,
          :hash,:old,'2026-01-01'::timestamptz
        FROM generate_series(0,:n-1) g JOIN days d ON d.i=g%257"""), params)
    db.commit()
    return old.id, other.id


def stage(db, root, source, amount, *, other=False, tombstone_percent=1, offset=2500):
    from sqlalchemy import text

    # A and B partially overlap; new codes exist; nontrivial NULL/identity mix.
    # base_row is the actual first public preimage, never invented from B.
    db.execute(text("""WITH days AS (
        SELECT cal_date,row_number() OVER (ORDER BY cal_date)-1 AS i
        FROM trade_calendar WHERE is_open ORDER BY cal_date LIMIT 257), rows AS (
        SELECT d.cal_date AS day,lpad((g/257+CASE WHEN :other THEN 15000 ELSE :offset END)::text,
        6,'0')||'.SZ' AS code,g FROM generate_series(0,:n-1) g JOIN days d ON d.i=g%257)
        INSERT INTO data_publication_row
          (publication_id,table_name,row_key,row_data,base_row,source_id,
           is_deleted,trade_date,entity_key)
        SELECT :root,'stock_trade_status_daily',jsonb_build_array(r.day,r.code),
          CASE WHEN r.g%100 < :tomb THEN NULL ELSE
          jsonb_build_object('up_limit',11.5,'down_limit',9.5,
          'is_limit_up_close',false,'is_limit_down_close',false,
          'status_reason',repeat(md5(r.g::text),4)) ||
          coalesce(to_jsonb(a),'{}'::jsonb) || jsonb_build_object(
          'trade_date',r.day,'ts_code',r.code,
          'is_active',true,'is_suspended',false,
          'is_st',CASE WHEN r.g%13=0 THEN NULL ELSE true END,
          'st_status_unknown',false,'tradable',true,'strategy_eligible',true,
          'calc_run_id',:source,'calculated_at','2026-01-02T00:00:00+00:00',
          'calc_version',CASE WHEN r.g%23=0 THEN 'wrong' ELSE 'trade_status_v1' END,
          'config_hash',CAST(:hash AS text)) END,
          to_jsonb(a),:source,r.g%100 < :tomb,r.day,r.code
        FROM rows r LEFT JOIN public.stock_trade_status_daily a
          ON a.trade_date=r.day AND a.ts_code=r.code"""),
        {"root": root, "source": source, "n": amount, "other": other, "offset": offset,
         "tomb": tombstone_percent,
         "hash": __import__("app.services.job_guard", fromlist=["data_queue_identity"])
         .data_queue_identity()["analysis"]})
    db.commit()


def run(args, output=None):
    from scripts.v14_test_database import isolated_v14_database, verified_test_url

    target = verified_test_url()
    import os

    # This CLI is a disposable process; set synthetic defaults only AFTER the
    # physical target check and BEFORE importing business settings.
    os.environ["DATABASE_URL"] = target.render_as_string(hide_password=False)
    os.environ["TUSHARE_TOKEN"] = "synthetic-v14"
    os.environ["LLM_ENABLED"] = "false"
    import importlib.metadata

    import pandas as pd
    import pytest
    from app.models.data_publication import DataPublication
    from app.services.job_guard import data_queue_identity
    from sqlalchemy import text

    from tests.integration.test_data_publication import candidate

    frozen, source_hash = frozen_q0()
    output = output if output is not None else {}
    output.update({"baseline": BASELINE, "frozen_source_sha256": source_hash,
              "python": platform.python_version(), "cache_control": "UNCONTROLLED",
              "versions": {n: importlib.metadata.version(n) for n in ("sqlalchemy", "psycopg")},
              "public_rows": args.public_rows, "candidate_rows": args.candidate_rows,
              "other_rows": args.other_rows, "tombstone_percent": args.tombstone_percent,
              "window_days": args.window_days, "runs": [], "plans": {},
              "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"])),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "network_decode_split": "UNPROVEN", "host_cpu_attribution": "UNPROVEN"})
    patch = pytest.MonkeyPatch()
    try:
        with isolated_v14_database(patch) as (factory, engine):
            with factory() as db:
                _, other = seed(db, public_rows=args.public_rows,
                                candidate_rows=args.candidate_rows, other_rows=args.other_rows)
                from uuid import uuid4

                db.add(DataPublication(job_id=other, execution_token=uuid4(), state="PREPARING",
                                       identity=data_queue_identity(), row_counts={}))
                db.commit()
                stage(db, other, other, args.other_rows, other=True,
                      tombstone_percent=args.tombstone_percent)
            # Use real workspace ownership/pinned connection with original Q0 views.
            patch.setattr("tests.integration.test_data_publication.PublicationWorkspace", frozen)
            with candidate(factory, engine, start=date(2024, 1, 1),
                           end=date(2024, 12, 31)) as (db, job):
                seed_started = perf_counter()
                stage(db, job.id, job.id, args.candidate_rows,
                      tombstone_percent=args.tombstone_percent,
                      offset=args.public_rows//257//4 if args.public_rows < 100000
                      else args.public_rows//257*3//4)
                output["candidate_fixture_write_seconds"] = perf_counter()-seed_started
                output["candidate_fixture_write_method"] = (
                    "synthetic INSERT SELECT, not writer throughput")
                for table in ("stock_trade_status_daily", "data_publication_row"):
                    db.execute(text(f'ANALYZE public."{table}"'))
                db.commit()
                db.execute(text("SELECT set_config('cursor_tuple_fraction',:value,false)"),
                           {"value": str(args.cursor_fraction)})
                output["pg_version"] = db.scalar(text("SHOW server_version"))
                output["schema"] = db.scalar(text("SELECT version_num FROM alembic_version"))
                output["settings"] = {n: db.scalar(text(f"SHOW {n}")) for n in
                    ("cursor_tuple_fraction", "work_mem", "shared_buffers", "effective_cache_size")}
                output["sizes"] = [dict(r) for r in db.execute(text("""SELECT relname,
                    pg_table_size(relid) AS table_bytes,pg_indexes_size(relid) AS index_bytes,
                    last_analyze FROM pg_stat_user_tables WHERE relname IN
                    ('stock_trade_status_daily','data_publication_row')""")).mappings()]
                output["actual_counts"] = dict(db.execute(text("""SELECT
                    (SELECT count(*) FROM public.stock_trade_status_daily) AS a,
                    count(*) FILTER (WHERE publication_id=:root) AS current_b,
                    count(*) FILTER (WHERE publication_id<>:root) AS other_b,
                    count(*) AS total_b FROM public.data_publication_row"""),
                    {"root": job.id}).mappings().one())
                output["width_sample"] = dict(db.execute(text("""SELECT count(*) AS samples,
                    percentile_cont(ARRAY[0.1,0.5,0.9,0.99]) WITHIN GROUP
                    (ORDER BY pg_column_size(s)) AS stored_row_bytes
                    FROM public.data_publication_row s TABLESAMPLE SYSTEM(1)"""))
                    .mappings().one())
                output["indexes"] = [dict(r) for r in db.execute(text("""SELECT
                    indexrelid::regclass::text AS name,indisvalid,
                    pg_get_indexdef(indexrelid) AS ddl,
                    pg_relation_size(indexrelid) AS bytes FROM pg_index WHERE indrelid IN
                    ('public.stock_trade_status_daily'::regclass,
                     'public.data_publication_row'::regclass)""")).mappings()]
                stmt = q0_statement()
                params = dict(lo=date(2024, 1, 1), hi=date(2024, 12, 31),
                              version="trade_status_v1", hash=data_queue_identity()["analysis"])
                db.execute(text("SET statement_timeout='300s'"))
                db.execute(text("SET lock_timeout='5s'"))
                variants = ("q0", "q1", "q2") if args.variant == "all" else (args.variant,)
                for variant in variants:
                    from app.repositories.ab_merge_read import (
                        ABMergeReadRepository,
                        ReadWindow,
                        calendar_windows,
                        trade_status_statement,
                    )

                    from scripts.publication_candidate_benchmark_v13 import (
                        ReaderProbe,
                        distribution,
                        rss_bytes,
                    )

                    plan_stmt = stmt if variant == "q0" else trade_status_statement(candidate=True)
                    plan_params = {**params, "root": job.id}
                    if variant == "q2":
                        first = calendar_windows(db, ReadWindow(params["lo"], params["hi"]),
                                                 args.window_days)[0]
                        plan_params.update(lo=first.start, hi=first.end)
                    output["plans"][variant] = {}
                    for label, prefix in (
                        ("select_estimated", "EXPLAIN (FORMAT JSON) "),
                        ("cursor_estimated", "EXPLAIN (FORMAT JSON) DECLARE v14_plan CURSOR FOR "),
                        ("select_actual", "EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) "),
                    ):
                        output["plans"][variant][label] = db.scalar(
                            text(prefix+str(plan_stmt)), plan_params)
                    with ReaderProbe(engine, args.readers) as probe:
                        probe.writer_pid = db.scalar(text("SELECT pg_backend_pid()"))
                        probe.measuring = True
                        for _ in range(args.repeats):
                            started, cpu_started = perf_counter(), process_time()
                            batches, rows, metrics = [], [], []
                            if variant == "q0":
                                with db.execute(stmt.execution_options(yield_per=5000),
                                                params) as result:
                                    iterator = iter(result.mappings().partitions(5000))
                                    while True:
                                        fetch = perf_counter()
                                        batch = next(iterator, None)
                                        if batch is None:
                                            break
                                        batches.append(perf_counter()-fetch)
                                        rows.extend(batch)
                                frame = pd.DataFrame(rows)
                            else:
                                reader = ABMergeReadRepository(db, observer=metrics.append)
                                frame = reader.read_trade_status(
                                    window=ReadWindow(params["lo"], params["hi"]),
                                    calc_version=params["version"], config_hash=params["hash"],
                                    window_days=args.window_days if variant == "q2" else None,
                                )
                                batches = [m["seconds"] for m in metrics if m["event"] == "fetch"]
                            output["runs"].append({"variant": variant,
                                "seconds": perf_counter()-started,
                                "client_process_cpu_seconds": process_time()-cpu_started,
                                "rows": len(frame), "hash": frame_digest(frame),
                                "dtypes": frame.dtypes.astype(str).to_dict(),
                                "fetch_seconds": distribution(batches),
                                "peak_rss_bytes": rss_bytes(),
                                "windows": [m for m in metrics if m["event"] == "window"]})
                            del rows, frame
                            save_output(args.output, output)
                        probe.measuring = False
                    output.setdefault("readers", {})[variant] = {
                        "count": args.readers, "latencies": distribution(probe.latencies),
                        "errors": probe.errors, "writer_waits": dict(probe.waits),
                        "max_blockers": probe.max_blockers}
                output["variant"] = args.variant
                output["comparison"] = compare_runs(output)
    finally:
        patch.undo()
    return output


def save_output(path, evidence):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, default=str, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-rows", type=int, default=2000)
    parser.add_argument("--candidate-rows", type=int, default=1350)
    parser.add_argument("--other-rows", type=int, default=2800)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--variant", choices=("q0", "q1", "q2", "all"), default="q0")
    parser.add_argument("--readers", type=int, choices=(0, 2), default=0)
    parser.add_argument("--cursor-fraction", type=float, choices=(0.1, 1.0), default=0.1)
    parser.add_argument("--window-days", type=int, choices=(1, 3, 5, 10, 20), default=5)
    parser.add_argument("--tombstone-percent", type=int, choices=(0, 1, 10), default=1)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    if min(options.public_rows, options.candidate_rows, options.other_rows, options.repeats) < 1:
        parser.error("positive synthetic counts required")
    evidence = {}
    try:
        run(options, evidence)
    except Exception as error:
        evidence["failure_type"] = type(error).__name__
        evidence["sqlstate"] = getattr(getattr(error, "orig", None), "sqlstate", None)
        raise
    finally:
        save_output(options.output, evidence)
    print(json.dumps({"status": "complete", "runs": len(evidence["runs"])}, default=str))
