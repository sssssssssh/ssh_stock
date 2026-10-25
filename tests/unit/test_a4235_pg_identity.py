"""AT01-10, 26-28: independent simulated identities never grant live execution."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import a4235_capability_guard as guard
from scripts.a4235_calibration_adapter_contract import (
    BASELINE,
    ROOT,
    Decisions,
    Fault,
    Identity,
    RealAdapter,
    Safety,
    digest,
)
from scripts.a4235_pg_identity import (
    Fixture,
    Grant,
    Privileges,
    compare_fixture,
    validate_mock_grant,
)
from scripts.a4235_prepared_probe import ALLOWLIST_SHA


@pytest.fixture
def identity():
    return Identity(head_sha=BASELINE, run_id='12345', attempt=1,
                    source_sha256='a' * 64, protocol_sha256='b' * 64, frozen_sha256='c' * 64)


@pytest.fixture
def fixture(identity):
    return Fixture(host='127.0.0.1', port=5432, database='v14_' + '1' * 32 + '_test',
                   owner_nonce='1' * 32, marker='11111111-1111-1111-1111-111111111111',
                   system_identifier='123456789', container_digest='a' * 64, pg_major=17,
                   created_this_run=True, cleanup_chain_verified=True, identity=identity)


@pytest.fixture
def grant(identity, fixture):
    return Grant(identity=identity, profile='a4235-capability-only-proposed-v1',
                 scope='SYNTHETIC_CAPABILITY_ONLY', event='workflow_dispatch',
                 fixture_sha256=digest(fixture.model_dump()), allowlist_sha256=ALLOWLIST_SHA,
                 issued_at=100, expires_at=200, nonce='f' * 32, consumed=False,
                 short_sql_budget=16, total_budget_ms=2000)


def test_AT01_AT02_AT10_actual_frozen_trees_and_baseline_receipt():
    assert len(guard.frozen_files()) == 64
    receipt = (ROOT / 'docs/acceptance/a42342_final_review.md').read_text()
    assert '3337' in receipt and 'STOP_TIMEOUT' in receipt and '尚未获准补丁' in receipt
    from scripts.a4234_calibration_contract import schedule, warmup_schedule
    from scripts.a42341_contract import definitions
    assert len(warmup_schedule()) == 8
    assert len(schedule()) == 128 and len({(r['block'], r['variant'], r['pair'])
                                         for r in schedule()}) == 64
    assert len(definitions()['frozen_files']) == 20


@pytest.mark.parametrize('changes', [
    {'selected': 'A'}, {'selected': 'B'}, {'effective_warmups_total': 16},
    {'candidate_a': 'APPROVED'}, {'candidate_b': 'APPROVED'}, {'automatic_escalation': True},
    {'retry_allowed': True}, {'candidate_fixed_budgets': (16, 16)}, {'prepared_stable': True},
    {'protocol_decision_status': 'APPROVED'}, {'formal_calibration_authorization': 'APPROVED'},
])
def test_AT03_AT04_AT26_decisions_cannot_self_approve(changes):
    with pytest.raises(ValueError):
        Decisions(**changes)


@pytest.mark.parametrize('key', list(Safety.model_fields)[:5])
def test_AT26_no_success_flag_can_be_set(key):
    with pytest.raises(ValueError):
        Safety(**{key: True})


@pytest.mark.parametrize('field,bad', [
    ('head_sha', 'abc123'), ('run_id', '0'), ('attempt', 0), ('attempt', True),
    ('source_sha256', 'x' * 64), ('protocol_sha256', 'b' * 40),
])
def test_AT05_identity_schema_rejects_short_sha_and_invalid_run(identity, field, bad):
    with pytest.raises(ValueError):
        Identity.model_validate(identity.model_dump() | {field: bad})


@pytest.mark.parametrize('field,bad', [
    ('host', '8.8.8.8'), ('host', 'localhost'), ('host', '127.0.0.2'),
    ('host', 'postgresql://secret@example.invalid/db'), ('host', '::ffff:127.0.0.1'),
    ('database', 'postgres'), ('database', 'v14_' + '2' * 32 + '_test'),
    ('owner_nonce', '2' * 32), ('marker', '22222222-2222-2222-2222-222222222222'),
    ('system_identifier', '98765'), ('container_digest', 'b' * 64), ('pg_major', 16),
    ('created_this_run', False), ('cleanup_chain_verified', False), ('port', 5433),
])
def test_AT06_AT07_fixture_drift_and_self_description_rejected(fixture, field, bad):
    with pytest.raises((ValueError, Fault)):
        compare_fixture(fixture.model_copy(update={field: bad}), fixture, Privileges())


@pytest.mark.parametrize('field', [
    'superuser', 'root', 'create_role', 'create_database', 'bypass_rls', 'replication', 'dml',
    'ddl', 'maintain', 'signal_others', 'read_business_rows', 'inherited_dangerous_roles',
    'read_all_stats',
])
def test_AT08_excess_privilege_rejected_even_constructed_model(fixture, field):
    with pytest.raises(ValueError):
        compare_fixture(fixture, fixture, Privileges().model_copy(update={field: True}))


@pytest.mark.parametrize('field,bad', [
    ('consumed', True), ('scope', 'PERFORMANCE'), ('profile', 'a4232'),
    ('event', 'push'), ('event', 'pull_request'), ('expires_at', 99), ('expires_at', 401),
    ('fixture_sha256', 'b' * 64), ('allowlist_sha256', 'c' * 64), ('nonce', 'e' * 32),
    ('short_sql_budget', 128), ('total_budget_ms', 10000), ('signature_status', 'VERIFIED'),
])
def test_AT09_mock_grant_expired_replayed_or_other_scope_rejected(grant, fixture, field, bad):
    with pytest.raises((ValueError, Fault)):
        validate_mock_grant(grant.model_copy(update={field: bad}), grant, 150,
                            fixture, ALLOWLIST_SHA)


def test_AT07_AT09_AT26_matching_mock_claims_are_not_physical_or_signed_proof(fixture, grant):
    result = compare_fixture(fixture, fixture, Privileges())
    assert result['physical_verified'] is False
    result = validate_mock_grant(grant, grant, 150, fixture, ALLOWLIST_SHA)
    assert result['signature_verified'] is False
    assert result['persistent_consumption_verified'] is False
    assert result['formal_calibration_authorization'] == 'NOT_AUTHORIZED'
    with pytest.raises(Fault, match='CAPABILITY_PROBE_NOT_AUTHORIZED'):
        RealAdapter().probe_synthetic(grant=grant, approved=True)
    assert not hasattr(RealAdapter, 'run') and not hasattr(RealAdapter, 'calibrate')


@pytest.mark.parametrize('key', ['DATABASE_URL', 'TEST_DATABASE_URL', 'PGHOST', 'PGPORT',
                                'HTTP_PROXY', 'https_proxy', 'ALL_PROXY'])
def test_AT06_static_ambient_connections_rejected_before_git(monkeypatch, key):
    monkeypatch.setenv(key, 'SECRET_DO_NOT_PRINT')
    monkeypatch.setattr(guard, 'expected_identity',
                        lambda *a, **kw: pytest.fail('must not inspect'))
    with pytest.raises(Fault, match='AMBIENT_CONNECTION_REJECTED'):
        guard.check_static(BASELINE)


@pytest.mark.parametrize('state', ['dirty', 'remote-different', 'short-sha'])
def test_AT05_static_git_context_negative(monkeypatch, identity, state):
    for key in list(os.environ):
        if key.startswith('PG') or key in ('DATABASE_URL', 'TEST_DATABASE_URL') \
                or key.lower().endswith('_proxy'):
            monkeypatch.delenv(key)
    monkeypatch.setattr(guard, 'expected_identity', lambda *a, **kw: identity)
    monkeypatch.setattr(guard, 'git', lambda root, *a:
                        (b'1' * 40 if state == 'remote-different' else BASELINE.encode())
                        if a[0] == 'rev-parse' else b' M tracked' if state == 'dirty' else b'')
    with pytest.raises(Fault):
        guard.check_static('abc' if state == 'short-sha' else BASELINE)


def test_AT05_static_success_only_static(monkeypatch, identity):
    for key in list(os.environ):
        if key.startswith('PG') or key in ('DATABASE_URL', 'TEST_DATABASE_URL') \
                or key.lower().endswith('_proxy'):
            monkeypatch.delenv(key)
    monkeypatch.setattr(guard, 'expected_identity', lambda *a, **kw: identity)
    monkeypatch.setattr(guard, 'git', lambda root, *a:
                        BASELINE.encode() if a[0] == 'rev-parse' else b'')
    value = guard.check_static(BASELINE)
    assert value['scope'] == value['evidence_kind'] == 'STATIC_ONLY'
    assert value['capability_probe_status'] == 'NOT_RUN_NOT_AUTHORIZED'
    assert value['execution_enabled'] is value['performance_eligible'] is False


@pytest.mark.parametrize('args', [['--probe-synthetic'], ['--execute'], ['--approve'],
                                ['--force'], ['--token', 'SECRET_DO_NOT_PRINT'], ['--repeat'],
                                ['--budget', '128'], ['--run'], ['--check-static', '--execute']])
def test_AT27_AT28_live_cli_rejects_before_any_database_action(args):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GITHUB_')}
    env.update(DATABASE_URL='postgresql://SECRET_DO_NOT_PRINT@127.0.0.1:1/blocked',
               PGHOST='SECRET_DO_NOT_PRINT', PYTHONPATH=str(ROOT))
    result = subprocess.run([sys.executable, '-m', 'scripts.a4235_capability_guard', *args],
                            cwd=Path(ROOT), env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 1 and not result.stderr
    assert 'A4235_CAPABILITY_PROBE_NOT_AUTHORIZED' in result.stdout
    assert 'SECRET_DO_NOT_PRINT' not in result.stdout
