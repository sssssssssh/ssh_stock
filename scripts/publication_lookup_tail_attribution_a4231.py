"""Single preregistered CI diagnostic; never production/performance admission."""

import argparse
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import tracemalloc
from contextlib import nullcontext
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter, process_time
from types import SimpleNamespace
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from scripts import publication_lookup_diagnostic_a422 as lab  # noqa: E402
from scripts.a42_artifacts import (  # noqa: E402
    atomic,
    container_receipt,
    deadline,
    failure,
    header,
    install_signals,
    now,
)
from scripts.a42_receipt_contract import require  # noqa: E402
from scripts.a4231_attribution_metrics import (  # noqa: E402
    REGIMES,
    NaturalGC,
    allocation_summary,
    memory_state,
    schedule,
    summarize,
    telemetry_checks,
)
from scripts.publication_lookup_tail_review_a423 import (  # noqa: E402
    C0_SOURCE,
    C1_SOURCE,
    INPUT_HASHES,
)
from scripts.publication_tail_historical_a4231 import BASELINE_SHA  # noqa: E402

PROTOCOL = "docs/acceptance/v14_a4_2_3_1_attribution_protocol.md"
PROTOCOL_SHA256 = "f2fe56c9b67376241d4c6fb55191172a4e178667fa89b983fefce81bf913d88e"
LAB_SHA256 = "2a2e1b73163ede40365941f9f0d9b9c4c4d5e31ba60b7bbf4a77e7b4f8e8d85a"
VERSION = "A4231_ATTRIBUTION_V1_TELEMETRY_ONLY_INTERVENTION"
CONTROL = lab.TABLES[2]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
                                     separators=(",", ":")).encode()).hexdigest()


def guard():
    require(os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "A4231_ONE_CI_ATTEMPT_ONLY")
    subject = subprocess.check_output(['git', 'log', '-1', '--format=%s'], text=True)
    require('[a4231-attribution-once]' in subject, "A4231_NOT_THE_SINGLE_DISPATCH_COMMIT")
    receipt = header("a4231-tail-attribution")
    require(not receipt["working_tree_dirty"], "A4231_DIRTY_TREE")
    protocol = (ROOT/PROTOCOL).read_bytes()
    require(hashlib.sha256(protocol).hexdigest() == PROTOCOL_SHA256
            and subprocess.check_output(['git', 'show', 'HEAD^:'+PROTOCOL]) == protocol,
            "A4231_PROTOCOL_NOT_PREREGISTERED_IN_PARENT")
    require(hashlib.sha256((ROOT/'scripts/publication_lookup_diagnostic_a422.py').read_bytes())
            .hexdigest() == LAB_SHA256, "A4231_ORIGINAL_OBSERVER_CHANGED")
    require(hashlib.sha256((ROOT/'backend/app/services/data_publication.py').read_bytes()).hexdigest()
            == C0_SOURCE, "A4231_PRODUCTION_MUST_REMAIN_C0")
    require(subprocess.run(['git', 'diff', '--quiet', BASELINE_SHA, '--', 'backend', 'config',
                           'migrations', 'frontend']).returncode == 0,
            "A4231_PRODUCTION_TREE_CHANGED")
    return dict(**receipt, protocol_sha256=PROTOCOL_SHA256,
        production_source_sha256=C0_SOURCE, proposed_source_sha256=C1_SOURCE,
        measurement_version=VERSION, evidence_kind="DIAGNOSTIC_ONLY", status="INCOMPLETE",
        capacity_ready=False, performance_eligible=False, production_matches_candidate=False,
        p2="NOT_AUTHORIZED", p3="NOT_AUTHORIZED", started_at=now(), samples=[])


def describe(db):
    from sqlalchemy import text

    env = lab.environment(db)
    indexes = [dict(r) for r in db.execute(text("""SELECT tablename,indexname,indexdef
        FROM pg_indexes WHERE schemaname='public' AND tablename IN
        ('stock_trade_status_daily','stock_opportunity_daily','signal_forward_eval',
         'data_publication_row') ORDER BY tablename,indexname""")).mappings()]
    # Only hash definitions; no SQL statement or synthetic bind values exported.
    return dict(environment=env, index_definition_sha256=digest(indexes),
                settings_sha256=digest(env['settings']))


def observer_wait(db, pid):
    from sqlalchemy import text

    db.execute(text('SELECT pg_stat_clear_snapshot()'))
    row = db.execute(text("""SELECT state,wait_event_type,wait_event,
        cardinality(pg_blocking_pids(pid)) AS blockers FROM pg_stat_activity WHERE pid=:pid"""),
        dict(pid=pid)).mappings().one()
    return dict(row)


def import_snapshot(db, snapshot):
    from sqlalchemy import text

    # PostgreSQL requires a literal, not a bound parameter, for SET SNAPSHOT.
    # Accept only the server-generated identifier grammar, before any statement.
    require(isinstance(snapshot, str) and re.fullmatch(r'[0-9A-Fa-f-]{1,64}', snapshot),
            'A4231_INVALID_SNAPSHOT_ID')
    db.connection(execution_options={'isolation_level':'REPEATABLE READ'})
    db.execute(text('SET TRANSACTION READ ONLY'))
    db.execute(text("SET TRANSACTION SNAPSHOT '"+snapshot+"'"))
    db.execute(text("SET LOCAL statement_timeout='300s'"))


def run_sample(ws, model, inputs, variant, mode, engine, pid, monitor, container):
    from scripts.ab_read_resources_v14_a4_2 import Telemetry

    require(len(inputs) == 2000 and variant in ('C0', 'C1') and mode in ('full', 'minimal'),
            'A4231_UNREGISTERED_SAMPLE')
    before_db = lab.db_snapshot(ws.db)
    before_cpu = lab.backend_snapshot(container, pid)
    wait_before = observer_wait(monitor, pid)
    metrics = dict(python_json_seconds=0.0, execute_seconds=0.0,
        buffered_row_materialization_seconds=0.0, gc_seconds=0.0, gc_count=0,
        scope='ORIGINAL_LAB_EXECUTE_JSON_NEXT_TIMERS_UNCHANGED_GC_NESTED')
    started_at = now()
    memory_before = memory_state()
    collector = NaturalGC()
    try:
        with collector:
            collector.phase = 'observer_enter'
            observer = Telemetry(engine, pid, container=True) if mode == 'full' else nullcontext()
            observer.__enter__()
            try:
                memory_entered = memory_state()
                collector.phase = 'lookup_wall'
                cpu, started = process_time(), perf_counter()
                returned, batches = lab.workload(ws, model, inputs, variant, metrics)
                ended, client_cpu = perf_counter(), process_time()-cpu
                collector.phase = 'observer_exit'
                memory_after_wall = memory_state()
            finally:
                collector.phase = 'observer_exit'
                observer.__exit__(*sys.exc_info())
            memory_exited = memory_state()
    except BaseException as error:
        # Preserve bounded evidence of the failing sample too. Never attach SQL,
        # input keys, returned rows, credentials or arbitrary exception messages.
        error.a4231_partial_sample = dict(status='INCOMPLETE', variant=variant, observer_mode=mode,
            started_at=started_at, phase=collector.phase, metrics=metrics,
            gc_events=collector.events, gc_overflow=collector.overflow,
            gc_event_pairing_invalid=collector.invalid, keys=2000)
        raise
    events = collector.wall_events(started, ended)
    metrics.update(gc_seconds=sum(e['seconds'] for e in events if e['fully_inside_wall']),
                   gc_count=sum(e['fully_inside_wall'] for e in events))
    return returned, dict(observer_mode=mode, variant=variant, started_at=started_at,
        finished_at=now(), wall_seconds=ended-started, wall_started=started, wall_ended=ended,
        batch_seconds=batches, client_cpu_seconds=client_cpu, metrics=metrics, gc_events=events,
        memory_before_enter=memory_before, memory_after_enter=memory_entered,
        memory_after_wall=memory_after_wall, memory_after_exit=memory_exited,
        backend_before=before_cpu, backend_after=lab.backend_snapshot(container, pid),
        database_before=before_db, database_after=lab.db_snapshot(ws.db),
        wait_before=wait_before, wait_after=observer_wait(monitor, pid),
        full_telemetry=observer.receipt() if mode == 'full' else 'NOT_APPLICABLE_MINIMAL_MODE',
        keys=2000, batch_size=500, golden='PASS',
        gc_scope='NESTED_NOT_ADDITIVE_NO_SUBTRACTION_FROM_WALL',
        dataframe_seconds='NOT_APPLICABLE', commit_seconds='NOT_APPLICABLE_READ_ONLY_LOOKUP')


def child(config, receipt, output):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    receipt.update(statistics=config['statistics'], block=config['block'], process_pid=os.getpid(),
                   parent_snapshot_sha256=digest(config['snapshot']))
    proof, c, _ = lab.setup_runtime()  # Repeats physical proof BEFORE app imports.
    receipt.update(proof)
    require(proof['physical_system_identifier'] == config['system_identifier']
            and proof['database_instance'] == config['marker'], "A4231_CHILD_INSTANCE_DRIFT")
    from scripts.v14_test_database import verified_test_url

    url = verified_test_url()
    require(url.database == config['database'] and re.fullmatch(r'v14_[0-9a-f]{32}_test',
            url.database), 'A4231_NOT_OWNED_CHILD_DATABASE')
    require(config['statistics'] in REGIMES and config['block'] in (0, 1)
            and re.fullmatch(r'[0-9A-Fa-f-]{1,64}', config['snapshot']),
            'A4231_INVALID_CHILD_CONFIG')
    engine = create_engine(url, hide_parameters=True)
    factory = sessionmaker(bind=engine)
    require(not tracemalloc.is_tracing(), 'A4231_MEMORY_TRACER_ALREADY_ACTIVE')
    tracemalloc.start(1)
    try:
        with factory() as db, factory() as monitor:
            import_snapshot(db, config['snapshot'])
            monitor.execute(text("SET LOCAL statement_timeout='3s'"))
            pid = db.scalar(text('SELECT pg_backend_pid()'))
            receipt.update(environment_before=describe(db), backend_pid=pid,
                           gc_initial=memory_state(),
                           actual_transaction_snapshot='PARENT_RR_IMPORTED')
            require(receipt['environment_before']['index_definition_sha256'] == config['indexes']
                    and receipt['environment_before']['settings_sha256'] == config['settings'],
                    'A4231_INITIAL_ENVIRONMENT_DRIFT')
            model = next(m for m in c.MODELS if m.__tablename__ == CONTROL)
            keys = ','.join('"'+key+'"' for key in c.KEYS[CONTROL])
            inputs = [dict(r) for r in db.execute(text(f'''SELECT {keys} FROM public."{CONTROL}"
                WHERE trade_date IN (:early,:late) AND ts_code <= 'S001000.SZ'
                ORDER BY trade_date,ts_code'''), dict(early=date(2026,1,11), late=date(2026,1,21)))
                .mappings()]
            receipt['input_key_sha256'] = hashlib.sha256(json.dumps(
                inputs, default=str, sort_keys=True).encode()).hexdigest()
            require(len(inputs) == 2000 and receipt['input_key_sha256'] == INPUT_HASHES[CONTROL],
                    'A4231_INPUT_KEY_DRIFT')
            ws = SimpleNamespace(db=db, job_id=UUID(config['root']))
            warmed = {}
            for variant in (('C0','C1') if config['block'] == 0 else ('C1','C0')):
                clock = perf_counter()
                value, _ = lab.workload(ws, model, inputs, variant)
                warmed[variant] = value
                receipt.setdefault('warmups', []).append(dict(variant=variant,
                    keys=2000, observer_mode='none', wall_seconds=perf_counter()-clock))
            require(warmed['C0'] == warmed['C1'], 'A4231_WARMUP_GOLDEN_MISMATCH')
            sql_hashes = {}
            # Five-key slow-table correctness sentinels, not a timing workload.
            for table in lab.TABLES[:2]:
                sentinel_model = next(m for m in c.MODELS if m.__tablename__ == table)
                selected = ','.join('"'+key+'"' for key in c.KEYS[table])
                for day in (date(2026,1,11), date(2026,1,21)):
                    small = [dict(r) for r in db.execute(text(f'SELECT {selected} FROM public.'
                        f'"{table}" WHERE trade_date=:day ORDER BY ts_code LIMIT 5'),
                        dict(day=day)).mappings()]
                    require(lab.lookup(ws, sentinel_model, small, 'C0') == lab.lookup(
                        ws, sentinel_model, small, 'C1'), 'A4231_SLOW_SENTINEL_MISMATCH')
            receipt['slow_sentinels'] = 'PASS_5_KEYS_PER_TABLE_AND_COVERAGE_CASE'
            for variant in ('C0', 'C1'):
                lab.lookup(ws, model, inputs[:1], variant,
                    observer=lambda sql, params, v=variant:sql_hashes.update(
                        {v:hashlib.sha256(sql.encode()).hexdigest()}))
            receipt['sql_template_sha256'] = sql_hashes
            atomic(output, receipt)
            container = os.environ['A421_CONTAINER']
            for round_, position, variant, mode in schedule(config['block']):
                receipt.update(current_round=round_, current_position=position,
                               current_variant=variant, current_mode=mode)
                atomic(output, receipt)
                value, sample = run_sample(ws, model, inputs, variant, mode, engine,
                                           pid, monitor, container)
                require(value == warmed['C0'], 'A4231_LOOKUP_GOLDEN_MISMATCH')
                sample.update(statistics=config['statistics'], block=config['block'],
                              round=round_, position=position, process_pid=os.getpid())
                receipt['samples'].append(sample)
                atomic(output, receipt)
            receipt['environment_after'] = describe(db)
            require(receipt['environment_after']['index_definition_sha256'] == config['indexes']
                    and receipt['environment_after']['settings_sha256'] == config['settings'],
                    'A4231_FINAL_ENVIRONMENT_DRIFT')
            receipt.update(status='COMPLETE', gc_final=memory_state(),
                           allocation_sources=allocation_summary())
    finally:
        tracemalloc.stop()
        engine.dispose()
    return receipt


def launch(config, output, child_url):
    control = output.parent.parent/'a4231-control'
    config_path = control/(output.stem+'.json')
    require(not config_path.exists() and not output.exists(), 'A4231_CHILD_OUTPUT_EXISTS')
    atomic(config_path, config)  # No URL/credentials in the internal control file.
    env = dict(os.environ, TEST_DATABASE_URL=child_url, DATABASE_URL=child_url)
    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--child-config',
        str(config_path), '--output', str(output)], env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        process.communicate(timeout=300)
    except BaseException:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)  # Only the child just created above.
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=15)
            except ProcessLookupError:
                process.wait(timeout=15)
        raise
    require(output.is_file(), 'A4231_CHILD_RECEIPT_MISSING')
    value = json.loads(output.read_text())
    require(process.returncode == 0 and value.get('status') == 'COMPLETE',
            'A4231_CHILD_INCOMPLETE')
    return value


def validate_child(value, parent, config):
    from scripts.a42_receipt_contract import physical

    physical(value)
    for key in ('head_sha', 'run_id', 'attempt', 'model_hash', 'protocol_sha256',
                'physical_system_identifier', 'database_instance', 'production_source_sha256'):
        require(value.get(key) == parent.get(key), 'A4231_CHILD_IDENTITY_MISMATCH')
    require(value.get('working_tree_dirty') is False and value.get('status') == 'COMPLETE'
            and value.get('capacity_ready') is False and value.get('performance_eligible') is False
            and value.get('p2') == value.get('p3') == 'NOT_AUTHORIZED'
            and value.get('input_key_sha256') == INPUT_HASHES[CONTROL]
            and value.get('parent_snapshot_sha256') == digest(config['snapshot']),
            'A4231_CHILD_NOT_COMPLETE_OR_UNAUTHORIZED_CLAIM')
    require(value.get('measurement_version') == VERSION
            and set(value.get('sql_template_sha256', {}))
            == {'C0', 'C1'} and all(re.fullmatch(r'[0-9a-f]{64}', h)
                for h in value['sql_template_sha256'].values()), 'A4231_SQL_IDENTITY_MISSING')
    if parent.get('sql_template_sha256'):
        require(value['sql_template_sha256'] == parent['sql_template_sha256'],
                'A4231_SQL_TEMPLATE_DRIFT')
    rows = value.get('samples', [])
    actual = [(r['round'], r['position'], r['variant'], r['observer_mode']) for r in rows]
    require(actual == schedule(config['block']) and all(
        r.get('golden') == 'PASS' and r.get('keys') == 2000 and r.get('batch_size') == 500
        and r.get('statistics') == config['statistics'] and r.get('block') == config['block']
        and r.get('process_pid') == value.get('process_pid') for r in rows),
        'A4231_CHILD_SAMPLE_COHORT_MISMATCH')
    for row in rows:
        measured = [row.get('wall_seconds'), row.get('client_cpu_seconds')]
        measured += [row.get('metrics', {}).get(k) for k in (
            'execute_seconds', 'python_json_seconds', 'buffered_row_materialization_seconds')]
        require(all(isinstance(n, (int, float)) and not isinstance(n, bool)
                    and math.isfinite(n) and n >= 0 for n in measured)
                and row['wall_seconds'] > 0 and len(row.get('batch_seconds', [])) == 4
                and isinstance(row.get('gc_events'), list), 'A4231_METRICS_INCOMPLETE')
        require(all(e.get('generation') in (0, 1, 2) and e.get('seconds', -1) >= 0
                    and isinstance(e.get('fully_inside_wall'), bool) for e in row['gc_events']),
                'A4231_GC_EVENT_INVALID')


def run(output, path):
    import pytest
    from sqlalchemy import text

    from scripts.ab_read_resources_v14_a4_2 import host_memory_bytes
    from scripts.v14_test_database import isolated_v14_database

    proof, c, candidate = lab.setup_runtime()
    output.update(proof, **container_receipt(os.environ['A421_CONTAINER']),
        python_version=sys.version.split()[0], hash_seed=os.environ.get('PYTHONHASHSEED',
        'DEFAULT_RANDOMIZED_PER_PROCESS'), configuration_source='EXPLICIT_SYNTHETIC_NO_DOTENV')
    output['host'] = dict(logical_cpus=os.cpu_count(), memory_bytes=host_memory_bytes(),
        platform=sys.platform, host_disk_wait_attribution='NOT_AVAILABLE',
        cold_cache='UNCONTROLLED_NOT_CLAIMED')
    require(hashlib.sha256(lab.candidate_source().encode()).hexdigest() == C1_SOURCE,
            'A4231_UNEXPECTED_C1_SOURCE')
    with deadline(20*60), pytest.MonkeyPatch.context() as patch:
        with isolated_v14_database(patch) as (factory, engine):
            days = [date(2026,1,2)+timedelta(days=i) for i in range(20)]
            output['phase'] = 'fixture_seed'
            atomic(path, output)
            c.seed(factory, 5000, days)
            with candidate(factory, engine, start=days[0], end=days[-1]) as (db, job):
                output['public_counts'] = {m.__tablename__:db.scalar(text(
                    f'SELECT count(*) FROM public."{m.__tablename__}"')) for m in c.MODELS}
                require(sum(output['public_counts'].values()) == 603040, 'A4231_PUBLIC_COUNT_DRIFT')
                output['candidate_counts'] = lab.seed_candidates(db, job.id, c, days)
                db.execute(text('CREATE EXTENSION IF NOT EXISTS pg_stat_statements'))
                db.commit()
                for regime in REGIMES:
                    if regime == 'analyzed':
                        for table in (*lab.TABLES, 'data_publication_row'):
                            db.execute(text(f'ANALYZE public."{table}"'))
                        db.commit()
                    with factory() as exporter:
                        exporter.connection(execution_options={'isolation_level':'REPEATABLE READ'})
                        exporter.execute(text('SET TRANSACTION READ ONLY'))
                        exporter.execute(text("SET LOCAL statement_timeout='300s'"))
                        snapshot = exporter.scalar(text('SELECT pg_export_snapshot()'))
                        environment = describe(exporter)
                        output.setdefault('environments', {})[regime] = environment
                        for block in (0, 1):
                            output.update(phase='child_measurement', current_regime=regime,
                                          current_block=block)
                            atomic(path, output)
                            config = dict(statistics=regime, block=block, snapshot=snapshot,
                                root=str(job.id), database=engine.url.database,
                                system_identifier=proof['physical_system_identifier'],
                                marker=proof['database_instance'],
                                indexes=environment['index_definition_sha256'],
                                settings=environment['settings_sha256'])
                            filename = path.parent/f'child-{regime}-{block}.json'
                            output['active_child_file'] = filename.name
                            atomic(path, output)
                            child_value = launch(config, filename, engine.url.render_as_string(
                                hide_password=False))
                            validate_child(child_value, output, config)
                            output['sql_template_sha256'] = child_value['sql_template_sha256']
                            output.setdefault('children', []).append(dict(file=filename.name,
                                sha256=hashlib.sha256(filename.read_bytes()).hexdigest(),
                                process_pid=child_value['process_pid'],
                                statistics=regime, block=block))
                            output['samples'].extend(child_value['samples'])
                            atomic(path, output)
                require(len(output['samples']) == 128, 'A4231_COHORT_INCOMPLETE')
                require(len({c['process_pid'] for c in output['children']}) == 4,
                        'A4231_PROCESSES_NOT_INDEPENDENT')
                output.update(summary=summarize(output['samples']),
                    h3_preregistered_checks=telemetry_checks(output['samples']),
                    status='COMPLETE', phase='finished',
                    root_cause='REQUIRES_MECHANISM_AND_COUNTEREXAMPLE_REVIEW')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--child-config', type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), 'A4231_OUTPUT_EXISTS_NO_RETRY')
    output = dict(status='INCOMPLETE', evidence_kind='DIAGNOSTIC_ONLY', capacity_ready=False,
                  p2='NOT_AUTHORIZED', p3='NOT_AUTHORIZED', samples=[])
    install_signals()
    try:
        output.update(guard())
        atomic(args.output, output)
        if args.child_config:
            child(json.loads(args.child_config.read_text()), output, args.output)
        else:
            run(output, args.output)
    except BaseException as error:
        output.update(status='INCOMPLETE', **failure(error))
        if hasattr(error, 'a4231_partial_sample'):
            output['failed_sample'] = error.a4231_partial_sample
        if isinstance(error, ValueError) and re.fullmatch(r'A4231_[A-Z0-9_]+', str(error)):
            output['failure_code'] = str(error)
        raise SystemExit(1) from None
    finally:
        output['finished_at'] = now()
        atomic(args.output, output)
    print(json.dumps(dict(status=output['status'], samples=len(output['samples']),
                         capacity_ready=False, evidence_kind='DIAGNOSTIC_ONLY')))


if __name__ == '__main__':
    main()
