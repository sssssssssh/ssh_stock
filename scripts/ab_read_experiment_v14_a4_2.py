"""A4-2 laboratory ONLY; never imported by backend application code."""

import argparse
import gc
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import date
from pathlib import Path
from time import perf_counter, process_time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
BASELINE = "f8df915febe24bce3f3bcdb8a52ae2f3a5b78e62"
CONTROLS = ("Q0_LEGACY_RAW", "Q0_SERVICE_CONTROL", "Q0_SAFETY_EQUIVALENT",
            "Q1_CURRENT", "Q2_CURRENT")
SQL_VARIANTS = ("S3", "S3_INLINE", "S4", "S5")


def source_contract():
    """Git blob identities handle Windows checkout line endings, without edits."""
    entries = subprocess.check_output(["git", "ls-tree", "-r", BASELINE,
        "backend", "migrations", "config", "scripts/ab_read_profile_v14_a4.py",
        "scripts/ab_read_profile_summary_v14_a4.py", "docs/acceptance/v14_a4_baseline.md",
        "docs/acceptance/evidence"], cwd=ROOT, text=True).splitlines()
    paths = [entry.split("\t", 1)[1] for entry in entries]
    hashes = subprocess.check_output(["git", "hash-object", "--stdin-paths"],
        input="\n".join(paths)+"\n", cwd=ROOT, text=True).splitlines()
    result = {}
    for entry, path, actual in zip(entries, paths, hashes, strict=True):
        expected = entry.split()[2]
        if actual != expected:
            raise ValueError("A42_FROZEN_SOURCE_CHANGED")
        result[path] = {"git_blob": actual,
                        "checkout_sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}
    return result


def alternate(items, repeats):
    return [list(items[n % len(items):] + items[:n % len(items)]) for n in range(repeats)]


def save(path, output):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, default=str, allow_nan=False, indent=2) + "\n",
                    encoding="utf-8")


def verified_environment():
    from scripts.v14_test_database import verified_test_url

    url = verified_test_url()  # No Settings/Engine from the business .env before this.
    os.environ.update(DATABASE_URL=url.render_as_string(hide_password=False),
                      TUSHARE_TOKEN="synthetic-a42", LLM_ENABLED="false",
                      AB_MERGE_READ_ENABLED="false")
    return url


def sql(variant):
    raise NotImplementedError("A42_SQL_CANDIDATE_NOT_IMPLEMENTED")


def measure(db, engine, variant, params, *, window_days=None, carry=False, container=None):
    from app.repositories import ab_merge_read as ab
    from app.repositories.calculation_frame import read_calculation_frame, read_calculation_windows
    from app.services.data_publication import workspace
    from sqlalchemy import text

    from scripts.ab_read_benchmark_v14 import frame_digest, q0_statement
    from scripts.ab_read_profile_v14_a4 import Profile, database_snapshot, resource_snapshot
    from scripts.publication_candidate_benchmark_v13 import rss_bytes

    current = workspace(db)
    if not carry:
        current.ab_public_read_evidence = {}
    gc.collect()
    before = {"database": database_snapshot(db), "resources": resource_snapshot(container)}
    db.commit()
    profile, metrics = Profile(db, engine), []
    start, cpu = perf_counter(), process_time()
    protected = variant not in CONTROLS[:2]
    with profile.observe() as constructor:
        if variant == "Q0_LEGACY_RAW":
            rows = []
            with db.execute(q0_statement().execution_options(yield_per=5000), params) as result:
                for batch in result.mappings().partitions(5000):
                    rows.extend(batch)
            frame = constructor(rows)
            del rows
        elif variant == "Q0_SERVICE_CONTROL":
            frame = read_calculation_frame(db, q0_statement().bindparams(**params), name="test.a42")
        elif variant in {"Q1_CURRENT", "Q2_CURRENT"}:
            frame = ab.ABMergeReadRepository(db, observer=metrics.append).read_trade_status(
                window=ab.ReadWindow(params["lo"], params["hi"]),
                calc_version=params["version"], config_hash=params["hash"],
                window_days=5 if variant == "Q2_CURRENT" else window_days)
        else:
            ab._prepare_candidate_read(db, current, ab.ReadWindow(params["lo"], params["hi"]))
            statement = q0_statement() if variant == "Q0_SAFETY_EQUIVALENT" else sql(variant)
            windows = (ab.calendar_windows(db, ab.ReadWindow(params["lo"], params["hi"]),
                                          window_days) if window_days else
                       [ab.ReadWindow(params["lo"], params["hi"])])
            frame = read_calculation_windows(db, [statement.bindparams(
                **{**params, "lo": w.start, "hi": w.end},
                **({"root": current.job_id} if variant != "Q0_SAFETY_EQUIVALENT" else {}))
                for w in windows], name="test.a42", observer=metrics.append)
        seconds = perf_counter() - start
        db.commit()
        verify_start = perf_counter()
        if protected:
            db.execute(text("LOCK TABLE public.stock_trade_status_daily IN SHARE MODE"))
            ab.verify_public_read_evidence(db, current)
        db.commit()
        final_seconds = perf_counter() - verify_start
    # A4-1 ordinary SELECT/driver controls have no global sort in their timed
    # path. Protected Q0 uses the exact same full-frame sort as Q1/Q2/S3-S5.
    if not frame.empty:
        frame = frame.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    result = {"variant": variant, "read_seconds": seconds,
        "final_transaction_seconds": final_seconds,
        "safe_total_seconds": perf_counter() - start,
        "read_plus_final_seconds": seconds + final_seconds,
        "client_cpu_seconds": process_time() - cpu, "rows": len(frame),
        "hash": frame_digest(frame), "dtypes": frame.dtypes.astype(str).to_dict(),
        "columns": list(frame.columns), "window_days": window_days,
        "frame_bytes": int(frame.memory_usage(index=True, deep=True).sum()),
        "process_lifetime_peak_rss_bytes": rss_bytes(),
        "protection": "E0" if protected else "NOT_EQUIVALENT",
        "aba_event_detection": "UNPROVEN", "metrics": metrics, **profile.receipt(),
        "before": before, "after": {"database": database_snapshot(db),
                                   "resources": resource_snapshot(container)}}
    # Golden canonicalization is not part of the safety timing.
    result["safe_total_seconds"] = result["read_plus_final_seconds"]
    del frame
    return result, profile.statements


def run(args, output):
    verified_environment()
    import pytest
    from app.models.data_publication import DataPublication
    from app.services.job_guard import data_queue_identity
    from loguru import logger
    from sqlalchemy import text

    from scripts.ab_read_benchmark_v14 import frozen_q0, seed, stage
    from scripts.ab_read_experiment_summary_v14_a4_2 import summarize
    from scripts.ab_read_profile_v14_a4 import seed_multitable
    from scripts.v14_test_database import isolated_v14_database
    from tests.integration import test_data_publication as support

    logger.remove()
    output.update(schema="a42-experiment-v1", baseline=BASELINE,
        head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
        source_contract=source_contract(), network="LOCAL_ONLY", cache_control="UNCONTROLLED",
        production_path_changes="NONE", read_performance_pass="NOT_CLAIMED",
        host=dict(platform=platform.platform(), python=platform.python_version(),
                  logical_cpus=os.cpu_count()), runs=[], plans={},
        orders=alternate(tuple(args.variants), args.repeats))
    with pytest.MonkeyPatch.context() as patch, isolated_v14_database(patch) as (factory, engine):
        with factory() as db:
            db.execute(text("CREATE EXTENSION pg_stat_statements"))
            _, other = seed(db, public_rows=args.public_rows, candidate_rows=0, other_rows=0)
            from uuid import uuid4

            db.add(DataPublication(job_id=other, execution_token=uuid4(), state="PREPARING",
                                   identity=data_queue_identity(), row_counts={}))
            db.commit()
            seed_multitable(db, other, other, args.other_rows)
        patch.setattr(support, "PublicationWorkspace", frozen_q0()[0])
        with support.candidate(factory, engine, start=date(2024, 1, 1),
                               end=date(2024, 12, 31)) as (db, job):
            stage(db, job.id, job.id, args.candidate_rows,
                  tombstone_percent=args.tombstones,
                  offset=args.public_rows//257//4 if args.public_rows<100000
                  else args.public_rows//257*3//4)
            db.execute(text("""INSERT INTO trade_calendar(cal_date,is_open,exchange)
                SELECT d::date,extract(isodow FROM d)<6,'SSE'
                FROM generate_series('2023-01-01'::date,'2025-12-31'::date,'1 day') d
                ON CONFLICT DO NOTHING"""))
            for table in ("stock_trade_status_daily", "stock_factor_daily", "data_publication_row"):
                db.execute(text(f"ANALYZE public.{table}"))
            db.commit()
            db.execute(text("SET statement_timeout='300s'"))
            db.execute(text("SET lock_timeout='5s'"))
            output["settings"] = {key: db.scalar(text(f"SHOW {key}")) for key in (
                "server_version", "work_mem", "shared_buffers", "cursor_tuple_fraction",
                "statement_timeout", "lock_timeout", "track_io_timing", "autovacuum")}
            output["fixture"] = dict(a=args.public_rows, b=args.candidate_rows,
                other_b=args.other_rows, tombstone_percent=args.tombstones,
                layout="frozen A4-1 stock-major/257 days; typed Factor other-root rows",
                sizes=[dict(r) for r in db.execute(text("""SELECT relname,
                pg_table_size(relid) AS table_bytes,pg_indexes_size(relid) AS index_bytes,
                pg_total_relation_size(relid) AS total_bytes FROM pg_stat_user_tables WHERE
                relname IN ('stock_trade_status_daily','stock_factor_daily','data_publication_row')
                """)).mappings()])
            db.commit()
            params = dict(lo=date(2024, 1, 1), hi=date(2024, 12, 31),
                          version="trade_status_v1", hash=data_queue_identity()["analysis"])
            for repeat, order in enumerate(output["orders"]):
                for variant in order:
                    record, _ = measure(db, engine, variant, params, container=args.container)
                    record.update(repeat=repeat, scope="full")
                    output["runs"].append(record)
                    save(args.output, output)
                    print(json.dumps({k:record[k] for k in (
                        "variant", "repeat", "rows", "read_plus_final_seconds")}), flush=True)
            output["summary"] = summarize(output)
            save(args.output, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-only", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-rows", type=int, default=10000)
    parser.add_argument("--candidate-rows", type=int, default=5253)
    parser.add_argument("--other-rows", type=int, default=10895)
    parser.add_argument("--tombstones", type=int, choices=(0, 1, 10), default=1)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--variants", nargs="+", choices=CONTROLS+SQL_VARIANTS, default=CONTROLS)
    parser.add_argument("--container")
    args = parser.parse_args()
    output = {"schema": "a42-contract-v1", "baseline": BASELINE,
              "production_path_changes": "NONE", "read_performance_pass": "NOT_CLAIMED"}
    try:
        verified_environment()
        output["source_contract"] = source_contract()
        save(args.output, output)
        if not args.contract_only:
            if min(args.public_rows,args.candidate_rows,args.other_rows)<1 or args.repeats<3:
                raise ValueError("A42_COMPLETE_POSITIVE_FIXTURE_AND_THREE_REPEATS_REQUIRED")
            run(args, output)
    except BaseException as error:
        import traceback

        output["failure_type"] = type(error).__name__
        output["failure_trace"] = [
            {"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
            for f in traceback.extract_tb(error.__traceback__)]
        save(args.output, output)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
