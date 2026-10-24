"""Blocked-stage contracts only: no real warmup, SQL, subprocess worker or samples."""

import ast
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest
from psycopg._preparing import Prepare, PrepareManager

from scripts import a4234_calibration_contract as contract
from scripts import a4234_calibration_guard as guard
from scripts.a4233_background_observer import FIELDS, SQL
from scripts.a4233_observation_contract import digest

ROOT = Path(__file__).resolve().parents[2]


def simulation():
    manifest = guard.definitions()
    marker, system = '00000000-0000-4000-8000-000000000001', '123456789'
    identity = contract.Identity(head_sha='a' * 40, run_id='local', attempt=1,
        protocol_sha256=contract.PROTOCOL_SHA, source_sha256=guard.source_sha(),
        model_sha256=manifest['model_tree_sha256'], fixture_sha256=contract.MANIFEST_SHA,
        input_sha256=manifest['input_key_sha256'],
        dependency_sha256=manifest['source_files']['requirements.lock'],
        instance_identity_sha256=digest([marker, system]), container_sha256='b' * 64,
        data_snapshot_sha256='c' * 64)
    role = {name: False for name in ('superuser', 'can_create_role', 'can_create_database',
        'can_bypass_rls', 'can_replication', 'can_dml', 'can_ddl', 'can_maintain',
        'can_signal_other_backend', 'can_read_business_rows')}
    role.update(readonly=True, autocommit=True, read_all_stats=True,
        control_system_execute=True, sql_timeout_ms=100, max_rows_per_view=128,
        sql_allowlist_sha256=digest(SQL), columns_allowlist_sha256=digest(FIELDS))
    value = dict(identity=identity.model_dump(), head_sha=identity.head_sha,
        origin_master_sha=identity.head_sha, target_sha=identity.head_sha, clean_tree=True,
        python_major_minor='3.12', dependencies_verified=True, event='SIMULATED_CONTRACT',
        physical=dict(container_sha256=identity.container_sha256, host='127.0.0.1', port=55440,
            database='v14_' + 'd' * 32 + '_test', owned_nonce='d' * 32,
            created_by_current_harness=True, before_ddl=True, pg_major=17,
            expected_marker=marker, observed_marker=marker,
            expected_system_id=system, observed_system_id=system), privileges=role)
    return value, identity


def test_exact_128_plan_and_user_confirmed_eight_warmup_definitions():
    plan, warmups = contract.schedule(), contract.warmup_schedule()
    assert digest(plan) == contract.SCHEDULE_SHA and plan == contract.schedule()
    assert len(plan) == 128 and [p['position'] for p in plan] == list(range(128))
    pairs = Counter((p['block'], p['variant'], p['pair']) for p in plan)
    assert len(pairs) == 64 and set(pairs.values()) == {2}
    assert Counter((p['variant'], p['mode']) for p in plan) == {
        ('C0', 'OFF'): 32, ('C0', 'ON'): 32, ('C1', 'OFF'): 32, ('C1', 'ON'): 32}
    assert len(warmups) == 8 and digest(warmups) == contract.WARMUP_SHA
    for b in range(4):
        variants = ['C0', 'C1'] if b % 2 == 0 else ['C1', 'C0']
        points = [p for p in plan if p['block'] == b]
        assert [points[0]['variant'], points[16]['variant']] == variants
        assert [p['variant'] for p in warmups if p['block'] == b] == variants
        for i in range(0, len(points), 2):
            pair = points[i:i + 2]
            assert [p['mode'] for p in pair] == (
                ['OFF', 'ON'] if (pair[0]['pair'] + b) % 2 == 0 else ['ON', 'OFF'])
    assert all(contract.SampleIdentity.model_validate(p).model_dump() == p for p in plan)


@pytest.mark.parametrize('field,value', [('block', 4), ('pair', 8), ('position', 128),
    ('mode', 'AUTO'), ('variant', 'C2'), ('block', True), ('extra', 'forbidden')])
def test_identity_rejects_out_of_protocol_definitions(field, value):
    point = dict(contract.schedule()[0], **{field: value})
    with pytest.raises(ValueError):
        contract.SampleIdentity.model_validate(point)


@pytest.mark.parametrize('variant', ['C0', 'C1'])
def test_existing_workload_splits_into_four_mocked_batches_only(monkeypatch, variant):
    from scripts import publication_lookup_diagnostic_a422 as lab

    calls = []
    def fake_lookup(ws, model, payload, selected, metrics=None):
        calls.append((len(payload), selected))
        return {}, {}, None
    monkeypatch.setattr(lab, 'lookup', fake_lookup)
    result, _ = lab.workload(None, None, list(range(2000)), variant)
    assert result == ({}, {}, None) and calls == [(500, variant)] * 4
    # Static AST only: a nonempty frozen batch has exactly one db.execute call.
    tree = ast.parse((ROOT / 'backend/app/services/data_publication.py').read_text())
    batch = next(n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == '_lookup_batch')
    assert sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == 'execute' for n in ast.walk(batch)) == 1


def test_pinned_driver_pure_cache_demonstrates_sixth_execution_prepares_without_connecting():
    # The installed locked driver cache is pure Python; no psycopg.connect/cursor/SQL.
    manager = PrepareManager()
    assert manager.prepare_threshold == 5 and manager.prepared_max == 100
    query = SimpleNamespace(query=b'synthetic_a4234_cache_key', types=())
    states = []
    for _ in range(6):
        state, name = manager.get(query)
        states.append(state)
        manager.maybe_add_to_cache(query, state, name)
    assert states == [Prepare.NO] * 5 + [Prepare.SHOULD]
    proof = contract.prepared_readiness()
    assert proof['sql_executions_per_condition'] == 4 < proof['first_prepared_execution'] == 6
    assert proof['warmups_total'] == 8 < proof['necessary_minimum_warmups_for_preparation'] == 16
    assert proof['minimum_is_not_steady_state_proof'] is True


def test_valid_simulation_is_blocked_not_physical_or_calibration_evidence():
    value, expected = simulation()
    result = guard.audit(value, expected)
    assert result['status'] == contract.BLOCKED and result['reason'] == contract.BLOCKER
    assert result['physical_verified'] is False
    assert result['calibration_decision'] == 'NOT_AUTHORIZED'
    assert result['backend_cpu_status'] == 'METRIC_UNAVAILABLE'
    assert result['recorder_implemented'] is result['calibration_reviewer_implemented'] is False
    for field in contract.Safety.model_fields:
        assert result[field] == getattr(contract.Safety(), field)


def test_check_cli_even_valid_preparation_exits_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(guard, 'check_repository', lambda *a: contract.prepared_readiness())
    assert guard.main(['--check', '--target-sha', 'a' * 40]) == 1
    assert json.loads(capsys.readouterr().out)['status'] == contract.BLOCKED


@pytest.mark.parametrize('section,field,bad', [
    (None, 'schema_version', 'a4233.preflight.v1'),
    (None, 'target_sha', 'a' * 12), (None, 'origin_master_sha', 'e' * 40),
    (None, 'clean_tree', False), (None, 'python_major_minor', '3.11'),
    (None, 'dependencies_verified', False), (None, 'event', 'push'),
    (None, 'event', 'pull_request'), (None, 'event', 'none'),
    (None, 'profile', 'a4232-statstable-once'), (None, 'token', 'consumed'),
    (None, 'environment_approval', 'APPROVED'), (None, 'execution_enabled', True),
    (None, 'performance_eligible', True), (None, 'capacity_ready', True),
    (None, 'production_read_authorized', True), (None, 'attribution_authorized', True),
    ('physical', 'host', '192.0.2.1'), ('physical', 'host', 'business.example.invalid'),
    ('physical', 'pg_major', 16), ('physical', 'owned_nonce', 'e' * 32),
    ('physical', 'created_by_current_harness', False), ('physical', 'before_ddl', False),
    ('physical', 'observed_marker', '00000000-0000-4000-8000-000000000002'),
    ('physical', 'observed_system_id', '987654321'),
    ('physical', 'container_sha256', 'e' * 64), ('physical', 'port', 0),
    ('privileges', 'superuser', True), ('privileges', 'can_create_role', True),
    ('privileges', 'can_create_database', True), ('privileges', 'can_bypass_rls', True),
    ('privileges', 'can_replication', True), ('privileges', 'can_dml', True),
    ('privileges', 'can_ddl', True), ('privileges', 'can_maintain', True),
    ('privileges', 'can_signal_other_backend', True),
    ('privileges', 'can_read_business_rows', True),
    ('privileges', 'readonly', False), ('privileges', 'autocommit', False),
    ('privileges', 'sql_timeout_ms', 101), ('privileges', 'max_rows_per_view', 129),
    ('privileges', 'sql_allowlist_sha256', 'e' * 64),
    ('privileges', 'columns_allowlist_sha256', 'e' * 64),
    ('identity', 'attempt', 2), ('identity', 'head_sha', 'e' * 40),
    ('identity', 'protocol_sha256', 'e' * 64), ('identity', 'fixture_sha256', 'e' * 64),
    ('identity', 'model_sha256', 'e' * 64), ('identity', 'source_sha256', 'e' * 64),
    ('identity', 'input_sha256', 'e' * 64), ('identity', 'dependency_sha256', 'e' * 64),
])
def test_preflight_mutations_fail_closed(section, field, bad):
    value, expected = simulation()
    (value if section is None else value[section])[field] = bad
    with pytest.raises(contract.Fault, match='^A4234_'):
        guard.audit(value, expected)


@pytest.mark.parametrize('field', ['protocol_sha256', 'fixture_sha256', 'model_sha256',
    'source_sha256', 'input_sha256', 'dependency_sha256'])
def test_both_sides_forging_frozen_hash_still_rejected(field):
    value, expected = simulation()
    expected = expected.model_copy(update={field: 'e' * 64})
    value['identity'] = expected.model_dump()
    with pytest.raises(contract.Fault):
        guard.audit(value, expected)


@pytest.mark.parametrize('relative', [contract.PROTOCOL, contract.MANIFEST, contract.INPUT,
    'backend/app/services/data_publication.py', 'scripts/a4232_plan_probe.py',
    '.github/actions/a4-governance/policy.json', 'requirements.lock'])
def test_frozen_file_replacement_fails_without_changing_real_files(monkeypatch, relative):
    original = guard.file_sha
    monkeypatch.setattr(guard, 'file_sha', lambda p: 'e' * 64
                        if Path(p) == ROOT / relative else original(p))
    with pytest.raises(contract.Fault):
        guard.definitions()


def repository_mocks(monkeypatch):
    def fake(root, *args, binary=False):
        if args[0] == 'rev-parse':
            return 'a' * 40
        if args[0] in ('status', 'diff'):
            return ''
        if args[0] == 'show':
            return (ROOT / args[1].removeprefix('HEAD:')).read_bytes()
        assert args[0] == 'ls-tree'
        return guard.subprocess.check_output(['git', *args], cwd=ROOT)
    monkeypatch.setattr(guard, 'git', fake)
    monkeypatch.setattr(guard.importlib.metadata, 'version', lambda name: next(
        line.split('==')[1] for line in (ROOT / 'requirements.lock').read_text().splitlines()
        if line.split('==')[0].split('[')[0] == name))
    return fake


def test_repository_all_checks_mocked_valid_still_blocked(monkeypatch):
    repository_mocks(monkeypatch)
    result = guard.check_repository(ROOT, 'a' * 40)
    assert result['status'] == contract.BLOCKED and not result['physical_verified']


@pytest.mark.parametrize('problem', ['remote', 'dirty', 'dependency', 'model', 'source', 'scope'])
def test_repository_independent_frozen_checks(monkeypatch, problem):
    original = repository_mocks(monkeypatch)
    def fake(root, *args, binary=False):
        if problem == 'remote' and args == ('rev-parse', 'origin/master'):
            return 'e' * 40
        if problem == 'dirty' and args[0] == 'status':
            return ' M README.md'
        if problem == 'model' and args[0] == 'ls-tree':
            return b'changed'
        if problem == 'source' and args[0] == 'show':
            return b'changed'
        if problem == 'scope' and args[0] == 'diff':
            return 'scripts/a4232_plan_probe.py'
        return original(root, *args, binary=binary)
    monkeypatch.setattr(guard, 'git', fake)
    if problem == 'dependency':
        monkeypatch.setattr(guard.importlib.metadata, 'version', lambda name: '0.0.0')
    with pytest.raises(contract.Fault):
        guard.check_repository(ROOT, 'a' * 40)


@pytest.mark.parametrize('bad', ['5215145', '', 'A' * 40])
def test_short_or_invalid_target_rejected(bad):
    with pytest.raises(contract.Fault, match='A4234_FULL_SHA_REQUIRED'):
        guard.check_repository(ROOT, bad)


@pytest.mark.parametrize('args', [[], ['--execute'], ['--approve'], ['--force'], ['--repeat', '2'],
    ['--budget', '99999'], ['--profile', 'a4232-statstable-once'], ['--token', 'SECRET_A4234'],
    ['--check', '--target-sha', 'a' * 40, '--execute']])
def test_cli_unknown_and_approval_flags_never_execute_or_echo_values(args, monkeypatch, capsys):
    monkeypatch.setenv('A4234_EXECUTION_ENABLED', 'true')
    monkeypatch.setenv('A4234_TOKEN', 'SECRET_A4234')
    monkeypatch.setenv('A4_REVIEW_POLICY_ACK', 'approved')
    monkeypatch.setattr(guard, 'check_repository', lambda *a: pytest.fail('must not check/run'))
    assert guard.main(args) == 1
    output = capsys.readouterr().out
    assert 'A4234_EXECUTION_NOT_AUTHORIZED' in output and 'SECRET_A4234' not in output
    with pytest.raises(contract.Fault, match='A4234_EXECUTION_NOT_AUTHORIZED'):
        guard.execute(approval=True, token='SECRET_A4234', callback=lambda: pytest.fail('no run'))


@pytest.mark.parametrize('body', ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', 'invalid'])
def test_bad_json_is_fixed_code_only(tmp_path, body):
    path = tmp_path / 'bad.json'
    path.write_text(body)
    with pytest.raises(contract.Fault, match='^A4234_'):
        contract.load(path)


def test_missing_symlink_or_oversized_input_rejected(tmp_path):
    absent = tmp_path / 'absent.json'
    with pytest.raises(contract.Fault):
        contract.load(absent)
    value = tmp_path / 'value.json'
    value.write_text('{}')
    link = tmp_path / 'link.json'
    link.symlink_to(value)
    with pytest.raises(contract.Fault):
        contract.load(link)
    with value.open('r+b') as stream:
        stream.truncate(16_000_001)
    with pytest.raises(contract.Fault):
        contract.load(value)


def junit(path, failure=False):
    item = '<failure>SECRET_A4234_DSN</failure>' if failure else ''
    path.write_text('<testsuites><testsuite tests="1" failures="' + str(int(failure)) +
        '" errors="0" skipped="0"><testcase classname="tests.unit.test_a4234" name="test_mock" '
        'time="0.01">' + item + '</testcase></testsuite></testsuites>')


@pytest.mark.parametrize('failure', [False, True])
def test_unit_receipt_is_sha_bound_counted_sanitized_and_never_calibration(tmp_path, monkeypatch,
                                                                      failure):
    for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'):
        monkeypatch.delenv(key, raising=False)
    source = tmp_path / 'tests.xml'
    junit(source, failure)
    value = guard.test_receipt(source)
    assert value['status'] == ('INCOMPLETE_CONTRACT' if failure else 'COMPLETE_CONTRACT')
    assert value['counts'] == dict(tests=1, failures=int(failure), errors=0, skipped=0)
    assert value['preparation']['status'] == contract.BLOCKED and not value['physical_verified']
    assert value['protocol_sha256'] == contract.PROTOCOL_SHA
    assert value['source_sha256'] == guard.source_sha()
    assert value['content_sha256'] == digest({k: v for k, v in value.items()
                                             if k != 'content_sha256'})
    assert 'SECRET_A4234_DSN' not in json.dumps(value) + source.read_text()


def test_missing_junit_and_write_failure_cannot_succeed(tmp_path, monkeypatch, capsys):
    assert guard.test_receipt(tmp_path / 'missing.xml')['status'] == 'INCOMPLETE_CONTRACT'
    monkeypatch.setattr(guard, 'test_receipt', lambda *a: dict(status='COMPLETE_CONTRACT'))
    def bad_write(*args):
        raise OSError('SECRET_A4234_DSN')
    monkeypatch.setattr(guard, 'write_new', bad_write)
    assert guard.main(['--tests', str(tmp_path / 'tests.xml'), '--output',
                       str(tmp_path / 'tests.json')]) == 1
    assert 'SECRET_A4234_DSN' not in capsys.readouterr().out


def test_new_receipt_refuses_overwrite(tmp_path, monkeypatch):
    source, output = tmp_path / 'tests.xml', tmp_path / 'tests.json'
    junit(source)
    for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'):
        monkeypatch.delenv(key, raising=False)
    args = ['--tests', str(source), '--output', str(output)]
    assert guard.main(args) == 0
    first = output.read_bytes()
    assert guard.main(args) == 1 and output.read_bytes() == first
