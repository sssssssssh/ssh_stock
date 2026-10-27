"""AT07/10-13/16/19-20: mock resource failures, immutable boundaries, exact CI whitelist."""

import ast
import copy
import importlib.util
import json
import subprocess
import sys
import warnings
from pathlib import Path

import pytest
import yaml

from scripts import a42341_calibration_guard as guard
from scripts import a42341_calibration_review as reviewer
from scripts import a42341_contract as c
from scripts.a42341_calibration_review import review
from scripts.a42341_calibration_runner import MockResources, MockWorkload, simulate

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def good():
    expected = c.identity()
    return expected, simulate(expected)


@pytest.mark.parametrize('field,bad', [('process_elapsed_ms', 0.0),
    ('process_rss_peak_bytes', None), ('cpu_scope', 'SUM_TICK_CPU_OVER_SQL_WALL'),
    ('rss_scope', 'OBSERVER_ONLY'), ('backend_scope', 'SQL_WALL'),
    ('backend_before', None), ('backend_status', 'NOT_AVAILABLE'),
    ('observer_thread_cpu_seconds', None), ('observer_worker_elapsed_ms', 0.0)])
def test_AT10_AT11_resource_missing_or_wrong_scope_rejected(good, field, bad):
    expected, original = good
    value = copy.deepcopy(original)
    value['samples'][1]['resources'][field] = bad
    with pytest.raises(c.Fault):
        review(c.seal(value), expected)


@pytest.mark.parametrize('field,bad', [('pid', 12345), ('backend_start', '2026-01-02T00:00:00Z'),
    ('process_start_ticks', 10001), ('clock_ticks', 1000), ('container_sha256', 'a' * 64),
    ('user_system_cpu_seconds', 10.0), ('observed_ns', 1000)])
def test_AT10_backend_lifecycle_pid_reuse_clock_units_zero_cpu_rejected(good, field, bad):
    expected, original = good
    value = copy.deepcopy(original)
    value['samples'][0]['resources']['backend_after'][field] = bad
    with pytest.raises(c.Fault):
        review(c.seal(value), expected)


@pytest.mark.parametrize('field', ['data_sha256', 'model_sha256', 'index_sha256',
    'statistics', 'sql_templates', 'fresh_plans', 'cached_plans', 'clock_domain_sha256'])
def test_AT12_environment_projection_drift_cannot_be_voted_away(good, field):
    expected, original = good
    value = copy.deepcopy(original)
    target = value['samples'][0]['environment_after']
    if isinstance(target[field], dict):
        target[field][next(iter(target[field]))] = 'a' * 64
    else:
        target[field] = 'a' * 64
    with pytest.raises(c.Fault, match='A42341_ENVIRONMENT_DRIFT'):
        review(c.seal(value), expected)


@pytest.mark.parametrize('field', ['head_sha', 'attempt', 'source_sha256', 'protocol_sha256',
    'manifest_sha256', 'old_source_sha256', 'model_sha256', 'input_sha256', 'dependency_sha256',
    'fixture_sha256', 'data_snapshot_sha256'])
def test_AT07_AT16_frozen_provenance_and_independent_attempt_binding(good, field):
    expected, original = good
    value = copy.deepcopy(original)
    bad = 999 if field == 'attempt' else 'a' * (40 if field == 'head_sha' else 64)
    if field == 'attempt':
        # Run/attempt are an external trusted context, not derivable from Git.
        # Change the untrusted artifact, never its independent expected context.
        value['identity'][field] = bad
    else:
        expected = expected.model_copy(update={field: bad})
        value['identity'] = expected.model_dump()
    with pytest.raises(c.Fault):
        review(c.seal(value), expected)


def test_AT10_missing_backend_or_rss_stops_with_last_incomplete_point(good):
    expected = good[0]
    for settings in (MockResources(backend_available=False), MockResources(rss_available=False)):
        value = simulate(expected, resources=settings)
        result = review(value, expected)
        assert result['calibration_decision'] == 'SIMULATED_REJECT'
        assert result['first_failure_code'] == 'A42341_METRIC_UNAVAILABLE'
        assert result['sample_count'] == 0 and result['failed_point']['partial_sample'] is not None


@pytest.mark.parametrize('option', ['--execute', '--approve', '--force', '--repeat', '--budget',
    '--token', '--profile', 'workflow_dispatch', '--check --force'])
def test_AT06_AT07_no_cli_or_environment_unlock(option, good, monkeypatch, capsys):
    monkeypatch.setenv('A42341_EXECUTION_ENABLED', 'true')
    monkeypatch.setenv('A42341_APPROVED', 'true')
    monkeypatch.setenv('A42341_TOKEN', 'SECRET_A42341_DSN')
    assert guard.main([option, 'SECRET_A42341_DSN']) == 1
    output = json.loads(capsys.readouterr().out)
    assert output['first_failure_code'] == 'A42341_EXECUTION_NOT_AUTHORIZED'
    assert 'SECRET_A42341_DSN' not in json.dumps(output)
    with pytest.raises(c.Fault, match='A42341_EXECUTION_NOT_AUTHORIZED'):
        guard.execute(approved=True, protocol_approved=True, token='unused', callback=lambda: 1)


def test_AT08_real_callbacks_and_mock_subclass_are_not_workload_adapters(good):
    class PretendReal(MockWorkload):
        def model_dump(self, *args, **kwargs):
            pytest.fail('not permitted to invoke a disguised real adapter')
    for workload in (lambda: pytest.fail('no real callback'), PretendReal(), object()):
        with pytest.raises(c.Fault, match='A42341_REAL_ADAPTER_FORBIDDEN'):
            simulate(good[0], workload=workload)


def test_AT16_malformed_mock_config_is_fixed_code_without_raw_input(good):
    workload = MockWorkload().model_copy(update={'off_wall_ms': 'SECRET_A42341_DSN'})
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter('always')
        with pytest.raises(c.Fault, match='A42341_MOCK_CONFIG_INVALID') as error:
            simulate(good[0], workload=workload)
    assert not captured
    assert 'SECRET_A42341_DSN' not in str(error.value)


def fake_repository(monkeypatch):
    actual = guard.git
    target = c.identity().head_sha
    def fake(root, *args, binary=False):
        if args[0] == 'rev-parse':
            return target
        if args[0] in ('status', 'diff'):
            return ''
        if args[0] == 'show':
            return (ROOT / args[1].removeprefix('HEAD:')).read_bytes()
        return actual(root, *args, binary=binary)
    monkeypatch.setattr(guard, 'git', fake)
    return target, fake


def test_AT07_clean_exact_environment_still_waits_for_two_human_gates(monkeypatch):
    target, _ = fake_repository(monkeypatch)
    value = guard.check_repository(ROOT, target)
    assert value['status'] == 'BLOCKED_NEEDS_USER_PROTOCOL_DECISION'
    assert value['protocol_gate'] == value['real_execution_gate'] == 'NOT_APPROVED'
    assert value['effective_warmups_total'] == 8 and value['proposed_warmups_total'] == 16


@pytest.mark.parametrize('problem', [
    'short', 'dirty', 'head', 'dependency', 'source', 'model', 'old'])
def test_AT07_source_head_dependency_and_dirty_tree_checks(monkeypatch, problem):
    target, original = fake_repository(monkeypatch)
    def fake(root, *args, binary=False):
        if problem == 'dirty' and args[0] == 'status':
            return ' M README.md'
        if problem == 'head' and args == ('rev-parse', 'origin/master'):
            return 'a' * 40
        if problem == 'source' and args[0] == 'show':
            return b'changed'
        if problem == 'model' and args[0] == 'ls-tree':
            return b'changed'
        if problem == 'old' and args[0] == 'diff':
            return 'scripts/a4234_calibration_guard.py'
        return original(root, *args, binary=binary)
    monkeypatch.setattr(guard, 'git', fake)
    if problem == 'dependency':
        monkeypatch.setattr(guard.importlib.metadata, 'version', lambda name: '0.0.0')
    with pytest.raises(c.Fault):
        guard.check_repository(ROOT, target[:12] if problem == 'short' else target)


def test_AT16_missing_junit_never_marks_toolchain_ready(tmp_path):
    value = guard.unit_receipt(tmp_path / 'missing.xml')
    assert value['unit_status'] == 'INCOMPLETE_CONTRACT'
    assert value['toolchain_status'] == 'INCOMPLETE' and not value['execution_enabled']


def test_AT16_path_traversal_and_symlink_parent_rejected(tmp_path):
    with pytest.raises(c.Fault):
        c.safe_path(tmp_path / 'child/../secret.json')
    real, link = tmp_path / 'real', tmp_path / 'link'
    real.mkdir()
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(c.Fault):
        c.write_new(link / 'output.json', {'value': 1})


def test_AT19_only_exact_new_offline_source_set_and_old_freezes():
    actual = {str(p.relative_to(ROOT)) for p in (ROOT / 'scripts').glob('a42341_*.py')}
    assert actual == set(c.SOURCES)
    for source in c.SOURCES:
        tree = ast.parse((ROOT / source).read_text())
        for n in ast.walk(tree):
            names = ([a.name for a in n.names] if isinstance(n, ast.Import)
                     else [n.module or ''] if isinstance(n, ast.ImportFrom) else [])
            assert not any(v.startswith(('app', 'psycopg', 'sqlalchemy', 'threading', 'gc',
                                         'multiprocessing', 'dotenv')) for v in names)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                assert n.func.attr not in ('connect', 'cursor', 'execute', 'disable', 'collect',
                    'set_threshold', 'Thread', 'Popen', 'spawn', 'workload')


def test_AT20_exact_ci_additions_no_other_workflow_or_old_step_change():
    path = '.github/workflows/a4233-observer-contracts.yml'
    before = yaml.safe_load(c.git(ROOT, 'show', c.BASELINE + ':' + path, binary=True))
    current = yaml.safe_load((ROOT / path).read_text())
    spec = importlib.util.spec_from_file_location('a42341_ci_whitelist',
        ROOT / 'tests/unit/test_a4234_ci_governance.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    additions = module.A42341_ADDITIONS
    assert c.digest(additions) == 'a0b73b261ca730fa9d056d3230a4c75373c2735068ca3f244e610db6ce0517dc'
    expected = copy.deepcopy(before)
    for event in expected['on'].values():
        event['paths'] += ['scripts/a42341_*.py', 'tests/**/test_a42341*.py',
                           'docs/acceptance/*a42341*']
    steps = expected['jobs']['contracts']['steps']
    index = next(i for i, s in enumerate(steps) if s.get('name') ==
                 'A4234 sanitized unit counts and static blocker (not calibration)')
    steps[index + 1:index + 1] = additions[:2]
    steps.append(additions[2])
    assert current == expected
    for name in ('ci.yml', 'ab-read-a4-baseline.yml', 'ab-read-a4-2.yml',
                 'publication-v13.yml', 'a4232-statistics-tail-diagnostic.yml'):
        assert (ROOT / '.github/workflows' / name).read_bytes() == c.git(
            ROOT, 'show', c.BASELINE + ':.github/workflows/' + name, binary=True)


def a42342_cli(directory, expected_file, *extra):
    import os

    env = dict(os.environ, PYTHONPATH=str(ROOT), LLM_ENABLED='false',
        DATABASE_URL='postgresql+psycopg://disabled:disabled@127.0.0.1:1/a42342_disabled_test',
        TEST_DATABASE_URL='postgresql+psycopg://disabled:disabled@127.0.0.1:1/a42342_disabled_test')
    result = subprocess.run([sys.executable, '-m', 'scripts.a42341_calibration_review',
        '--directory', str(directory), '--expected', str(expected_file), *extra],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=20, check=False)
    assert not result.stderr and len(result.stdout) < 4000
    assert 'SECRET_A42342_DSN' not in result.stdout
    assert str(directory) not in result.stdout and str(expected_file) not in result.stdout
    output = json.loads(result.stdout)
    assert output['authorization_status'] == 'NOT_RUN_NOT_AUTHORIZED'
    assert output['real_performance_eligible'] is False
    for name, value in c.Safety().model_dump().items():
        assert output[name] == value
    return result.returncode, output


@pytest.mark.parametrize('scenario,exit_code,decision', [
    ('accept', 2, 'SIMULATED_ACCEPT'), ('reject', 3, 'SIMULATED_REJECT'),
    ('incomplete', 3, 'SIMULATED_REJECT'),
])
def test_A42342_T13_T15_real_cli_mock_results_never_exit_zero(good, tmp_path,
                                                            scenario, exit_code, decision):
    expected = good[0]
    workload = (MockWorkload(on_wall_ms=70.0) if scenario == 'reject' else
        MockWorkload(fail_at=3, failure_code='A42341_SQL_TIMEOUT')
        if scenario == 'incomplete' else MockWorkload())
    data = simulate(expected, workload=workload)
    directory, expected_file = tmp_path / 'mock', tmp_path / 'independent.json'
    reviewer.write_bundle(directory, data, expected)
    c.write_new(expected_file, expected.model_dump())
    actual, output = a42342_cli(directory, expected_file)
    assert actual == exit_code and actual != 0
    assert output['mock_contract_validated'] is True
    assert output['simulated_threshold_decision'] == decision
    assert output['result'] == ('MOCK_VALID_SIMULATED_ACCEPT_NOT_AUTHORIZED'
        if scenario == 'accept' else 'MOCK_VALID_NOT_QUALIFIED')


@pytest.mark.parametrize('change', ['expected_head', 'expected_attempt', 'expected_run',
    'self_reported_expected', 'sample_head', 'sample_attempt', 'failure', 'manifest',
    'manifest_raw_error', 'missing', 'extra', 'symlink', 'traversal'])
def test_A42342_T16_T18_real_cli_corruption_and_wrong_identity_rejected(good, tmp_path, change):
    expected, data = good
    directory, expected_file = tmp_path / 'mock', tmp_path / 'independent.json'
    reviewer.write_bundle(directory, data, expected)
    c.write_new(expected_file, expected.model_dump())
    manifest = c.load(directory / 'manifest.json')
    modified = None
    if change.startswith('expected_'):
        value = expected.model_dump()
        field = change.removeprefix('expected_')
        key = {'head': 'head_sha', 'run': 'run_id', 'attempt': 'attempt'}[field]
        value[key] = 'a' * 40 if field == 'head' else '999999' if field == 'run' else 999
        expected_file.write_text(json.dumps(value))
    elif change == 'self_reported_expected':
        expected_file = directory / 'manifest.json'
    elif change in ('sample_head', 'sample_attempt'):
        modified = 'samples.json'
        value = c.load(directory / modified)
        value['identity']['head_sha' if change == 'sample_head' else 'attempt'] = (
            'a' * 40 if change == 'sample_head' else 999)
        (directory / modified).write_text(json.dumps(c.seal(value)))
    elif change == 'failure':
        modified = 'failure.json'
        value = c.load(directory / modified)
        value['first_failure_code'] = 'A42341_SQL_TIMEOUT'
        (directory / modified).write_text(json.dumps(value))
    elif change == 'manifest':
        manifest['identity']['attempt'] = 999
    elif change == 'manifest_raw_error':
        manifest['raw_error'] = 'SECRET_A42342_DSN'
    elif change == 'missing':
        (directory / 'failure.json').unlink()
    elif change == 'extra':
        (directory / 'extra.json').write_text('{}')
    elif change == 'symlink':
        target = tmp_path / 'outside.json'
        target.write_text('SECRET_A42342_DSN')
        (directory / 'samples.json').unlink()
        (directory / 'samples.json').symlink_to(target)
    else:
        manifest['files']['../outside.json'] = manifest['files'].pop('samples.json')
    if modified:
        path = directory / modified
        manifest['files'][modified] = dict(sha256=c.file_sha(path), bytes=path.stat().st_size)
    (directory / 'manifest.json').write_text(json.dumps(c.seal(manifest)))
    code, output = a42342_cli(directory, expected_file)
    assert code == 1 and output['mock_contract_validated'] is False
    assert output['simulated_threshold_decision'] is None
    assert output['result'].startswith('A42341_')


@pytest.mark.parametrize('option', ['--execute', '--approve', '--force', '--repeat', '--profile',
    '--token', '--budget', '--validate-mock', '--unknown'])
def test_A42342_T17_real_cli_flags_cannot_unlock_execution(tmp_path, option):
    # Rejected before any file lookup, including when paths do not exist.
    code, output = a42342_cli(tmp_path / 'no-bundle', tmp_path / 'no-expected',
                               option, 'SECRET_A42342_DSN')
    assert code == 1 and output['result'] == 'A42341_EXECUTION_NOT_AUTHORIZED'
    assert output['mock_contract_validated'] is False


def test_A42342_T19_T20_no_workflow_schema_or_other_tool_change():
    from scripts.business_source_contract import HISTORICAL_SOURCE, historical_bytes

    baseline = "a05ab9ffa77d54126aedbdc4fee5396359326edc"
    for name in c.SOURCES:
        if name != "scripts/a42341_calibration_review.py":
            assert historical_bytes(name) == c.git(
                ROOT, "show", baseline + ":" + name, binary=True
            )
    assert not c.git(
        ROOT,
        "diff",
        baseline,
        HISTORICAL_SOURCE,
        "--",
        "backend",
        "config",
        "migrations",
        "frontend",
        ".github",
        "docs/acceptance/evidence",
    )
    assert c.definitions()["effective_warmups_total"] == 8

    from scripts.business_source_contract import verify as verify_current_business

    assert len(verify_current_business()) == 64


@pytest.mark.parametrize('index', [1, 3])
def test_A42342_T17_execute_switch_is_not_interpreted_as_input_path(index, capsys):
    args = ['--directory', 'unused', '--expected', 'unused']
    args[index] = '--execute'
    assert reviewer.main(args) == 1
    output = json.loads(capsys.readouterr().out)
    assert output['result'] == 'A42341_EXECUTION_NOT_AUTHORIZED'
    assert output['mock_contract_validated'] is False
