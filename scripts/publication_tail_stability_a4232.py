"""One preregistered statistics-stable CI diagnostic, never performance admission."""

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
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter, process_time
from types import SimpleNamespace
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT/'backend')]

from scripts import publication_lookup_diagnostic_a422 as lab  # noqa: E402
from scripts.a42_artifacts import (  # noqa: E402
    atomic,
    container_receipt,
    deadline,
    failure,
    install_signals,
    now,
)
from scripts.a42_receipt_contract import physical, require  # noqa: E402
from scripts.a4231_attribution_metrics import allocation_summary, memory_state  # noqa: E402
from scripts.a4232_plan_probe import (  # noqa: E402
    assert_plans,
    capture_queries,
    fresh_snapshot,
    plan_identity,
    plan_snapshot,
)
from scripts.a4232_stability_contract import (  # noqa: E402
    CONTROL,
    PassiveGC,
    assert_counts,
    assert_stable,
    causal_checks,
    count_snapshot,
    guard,
    schedule,
    stabilize,
    statistics_snapshot,
    summarize,
)
from scripts.publication_lookup_tail_attribution_a4231 import (  # noqa: E402
    digest,
    import_snapshot,
    observer_wait,
)
from scripts.publication_lookup_tail_review_a423 import INPUT_HASHES  # noqa: E402


def remember(receipt, error):
    earliest,seen = error,set()
    while id(earliest) not in seen:
        seen.add(id(earliest))
        previous = earliest.__cause__ or earliest.__context__
        if previous is None or id(previous) in seen:
            break
        earliest = previous
    receipt.setdefault('first_failure',getattr(error,'a4232_first_failure',failure(earliest)))
    receipt['terminal_failure'] = failure(error)
    if re.fullmatch(r'A4232_[A-Z0-9_]{1,100}',str(error)):
        receipt['terminal_failure']['failure_code'] = str(error)
    if hasattr(error,'a4232_drift'):
        receipt.update(status='INCOMPLETE_ENVIRONMENT_DRIFT',drift=error.a4232_drift)
    else:
        receipt['status'] = 'INCOMPLETE'
    if hasattr(error,'a4232_failed_sample'):
        receipt['failed_sample'] = error.a4232_failed_sample
    if hasattr(error,'a4232_cleanup_failures'):
        receipt['cleanup_failures'] = error.a4232_cleanup_failures


def close_owned_observer(observer):
    errors = []
    actions = []
    if getattr(observer,'stop',None) is not None:
        actions.append(observer.stop.set)
    thread = getattr(observer,'thread',None)
    if thread is not None and thread.ident is not None:
        def join():
            thread.join(timeout=10)
            require(not thread.is_alive(),'A4232_OBSERVER_THREAD_STILL_ACTIVE')
        actions.append(join)
    if getattr(observer,'reader',None) is not None:
        actions.append(observer.reader.finish)
    if getattr(observer,'engine',None) is not None:
        actions.append(observer.engine.dispose)
    for action in actions:
        try:
            action()
        except BaseException as error:
            errors.append(failure(error))
    return errors


@contextmanager
def observer_scope(engine, pid, mode):
    from scripts.ab_read_resources_v14_a4_2 import Telemetry

    require(mode in ('full','minimal'), 'A4232_OBSERVER_MODE_INVALID')
    observer, entered, original_error = None, False, None
    try:
        if mode == 'full':
            observer = Telemetry.__new__(Telemetry)
            observer.__init__(engine,pid,container=True)
            observer.__enter__()
            entered = True
        yield observer
    except BaseException as error:
        original_error = error
        raise
    finally:
        if observer is not None:
            try:
                if entered:
                    observer.__exit__(*sys.exc_info())
                else:
                    errors = close_owned_observer(observer)
                    if errors:
                        terminal = ValueError('A4232_PARTIAL_OBSERVER_CLEANUP_FAILED')
                        terminal.a4232_cleanup_failures = errors
                        raise terminal
            except BaseException as terminal:
                terminal.a4232_cleanup_failures = (
                    getattr(terminal,'a4232_cleanup_failures',[]) + close_owned_observer(observer))
                if original_error is not None:
                    terminal.a4232_first_failure = failure(original_error)
                raise


def run_sample(ws, model, inputs, variant, mode, engine, pid, probe, container):
    require(len(inputs) == 2000 and variant in ('C0','C1'), 'A4232_SAMPLE_INPUT_INVALID')
    before_db, before_cpu = lab.db_snapshot(ws.db), lab.backend_snapshot(container,pid)
    wait_before, memory_before = observer_wait(probe,pid), memory_state()
    metrics = dict(python_json_seconds=0.0,execute_seconds=0.0,
        buffered_row_materialization_seconds=0.0,gc_seconds=0.0,gc_count=0,
        scope='ORIGINAL_LAB_TIMERS_GC_NESTED_NOT_ADDITIVE')
    collector, started_at = PassiveGC(), now()
    try:
        with collector:
            collector.phase = 'observer_enter'
            with observer_scope(engine,pid,mode) as observer:
                memory_entered = memory_state()
                collector.phase = 'lookup_wall'
                cpu, started = process_time(), perf_counter()
                returned,batches = lab.workload(ws,model,inputs,variant,metrics)
                ended, client_cpu = perf_counter(), process_time()-cpu
                collector.phase = 'observer_exit'
                memory_after = memory_state()
            memory_exited = memory_state()
    except BaseException as error:
        error.a4232_failed_sample = dict(variant=variant,observer_mode=mode,keys=2000,
            phase=collector.phase,metrics=metrics,gc_events=collector.events,
            gc_overflow=collector.overflow,gc_callback_error=getattr(collector,'callback_error',None))
        raise
    events = collector.wall_events(started,ended)
    metrics.update(gc_seconds=sum(e['seconds'] for e in events if e['fully_inside_wall']),
                   gc_count=sum(e['fully_inside_wall'] for e in events))
    return returned,dict(statistics='analyzed_stable',variant=variant,observer_mode=mode,
        started_at=started_at,finished_at=now(),wall_seconds=ended-started,
        wall_started=started,wall_ended=ended,client_cpu_seconds=client_cpu,batch_seconds=batches,
        metrics=metrics,gc_events=events,memory_before_enter=memory_before,
        memory_after_enter=memory_entered,memory_after_wall=memory_after,
        memory_after_exit=memory_exited,backend_before=before_cpu,
        backend_after=lab.backend_snapshot(container,pid),database_before=before_db,
        database_after=lab.db_snapshot(ws.db),wait_before=wait_before,
        wait_after=observer_wait(probe,pid),full_telemetry=observer.receipt() if observer else
        'NOT_APPLICABLE_MINIMAL_MODE',keys=2000,batch_size=500,golden='PASS',
        gc_scope='NESTED_NOT_ADDITIVE_NO_SUBTRACTION',fetch_seconds='NOT_AVAILABLE_DRIVER_BUFFERED',
        dataframe_seconds='NOT_APPLICABLE',commit_seconds='NOT_APPLICABLE_READ_ONLY')


def checked_snapshot(db, probe, queries, expected_statistics, expected_plans):
    stats = statistics_snapshot(probe)
    assert_stable(expected_statistics,stats)
    plans = plan_snapshot(db,probe,queries)
    if expected_plans is not None:
        assert_plans(expected_plans,plans)
    return dict(statistics=stats,plans=plans)


def bound_owned_engine(engine):
    from sqlalchemy import event

    def checkout(connection, *args):
        from psycopg.pq import TransactionStatus

        require(connection.info.transaction_status == TransactionStatus.IDLE,
                'A4232_CHECKOUT_NOT_IDLE')
        previous = connection.autocommit
        connection.autocommit = True
        try:
            connection.execute("SET statement_timeout='300s'",prepare=False)
        finally:
            connection.autocommit = previous
    event.listen(engine,'checkout',checkout)


def run_child(config, output, path):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from scripts.v14_test_database import verified_test_url

    proof,c,_ = lab.setup_runtime()
    output.update(proof,block=config['block'],process_pid=os.getpid(),
                  parent_snapshot_sha256=digest(config['snapshot']))
    require(proof['physical_system_identifier'] == config['system_identifier']
            and proof['database_instance'] == config['marker'], 'A4232_CHILD_INSTANCE_DRIFT')
    url = verified_test_url()
    require(url.database == config['database']
            and re.fullmatch(r'v14_[0-9a-f]{32}_test',url.database or '')
            and config['block'] in range(4), 'A4232_INVALID_CHILD_CONFIG')
    require(sys.version_info[:3] == (3,12,15), 'A4232_PYTHON_VERSION_CHANGED')
    engine = create_engine(url,hide_parameters=True)
    bound_owned_engine(engine)
    factory = sessionmaker(bind=engine)
    require(not tracemalloc.is_tracing(),'A4232_MEMORY_TRACER_ALREADY_ACTIVE')
    tracemalloc.start(1)
    try:
        with factory() as db,factory() as probe:
            probe.connection(execution_options={'isolation_level':'AUTOCOMMIT'})
            probe.execute(text("SET statement_timeout='300s'"))
            import_snapshot(db,config['snapshot'])
            output['backend_pid'] = pid = db.scalar(text('SELECT pg_backend_pid()'))
            output['statistics_before_warmup'] = statistics_snapshot(probe)
            assert_stable(config['statistics_identity'],output['statistics_before_warmup'])
            assert_counts(count_snapshot(probe))
            model = next(m for m in c.MODELS if m.__tablename__ == CONTROL)
            inputs = [dict(r) for r in db.execute(text("SELECT trade_date,ts_code FROM public."
                "stock_trade_status_daily WHERE trade_date IN (:early,:late) "
                "AND ts_code <= 'S001000.SZ' ORDER BY trade_date,ts_code"),
                dict(early=date(2026,1,11),late=date(2026,1,21))).mappings()]
            output['input_key_sha256'] = hashlib.sha256(json.dumps(
                inputs,default=str,sort_keys=True).encode()).hexdigest()
            require(len(inputs) == 2000 and output['input_key_sha256'] == INPUT_HASHES[CONTROL],
                    'A4232_FIXED_KEYS_CHANGED')
            ws = SimpleNamespace(db=db,job_id=UUID(config['root']))
            queries = capture_queries(ws,model,inputs)
            output['fresh_plans_before_warmup'] = fresh_snapshot(probe,queries)
            golden = None
            for index,variant in enumerate((('C0','C1') if config['block'] % 2 == 0
                                           else ('C1','C0'))*4):
                clock = perf_counter()
                returned,_ = lab.workload(ws,model,inputs,variant)
                if golden is None:
                    golden = returned
                require(returned == golden,'A4232_WARMUP_GOLDEN_MISMATCH')
                output.setdefault('warmups',[]).append(dict(index=index,variant=variant,
                    keys=2000,wall_seconds=perf_counter()-clock,observer_mode='none'))
            for table in lab.TABLES[:2]:
                sentinel = next(m for m in c.MODELS if m.__tablename__ == table)
                keys = ','.join('"'+k+'"' for k in c.KEYS[table])
                for day in (date(2026,1,11),date(2026,1,21)):
                    small = [dict(r) for r in db.execute(text(f'SELECT {keys} FROM public.'
                        f'"{table}" WHERE trade_date=:day ORDER BY ts_code LIMIT 5'),
                        dict(day=day)).mappings()]
                    require(lab.lookup(ws,sentinel,small,'C0')
                            == lab.lookup(ws,sentinel,small,'C1'),
                            'A4232_SLOW_SENTINEL_MISMATCH')
            output['slow_sentinels'] = 'PASS_5_KEYS_PER_TABLE_AND_CASE'
            frozen = checked_snapshot(db,probe,queries,config['statistics_identity'],None)
            fresh_after = {v:dict(structure=p['fresh_structure'],sha256=p['fresh_sha256'])
                           for v,p in frozen['plans']['variants'].items()}
            if fresh_after != output['fresh_plans_before_warmup']:
                error = ValueError('A4232_ENVIRONMENT_DRIFT')
                error.a4232_drift = dict(fresh_before=output['fresh_plans_before_warmup'],
                                         fresh_after=fresh_after)
                raise error
            output['initial_snapshot'] = frozen
            output['gc_initial'] = memory_state()
            atomic(path,output)
            for round_ in range(8):
                check = dict(round=round_,before=checked_snapshot(db,probe,queries,
                    config['statistics_identity'],frozen['plans']))
                output.setdefault('round_checks',[]).append(check)
                atomic(path,output)
                for r,position,variant,mode in schedule(config['block']):
                    if r != round_:
                        continue
                    output.update(current_round=round_,current_position=position,
                                  current_variant=variant,current_mode=mode)
                    atomic(path,output)
                    returned,sample = run_sample(ws,model,inputs,variant,mode,engine,pid,probe,
                                               os.environ['A421_CONTAINER'])
                    require(returned == golden,'A4232_LOOKUP_GOLDEN_MISMATCH')
                    sample.update(block=config['block'],round=round_,position=position,
                        process_pid=os.getpid(),round_plan_before=digest(plan_identity(
                            check['before']['plans'])),round_plan_after=None,
                        plan_scope='BRACKETED_NOT_EVERY_EXECUTION_PLAN')
                    output['samples'].append(sample)
                    atomic(path,output)
                check['after'] = checked_snapshot(db,probe,queries,config['statistics_identity'],
                                                   frozen['plans'])
                for sample in output['samples'][-4:]:
                    sample['round_plan_after'] = digest(plan_identity(check['after']['plans']))
                atomic(path,output)
            output['final_snapshot'] = checked_snapshot(db,probe,queries,
                config['statistics_identity'],frozen['plans'])
            assert_counts(count_snapshot(probe))
            output.update(gc_final=memory_state(),allocation_sources=allocation_summary(),
                          status='COMPLETE',actual_transaction_snapshot='PARENT_RR_IMPORTED')
    except BaseException as error:
        remember(output,error)
        raise
    finally:
        tracemalloc.stop()
        engine.dispose()


def validate_child(value, parent, config):
    physical(value)
    for key in ('head_sha','run_id','attempt','model_hash','protocol_sha256','measurement_version',
                'database_instance','physical_system_identifier','production_source_sha256'):
        require(value.get(key) == parent.get(key),'A4232_CHILD_IDENTITY_MISMATCH')
    require(value.get('status') == 'COMPLETE' and value.get('working_tree_dirty') is False
            and value.get('block') == config['block']
            and value.get('capacity_ready') is False and value.get('performance_eligible') is False
            and value.get('production_matches_candidate') is False
            and value.get('p2') == value.get('p3') == 'NOT_AUTHORIZED'
            and value.get('unique_repair_candidate') is None
            and value.get('parent_snapshot_sha256') == digest(config['snapshot'])
            and value.get('input_key_sha256') == INPUT_HASHES[CONTROL],
            'A4232_CHILD_INCOMPLETE_OR_UNAUTHORIZED')
    rows = value.get('samples',[])
    require([(r['round'],r['position'],r['variant'],r['observer_mode']) for r in rows]
            == schedule(config['block']) and all(r.get('block') == config['block']
                and r.get('keys') == 2000 and r.get('batch_size') == 500
                and r.get('golden') == 'PASS'
                and r.get('statistics') == 'analyzed_stable'
                and r.get('process_pid') == value.get('process_pid') for r in rows),
            'A4232_COHORT_MISMATCH')
    for row in rows:
        require(all(isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n)
            and n >= 0 for n in [row['wall_seconds'],row['client_cpu_seconds'],
                *[row['metrics'][k] for k in ('execute_seconds','python_json_seconds',
                                           'buffered_row_materialization_seconds','gc_seconds')]])
            and row['wall_seconds'] > 0 and len(row['batch_seconds']) == 4
            and row['round_plan_before'] == row['round_plan_after']
            and re.fullmatch(r'[0-9a-f]{64}',row['round_plan_before']),
            'A4232_SAMPLE_METRICS_OR_PLAN_INCOMPLETE')
        require(isinstance(row.get('gc_events'),list) and all(
            e.get('generation') in (0,1,2) and isinstance(e.get('fully_inside_wall'),bool)
            and isinstance(e.get('seconds'),(int,float)) and math.isfinite(e['seconds'])
            and e['seconds'] >= 0 for e in row['gc_events']), 'A4232_GC_EVENTS_INVALID')
    require(len(value.get('round_checks',[])) == 8,'A4232_ROUND_CHECKS_MISSING')
    require([c['round'] for c in value['round_checks']] == list(range(8)),
            'A4232_ROUND_CHECK_ORDER_MISMATCH')
    expected_warmups = (('C0','C1') if config['block'] % 2 == 0 else ('C1','C0'))*4
    require([w['variant'] for w in value.get('warmups',[])] == list(expected_warmups)
            and all(w['keys'] == 2000 and w['observer_mode'] == 'none'
                    for w in value['warmups']), 'A4232_WARMUP_COHORT_MISMATCH')
    for check in value['round_checks']:
        for phase in ('before','after'):
            assert_stable(config['statistics_identity'],check[phase]['statistics'])
            assert_plans(value['initial_snapshot']['plans'],check[phase]['plans'])
        for row in rows[check['round']*4:check['round']*4+4]:
            require(row['round_plan_before'] == digest(plan_identity(check['before']['plans']))
                    and row['round_plan_after'] == digest(plan_identity(check['after']['plans'])),
                    'A4232_SAMPLE_PLAN_NOT_BOUND_TO_ROUND')
    assert_stable(config['statistics_identity'],value['statistics_before_warmup'])
    assert_stable(config['statistics_identity'],value['final_snapshot']['statistics'])
    assert_plans(value['initial_snapshot']['plans'],value['final_snapshot']['plans'])


def launch(config, path, url):
    control = path.parent.parent/'a4232-control'/path.name
    require(not path.exists() and not control.exists(),'A4232_CHILD_OUTPUT_EXISTS')
    atomic(control,config)
    process = subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--child-config',
        str(control),'--output',str(path)],env=dict(os.environ,TEST_DATABASE_URL=url,DATABASE_URL=url),
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    try:
        process.communicate(timeout=300)
    except BaseException as first:
        try:
            if process.poll() is None:
                try:
                    os.killpg(process.pid,signal.SIGTERM)
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL)
                    process.wait(timeout=15)
                except ProcessLookupError:
                    process.wait(timeout=15)
        except BaseException as terminal:
            terminal.a4232_first_failure = failure(first)
            raise
        raise
    require(path.is_file(),'A4232_CHILD_RECEIPT_MISSING')
    return json.loads(path.read_text())


def run(output, path):
    import pytest
    from sqlalchemy import text

    from scripts.ab_read_resources_v14_a4_2 import host_memory_bytes
    from scripts.v14_test_database import isolated_v14_database

    proof,c,candidate = lab.setup_runtime()
    output.update(proof,**container_receipt(os.environ['A421_CONTAINER']),python_version=sys.version,
        host=dict(logical_cpus=os.cpu_count(),memory_bytes=host_memory_bytes(),
            exclusive_io='NOT_AVAILABLE',cold_cache='UNCONTROLLED_NOT_CLAIMED'),
        hash_seed=os.environ.get('PYTHONHASHSEED','DEFAULT_RANDOMIZED_PER_PROCESS'))
    require(sys.version_info[:3] == (3,12,15),'A4232_PYTHON_VERSION_CHANGED')
    with deadline(20*60),pytest.MonkeyPatch.context() as patch:
        with isolated_v14_database(patch) as (factory,engine):
            bound_owned_engine(engine)
            try:
                output['phase'] = 'fixture_seed'
                atomic(path,output)
                days = [date(2026,1,2)+timedelta(days=i) for i in range(20)]
                c.seed(factory,5000,days)
                with (candidate(factory,engine,start=days[0],end=days[-1]) as (db,job),
                      factory() as probe):
                    probe.connection(execution_options={'isolation_level':'AUTOCOMMIT'})
                    probe.execute(text("SET statement_timeout='300s'"))
                    lab.seed_candidates(db,job.id,c,days)
                    db.execute(text('CREATE EXTENSION IF NOT EXISTS pg_stat_statements'))
                    db.commit()
                    output['counts'] = count_snapshot(probe)
                    assert_counts(output['counts'])
                    output['phase'] = 'statistics_stabilization'
                    atomic(path,output)
                    output['stabilization'] = stabilize(db,engine.url.database,
                                                       lambda:statistics_snapshot(probe))
                    atomic(path,output)
                    with factory() as exporter:
                        exporter.connection(execution_options={'isolation_level':'REPEATABLE READ'})
                        exporter.execute(text('SET TRANSACTION READ ONLY'))
                        exporter.execute(text("SET LOCAL statement_timeout='300s'"))
                        snapshot = exporter.scalar(text('SELECT pg_export_snapshot()'))
                        output['parent_snapshot_sha256'] = digest(snapshot)
                        for block in range(4):
                            assert_stable(output['stabilization']['identity'],statistics_snapshot(probe))
                            output.update(phase='child_measurement',current_block=block)
                            config = dict(block=block,snapshot=snapshot,root=str(job.id),
                                database=engine.url.database,marker=proof['database_instance'],
                                system_identifier=proof['physical_system_identifier'],
                                statistics_identity=output['stabilization']['identity'])
                            filename = path.parent/f'child-{block}.json'
                            output['active_child_file'] = filename.name
                            atomic(path,output)
                            child = launch(config,filename,engine.url.render_as_string(
                                hide_password=False))
                            output.setdefault('children',[]).append(dict(file=filename.name,
                                sha256=hashlib.sha256(filename.read_bytes()).hexdigest(),block=block,
                                status=child['status'],process_pid=child.get('process_pid')))
                            if child['status'] != 'COMPLETE':
                                output['child_failure'] = {k:child[k] for k in
                                    ('first_failure','terminal_failure','drift','failed_sample')
                                    if k in child}
                                error = ValueError('A4232_ENVIRONMENT_DRIFT' if 'drift' in child
                                                   else 'A4232_CHILD_INCOMPLETE')
                                if 'drift' in child:
                                    error.a4232_drift = dict(block=block,child_drift=child['drift'])
                                if 'first_failure' in child:
                                    error.a4232_first_failure = child['first_failure']
                                raise error
                            validate_child(child,output,config)
                            if block:
                                assert_plans(output['frozen_plans'],child['initial_snapshot']['plans'])
                            else:
                                output['frozen_plans'] = child['initial_snapshot']['plans']
                            output['samples'].extend(child['samples'])
                            assert_stable(output['stabilization']['identity'],statistics_snapshot(probe))
                            atomic(path,output)
                        require(len(output['samples']) == 128 and len({
                            c['process_pid'] for c in output['children']}) == 4,
                            'A4232_COHORT_INCOMPLETE')
                        output['final_statistics'] = statistics_snapshot(probe)
                        assert_stable(output['stabilization']['identity'],output['final_statistics'])
                        output.update(status='COMPLETE',phase='finished',summary=summarize(output['samples']),
                            h3_checks=causal_checks(output['samples']),
                            root_cause='REQUIRES_MECHANISM_AND_COUNTEREXAMPLE_REVIEW')
            except BaseException as error:
                remember(output,error)
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--child-config',type=Path)
    args = parser.parse_args()
    require(not args.output.exists(),'A4232_OUTPUT_EXISTS_NO_RETRY')
    output = dict(status='INCOMPLETE',samples=[],evidence_kind='DIAGNOSTIC_ONLY',
        capacity_ready=False,performance_eligible=False,production_matches_candidate=False,
        unique_repair_candidate=None,p2='NOT_AUTHORIZED',p3='NOT_AUTHORIZED')
    install_signals()
    try:
        output.update(guard())
        atomic(args.output,output)
        if args.child_config:
            run_child(json.loads(args.child_config.read_text()),output,args.output)
        else:
            run(output,args.output)
    except BaseException as error:
        remember(output,error)
        raise SystemExit(1) from None
    finally:
        output['finished_at'] = now()
        atomic(args.output,output)
    print(json.dumps(dict(status=output['status'],samples=len(output['samples']),capacity_ready=False)))


if __name__ == '__main__':
    main()
