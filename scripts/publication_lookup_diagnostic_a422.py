"""CI-only, read-only C0/C1/C2/C3 lookup comparison; never a capacity receipt."""

import argparse
import gc
import hashlib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import types
from contextlib import contextmanager
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from time import perf_counter, process_time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
BASELINE = "4a095883bff09e0e5da6fe5fcf308f8206651f35"
VARIANTS = {"C0": 500, "C1": 500, "C2": 500, "C3_100": 100, "C3_1000": 1000}
TABLES = ("stock_opportunity_daily", "signal_forward_eval", "stock_trade_status_daily")
CONTROL_REPEATS = 100  # Fixed before this trial, not a retry-until-pass policy.


@contextmanager
def observe_gc(metrics):
    started = []

    def callback(phase, info):
        if phase == 'start':
            started.append(perf_counter())
        elif started:
            metrics['gc_seconds'] += perf_counter()-started.pop()
            metrics['gc_count'] += 1
    gc.callbacks.append(callback)
    try:
        yield
    finally:
        gc.callbacks.remove(callback)


def candidate_source():
    source = subprocess.check_output([
        'git', 'show', BASELINE+':backend/app/services/data_publication.py'], text=True)
    old = '''WHERE (c.publication_id,c.table_name,c.row_key) >=
                (:publication,:table_name,jsonb_build_array({key_sql}))
              AND (c.publication_id,c.table_name,c.row_key) <=
                (:publication,:table_name,jsonb_build_array({key_sql}))'''
    new = '''WHERE c.publication_id=:publication AND c.table_name=:table_name
              AND c.row_key=jsonb_build_array({key_sql})'''
    if source.count(old) != 1:
        raise ValueError('A422_BASELINE_SQL_CHANGED')
    source = source.replace(old, new)
    comment = '''# Equal inclusive bounds on the non-NULL, totally ordered PK are a point
        # lookup. Full PK ordering keeps the covering key access path even when
        # empty-table statistics underestimate our own uncommitted candidates.'''
    if source.count(comment) != 1:
        raise ValueError('A422_BASELINE_COMMENT_CHANGED')
    return source.replace(comment, '''# Explicit equalities expose the unique non-NULL candidate PK,
        # including negative probes when this key has not been staged yet.
        # Keep the same typed row, tombstone and public-preimage semantics.''')


def redact_plan(value):
    if isinstance(value, dict):
        return {k:redact_plan(v) for k, v in value.items() if k != 'Query Parameters'}
    if isinstance(value, list):
        return [redact_plan(v) for v in value]
    if isinstance(value, str):
        return re.sub(r"'\[.*?\]'::jsonb", "'<synthetic-keys-redacted>'::jsonb", value,
                      flags=re.S)
    return value


def prepared_snapshot(db):
    from sqlalchemy import text

    return [dict(name=row['name'], generic_plans=row['generic_plans'],
                 custom_plans=row['custom_plans'],
                 sql_sha256=hashlib.sha256(row['statement'].encode()).hexdigest())
            for row in db.execute(text('SELECT name,statement,generic_plans,custom_plans '
                "FROM pg_prepared_statements WHERE statement LIKE 'WITH input_keys AS%%'"))
            .mappings()]


def parse_backend_process(raw, ticks):
    first, _, status = raw.partition('\n')
    fields = first.rsplit(')', 1)[1].split()
    memory = {}
    for line in status.splitlines():
        parts = line.split()
        if parts and parts[0] in ('VmRSS:', 'VmHWM:'):
            if len(parts) != 3 or parts[2] != 'kB':
                raise ValueError('A422_BACKEND_MEMORY_UNITS_CHANGED')
            memory[parts[0][:-1]] = int(parts[1])*1024
    return dict(cpu_seconds=(int(fields[11])+int(fields[12]))/ticks,
        current_rss_bytes=memory['VmRSS'], process_lifetime_peak_rss_bytes=memory['VmHWM'],
        scope='MAIN_BACKEND_INTERVAL_INCLUDES_OBSERVERS_HWM_IS_PROCESS_LIFETIME')


@lru_cache
def backend_clock_ticks(container):
    return int(subprocess.check_output(['docker', 'exec', container, 'getconf', 'CLK_TCK'],
                                      text=True, timeout=10))


def backend_snapshot(container, pid):
    raw = subprocess.check_output(['docker', 'exec', container, 'cat',
        f'/proc/{int(pid)}/stat', f'/proc/{int(pid)}/status'], text=True, timeout=10)
    return parse_backend_process(raw, backend_clock_ticks(container))


def logged_plans(log):
    """Extract only auto_explain JSON; never export raw server logs or binds."""
    decoder, result, offset = json.JSONDecoder(), [], 0
    while (start := log.find('{', offset)) >= 0:
        try:
            value, end = decoder.raw_decode(log[start:])
        except ValueError:
            offset = start+1
            continue
        offset = start+end
        if (isinstance(value, dict)
                and str(value.get('Query Text', '')).startswith('WITH input_keys')):
            result.append(redact_plan(value))
    return result


def enable_auto_explain(db):
    from sqlalchemy import text

    db.execute(text("LOAD 'auto_explain'"))
    for name, value in {'log_format':'json', 'log_analyze':'on', 'log_buffers':'on',
        'log_verbose':'on', 'log_timing':'on', 'log_settings':'on',
        'log_parameter_max_length':'0', 'log_min_duration':'0ms'}.items():
        db.execute(text(f"SET LOCAL auto_explain.{name}='{value}'"))


def read_logged_plans(container, started):
    raw = subprocess.run(['docker', 'logs', '--since', started, container],
                         text=True, capture_output=True, timeout=30, check=True)
    return logged_plans(raw.stdout+raw.stderr)


def actual_execution_probe(db, ws, models, inputs, container):
    from sqlalchemy import text

    from scripts.a42_artifacts import now

    # Only after timed comparisons. No plan-cache or planner hints are changed.
    started = now()
    before = prepared_snapshot(db)
    enable_auto_explain(db)
    cases = []
    golden = {}
    for model in models:
        table = model.__tablename__
        for variant in ('C0', 'C1', 'C2'):
            for case, offset in (('b_present', 0), ('late_keys', 1000)):
                clock = perf_counter()
                result = lookup(ws, model, inputs[table][offset:offset+500], variant)
                if variant == 'C0':
                    golden[table, case] = result
                elif result != golden[table, case]:
                    raise ValueError('A422_ACTUAL_PROBE_GOLDEN_MISMATCH')
                cases.append(dict(table=table, variant=variant, case=case,
                    wall_seconds=perf_counter()-clock, existing_rows=len(result[0]), golden='PASS'))
    db.execute(text("SET LOCAL auto_explain.log_min_duration='-1'"))
    plans = read_logged_plans(container, started)
    if len(plans) != len(cases):
        raise ValueError('A422_ACTUAL_EXECUTION_PLAN_COUNT_MISMATCH')
    return dict(prepared_before=before, prepared_after=prepared_snapshot(db),
        observer_scope='UNTIMED_POST_COMPARISON_AUTO_EXPLAIN_NO_BIND_VALUES',
        cases=[dict(**case, plan=plan) for case, plan in zip(cases, plans, strict=True)])


@lru_cache
def baseline_module():
    source = subprocess.check_output([
        "git", "show", BASELINE+":backend/app/services/data_publication.py"], text=True)
    module = types.ModuleType("a422_frozen_publication")
    exec(compile(source, "<a422-frozen-publication>", "exec"), module.__dict__)
    return module


def rewrite(sql, keys, variant):
    if variant == "C0":
        return sql
    if variant not in VARIANTS:
        raise ValueError("A422_UNKNOWN_VARIANT")
    key_sql = ",".join(f'i."{k}"' for k in keys)
    old = f"""WHERE (c.publication_id,c.table_name,c.row_key) >=
                (:publication,:table_name,jsonb_build_array({key_sql}))
              AND (c.publication_id,c.table_name,c.row_key) <=
                (:publication,:table_name,jsonb_build_array({key_sql}))"""
    new = f"""WHERE c.publication_id=:publication AND c.table_name=:table_name
              AND c.row_key=jsonb_build_array({key_sql})"""
    if sql.count(old) != 1:
        raise ValueError("A422_BASELINE_SQL_CHANGED")
    sql = sql.replace(old, new)
    if variant == "C2":
        old_join = f"""LEFT JOIN LATERAL (SELECT * FROM public.data_publication_row c
              {new}
              ORDER BY c.publication_id,c.table_name,c.row_key LIMIT 1) c ON true"""
        new_join = ("LEFT JOIN public.data_publication_row c ON c.publication_id=:publication "
                    "AND c.table_name=:table_name "
                    f"AND c.row_key=jsonb_build_array({key_sql})")
        if sql.count(old_join) != 1:
            raise ValueError("A422_CANDIDATE_JOIN_CHANGED")
        sql = sql.replace(old_join, new_join)
    return sql


def lookup(ws, model, payload, variant, observer=None, metrics=None):
    """Execute the exact frozen Python implementation, changing only lab SQL."""
    from sqlalchemy import text

    module = baseline_module()
    db = ws.db
    original_json = module.json

    def timed(function):
        def call(*args, **kwargs):
            started = perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                metrics['python_json_seconds'] += perf_counter()-started
        return call

    class Proxy:
        def execute(self, statement, parameters):
            sql = rewrite(statement.text, module.KEYS[model.__tablename__], variant)
            if observer is not None:
                observer(sql, parameters)
            started = perf_counter()
            try:
                result = db.execute(text(sql), parameters)
            finally:
                if metrics is not None:
                    metrics['execute_seconds'] += perf_counter()-started
            if metrics is None:
                return result

            class Rows:
                def mappings(self):
                    rows = iter(result.mappings())
                    while True:
                        clock = perf_counter()
                        try:
                            row = next(rows)
                        except StopIteration:
                            return
                        finally:
                            metrics['buffered_row_materialization_seconds'] += perf_counter()-clock
                        yield row
            return Rows()

    ws.db = Proxy()
    if metrics is not None:
        module.json = types.SimpleNamespace(dumps=timed(json.dumps), loads=timed(json.loads))
    try:
        return module.PublicationWorkspace._lookup_batch(ws, model, payload)
    finally:
        ws.db = db
        module.json = original_json


def workload(ws, model, inputs, variant, metrics=None):
    returned, batches = [{}, {}, None], []
    size = VARIANTS[variant]
    for offset in range(0, len(inputs), size):
        started = perf_counter()
        a, b, now = lookup(ws, model, inputs[offset:offset+size], variant, metrics=metrics)
        batches.append(perf_counter()-started)
        returned[0].update(a)
        returned[1].update(b)
        returned[2] = now
    return tuple(returned), batches


def distribution(values):
    if len(values) < 5:
        raise ValueError("A422_FIVE_REPEATS_REQUIRED")
    return dict(median=statistics.median(values),
                p95=statistics.quantiles(values, n=100, method="inclusive")[94], samples=values)


def summarize(samples):
    groups = {}
    for sample in samples:
        groups.setdefault((sample["statistics"], sample["table"], sample["variant"]), []).append(
            sample["wall_seconds"])
    return [dict(statistics=k[0], table=k[1], variant=k[2], **distribution(v))
            for k, v in groups.items()]


def whole_workloads(samples):
    groups, seen = {}, set()
    for s in samples:
        identity = s['statistics'], s['table'], s['variant'], s['repeat']
        if identity in seen:
            raise ValueError('A422_DUPLICATE_SAMPLE')
        seen.add(identity)
        if s['repeat'] >= 5:
            if s['table'] != TABLES[2] or s['repeat'] >= CONTROL_REPEATS:
                raise ValueError('A422_UNEXPECTED_EXTRA_REPEAT')
            continue  # Tail-only repetitions remain in raw samples and table summaries.
        key = s['statistics'], s['variant'], s['repeat']
        tables = groups.setdefault(key, {})
        if s['table'] in tables:
            raise ValueError('A422_DUPLICATE_SAMPLE')
        tables[s['table']] = s['wall_seconds']
    workloads = {}
    for (regime, variant, repeat), tables in groups.items():
        if set(tables) != set(TABLES):
            raise ValueError('A422_WHOLE_WORKLOAD_INCOMPLETE')
        workloads.setdefault((regime, variant), []).append((repeat, sum(tables.values())))
    return [dict(statistics=regime, variant=variant,
                 **distribution([seconds for _, seconds in sorted(values)]))
            for (regime, variant), values in workloads.items()]


def performance_decision(summary, workloads=None):
    """Both stats regimes and every table are required; never cherry-pick."""
    rows = {(r["statistics"], r["table"], r["variant"]): r for r in summary}
    reasons = []
    ratios = []
    for regime in ("as_seeded", "analyzed"):
        before, after = [], []
        for table in TABLES:
            a, b = rows.get((regime, table, "C0")), rows.get((regime, table, "C1"))
            if not a or not b:
                reasons.append("MISSING_COMPARISON")
                continue
            ratio = b["median"] / a["median"]
            ratios.append(dict(statistics=regime, table=table, c1_over_c0=ratio))
            if table in TABLES[:2] and ratio > 0.7:
                reasons.append("SLOW_TABLE_MEDIAN_TARGET_NOT_MET")
            if b["p95"] > a["p95"] * 1.1:
                reasons.append("P95_REGRESSION")
            if table == TABLES[2] and ratio > 1.1:
                reasons.append("CONTROL_REGRESSION")
            before.append(a["median"])
            after.append(b["median"])
        whole = {(r['statistics'], r['variant']): r for r in (workloads or [])}
        a, b = whole.get((regime, 'C0')), whole.get((regime, 'C1'))
        if len(before) != len(TABLES) or not a or not b or b['median'] > a['median'] * 0.8:
            reasons.append("WORKLOAD_MEDIAN_TARGET_NOT_MET")
    return dict(performance_eligible=not reasons, reasons=sorted(set(reasons)), ratios=ratios,
                caveat="Per-repeat sum of all 3 tables' measured lookup walls (not contiguous); "
                       "NOT full table, upsert/publication or formal L2 acceptance; "
                       "manual plan/resource review required before any production change")


def setup_runtime():
    from scripts.a42_artifacts import isolation
    from scripts.v14_test_database import verified_test_url

    proof = isolation()
    url = verified_test_url()
    if os.environ.get("AB_MERGE_READ_ENABLED", "false").lower() != "false":
        raise ValueError("A422_READ_FLAG_MUST_BE_FALSE")
    os.environ.update(DATABASE_URL=url.render_as_string(hide_password=False),
                      AB_MERGE_READ_ENABLED="false", LLM_ENABLED="false",
                      TUSHARE_TOKEN="synthetic-a422")
    from app.core.config import Settings, get_settings

    Settings.model_config['env_file'] = None  # Standalone lab process, never business dotenv.
    from app.models import market_data as m
    from app.models.job import JobRun
    from app.services.data_publication import KEYS, MODELS

    from scripts import data_publication_capacity_v12 as c
    from tests.integration.test_data_publication import candidate, sample_row

    for name, value in dict(m=m, JobRun=JobRun, KEYS=KEYS, MODELS=MODELS,
                            get_settings=get_settings, sample_row=sample_row).items():
        setattr(c, name, value)
    get_settings.cache_clear()
    return proof, c, candidate


def seed_candidates(db, root, c, days):
    """Only synthetic setup, not real upsert/publication or formal L2 success."""
    from sqlalchemy import text

    counts = {}
    for model in c.MODELS[:9]:
        name = model.__tablename__
        keys = ",".join(f'p."{k}"' for k in c.KEYS[name])
        change = ("jsonb_build_object('calc_run_id',CAST(:root AS text))"
                  if "calc_run_id" in model.__table__.c else "'{}'::jsonb")
        # Reproduce first-write A-only keys as well as A/B-covered keys for BOTH
        # slow representatives; P1's opportunity fixture covered every B key.
        limit = ("WHERE p.trade_date <= :cutoff"
                 if name in {'signal_forward_eval', 'stock_opportunity_daily'} else "")
        entity = 'p.ts_code' if 'ts_code' in model.__table__.c else 'NULL::text'
        count = db.execute(text(f"""INSERT INTO public.data_publication_row
            (publication_id,table_name,row_key,row_data,base_row,source_id,is_deleted,
             trade_date,entity_key)
            SELECT :root,:name,jsonb_build_array({keys}),to_jsonb(p)||{change},to_jsonb(p),
              :root,false,p.trade_date,{entity} FROM public."{name}" p {limit}"""),
            dict(root=root, name=name, cutoff=days[9])).rowcount
        counts[name] = count
    db.commit()
    if sum(counts.values()) != 503020:
        raise ValueError("A422_FIXTURE_CANDIDATE_COUNT_CHANGED")
    return counts


def db_snapshot(db):
    from sqlalchemy import text

    db.execute(text("SELECT pg_stat_force_next_flush()"))
    db.execute(text("SELECT pg_stat_clear_snapshot()"))
    result = dict(database=dict(db.execute(text("""SELECT blks_read,blks_hit,temp_files,
        temp_bytes,blk_read_time,blk_write_time FROM pg_stat_database
        WHERE datname=current_database()""")).mappings().one()))
    exists = db.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_extension "
                            "WHERE extname='pg_stat_statements')"))
    if exists:
        result["lookup_statements"] = [dict(r) for r in db.execute(text("""SELECT queryid::text,
          calls,rows,total_exec_time,min_exec_time,max_exec_time,mean_exec_time,shared_blks_hit,
          shared_blks_read,temp_blks_read,temp_blks_written,shared_blk_read_time,
          shared_blk_write_time,wal_bytes FROM pg_stat_statements
          WHERE dbid=(SELECT oid FROM pg_database WHERE datname=current_database())
          AND query LIKE 'WITH input_keys AS%%'""")).mappings()]
    else:
        result["lookup_statements"] = "NOT_AVAILABLE"
    result["scope"] = ("Cumulative child DB, includes observers; queryid only, no SQL or binds; "
                       "pg_stat_database can lag until transaction end; NOT per-query I/O")
    return result


def environment(db):
    from sqlalchemy import text

    settings = dict(db.execute(text("""SELECT name,setting||coalesce(' '||unit,'')
      FROM pg_settings WHERE name IN ('shared_buffers','work_mem','random_page_cost',
      'effective_cache_size','max_parallel_workers_per_gather','track_io_timing',
      'shared_preload_libraries','statement_timeout','jit')""")).all())
    tables = [dict(r) for r in db.execute(text("""SELECT c.relname,
      pg_table_size(c.oid) AS table_bytes,pg_indexes_size(c.oid) AS index_bytes,
      c.reltuples,c.relpages,s.n_live_tup,s.last_analyze,s.last_autoanalyze FROM pg_class c
      JOIN pg_namespace n ON c.relnamespace=n.oid LEFT JOIN pg_stat_user_tables s ON s.relid=c.oid
      WHERE n.nspname='public' AND c.relname IN ('stock_opportunity_daily',
      'signal_forward_eval','stock_trade_status_daily','data_publication_row')""")).mappings()]
    return dict(settings=settings, tables=tables)


def run(output, path):
    import pytest
    from sqlalchemy import text

    from scripts.a42_artifacts import atomic, container_receipt, deadline, now
    from scripts.ab_read_profile_v14_a4 import resource_snapshot
    from scripts.ab_read_resources_v14_a4_2 import Telemetry, host_memory_bytes
    from scripts.v14_test_database import isolated_v14_database

    # Only this CI-created instance is used for performance evidence.
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("A422_MEASUREMENTS_REQUIRE_ISOLATED_CI_RUNNER")
    proof, c, candidate = setup_runtime()
    output.update(proof)
    container = os.environ["A421_CONTAINER"]
    output.update(container_receipt(container))
    output["host"] = dict(platform=platform.platform(), logical_cpus=os.cpu_count(),
        memory_bytes=host_memory_bytes(), cpu_model=next((line.split(':',1)[1].strip()
        for line in Path('/proc/cpuinfo').read_text().splitlines()
        if line.startswith('model name')), 'NOT_AVAILABLE'),
        host_disk_wait_attribution="NOT_AVAILABLE", cold_cache="UNCONTROLLED_NOT_CLAIMED")
    with deadline(100*60), pytest.MonkeyPatch.context() as patch:
        with isolated_v14_database(patch) as (factory, engine):
            with factory() as observer:
                clock = now()
                enable_auto_explain(observer)
                observer.execute(text('WITH input_keys AS (SELECT 1 AS synthetic) '
                                      'SELECT * FROM input_keys')).all()
                observer.execute(text("SET LOCAL auto_explain.log_min_duration='-1'"))
                if len(read_logged_plans(container, clock)) != 1:
                    raise ValueError('A422_OBSERVER_PREFLIGHT_FAILED')
                output['backend_observer_preflight'] = backend_snapshot(
                    container, observer.scalar(text('SELECT pg_backend_pid()')))
            output['observer_preflight'] = 'PASS'
            output['configuration_source'] = 'EXPLICIT_SYNTHETIC_ENV_NO_DOTENV'
            days = [date(2026, 1, 2)+timedelta(days=i) for i in range(20)]
            output.update(phase="fixture_seed", public_stocks=5000, public_days=20,
                          public_total_rows=603040)
            atomic(path, output)
            c.seed(factory, 5000, days)
            with candidate(factory, engine, start=days[0], end=days[-1]) as (db, job):
                ws = db.info['publication_workspace']
                output['public_counts'] = {model.__tablename__:db.scalar(text(
                    f'SELECT count(*) FROM public."{model.__tablename__}"')) for model in c.MODELS}
                if sum(output['public_counts'].values()) != 603040:
                    raise ValueError('A422_PUBLIC_FIXTURE_COUNT_CHANGED')
                output['candidate_rows'] = seed_candidates(db, job.id, c, days)
                db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_stat_statements"))
                db.commit()
                db.execute(text("SET LOCAL statement_timeout='300s'"))
                pid = db.scalar(text("SELECT pg_backend_pid()"))
                inputs = {}
                for name in TABLES:
                    keys = ','.join('"'+k+'"' for k in c.KEYS[name])
                    inputs[name] = [dict(r) for r in db.execute(text(f"""SELECT {keys}
                      FROM public."{name}" WHERE trade_date IN (:early,:late)
                      AND ts_code <= 'S001000.SZ' ORDER BY trade_date,ts_code"""),
                      dict(early=days[9], late=days[19])).mappings()]
                    if len(inputs[name]) != 2000:
                        raise ValueError("A422_REPRESENTATIVE_KEY_COUNT_CHANGED")
                    row_keys = [[row[key] for key in c.KEYS[name]] for row in inputs[name]]
                    hits = db.scalar(text('''SELECT count(*)
                        FROM jsonb_array_elements(CAST(:keys AS jsonb)) k(value)
                        JOIN public.data_publication_row c ON c.publication_id=:root
                          AND c.table_name=:name AND c.row_key=k.value'''),
                        dict(keys=json.dumps(row_keys, default=str), root=job.id, name=name))
                    if hits != (1000 if name in TABLES[:2] else 2000):
                        raise ValueError('A422_CANDIDATE_COVERAGE_CHANGED')
                    output.setdefault('candidate_key_hits', {})[name] = hits
                output['input_key_sha256'] = {name:hashlib.sha256(json.dumps(
                    rows, default=str, sort_keys=True).encode()).hexdigest()
                    for name, rows in inputs.items()}
                for regime in ('as_seeded', 'analyzed'):
                    if regime == 'analyzed':
                        for name in (*TABLES, 'data_publication_row'):
                            db.execute(text(f'ANALYZE public."{name}"'))
                        db.commit()
                        db.execute(text("SET LOCAL statement_timeout='300s'"))
                    output.setdefault('environments', {})[regime] = environment(db)
                    # Persist all three tables' actual plans before the longer
                    # repeated measurements; a deadline must not erase diagnosis.
                    for name in TABLES:
                        model = next(m for m in c.MODELS if m.__tablename__ == name)
                        for variant in VARIANTS:
                            def explain(sql, params, regime=regime, name=name, variant=variant):
                                prefix = ('EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS, '
                                          'FORMAT JSON) ')
                                plan = db.execute(text(prefix+sql), params).scalar()
                                output.setdefault('plans', []).append(dict(statistics=regime,
                                    table=name, variant=variant, plan=redact_plan(plan)))
                            for case, offset in (('b_present', 0), ('late_keys', 1000)):
                                before_plans = len(output.get('plans', []))
                                lookup(ws, model, inputs[name][offset:offset+VARIANTS[variant]],
                                       variant, explain)
                                output['plans'][before_plans]['case'] = case
                                atomic(path, output)
                    for name in TABLES:
                        model = next(m for m in c.MODELS if m.__tablename__ == name)
                        expected, _ = workload(ws, model, inputs[name], 'C0')
                        repeats = CONTROL_REPEATS if name == TABLES[2] else 5
                        for repeat in range(repeats):
                            variants = list(VARIANTS)
                            rotation = repeat % len(variants)
                            variants = variants[rotation:]+variants[:rotation]
                            for variant in variants:
                                size = VARIANTS[variant]
                                output.update(phase='query_comparison', current_table=name,
                                    current_variant=variant, current_repeat=repeat)
                                atomic(path, output)
                                before = db_snapshot(db)
                                resources_before = resource_snapshot(container)
                                backend_before = backend_snapshot(container, pid)
                                started_at = now()
                                metrics = dict(python_json_seconds=0.0, execute_seconds=0.0,
                                    buffered_row_materialization_seconds=0.0,
                                    gc_seconds=0.0, gc_count=0,
                                    gc_scope='PROCESS_GC_NESTED_IN_JSON_ROW_AND_WALL',
                                    execute_scope='DRIVER_EXECUTE_INCLUDES_NETWORK_AND_BUFFERING',
                                    dataframe_seconds='NOT_APPLICABLE_NO_DATAFRAME_IN_LOOKUP')
                                with (Telemetry(engine, pid, container=True) as telemetry,
                                      observe_gc(metrics)):
                                    cpu, clock = process_time(), perf_counter()
                                    returned, batches = workload(
                                        ws, model, inputs[name], variant, metrics)
                                    wall, client_cpu = perf_counter()-clock, process_time()-cpu
                                if returned != expected:
                                    raise ValueError('A422_LOOKUP_GOLDEN_MISMATCH')
                                sample = dict(statistics=regime, table=name, variant=variant,
                                    repeat=repeat, keys=2000, batch_size=size, wall_seconds=wall,
                                    purpose='tail_only' if repeat >= 5 else 'whole_workload',
                                    started_at=started_at, finished_at=now(),
                                    rows_per_second=2000/wall,
                                    batch_seconds=batches, client_cpu_seconds=client_cpu,
                                    metrics=metrics, telemetry=telemetry.receipt(),
                                    backend_before=backend_before,
                                    backend_after=backend_snapshot(container, pid),
                                    resources_before=resources_before,
                                    resources_after=resource_snapshot(container),
                                    database_before=before, database_after=db_snapshot(db),
                                    commit_seconds='NOT_APPLICABLE_READ_ONLY_LOOKUP', golden='PASS')
                                output.setdefault('samples', []).append(sample)
                                atomic(path, output)
                                print(json.dumps(dict(statistics=regime, table=name,
                                    variant=variant, repeat=repeat, wall_seconds=wall)), flush=True)
                    models = [next(m for m in c.MODELS if m.__tablename__ == name)
                              for name in TABLES]
                    probes = output.setdefault('actual_execution_probes', {})
                    probes[regime] = actual_execution_probe(db, ws, models, inputs, container)
                    atomic(path, output)
                output['summary'] = summarize(output['samples'])
                output['whole_workloads'] = whole_workloads(output['samples'])
                output['decision'] = performance_decision(
                    output['summary'], output['whole_workloads'])
                current = (ROOT/'backend/app/services/data_publication.py').read_text()
                proposed = candidate_source()
                output.update(lookup_baseline_sha=BASELINE,
                    proposed_source_sha256=hashlib.sha256(proposed.encode()).hexdigest(),
                    production_source_sha256=hashlib.sha256(current.encode()).hexdigest(),
                    production_matches_candidate=current == proposed)
                output.update(status='COMPLETE', phase='finished',
                              root_cause='INSUFFICIENT_EVIDENCE_REQUIRES_PLAN_REVIEW')
                atomic(path, output)


def main():
    from scripts.a42_artifacts import atomic, failure, header, install_signals, now

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('A422_OUTPUT_ALREADY_EXISTS')
    output = dict(**header('a422-lookup-diagnosis'), artifact_kind='DIAGNOSTIC_ONLY',
                  status='INCOMPLETE', started_at=now(), samples=[], plans=[],
                  repeats=dict(slow_tables=5, control=CONTROL_REPEATS),
                  formal_capacity_complete=False)
    install_signals()
    try:
        run(output, args.output)
    except BaseException as error:
        output.update(status='INCOMPLETE', **failure(error))
        if isinstance(error, ValueError) and re.fullmatch(r'A422_[A-Z0-9_]+', str(error)):
            output['failure_code'] = str(error)
        atomic(args.output, output)
        raise SystemExit(1) from None
    finally:
        output['finished_at'] = now()
        atomic(args.output, output)
    if os.environ.get('GITHUB_OUTPUT'):
        ready = (output.get('status') == 'COMPLETE'
                 and output.get('production_matches_candidate') is True
                 and output.get('decision', {}).get('performance_eligible') is True)
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
            stream.write('capacity_ready='+str(ready).lower()+'\n')


if __name__ == '__main__':
    main()
