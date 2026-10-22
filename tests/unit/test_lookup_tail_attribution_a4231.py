"""Pure diagnostic contract controls; never benchmark numbers or business settings."""

import ast
import copy
import gc
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import a4231_attribution_metrics as metrics
from scripts import publication_lookup_tail_attribution_a4231 as runner
from scripts.a42_receipt_contract import ReceiptError


def test_frozen_schedule_is_balanced_for_both_sql_and_observer_modes():
    for block in (0, 1):
        rows = metrics.schedule(block)
        assert len(rows) == 32
        assert Counter((v, m) for _, _, v, m in rows) == {
            condition:8 for condition in metrics.CONDITIONS}
        assert Counter(position for _, position, _, _ in rows) == dict.fromkeys(range(4), 8)
        for round_ in range(8):
            sequence = [metrics.CONDITIONS.index((v, m)) for r, _, v, m in rows if r == round_]
            expected = metrics.WILLIAMS[round_ % 4]
            assert sequence == list(expected if block == 0 else reversed(expected))
    with pytest.raises(ReceiptError):
        metrics.schedule(2)


@pytest.mark.parametrize('raise_error', [False, True])
def test_natural_gc_records_generation_and_cleans_up_on_error(monkeypatch, raise_error):
    original = list(gc.callbacks), gc.isenabled(), gc.get_threshold()
    with pytest.raises(RuntimeError) if raise_error else __import__('contextlib').nullcontext():
        with metrics.NaturalGC() as observer:
            observer.phase = 'lookup_wall'
            observer.callback('start', dict(generation=2))
            observer.callback('stop', dict(generation=2, collected=13, uncollectable=0))
            if raise_error:
                raise RuntimeError('synthetic')
    assert (list(gc.callbacks), gc.isenabled(), gc.get_threshold()) == original
    event = next(e for e in observer.events if e['collected'] == 13)
    assert event['generation'] == 2 and event['seconds'] >= 0
    assert event['phase'] == 'lookup_wall'
    assert observer.wall_events(0, float('inf'))[0]['fully_inside_wall']


def test_gc_overflow_is_explicit_incomplete_not_silent_truncation():
    observer = metrics.NaturalGC()
    # Simulated events without registering a callback: no forced real collection.
    for _ in range(257):
        observer.callback('start', dict(generation=0))
        observer.callback('stop', dict(generation=0, collected=0, uncollectable=0))
    assert len(observer.events) == 256 and observer.overflow == 1
    with pytest.raises(ReceiptError, match='GC_EVENTS_INCOMPLETE'), observer:
        pass
    assert observer.registered is None


def test_gc_is_nested_and_wall_boundary_not_subtracted():
    observer = metrics.NaturalGC()
    observer.events = [dict(started=1.0, ended=1.2, seconds=.2, generation=2)]
    assert observer.wall_events(0, 2)[0]['fully_inside_wall']
    assert not observer.wall_events(1.1, 2)[0]['fully_inside_wall']
    assert observer.events[0]['seconds'] == .2


def test_even_mechanistic_screen_pass_never_automatically_claims_causality_or_admission():
    rows = []
    for regime in metrics.REGIMES:
        for block in (0, 1):
            for round_, position, variant, mode in metrics.schedule(block):
                rows.append(dict(statistics=regime, block=block, round=round_, position=position,
                    variant=variant, observer_mode=mode, wall_seconds=.2 if mode == 'full' else .06,
                    memory_before_enter={'allocated_blocks':0},
                    memory_after_enter={'allocated_blocks':100 if mode == 'full' else 1},
                    gc_events=[dict(seconds=.06, generation=2, fully_inside_wall=True)]
                              if mode == 'full' else []))
    result = metrics.telemetry_checks(rows)
    assert result['all_preregistered_conditions_met']
    assert len(result['checks']) == 8
    assert 'REQUIRES_MECHANISM' in result['conclusion']
    assert 'capacity_ready' not in result
    rows[0]['gc_events'].clear()
    # A whole block without the required mechanism cannot pass the screen.
    for row in rows:
        if row['statistics'] == 'as_seeded' and row['block'] == 0:
            row['gc_events'].clear()
    assert not metrics.telemetry_checks(rows)['all_preregistered_conditions_met']


@pytest.mark.parametrize('variant', ['C0', 'C1'])
@pytest.mark.parametrize('mode', ['full', 'minimal'])
@pytest.mark.parametrize('fail', [False, True])
def test_observer_intervention_preserves_same_workload_and_exception_cleanup(monkeypatch,
                                                                          variant, mode, fail):
    from scripts import ab_read_resources_v14_a4_2 as resources

    calls = []
    class Observer:
        def __init__(self, *args, **kwargs):
            calls.append('construct')
        def __enter__(self):
            calls.append('enter')
            return self
        def __exit__(self, *error):
            calls.append('exit')
        def receipt(self):
            return {'synthetic_unit_only':True}
    def workload(ws, model, inputs, selected, values):
        calls.append(('lookup', len(inputs), selected, id(values)))
        if fail:
            raise RuntimeError('synthetic')
        return ({}, {}, None), [.01]*4
    monkeypatch.setattr(resources, 'Telemetry', Observer)
    monkeypatch.setattr(runner.lab, 'workload', workload)
    monkeypatch.setattr(runner.lab, 'db_snapshot', lambda db:{'synthetic':True})
    monkeypatch.setattr(runner.lab, 'backend_snapshot', lambda *a:{'cpu_seconds':0})
    monkeypatch.setattr(runner, 'observer_wait', lambda *a:{'blockers':0})
    monkeypatch.setattr(runner, 'memory_state', lambda:{'allocated_blocks':0})
    inputs, before = [{}]*2000, list(gc.callbacks)
    args = (SimpleNamespace(db=object()), object(), inputs, variant, mode, object(), 42,
            object(), 'synthetic-container-not-executed')
    if fail:
        with pytest.raises(RuntimeError, match='synthetic'):
            runner.run_sample(*args)
    else:
        _, sample = runner.run_sample(*args)
        assert sample['keys'] == 2000 and sample['batch_size'] == 500
        assert sample['wall_seconds'] == sample['wall_ended']-sample['wall_started']
    assert len([c for c in calls if isinstance(c, tuple)]) == 1
    assert ('construct' in calls) is (mode == 'full')
    assert ('exit' in calls) is (mode == 'full')
    assert gc.callbacks == before


def child_receipt():
    marker = '00000000-0000-0000-0000-000000000042'
    parent = dict(head_sha='a'*40, run_id='synthetic-unit', attempt='1', model_hash='b'*64,
        protocol_sha256=runner.PROTOCOL_SHA256, physical_system_identifier='42',
        database_instance=marker, production_source_sha256=runner.C0_SOURCE)
    config = dict(snapshot='00000003-0000001B-1', statistics='as_seeded', block=0)
    value = dict(**parent, working_tree_dirty=False, status='COMPLETE', capacity_ready=False,
        performance_eligible=False, p2='NOT_AUTHORIZED', p3='NOT_AUTHORIZED',
        input_key_sha256=runner.INPUT_HASHES[runner.CONTROL],
        parent_snapshot_sha256=runner.digest(config['snapshot']),
        measurement_version=runner.VERSION,
        sql_template_sha256={'C0':'c'*64, 'C1':'d'*64}, postgres_version='17.11',
        isolation=dict(verified=True, before_ddl=True,
            expected_marker=marker, observed_marker=marker,
            expected_system_identifier='42', observed_system_identifier='42'), process_pid=42)
    value['samples'] = [dict(round=r, position=p, variant=v, observer_mode=m, keys=2000,
        batch_size=500, golden='PASS', statistics='as_seeded', block=0, process_pid=42,
        wall_seconds=.1, client_cpu_seconds=.05, batch_seconds=[.025]*4, gc_events=[],
        metrics=dict(execute_seconds=.04, python_json_seconds=.01,
                     buffered_row_materialization_seconds=.02))
        for r, p, v, m in metrics.schedule(0)]
    return value, parent, config


def test_complete_diagnostic_cohort_still_cannot_authorize_capacity():
    value, parent, config = child_receipt()
    runner.validate_child(value, parent, config)
    assert value['capacity_ready'] is False and value['p2'] == value['p3'] == 'NOT_AUTHORIZED'


@pytest.mark.parametrize('damage', ['missing', 'duplicate', 'order', 'sha', 'run', 'attempt',
    'dirty', 'incomplete', 'ready', 'performance', 'snapshot', 'keys', 'batch', 'golden', 'nan',
    'metric', 'gc', 'sql', 'version'])
def test_missing_mixed_or_unauthorized_diagnostics_fail_closed(damage):
    value, parent, config = child_receipt()
    if damage == 'missing':
        value['samples'].pop()
    elif damage == 'duplicate':
        value['samples'][-1] = copy.deepcopy(value['samples'][-2])
    elif damage == 'order':
        value['samples'][:2] = reversed(value['samples'][:2])
    elif damage in ('sha', 'run', 'attempt'):
        value[{'sha':'head_sha', 'run':'run_id', 'attempt':'attempt'}[damage]] = 'other'
    elif damage == 'dirty':
        value['working_tree_dirty'] = True
    elif damage == 'incomplete':
        value['status'] = 'INCOMPLETE'
    elif damage in ('ready', 'performance'):
        value['capacity_ready' if damage == 'ready' else 'performance_eligible'] = True
    elif damage == 'snapshot':
        value['parent_snapshot_sha256'] = 'other'
    elif damage in ('keys', 'batch'):
        value['samples'][0]['keys' if damage == 'keys' else 'batch_size'] = 1
    elif damage == 'golden':
        value['samples'][0]['golden'] = 'FAIL'
    elif damage == 'nan':
        value['samples'][0]['wall_seconds'] = float('nan')
    elif damage == 'metric':
        value['samples'][0]['metrics'].pop('execute_seconds')
    elif damage == 'gc':
        value['samples'][0]['gc_events'] = [dict(generation=9, seconds=.01, fully_inside_wall=True)]
    elif damage == 'sql':
        value['sql_template_sha256'].clear()
    else:
        value['measurement_version'] = 'old-or-different-timing'
    with pytest.raises(ReceiptError):
        runner.validate_child(value, parent, config)


@pytest.mark.parametrize('snapshot', ['bad quote\' ; SELECT private', '', 'x'*100, None])
def test_snapshot_identifier_rejected_before_any_statement(snapshot):
    class NoSQL:
        def connection(self, **kwargs):
            pytest.fail('invalid identifier reached database')
    with pytest.raises(ReceiptError):
        runner.import_snapshot(NoSQL(), snapshot)


def test_snapshot_import_exactly_preserves_readonly_rr_and_300s_before_first_query():
    calls = []
    class DB:
        def connection(self, **kwargs):
            calls.append(('connection', kwargs))
        def execute(self, statement):
            calls.append(statement.text)
    runner.import_snapshot(DB(), '00000003-0000001B-1')
    assert calls == [('connection', {'execution_options':{'isolation_level':'REPEATABLE READ'}}),
        'SET TRANSACTION READ ONLY', "SET TRANSACTION SNAPSHOT '00000003-0000001B-1'",
        "SET LOCAL statement_timeout='300s'"]


@pytest.mark.parametrize('actions,attempt', [('false', '1'), ('true', '2'), ('true', 'local-1')])
def test_guard_refuses_non_ci_and_repeated_attempt_before_settings_or_sql(monkeypatch,
                                                                       actions, attempt):
    monkeypatch.setenv('GITHUB_ACTIONS', actions)
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT', attempt)
    with pytest.raises(ReceiptError, match='ONE_CI_ATTEMPT_ONLY'):
        runner.guard()


def test_parent_interruption_stops_only_the_child_it_created_without_retry(tmp_path, monkeypatch):
    from scripts.a42_artifacts import BudgetExhausted

    calls = []
    class Process:
        pid = 12345
        def communicate(self, timeout):
            calls.append(('communicate', timeout))
            raise BudgetExhausted('RESOURCE_DEFERRED')
        def poll(self):
            return None
        def wait(self, timeout):
            calls.append(('wait', timeout))
            return 0
    def popen(*args, **kwargs):
        calls.append('spawn')
        return Process()
    monkeypatch.setattr(runner.subprocess, 'Popen', popen)
    monkeypatch.setattr(runner.os, 'killpg', lambda pid, sig:calls.append(('signal', pid, sig)))
    with pytest.raises(BudgetExhausted):
        runner.launch({'synthetic_no_credentials':True}, tmp_path/'out/child.json',
                      'synthetic-target-not-connected')
    assert calls.count('spawn') == 1
    assert ('communicate', 300) in calls and ('signal', 12345, runner.signal.SIGTERM) in calls


def test_child_partial_samples_survive_main_failure_and_no_private_message(tmp_path, monkeypatch):
    output, config = tmp_path/'result.json', tmp_path/'control.json'
    config.write_text('{}')
    monkeypatch.setattr(runner, 'guard', lambda:dict(status='INCOMPLETE', samples=[]))
    monkeypatch.setattr(runner, 'install_signals', lambda:None)
    def interrupted(config, receipt, path):
        receipt['samples'].append(dict(synthetic_unit_only=True))
        raise RuntimeError('PRIVATE_BIND_DO_NOT_EXPORT')
    monkeypatch.setattr(runner, 'child', interrupted)
    monkeypatch.setattr(runner.sys, 'argv', ['diagnostic', '--output', str(output),
                                          '--child-config', str(config)])
    with pytest.raises(SystemExit):
        runner.main()
    result = json.loads(output.read_text())
    assert result['status'] == 'INCOMPLETE' and len(result['samples']) == 1
    assert result['failure_type'] == 'RuntimeError' and result['capacity_ready'] is False
    assert 'PRIVATE_BIND' not in output.read_text()


def test_no_gc_policy_changes_and_no_release_authorization_edge():
    import hashlib

    import yaml

    for module in (metrics, runner):
        tree = ast.parse(Path(module.__file__).read_text())
        assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == 'gc'
            and n.func.attr in {'collect', 'disable', 'enable', 'set_threshold', 'set_debug'}
            for n in ast.walk(tree))
    assert hashlib.sha256(Path(runner.PROTOCOL).read_bytes()).hexdigest() == runner.PROTOCOL_SHA256
    jobs = yaml.safe_load(Path('.github/workflows/ci.yml').read_text())['jobs']
    job = jobs['lookup-tail-attribution']
    assert job['timeout-minutes'] == 30
    assert "github.run_attempt == 1" in job['if'] and '[a4231-attribution-once]' in job['if']
    assert 'outputs' not in job and 'lookup-tail-attribution' not in jobs[
        'publication-release-gate']['needs']
    assert jobs['capacity']['if'] == "needs.lookup-diagnosis.outputs.capacity_ready == 'true'"
