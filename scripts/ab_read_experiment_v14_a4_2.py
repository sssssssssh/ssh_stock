"""A4-2 laboratory ONLY; never imported by backend application code."""

import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter, process_time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
BASELINE = "f8df915febe24bce3f3bcdb8a52ae2f3a5b78e62"
CONTROLS = ("Q0_LEGACY_RAW", "Q0_SERVICE_CONTROL", "Q0_SAFETY_EQUIVALENT",
            "Q1_CURRENT", "Q2_CURRENT")
SQL_VARIANTS = ("S3", "S3_INLINE", "S3_KEYS", "S4", "S5")


def source_contract():
    """Git blob identities handle Windows checkout line endings, without edits."""
    for command in (["git","diff","--name-only",BASELINE,"--","backend","migrations","config"],
                    ["git","ls-files","--others","--exclude-standard","--",
                     "backend","migrations","config"]):
        if subprocess.check_output(command,cwd=ROOT):
            raise ValueError("A42_PRODUCTION_TREE_CHANGED")
    entries = subprocess.check_output(["git", "ls-tree", "-r", BASELINE,
        "backend", "migrations", "config", "scripts/ab_read_profile_v14_a4.py",
        "scripts/ab_read_profile_summary_v14_a4.py", "docs/acceptance/v14_a4_baseline.md",
        "docs/acceptance/evidence", "scripts/ab_read_benchmark_v14.py",
        "scripts/v14_test_database.py", "scripts/publication_candidate_benchmark_v13.py",
        "tests/integration/test_data_publication.py",
        "tests/integration/test_ab_merge_read_v14.py",
        "tests/integration/m16_6_support.py"], cwd=ROOT, text=True).splitlines()
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
    if getattr(output, "writer", None) is not None:
        output.writer.checkpoint(output)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    from scripts.a42_artifacts import without_query_parameters

    temporary.write_text(json.dumps(without_query_parameters(output),
                         default=str, allow_nan=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def laboratory_sources():
    return {name:hashlib.sha256((ROOT / "scripts" / name).read_bytes()).hexdigest()
            for name in ("ab_read_experiment_v14_a4_2.py","ab_read_resources_v14_a4_2.py",
                         "ab_read_evidence_v14_a4_2.py","ab_read_experiment_summary_v14_a4_2.py",
                         "a42_scope.py", "a42_artifacts.py", "a42_ci_contract.py",
                         "a42_receipt_contract.py", "a42_gate_io.py")}


def cursor_plans_without_parameters(db, statements):
    """Untimed only: preserve the frozen native probe, disable bind-value logging."""
    from sqlalchemy import text

    from scripts.a42_artifacts import without_query_parameters
    from scripts.ab_read_profile_v14_a4 import cursor_actual_plans

    db.execute(text("LOAD 'auto_explain'"))
    db.execute(text("SET auto_explain.log_parameter_max_length='0'"))
    if db.scalar(text("SHOW auto_explain.log_parameter_max_length")) != "0":
        raise ValueError("A42_PARAMETER_LOGGING_NOT_DISABLED")
    return without_query_parameters(cursor_actual_plans(db, statements))


def database_snapshot(db):
    from sqlalchemy import text

    # Never repeat thousands of cumulative FETCH utility query texts per trial.
    # Raw per-trial cursors/FETCH timings remain in Profile; counters are grouped.
    db.execute(text("SELECT pg_stat_force_next_flush()"))
    db.execute(text("SELECT pg_stat_clear_snapshot()"))
    return {"database": dict(db.execute(text("""SELECT blks_read,blks_hit,temp_files,temp_bytes,
        blk_read_time,blk_write_time FROM pg_stat_database WHERE datname=current_database()
        """)).mappings().one()),
        "statements": [dict(r) for r in db.execute(text("""SELECT
        CASE WHEN query LIKE 'FETCH%%' THEN 'FETCH' WHEN query LIKE 'DECLARE%%' THEN 'DECLARE'
        WHEN query LIKE '%string_agg(encode(sha256%' THEN 'FINGERPRINT' ELSE 'OTHER' END AS phase,
        count(*) AS normalized_entries,sum(calls) AS calls,sum(rows) AS rows,
        sum(total_exec_time) AS exec_ms,sum(shared_blks_hit) AS shared_hit,
        sum(shared_blks_read) AS shared_read,sum(local_blks_read) AS local_read,
        sum(local_blks_written) AS local_written,sum(temp_blks_read) AS temp_read,
        sum(temp_blks_written) AS temp_written,sum(wal_bytes) AS wal_bytes
        FROM pg_stat_statements WHERE dbid=(SELECT oid FROM pg_database
        WHERE datname=current_database()) GROUP BY 1""")).mappings()],
        "maintenance": [dict(r) for r in db.execute(text("""SELECT relname,
        last_autovacuum,last_autoanalyze,n_live_tup,n_dead_tup FROM pg_stat_user_tables WHERE
        relname IN ('stock_trade_status_daily','stock_factor_daily','data_publication_row')
        """)).mappings()],
        "autovacuum_workers": [dict(r) for r in db.execute(text("SELECT pid,wait_event_type,"
        "wait_event FROM pg_stat_activity WHERE datname=current_database() "
        "AND backend_type='autovacuum worker'")).mappings()],
        "statements_info":dict(db.execute(text("SELECT * FROM pg_stat_statements_info"))
                               .mappings().one()),
        "scope":"cumulative grouped counters, may include observer/reader/background work"}


def verified_environment():
    from scripts.v14_test_database import verified_test_url

    url = verified_test_url()  # No Settings/Engine from the business .env before this.
    os.environ.update(DATABASE_URL=url.render_as_string(hide_password=False),
                      TUSHARE_TOKEN="synthetic-a42", LLM_ENABLED="false",
                      AB_MERGE_READ_ENABLED="false")
    return url


def fixture_census(db, root, fixture):
    """Exact setup-only census: one snapshot, all A/B rows, bounded named FETCH."""
    from sqlalchemy import text

    counts = dict(a=0,b=0,other_b=0)
    proof = fixture["census"] = dict(method="single_snapshot_named_cursor_all_rows",
        rows=0,batches=0,complete=False,cursor_closed=False)
    statement = text("""SELECT false AS candidate_row,NULL::uuid AS publication_id
        FROM public.stock_trade_status_daily UNION ALL
        SELECT true,publication_id FROM public.data_publication_row""").execution_options(
            yield_per=5000,a42_fixture_census=True)
    result,started = None,perf_counter()
    try:
        with db.execute(statement) as result:
            proof["cursor_name"] = getattr(result.cursor,"name",None)
            if not proof["cursor_name"]:
                raise ValueError("A42_FIXTURE_CENSUS_REQUIRES_NAMED_CURSOR")
            for batch in result.partitions(5000):
                for candidate,publication in batch:
                    if candidate is False:
                        counts["a"] += 1
                    elif candidate is True and publication is not None:
                        counts["b" if publication==root else "other_b"] += 1
                    else:
                        raise ValueError("A42_FIXTURE_CENSUS_INVALID_ROW")
                proof["rows"] += len(batch)
                proof["batches"] += 1
        if not result.closed or proof["rows"] != sum(counts.values()):
            raise ValueError("A42_FIXTURE_CENSUS_INCOMPLETE")
        proof["complete"] = True
        return counts
    finally:
        proof["seconds"] = perf_counter()-started
        proof["cursor_closed"] = bool(result is not None and result.closed)


def sql(variant, columns=None):
    from app.models.market_data import StockTradeStatusDaily as Model
    from app.repositories.ab_merge_read import FACTOR_COLUMNS
    from sqlalchemy import text

    columns = FACTOR_COLUMNS if columns is None else tuple(columns)
    if not columns or any(c not in Model.__table__.c for c in columns):
        raise ValueError("A42_INVALID_PROJECTION")
    if variant not in SQL_VARIANTS:
        raise ValueError("A42_INVALID_SQL_VARIANT")
    modifier = "NOT MATERIALIZED" if variant == "S3_INLINE" else "MATERIALIZED"
    narrow = variant in {"S3_KEYS","S4","S5"}
    keys = "s.row_key,s.trade_date,s.row_key->>1 AS code"
    if not narrow:
        keys += ",s.row_data,s.is_deleted"
    candidates = f"""WITH candidate_keys AS {modifier} (SELECT {keys}
        FROM public.data_publication_row s WHERE s.publication_id=:root
        AND s.table_name='stock_trade_status_daily' AND s.trade_date BETWEEN :lo AND :hi)"""
    if variant == "S4":
        public = """SELECT a.* FROM public.stock_trade_status_daily a
            LEFT JOIN candidate_keys k ON k.trade_date=a.trade_date AND k.code=a.ts_code
            WHERE a.trade_date BETWEEN :lo AND :hi AND k.row_key IS NULL"""
    else:
        public = """SELECT a.* FROM public.stock_trade_status_daily a
            WHERE a.trade_date BETWEEN :lo AND :hi AND NOT EXISTS (
            SELECT 1 FROM candidate_keys k
            WHERE k.row_key=jsonb_build_array(a.trade_date,a.ts_code))"""
    # The unchanged E0 whole-root key guard is mandatory BEFORE every variant.
    # Keys include wrong-version B and tombstones; identity is filtered LAST.
    if narrow:
        selected = """SELECT r.* FROM public.data_publication_row s CROSS JOIN LATERAL
            jsonb_populate_record(NULL::public.stock_trade_status_daily,s.row_data) r
            WHERE s.publication_id=:root AND s.table_name='stock_trade_status_daily'
            AND s.trade_date BETWEEN :lo AND :hi AND NOT s.is_deleted"""
    else:
        selected = """SELECT r.* FROM candidate_keys k CROSS JOIN LATERAL
            jsonb_populate_record(NULL::public.stock_trade_status_daily,k.row_data) r
            WHERE NOT k.is_deleted"""
    union = selected + " UNION ALL " + public
    projection = ",".join(f'"{c}"' for c in columns)
    order = "" if variant == "S5" else " ORDER BY ts_code,trade_date"
    return text(candidates + f" SELECT {projection} FROM ({union}) merged "
                "WHERE calc_version=:version AND config_hash=:hash" + order)


@contextmanager
def observe(profile):
    import pytest

    from scripts import ab_read_profile_v14_a4 as old

    original = old.sql_phase
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(old, "sql_phase", lambda statement:
            "T5_declare" if statement.lstrip().upper().startswith("WITH CANDIDATE_KEYS")
            else original(statement))
        try:
            with profile.observe() as constructor:
                yield constructor
        except BaseException as error:
            error.a42_profile = profile.receipt()
            raise


def measure(db, engine, variant, params, *, window_days=None, carry=False, container=None,
            cursor_fraction="0.1", service_call=False, readers=0, reader_pause=2,
            verify_final=True):
    from app.repositories import ab_merge_read as ab
    from app.repositories.calculation_frame import read_calculation_frame, read_calculation_windows
    from app.services.data_publication import workspace
    from sqlalchemy import text

    from scripts.ab_read_benchmark_v14 import frame_digest, q0_statement
    from scripts.ab_read_profile_v14_a4 import Profile, resource_snapshot
    from scripts.ab_read_resources_v14_a4_2 import Telemetry
    from scripts.publication_candidate_benchmark_v13 import rss_bytes

    current = workspace(db)
    if not carry:
        current.ab_public_read_evidence = {}
        current.a42_events = None
    previous_dates = len(current.ab_public_read_evidence)
    gc.collect()
    before = {"database": database_snapshot(db), "resources": resource_snapshot(container)}
    before["wal_lsn"] = db.scalar(text("SELECT pg_current_wal_insert_lsn()::text"))
    before["pg_stat_io"] = db.scalar(text("SELECT jsonb_agg(to_jsonb(i)) FROM pg_stat_io i"))
    pid = db.scalar(text("SELECT pg_backend_pid()"))
    db.commit()
    db.execute(text("SELECT set_config('cursor_tuple_fraction',:fraction,true)"),
               {"fraction": cursor_fraction})
    profile, metrics = Profile(db, engine), []
    start, cpu = perf_counter(), process_time()
    protected = variant not in CONTROLS[:2]
    with (Telemetry(engine, pid, readers, container=bool(container),
                    reader_pause=reader_pause) as telemetry,
          observe(profile) as constructor):
        def read():
            return read_variant()

        def read_variant():
            if variant == "Q0_LEGACY_RAW":
                rows = []
                with db.execute(q0_statement().execution_options(yield_per=5000), params) as result:
                    for batch in result.mappings().partitions(5000):
                        rows.extend(batch)
                return constructor(rows)
            if variant == "Q0_SERVICE_CONTROL":
                return read_calculation_frame(
                    db, q0_statement().bindparams(**params), name="test.a42")
            if variant in {"Q1_CURRENT", "Q2_CURRENT"}:
                return ab.ABMergeReadRepository(db, observer=metrics.append).read_trade_status(
                    window=ab.ReadWindow(params["lo"], params["hi"]),
                    calc_version=params["version"], config_hash=params["hash"],
                    window_days=5 if variant == "Q2_CURRENT" else window_days)
            if variant == "E3":
                from scripts.ab_read_evidence_v14_a4_2 import EventEvidence

                if current.a42_events is None:
                    current.a42_events = EventEvidence()
                current.a42_events.prepare(db, current, ab.ReadWindow(params["lo"], params["hi"]))
            else:
                ab._prepare_candidate_read(db, current, ab.ReadWindow(params["lo"], params["hi"]))
            statement = (q0_statement() if variant == "Q0_SAFETY_EQUIVALENT" else
                         sql("S3" if variant == "E3" else variant))
            windows = (ab.calendar_windows(db, ab.ReadWindow(params["lo"], params["hi"]),
                                          window_days) if window_days else
                       [ab.ReadWindow(params["lo"], params["hi"])])
            return read_calculation_windows(db, [statement.bindparams(
                **{**params, "lo": w.start, "hi": w.end},
                **({"root": current.job_id} if variant != "Q0_SAFETY_EQUIVALENT" else {}))
                for w in windows], name="test.a42", observer=metrics.append)

        if service_call:
            import pytest
            from app.services.factors import service as factors

            def intercept(db_arg, statement, *, name):
                assert db_arg is db and name == "factors.trade_status"
                values = list(statement.compile().params.values())
                assert all(params[key] in values for key in ("lo","hi","version","hash"))
                return read()

            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(factors, "read_calculation_frame", intercept)
                frame = factors.FactorService(db)._read_trade_status(params["lo"], params["hi"])
        else:
            frame = read()
        seconds = perf_counter() - start
        commit_start = perf_counter()
        db.commit()
        commit_seconds = perf_counter()-commit_start
        verify_start = perf_counter()
        if protected and verify_final:
            db.execute(text("LOCK TABLE public.stock_trade_status_daily IN SHARE MODE"))
            if variant == "E3":
                current.a42_events.verify(db)
            ab.verify_public_read_evidence(db, current)
        db.commit()
        final_seconds = perf_counter() - verify_start
    client_cpu = process_time()-cpu
    # A4-1 ordinary SELECT/driver controls have no global sort in their timed
    # path. Protected Q0 uses the exact same full-frame sort as Q1/Q2/S3-S5.
    if not frame.empty:
        frame = frame.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    result = {"variant": variant, "read_seconds": seconds,
        "final_transaction_seconds": final_seconds,
        "safe_total_seconds": seconds + commit_seconds + final_seconds,
        "read_commit_seconds": commit_seconds,
        "final_verification_applied": protected and verify_final,
        "read_plus_final_seconds": seconds + commit_seconds + final_seconds,
        "client_cpu_seconds": client_cpu, "rows": len(frame),
        "hash": frame_digest(frame), "dtypes": frame.dtypes.astype(str).to_dict(),
        "key_hash": frame_digest(frame[["trade_date", "ts_code"]]),
        "null_counts": {k:int(v) for k,v in frame.isna().sum().items()},
        "duplicate_keys": int(frame.duplicated(["trade_date", "ts_code"]).sum()),
        "columns": list(frame.columns), "window_days": window_days,
        "previous_read_set_dates": previous_dates,
        "current_read_set_dates": len(current.ab_public_read_evidence),
        "read_set_shallow_bytes": sys.getsizeof(current.ab_public_read_evidence)
            + sum(sys.getsizeof(k)+sys.getsizeof(v)
                  for k,v in current.ab_public_read_evidence.items()),
        "cursor_fraction": cursor_fraction, "service_call": service_call, "reader_count":readers,
        "frame_bytes": int(frame.memory_usage(index=True, deep=True).sum()),
        "process_lifetime_peak_rss_bytes": rss_bytes(),
        "protection": ("UNPROVEN_E3_PLUS_E0_FINAL" if variant == "E3" else
                       "E0" if protected else "NOT_EQUIVALENT"),
        "aba_event_detection": "UNPROVEN", "metrics": metrics, **profile.receipt(),
        "before": before, "after": {"database": database_snapshot(db),
                                   "resources": resource_snapshot(container)}}
    result["telemetry"] = telemetry.receipt()
    result["after"]["pg_stat_io"] = db.scalar(text(
        "SELECT jsonb_agg(to_jsonb(i)) FROM pg_stat_io i"))
    result["wal_bytes_whole_instance"] = int(db.scalar(text(
        "SELECT pg_wal_lsn_diff(pg_current_wal_insert_lsn(),CAST(:lsn AS pg_lsn))"),
        {"lsn":before["wal_lsn"]}))
    # Golden canonicalization is not part of the safety timing.
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
    from scripts.ab_read_evidence_v14_a4_2 import event_dml_cost, install_events
    from scripts.ab_read_experiment_summary_v14_a4_2 import summarize
    from scripts.ab_read_profile_v14_a4 import seed_multitable
    from scripts.ab_read_resources_v14_a4_2 import host_memory_bytes
    from scripts.v14_test_database import isolated_v14_database
    from tests.integration import test_data_publication as support

    logger.remove()
    output.update(schema="a42-experiment-v1", baseline=BASELINE,
        head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
        source_contract=source_contract(), network="LOCAL_ONLY", cache_control="UNCONTROLLED",
        versions={name:importlib.metadata.version(name) for name in
                  ("pandas","psycopg","SQLAlchemy")},
        image_id=(subprocess.check_output(["docker","inspect","--format","{{.Image}}",
                  args.container],text=True).strip() if args.container else "LOCAL_PORTABLE_PG17"),
        production_path_changes="NONE", read_performance_pass="NOT_CLAIMED",
        host=dict(platform=platform.platform(), python=platform.python_version(),
                  logical_cpus=os.cpu_count(), ram_bytes=host_memory_bytes()), runs=[], plans={},
        orders=alternate(tuple(args.variants), args.repeats), monthly=[], windows=[])
    setup_started = perf_counter()
    with pytest.MonkeyPatch.context() as patch, isolated_v14_database(patch) as (factory, engine):
        output["setup_timings"] = dict(schema_seconds=perf_counter()-setup_started)
        fixture_started = perf_counter()
        with factory() as db:
            db.execute(text("CREATE EXTENSION pg_stat_statements"))
            _, other = seed(db, public_rows=args.public_rows, candidate_rows=0, other_rows=0)
            from uuid import uuid4

            db.add(DataPublication(job_id=other, execution_token=uuid4(), state="PREPARING",
                                   identity=data_queue_identity(), row_counts={}))
            db.commit()
            seed_multitable(db, other, other, args.other_rows)
            if args.coverage == "b_only":
                db.execute(text("UPDATE public.stock_trade_status_daily "
                                "SET trade_date=trade_date+366"))
                db.commit()
        output["setup_timings"]["public_and_other_seed_seconds"] = perf_counter()-fixture_started
        candidate_started = perf_counter()
        patch.setattr(support, "PublicationWorkspace", frozen_q0()[0])
        job_end = date(2025 if args.coverage=="a_only" else 2024,12,31)
        with support.candidate(factory, engine, start=date(2024, 1, 1),
                               end=job_end) as (db, job):
            if args.coverage == "a_only":
                db.execute(text("DELETE FROM trade_calendar"))  # Owned fixture only, before B seed.
                db.execute(text("""INSERT INTO trade_calendar(cal_date,is_open,exchange)
                    SELECT d::date,extract(isodow FROM d)<6,'SSE' FROM generate_series(
                    '2025-01-01'::date,'2025-12-31'::date,'1 day') d"""))
                db.commit()
            stage(db, job.id, job.id, args.candidate_rows,
                  tombstone_percent=args.tombstones,
                  offset=0 if args.coverage=="high" else
                    args.public_rows//257//4 if args.public_rows<100000
                    else args.public_rows//257*3//4)
            if args.coverage == "mismatched":
                db.execute(text("""UPDATE public.data_publication_row SET
                    row_data=jsonb_set(row_data,'{config_hash}','"wrong"'::jsonb)
                    WHERE publication_id=:root AND NOT is_deleted"""), {"root":job.id})
            db.execute(text("""INSERT INTO trade_calendar(cal_date,is_open,exchange)
                SELECT d::date,extract(isodow FROM d)<6,'SSE'
                FROM generate_series('2023-01-01'::date,'2025-12-31'::date,'1 day') d
                ON CONFLICT DO NOTHING"""))
            output["setup_timings"]["current_candidate_seed_seconds"] = (
                perf_counter()-candidate_started)
            analyze_started = perf_counter()
            for table in ("stock_trade_status_daily", "stock_factor_daily", "data_publication_row"):
                db.execute(text(f"ANALYZE public.{table}"))
            db.commit()
            output["setup_timings"]["analyze_seconds"] = perf_counter()-analyze_started
            db.execute(text("SET statement_timeout='300s'"))
            db.execute(text("SET lock_timeout='5s'"))
            output["settings"] = {key: db.scalar(text(f"SHOW {key}")) for key in (
                "server_version", "work_mem", "shared_buffers", "cursor_tuple_fraction",
                "statement_timeout", "lock_timeout", "track_io_timing", "autovacuum", "TimeZone",
                "max_parallel_workers_per_gather", "effective_cache_size", "random_page_cost",
                "default_statistics_target", "pg_stat_statements.max", "pg_stat_statements.track")}
            output["system_identifier"] = db.scalar(text(
                "SELECT system_identifier::text FROM pg_control_system()"))
            output["phase"] = "fixture_metadata"
            fixture = output["fixture"] = dict(a=args.public_rows, b=args.candidate_rows,
                other_b=args.other_rows, tombstone_percent=args.tombstones, coverage=args.coverage,
                layout="frozen A4-1 stock-major/257 days; typed Factor other-root rows")
            fixture["sizes"] = [dict(r) for r in db.execute(text("""SELECT relname,
                pg_table_size(relid) AS table_bytes,pg_indexes_size(relid) AS index_bytes,
                pg_total_relation_size(relid) AS total_bytes,
                (SELECT CASE WHEN reltoastrelid=0 THEN 0 ELSE
                pg_total_relation_size(reltoastrelid) END FROM pg_class
                WHERE oid=relid) AS toast_bytes
                FROM pg_stat_user_tables WHERE
                relname IN ('stock_trade_status_daily','stock_factor_daily','data_publication_row')
                """)).mappings()]
            fixture["indexes"] = [dict(r) for r in db.execute(text(
                    "SELECT tablename,indexdef FROM pg_indexes "
                    "WHERE schemaname='public' AND tablename IN "
                    "('data_publication_row','stock_trade_status_daily','stock_factor_daily')"))
                    .mappings()]
            fixture["width_sample"] = dict(db.execute(text("SELECT count(*) AS sampled_rows,"
                    "avg(pg_column_size(s)) AS average_stored_bytes FROM "
                    "public.data_publication_row s TABLESAMPLE SYSTEM(1)")).mappings().one())
            save(args.output, output)
            output["phase"] = "fixture_count_verification"
            fixture["actual_counts"] = fixture_census(db,job.id,fixture)
            output["setup_timings"]["census_seconds"] = fixture["census"]["seconds"]
            if fixture["actual_counts"] != dict(a=args.public_rows,b=args.candidate_rows,
                                                other_b=args.other_rows):
                raise ValueError("A42_FIXTURE_ACTUAL_COUNT_MISMATCH")
            db.commit()
            output["phase"] = "timed_trials"
            params = dict(lo=date(2024, 1, 1), hi=date(2024, 12, 31),
                          version="trade_status_v1", hash=data_queue_identity()["analysis"])
            captured = {}

            def trial(variant, *, scope, repeat, values=params, **kwargs):
                if variant == "E3" and not output.get("event_install_seconds"):
                    output["event_dml_without_events"] = event_dml_cost(db)
                    started = perf_counter()
                    install_events(db)
                    output["event_install_seconds"] = perf_counter()-started
                    output["event_dml_with_events"] = event_dml_cost(db)
                try:
                    record, statements = measure(db, engine, variant, values,
                        container=args.container, readers=args.readers,
                        reader_pause=args.reader_pause, **kwargs)
                except BaseException as error:
                    output["failed_trial"] = {"variant": variant, "scope": scope,
                        "repeat": repeat, "failure_type": type(error).__name__,
                        "partial_profile":getattr(error,"a42_profile",None),
                        "sqlstate": getattr(getattr(error, "orig", None), "sqlstate", None)}
                    save(args.output, output)
                    raise
                record.update(repeat=repeat, scope=scope)
                output["runs"].append(record)
                captured.setdefault((variant, record["cursor_fraction"], scope,
                                     record["window_days"]), statements)
                save(args.output, output)
                print(json.dumps({k:record[k] for k in (
                    "variant", "scope", "repeat", "rows", "read_plus_final_seconds")}), flush=True)
                return record

            if getattr(args, "shard", None) is not None:
                from scripts.a42_scope import execute

                execute(args, output, db, engine, job, params, trial, captured)
                source_contract()
                if laboratory_sources() != output["laboratory_sources"]:
                    raise ValueError("A42_LABORATORY_SOURCE_CHANGED_DURING_TRIALS")
                return

            for repeat, order in enumerate(output["orders"]):
                for fraction in args.cursor_fractions:
                    for variant in order:
                        trial(variant, scope="full", repeat=repeat, cursor_fraction=fraction)
            if args.window_matrix:
                for fraction in ("0.1", "1.0"):
                    for repeat, order in enumerate(alternate((None,1,3,5,10,20), args.repeats)):
                        for days in order:
                            trial("S3", scope="window_matrix", repeat=repeat,
                                  window_days=days, cursor_fraction=fraction)
            if args.monthly:
                from app.services.recalculation import _month_chunks

                chunks = list(_month_chunks(date(2025,1,1),date(2025,3,31)))
                output["monthly_verification_protocol"] = "ROOT_TAIL_ONLY"
                variants = tuple(v for v in args.variants if v != "Q0_LEGACY_RAW")
                for repeat, order in enumerate(alternate(variants, args.repeats)):
                    for variant in order:
                        for index,(lo,hi) in enumerate(chunks):
                            record = trial(variant, scope=f"month_{lo.month}", repeat=repeat,
                                values={**params,"lo":lo-timedelta(days=430),"hi":hi},
                                carry=index>0, service_call=True,
                                verify_final=index==len(chunks)-1)
                            record.update(input_start=str(lo-timedelta(days=430)),
                                          input_end=str(hi),chunk_start=str(lo),chunk_end=str(hi))
                            output["monthly"].append(record)
                output["monthly_scope"] = (
                    "Actual FactorService._read_trade_status called with original 430-day bounds; "
                    "process-local transport substitution only; no numerical engine/Raw writes; "
                    "read commits each month, original final verification once at root tail")
            if args.plans:
                from scripts.ab_read_profile_v14_a4 import capture_plans

                output["phase"] = "untimed_actual_plans"
                for (variant, fraction, scope, days), statements in captured.items():
                    db.execute(text("SELECT set_config('cursor_tuple_fraction',:f,true)"),
                               {"f":fraction})
                    output["plans"][f"{variant}_{fraction}_{scope}_window_{days}"] = {
                        "scope":scope,"window_days":days,"cursor_fraction":fraction,
                        "select_and_cursor_estimate": capture_plans(db, statements),
                        "actual_cursor_untimed": cursor_plans_without_parameters(db, statements)}
                    save(args.output, output)
            from scripts.ab_read_profile_v14_a4 import lock_probe

            output["lock_probe_outside_timed_trials"] = lock_probe(db, engine)
            source_contract()
            if laboratory_sources() != output["laboratory_sources"]:
                raise ValueError("A42_LABORATORY_SOURCE_CHANGED_DURING_TRIALS")
            output["experiment_complete"] = True
            output["summary"] = summarize(output)
            output["phase"] = "complete"
            save(args.output, output)


def main():
    if any(a.split("=", 1)[0] in {"--scope", "--job-id"} for a in sys.argv[1:]):
        from scripts.a42_scope import main as scoped_main

        return scoped_main()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-only", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-rows", type=int, default=10000)
    parser.add_argument("--candidate-rows", type=int, default=5253)
    parser.add_argument("--other-rows", type=int, default=10895)
    parser.add_argument("--tombstones", type=int, choices=(0, 1, 10), default=1)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--variants", nargs="+", choices=CONTROLS+SQL_VARIANTS+("E3",),
                        default=CONTROLS+SQL_VARIANTS)
    parser.add_argument("--monthly", action="store_true")
    parser.add_argument("--window-matrix", action="store_true")
    parser.add_argument("--plans", action="store_true")
    parser.add_argument("--container")
    parser.add_argument("--readers", type=int, choices=(0,2), default=0)
    parser.add_argument("--reader-pause",type=int,choices=(1,2,5),default=2)
    parser.add_argument("--cursor-fractions", nargs="+", choices=("0.1","1.0"),
                        default=["0.1","1.0"])
    parser.add_argument("--coverage", choices=("partial","a_only","b_only","high","mismatched"),
                        default="partial")
    args = parser.parse_args()
    output = {"schema": "a42-contract-v1", "baseline": BASELINE,
              "measurement_version":"a42-v3-full-census-tail-final",
              "laboratory_sources":laboratory_sources(),
              "script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "production_path_changes": "NONE", "read_performance_pass": "NOT_CLAIMED"}
    try:
        verified_environment()
        from scripts.business_source_contract import MANIFEST, a42_static_contract, source_versions

        if args.contract_only and (ROOT / MANIFEST).exists():
            # Static compatibility only. run() and every real measurement still
            # call the original strict source_contract(), which rejects BIZ SQL.
            output["source_contract"] = a42_static_contract()
            output["source_versions"] = source_versions([
                "backend/app/services/data_publication.py"])
            output["production_path_changes"] = "BIZ_VERSIONED_STATIC_ONLY"
        else:
            output["source_contract"] = source_contract()
        save(args.output, output)
        if not args.contract_only:
            if (not 1<=args.public_rows<=2570000 or not 1<=args.candidate_rows<=1350000
                    or not 1<=args.other_rows<=2800000 or not 3<=args.repeats<=5):
                raise ValueError("A42_COMPLETE_POSITIVE_FIXTURE_AND_THREE_REPEATS_REQUIRED")
            run(args, output)
    except BaseException as error:
        import traceback

        output["failure_type"] = type(error).__name__
        output["failure_sqlstate"] = getattr(getattr(error, "orig", None), "sqlstate", None)
        output["failure_trace"] = [
            {"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
            for f in traceback.extract_tb(error.__traceback__)]
        save(args.output, output)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
