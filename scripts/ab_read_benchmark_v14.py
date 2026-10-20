"""Frozen Q0 and marked PG17 read experiment. Outputs synthetic evidence only."""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import date
from pathlib import Path
from time import perf_counter

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


def run(args):
    from scripts.v14_test_database import isolated_v14_database, verified_test_url

    verified_test_url()
    import importlib.metadata

    import pandas as pd
    import pytest
    from app.models.data_publication import DataPublication
    from app.services.job_guard import data_queue_identity
    from sqlalchemy import text

    from tests.integration.test_data_publication import candidate

    frozen, source_hash = frozen_q0()
    output = {"baseline": BASELINE, "frozen_source_sha256": source_hash,
              "python": platform.python_version(), "cache_control": "UNCONTROLLED",
              "versions": {n: importlib.metadata.version(n) for n in ("sqlalchemy", "psycopg")},
              "public_rows": args.public_rows, "candidate_rows": args.candidate_rows,
              "other_rows": args.other_rows, "runs": []}
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
                stage(db, other, other, args.other_rows, other=True)
            # Use real workspace ownership/pinned connection with original Q0 views.
            patch.setattr("tests.integration.test_data_publication.PublicationWorkspace", frozen)
            with candidate(factory, engine, start=date(2024, 1, 1),
                           end=date(2024, 12, 31)) as (db, job):
                stage(db, job.id, job.id, args.candidate_rows,
                      offset=args.public_rows//257//4)
                for table in ("stock_trade_status_daily", "data_publication_row"):
                    db.execute(text(f'ANALYZE public."{table}"'))
                db.commit()
                output["pg_version"] = db.scalar(text("SHOW server_version"))
                output["schema"] = db.scalar(text("SELECT version_num FROM alembic_version"))
                output["settings"] = {n: db.scalar(text(f"SHOW {n}")) for n in
                    ("cursor_tuple_fraction", "work_mem", "shared_buffers", "effective_cache_size")}
                output["sizes"] = [dict(r) for r in db.execute(text("""SELECT relname,
                    pg_table_size(relid) AS table_bytes,pg_indexes_size(relid) AS index_bytes,
                    last_analyze FROM pg_stat_user_tables WHERE relname IN
                    ('stock_trade_status_daily','data_publication_row')""")).mappings()]
                stmt = q0_statement()
                params = dict(lo=date(2024, 1, 1), hi=date(2024, 12, 31),
                              version="trade_status_v1", hash=data_queue_identity()["analysis"])
                db.execute(text("SET statement_timeout='300s'"))
                db.execute(text("SET lock_timeout='5s'"))
                if args.variant == "q0":
                    plan_stmt = stmt
                else:
                    from app.repositories.ab_merge_read import trade_status_statement

                    plan_stmt = trade_status_statement(candidate=True)
                    params["root"] = job.id
                output["plans"] = {}
                for label, prefix in (
                    ("select_estimated", "EXPLAIN (FORMAT JSON) "),
                    ("cursor_estimated", "EXPLAIN (FORMAT JSON) DECLARE v14_plan CURSOR FOR "),
                    ("select_actual", "EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) "),
                ):
                    output["plans"][label] = db.scalar(text(prefix+str(plan_stmt)), params)
                for _ in range(args.repeats):
                    started = perf_counter()
                    batches, rows = [], []
                    if args.variant == "q0":
                        with db.execute(stmt.execution_options(yield_per=5000), params) as result:
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
                        from app.repositories.ab_merge_read import ABMergeReadRepository, ReadWindow

                        extra = {"window_days": args.window_days if args.variant == "q2" else None}
                        metrics = []
                        reader = ABMergeReadRepository(db, observer=metrics.append)
                        frame = reader.read_trade_status(
                            window=ReadWindow(params["lo"], params["hi"]),
                            calc_version=params["version"], config_hash=params["hash"],
                            **extra,
                        )
                        batches = [m["seconds"] for m in metrics if m["event"] == "fetch"]
                    from scripts.publication_candidate_benchmark_v13 import distribution, rss_bytes

                    output["runs"].append({"seconds": perf_counter()-started, "rows": len(frame),
                        "hash": frame_digest(frame), "dtypes": frame.dtypes.astype(str).to_dict(),
                        "fetch_seconds": distribution(batches), "peak_rss_bytes": rss_bytes()})
                    if args.variant != "q0":
                        output["runs"][-1]["windows"] = [
                            m for m in metrics if m["event"] == "window"]
                output["variant"] = args.variant
    finally:
        patch.undo()
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-rows", type=int, default=2000)
    parser.add_argument("--candidate-rows", type=int, default=1350)
    parser.add_argument("--other-rows", type=int, default=2800)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--variant", choices=("q0", "q1", "q2"), default="q0")
    parser.add_argument("--window-days", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    if min(options.public_rows, options.candidate_rows, options.other_rows, options.repeats) < 1:
        parser.error("positive synthetic counts required")
    evidence = run(options)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(evidence, default=str, indent=2), encoding="utf-8")
    print(json.dumps(evidence, default=str))
