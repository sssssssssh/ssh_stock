"""Frozen single-round controls; synthetic failure injection is not timing evidence."""

import ast
import copy
import gc
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
import yaml

from scripts import a4232_plan_probe as plans
from scripts import a4232_stability_contract as c
from scripts import publication_tail_stability_a4232 as runner
from scripts.a4232_test_receipt import receipt


def statistics_snapshot():
    return dict(observed_at='fixed-observation',relations=[dict(relname=name,reltuples=100,
        relpages=2,reloptions=None,last_analyze='fixed-analyze',last_autoanalyze=None,
        statistic_count=3,statistic_sha256='1'*64) for name in sorted(c.TABLES)],
        index_sha256='2'*64,settings={'statement_timeout':'300000 ms'},
        planner_settings={'plan_cache_mode':'auto'},active_autovacuum_workers=0)


def plan_snapshot():
    return dict(variants={v:dict(fresh_sha256='3'*64,cached_sha256='4'*64,cached_mode='generic',
        server_sql_sha256='5'*64,parameter_types_sha256='6'*64,generic_plans=5,custom_plans=5)
        for v in ('C0','C1')})


def test_protocol_is_immutable_and_production_still_exact_c0():
    assert hashlib.sha256(Path(c.PROTOCOL).read_bytes()).hexdigest() == c.PROTOCOL_HASH
    source = Path('backend/app/services/data_publication.py').read_bytes()
    assert hashlib.sha256(source).hexdigest() == c.C0_SOURCE
    for filename in ('scripts/a4232_stability_contract.py','scripts/a4232_plan_probe.py',
                     'scripts/publication_tail_stability_a4232.py'):
        tree = ast.parse(Path(filename).read_text())
        assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
            and n.func.attr in ('collect','disable','enable','set_threshold')
            for n in ast.walk(tree))


def test_four_process_fixed_order_is_balanced_without_extra_samples():
    for block in range(4):
        rows = c.schedule(block)
        assert len(rows) == 32
        assert Counter((v,m) for _,_,v,m in rows) == dict.fromkeys(
            [('C0','full'),('C1','full'),('C0','minimal'),('C1','minimal')],8)
        assert rows == c.schedule(block % 2)
    assert sum(len(c.schedule(b)) for b in range(4)) == 128


@pytest.mark.parametrize('block', [-1,4,None,True,'0'])
def test_unregistered_block_rejected(block):
    with pytest.raises(ValueError,match='UNREGISTERED_BLOCK'):
        c.schedule(block)


@pytest.mark.parametrize('field', ['reltuples','relpages','last_analyze','last_autoanalyze',
                                  'statistic_sha256','reloptions'])
def test_same_data_snapshot_does_not_hide_planner_statistics_drift(field):
    before,after = statistics_snapshot(),statistics_snapshot()
    after['relations'][0][field] = {'reltuples':101,'relpages':3,'last_analyze':'changed',
        'last_autoanalyze':'changed','statistic_sha256':'9'*64,'reloptions':['changed']}[field]
    with pytest.raises(ValueError,match='ENVIRONMENT_DRIFT') as error:
        c.assert_stable(before,after)
    assert error.value.a4232_drift['after'] == after


@pytest.mark.parametrize('field', ['relations','settings','planner_settings','index_sha256'])
def test_missing_statistics_cannot_mean_stable(field):
    value = statistics_snapshot()
    del value[field]
    with pytest.raises(ValueError,match='STATISTICS_MISSING'):
        c.stable_identity(value)


def test_observation_timestamp_is_not_statistical_identity():
    before,after = statistics_snapshot(),statistics_snapshot()
    after['observed_at'] = 'later'
    c.assert_stable(before,after)


def test_missing_plan_or_bind_expression_cannot_be_exported():
    raw = {'Node Type':'Index Scan','Relation Name':'data_publication_row',
           'Filter':"secret-bind-value",'Index Cond':'secret-bind-value',
           'Output':['secret-bind-value'],'Actual Total Time':42,'Plans':[{'Node Type':'Result'}]}
    safe = c.plan_structure(raw)
    assert safe == {'Node Type':'Index Scan','Relation Name':'data_publication_row',
                    'Plans':[{'Node Type':'Result'}]}
    assert 'secret' not in json.dumps(safe)
    with pytest.raises(ValueError,match='PLAN_MISSING'):
        c.plan_structure({})
    with pytest.raises(ValueError,match='UNSAFE_PLAN_LABEL'):
        c.plan_structure({'Node Type':"literal 'untrusted'"})


@pytest.mark.parametrize('field', ['fresh_sha256','cached_sha256','cached_mode',
                                  'server_sql_sha256','parameter_types_sha256'])
def test_plan_dimensions_checked_even_when_data_statistics_match(field):
    before,after = plan_snapshot(),plan_snapshot()
    after['variants']['C1'][field] = 'changed'
    with pytest.raises(ValueError,match='ENVIRONMENT_DRIFT'):
        plans.assert_plans(before,after)


def test_natural_prepared_counter_growth_is_not_a_plan_change():
    before,after = plan_snapshot(),plan_snapshot()
    after['variants']['C1']['generic_plans'] += 4
    plans.assert_plans(before,after)


@pytest.mark.parametrize('part', ['public','candidate'])
def test_same_total_wrong_per_table_counts_are_rejected(part):
    value = dict(public=dict(c.PUBLIC),candidate=dict(c.CANDIDATE))
    c.assert_counts(value)
    value[part]['stock_trade_status_daily'] -= 1
    value[part]['stock_factor_daily'] += 1
    with pytest.raises(ValueError,match='COUNT_DRIFT'):
        c.assert_counts(value)


@pytest.mark.parametrize('unstable', [False,True])
def test_only_before_sampling_owned_table_fallback_is_bounded(monkeypatch,unstable):
    sql,proofs = [],[]
    db = SimpleNamespace(execute=lambda s:sql.append(str(s)),commit=lambda:None)
    monkeypatch.setattr(c,'owned',lambda db,name:proofs.append(name))
    monkeypatch.setattr(c,'sleep',lambda seconds:None)
    states = [statistics_snapshot() for _ in range(8)]
    if unstable:
        states[1]['relations'][0]['last_autoanalyze'] = 'unexpected'
        for s in states[4:]:
            for row in s['relations']:
                row['reloptions'] = ['autovacuum_enabled=false']
    iterator = iter(states)
    result = c.stabilize(db,'owned-test',lambda:next(iterator))
    assert len(proofs) == (2 if unstable else 1)
    assert len(result['attempts']) == len(proofs)
    assert len([s for s in sql if s.startswith('ALTER TABLE')]) == (4 if unstable else 0)
    assert all('ALTER SYSTEM' not in s and 'SET autovacuum' not in s for s in sql)
    assert all(a['measured_samples'] == 0 for a in result['attempts'])


def test_both_preflight_attempts_unstable_stop_without_a_third_try(monkeypatch):
    monkeypatch.setattr(c,'owned',lambda *a:None)
    monkeypatch.setattr(c,'sleep',lambda seconds:None)
    states = [statistics_snapshot() for _ in range(8)]
    for i,s in enumerate(states):
        s['relations'][0]['reltuples'] = i
    db = SimpleNamespace(execute=lambda s:None,commit=lambda:None)
    iterator = iter(states)
    with pytest.raises(ValueError,match='ENVIRONMENT_DRIFT') as error:
        c.stabilize(db,'synthetic',lambda:next(iterator))
    assert len(error.value.a4232_drift['preflight_attempts']) == 2


def test_physical_failure_prevents_any_statistics_ddl(monkeypatch):
    calls = []
    def invalid():
        raise RuntimeError('V14_PHYSICAL_INSTANCE_ID_MISMATCH')
    monkeypatch.setattr(c,'isolation',invalid)
    with pytest.raises(RuntimeError,match='PHYSICAL_INSTANCE'):
        c.owned(SimpleNamespace(scalar=lambda x:calls.append(str(x))),'v14_'+'1'*32+'_test')
    assert calls == []


def test_passive_callback_failure_is_not_silently_ignored(monkeypatch):
    from scripts import a4231_attribution_metrics as original

    before = list(gc.callbacks),gc.isenabled(),gc.get_threshold()
    def invalid_labels():
        raise RuntimeError('canned-callback-failure')
    monkeypatch.setattr(original,'function_labels',invalid_labels)
    observer = c.PassiveGC()
    with pytest.raises(ValueError,match='GC_CALLBACK_FAILED'):
        with observer:
            observer.callback('start',dict(generation=2))
            observer.callback('stop',dict(generation=2,collected=0,uncollectable=0))
    assert observer.callback_error == 'RuntimeError'
    assert (list(gc.callbacks),gc.isenabled(),gc.get_threshold()) == before


@pytest.mark.parametrize('generation', [0,1,2])
def test_all_gc_generations_preserved_without_policy_changes(generation):
    before = list(gc.callbacks),gc.isenabled(),gc.get_threshold()
    with c.PassiveGC() as observer:
        observer.callback('start',dict(generation=generation))
        observer.callback('stop',dict(generation=generation,collected=7,uncollectable=0))
    assert any(e['generation'] == generation and e['collected'] == 7 for e in observer.events)
    assert (list(gc.callbacks),gc.isenabled(),gc.get_threshold()) == before


@pytest.mark.parametrize('failure_point', ['none','init','enter','body','exit'])
def test_observer_partial_initialization_and_exit_cleanup(monkeypatch,failure_point):
    from scripts import ab_read_resources_v14_a4_2 as resources

    calls = []
    class Observer:
        def __init__(self,*a,**kw):
            self.engine = SimpleNamespace(dispose=lambda:calls.append('dispose'))
            if failure_point == 'init':
                raise RuntimeError('canned-init')
        def __enter__(self):
            if failure_point == 'enter':
                raise RuntimeError('canned-enter')
        def __exit__(self,*args):
            if failure_point == 'exit':
                raise RuntimeError('canned-exit')
            self.engine.dispose()
    monkeypatch.setattr(resources,'Telemetry',Observer)
    if failure_point == 'none':
        with runner.observer_scope(object(),1,'full'):
            pass
    else:
        with pytest.raises(RuntimeError):
            with runner.observer_scope(object(),1,'full'):
                if failure_point == 'body':
                    raise RuntimeError('canned-body')
    assert calls == ['dispose']
    calls.clear()
    with runner.observer_scope(object(),1,'minimal') as observer:
        assert observer is None
    assert calls == []


def test_128_collected_samples_do_not_override_environment_drift_or_expose_messages():
    value = dict(samples=[{}]*128,capacity_ready=False)
    error = ValueError('A4232_ENVIRONMENT_DRIFT')
    error.a4232_drift = {'block':3,'field':'last_autoanalyze'}
    runner.remember(value,error)
    assert value['status'] == 'INCOMPLETE_ENVIRONMENT_DRIFT' and len(value['samples']) == 128
    assert value['capacity_ready'] is False
    first = value['first_failure']
    runner.remember(value,RuntimeError('SECRET_DONT_EXPORT'))
    assert value['first_failure'] == first and 'SECRET' not in json.dumps(value)


def test_h3_screen_is_not_automatic_causal_admission():
    samples = []
    for block in range(4):
        for r,p,v,m in c.schedule(block):
            samples.append(dict(block=block,round=r,position=p,variant=v,observer_mode=m,
                wall_seconds=.2 if m == 'full' else .05,
                memory_before_enter={'allocated_blocks':0},
                memory_after_enter={'allocated_blocks':100 if m == 'full' else 1},
                gc_events=[dict(generation=2,seconds=.06,fully_inside_wall=True)] if m == 'full'
                          else []))
    checks = c.causal_checks(samples)
    assert checks['all_met'] and len(checks['checks']) == 8
    assert checks['conclusion'].startswith('REQUIRES_COUNTEREXAMPLE')
    for s in samples:
        if s['block'] == 2:
            s['gc_events'] = []
    assert c.causal_checks(samples)['all_met'] is False


def test_sanitized_junit_never_exports_arbitrary_failure_sql(tmp_path):
    path = tmp_path/'tests.xml'
    path.write_text('<testsuites><testsuite tests="1" failures="1" errors="0" skipped="0">'
                    '<testcase><failure message="SECRET_DONT_EXPORT">SQL private</failure>'
                    '</testcase></testsuite></testsuites>')
    output = receipt(path)
    assert output['status'] == 'INCOMPLETE' and output['counts']['failures'] == 1
    assert 'SECRET' not in json.dumps(output) and 'SQL private' not in json.dumps(output)


def test_once_workflow_is_independent_and_preserves_original_release_gate():
    path = Path('.github/workflows/a4232-statistics-tail-diagnostic.yml')
    jobs = yaml.safe_load(path.read_text())['jobs']
    assert set(jobs) == {'authorize','contracts','attribution'}
    assert jobs['attribution']['needs'] == ['authorize','contracts']
    assert jobs['attribution']['timeout-minutes'] == 30
    assert 'github.run_attempt == 1' in jobs['attribution']['if']
    assert '[a4232-statstable-once]' in jobs['attribution']['if']
    assert "github.event_name == 'workflow_dispatch'" in jobs['attribution']['if']
    assert 'inputs.confirm_expensive_run == true' in jobs['attribution']['if']
    assert jobs['authorize']['environment'] == 'a4-expensive-measurements'
    assert 'outputs' not in jobs['attribution']
    current = Path('.github/workflows/ci.yml').read_text()
    assert 'a4232' not in current


@pytest.mark.parametrize('attempt', ['2','local'])
def test_repeated_attempt_refused_before_configuration_or_ddl(monkeypatch,attempt):
    monkeypatch.setenv('GITHUB_ACTIONS','true')
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT',attempt)
    with pytest.raises(ValueError,match='ONE_CI_ATTEMPT_ONLY'):
        c.guard()


def complete_child():
    marker,system = '00000000-0000-0000-0000-000000000001','123456'
    parent = dict(head_sha='a'*40,run_id='1',attempt='1',model_hash=c.MODEL_HASH,
        protocol_sha256=c.PROTOCOL_HASH,measurement_version=c.VERSION,
        database_instance=marker,physical_system_identifier=system,
        production_source_sha256=c.C0_SOURCE,postgres_version='17.11',
        isolation=dict(before_ddl=True,verified=True,expected_marker=marker,observed_marker=marker,
            expected_system_identifier=system,observed_system_identifier=system))
    stats,plan = statistics_snapshot(),plan_snapshot()
    config = dict(block=0,snapshot='00000003-0000001A-1',statistics_identity=stats)
    point = dict(statistics=stats,plans=plan)
    ph = runner.digest(plans.plan_identity(plan))
    child = dict(**parent,status='COMPLETE',working_tree_dirty=False,block=0,process_pid=123,
        capacity_ready=False,performance_eligible=False,production_matches_candidate=False,
        unique_repair_candidate=None,p2='NOT_AUTHORIZED',p3='NOT_AUTHORIZED',
        parent_snapshot_sha256=runner.digest(config['snapshot']),
        input_key_sha256=runner.INPUT_HASHES[c.CONTROL],statistics_before_warmup=stats,
        initial_snapshot=point,final_snapshot=point,
        round_checks=[dict(round=r,before=point,after=point) for r in range(8)],
        warmups=[dict(variant=v,keys=2000,observer_mode='none') for v in ('C0','C1')*4],
        samples=[dict(round=r,position=p,variant=v,observer_mode=m,statistics='analyzed_stable',
            block=0,keys=2000,batch_size=500,golden='PASS',process_pid=123,
            wall_seconds=.1,client_cpu_seconds=.05,metrics=dict(execute_seconds=.01,
                python_json_seconds=.01,buffered_row_materialization_seconds=.02,gc_seconds=0),
            gc_events=[],batch_seconds=[.025]*4,round_plan_before=ph,round_plan_after=ph)
            for r,p,v,m in c.schedule(0)])
    return child,parent,config


def test_complete_child_rejects_no_valid_evidence():
    child,parent,config = complete_child()
    runner.validate_child(child,parent,config)


@pytest.mark.parametrize('problem', ['head','run','attempt','model','dirty','capacity','production',
    'candidate','keys','snapshot','missing','duplicate','order','batch','nan','gc','round_order',
    'missing_plan','forged_plan','statistic','warmups'])
def test_child_receipt_fail_closed_for_incomplete_or_forged_evidence(problem):
    child,parent,config = complete_child()
    child = copy.deepcopy(child)
    changes = dict(head='head_sha',run='run_id',attempt='attempt',model='model_hash')
    if problem in changes:
        child[changes[problem]] = 'wrong'
    elif problem in ('dirty','capacity','production'):
        child[dict(dirty='working_tree_dirty',capacity='capacity_ready',
                   production='production_matches_candidate')[problem]] = True
    elif problem == 'candidate':
        child['unique_repair_candidate'] = 'not-authorized'
    elif problem == 'keys':
        child['input_key_sha256'] = 'wrong'
    elif problem == 'snapshot':
        child['parent_snapshot_sha256'] = 'wrong'
    elif problem == 'missing':
        child['samples'].pop()
    elif problem == 'duplicate':
        child['samples'][1] = child['samples'][0]
    elif problem == 'order':
        child['samples'].reverse()
    elif problem == 'batch':
        child['samples'][0]['batch_size'] = 100
    elif problem == 'nan':
        child['samples'][0]['wall_seconds'] = float('nan')
    elif problem == 'gc':
        child['samples'][0]['gc_events'] = [dict(generation=3,seconds=.1,fully_inside_wall=True)]
    elif problem == 'round_order':
        child['round_checks'].reverse()
    elif problem == 'missing_plan':
        child['round_checks'][0]['after']['plans'] = {'variants':{}}
    elif problem == 'forged_plan':
        for row in child['samples']:
            row['round_plan_before'] = row['round_plan_after'] = 'f'*64
    elif problem == 'statistic':
        child['statistics_before_warmup']['relations'][0]['last_autoanalyze'] = 'changed'
    else:
        child['warmups'].append(child['warmups'][0])
    with pytest.raises((ValueError,KeyError,TypeError)):
        runner.validate_child(child,parent,config)


def test_timeout_terminates_only_just_spawned_process_and_does_not_retry(monkeypatch,tmp_path):
    actions = []
    process = SimpleNamespace(pid=54321,poll=lambda:None,wait=lambda timeout:actions.append('wait'))
    def timed_out(timeout):
        raise subprocess.TimeoutExpired('synthetic-child',timeout)
    process.communicate = timed_out
    monkeypatch.setattr(runner.subprocess,'Popen',lambda *a,**kw:process)
    monkeypatch.setattr(runner.os,'killpg',lambda pid,sig:actions.append((pid,sig)))
    with pytest.raises(subprocess.TimeoutExpired):
        runner.launch({'synthetic':True},tmp_path/'outputs'/'child.json','not-a-real-url')
    assert actions == [(54321,runner.signal.SIGTERM),'wait']


def test_driver_parameter_order_is_explicit_not_bind_data():
    server,driver,order = plans.parameterize('WITH input_keys AS (:keys) SELECT :publication,'
                                            ':table_name,:publication')
    assert server == 'WITH input_keys AS ($1) SELECT $2,$3,$2'
    assert order == ['keys','publication','table_name']
    assert '%(keys)s' in driver and 'value' not in driver


def test_new_unit_and_pg17_modules_have_distinct_names_for_pytest_collection():
    names = [p.name for folder in ('tests/unit','tests/integration')
             for p in Path(folder).glob('test_*a4232.py')]
    assert len(names) == len(set(names)) == 2


def test_failure_metadata_keeps_driver_class_and_state_not_message_or_sql():
    from scripts.a4232_pytest_receipt import safe_exception

    error = RuntimeError('SECRET_DONT_EXPORT and SQL')
    error.a4232_driver_type = 'UndefinedFunction'
    error.a4232_sqlstate = '42883'
    value = safe_exception(error)
    assert value['sqlstate'] == '42883' and value['driver_type'] == 'UndefinedFunction'
    assert 'SECRET' not in json.dumps(value) and ' SQL' not in json.dumps(value)


def test_context_manager_cleanup_does_not_replace_first_failure():
    try:
        try:
            raise RuntimeError('SECRET_FIRST')
        except RuntimeError:
            raise ValueError('SECRET_TERMINAL') from None
    except ValueError as error:
        output = {}
        runner.remember(output,error)
    assert output['first_failure']['failure_type'] == 'RuntimeError'
    assert output['terminal_failure']['failure_type'] == 'ValueError'
    assert 'SECRET' not in json.dumps(output)


def test_offline_review_rejects_wrong_source_before_reading_archive(tmp_path):
    from scripts.publication_tail_stability_review_a4232 import review

    with pytest.raises(ValueError,match='MANIFEST_IDENTITY_MISMATCH'):
        review(tmp_path/'not-read.zip',dict(source_sha='wrong'))


def test_offline_review_rejects_wrong_zip_digest(tmp_path):
    from scripts import publication_tail_stability_review_a4232 as offline

    path = tmp_path/'wrong.zip'
    path.write_bytes(b'not-the-source-archive')
    manifest = dict(source_sha=offline.SOURCE_SHA,run_id=offline.SOURCE_RUN,attempt=1,
                    artifact_id=1,zip_sha256='0'*64)
    with pytest.raises(ValueError,match='ZIP_DIGEST_MISMATCH'):
        offline.review(path,manifest)


def test_partial_receipt_cannot_become_zero_latency_or_stable_evidence(tmp_path):
    from scripts import publication_tail_stability_review_a4232 as offline

    path = tmp_path/'partial.zip'
    value = dict(head_sha=offline.SOURCE_SHA,run_id=offline.SOURCE_RUN,attempt='1',
        status='INCOMPLETE_ENVIRONMENT_DRIFT',samples=[],first_failure={'failure_type':'ValueError'},
        capacity_ready=False,performance_eligible=False,production_matches_candidate=False,
        production_read_authorized=False,unique_repair_candidate=None,
        p2='NOT_AUTHORIZED',p3='NOT_AUTHORIZED',model_hash=c.MODEL_HASH,working_tree_dirty=False,
        protocol_sha256=c.PROTOCOL_HASH,measurement_version=c.VERSION,
        production_source_sha256=c.C0_SOURCE,proposed_source_sha256=c.C1_SOURCE)
    with ZipFile(path,'w') as z:
        z.writestr('attribution.json',json.dumps(value))
    manifest = dict(source_sha=offline.SOURCE_SHA,run_id=offline.SOURCE_RUN,attempt=1,
        artifact_id=1,zip_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    report = offline.review(path,manifest)
    assert report['collection_status'] == 'INCOMPLETE_ENVIRONMENT_DRIFT'
    assert report['statistics_plan_status'] == 'NOT_VERIFIED'
    assert report['sample_count'] == 0 and report['summary'] == []
    assert report['root_cause'] == 'INSUFFICIENT_EVIDENCE'
    assert report['unique_repair_candidate'] is None and report['capacity_ready'] is False


def test_offline_plan_replay_rejects_bind_expressions_even_with_matching_hash():
    from scripts.publication_tail_stability_review_a4232 import validate_plan_hashes

    node = {'Node Type':'Result','Filter':'PRIVATE_BIND_DONT_EXPORT'}
    value = dict(variants={'C0':dict(fresh_structure=node,fresh_sha256=runner.digest(node))})
    with pytest.raises(ValueError,match='PLAN_HASH_MISMATCH'):
        validate_plan_hashes(value)


def test_background_worker_guard_fails_even_without_any_relation_statistics_change():
    before,after = statistics_snapshot(),statistics_snapshot()
    after['active_autovacuum_workers'] = 1
    assert before['relations'] == after['relations']
    with pytest.raises(ValueError,match='ENVIRONMENT_DRIFT') as error:
        c.assert_stable(before,after)
    assert error.value.a4232_drift['after']['active_autovacuum_workers'] == 1


def test_real_review_keeps_64_samples_and_distinguishes_activity_from_analyze_drift():
    data = json.loads(Path('docs/acceptance/evidence/a4232_stability_review.json').read_text())
    assert data['sample_count'] == data['uncollected_samples'] == 64
    assert data['planned_samples'] == 128 and data['excluded_samples'] == 0
    audit = data['field_audit']
    assert audit['parent_validated_samples'] == 32 and audit['missing_plan_brackets'] == 4
    assert audit['recorded_plan_snapshots'] == 34
    assert audit['relation_field_changes'] == audit['plan_identity_changes'] == []
    assert len(audit['background_activity_changes']) == 1
    assert audit['background_activity_changes'][0]['field'] == 'active_autovacuum_workers'
    assert data['root_cause'] == 'INSUFFICIENT_EVIDENCE'
    assert data['statistics_plan_status'] == 'NOT_VERIFIED' and data['h3_checks'] is None
    assert len(data['generation2_events']) == 8
    assert data['unique_repair_candidate'] is None and data['capacity_ready'] is False
