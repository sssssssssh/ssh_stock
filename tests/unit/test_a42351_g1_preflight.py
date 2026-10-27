"""A42351 offline-only design negatives; no physical collector is invoked."""

import ast
import copy
import json
import os
import subprocess
import sys

import pytest

from scripts import a42351_g1_preflight_contract as p
from scripts.a4235_calibration_adapter_contract import ROOT, Fault, Identity, Safety


@pytest.fixture
def design():
    identity = Identity(head_sha='1' * 40, run_id='12345', attempt=1,
        source_sha256='a' * 64, protocol_sha256='b' * 64, frozen_sha256='c' * 64)
    uuid = '11111111-1111-4111-8111-111111111111'
    nonce = '22222222-2222-4222-8222-222222222222'
    suffix = uuid.replace('-', '')
    value = p.PreflightDesign(identity=identity,
        fixture=p.FixtureDesign(fixture_uuid=uuid, nonce=nonce, marker_sha256='d' * 64,
            host='127.0.0.1', database=f'a42351_{suffix}', owner=f'a42351_ro_{suffix}'),
        grant_design=p.FutureGrantDesign(identity=identity, nonce=nonce, issued_at=100,
                                         expires_at=200)).model_dump()
    return identity, value


@pytest.mark.parametrize('host', ['127.0.0.1', '::1', 'UNIX'])
def test_a42351_AT23_missing_physical_evidence_never_proven(design, host):
    expected, value = design
    value['fixture']['host'] = host
    if host == 'UNIX':
        value['fixture']['socket_directory'] = (
            '/run/postgresql/a42351/' + value['fixture']['fixture_uuid'])
    result = p.review_design(value, expected, now=150)
    assert result['status'] == 'G1_PREFLIGHT_READY_FOR_REVIEW'
    assert result['physical_status'] == 'NOT_RUN_NOT_AUTHORIZED'
    assert result['real_sql_executed'] == 0
    assert result['cleanup_status'] == 'NOT_RUN_NOT_PROVEN'
    assert set(result['capabilities']) == set(p.CAPABILITIES)
    assert all(v == {'execution': 'NOT_RUN', 'proof': 'NOT_PROVEN'}
               for v in result['capabilities'].values())
    assert all(result[k] == v for k, v in Safety().model_dump().items())


@pytest.mark.parametrize('field,bad', [
    ('host', 'localhost'), ('host', '0.0.0.0'), ('host', 'public.example'),
    ('host', '127.0.0.2'), ('host', 'postgresql://SECRET_BUSINESS_DSN'),
    ('existing_database', True), ('disposable', False), ('public_port_mapping', True),
    ('database', 'postgres'), ('database', 'stock'), ('owner', 'postgres'),
    ('socket_directory', '/tmp'), ('pg_major', 16),
    ('system_identifier_status', 'VERIFIED'), ('container_namespace_status', 'VERIFIED'),
    ('image_digest_status', 'VERIFIED'), ('independent_harness_status', 'VERIFIED'),
])
def test_a42351_AT22_AT23_unsafe_fixture_or_self_asserted_proof_rejected(design, field, bad):
    expected, value = design
    value['fixture'][field] = bad
    with pytest.raises(Fault, match='^A4235_G1_') as error:
        p.review_design(value, expected, now=150)
    assert 'SECRET_BUSINESS_DSN' not in str(error.value)


@pytest.mark.parametrize('field', ['superuser', 'createdb', 'createrole', 'bypassrls',
    'replication', 'maintain', 'writes', 'business_read', 'pg_read_all_stats'])
def test_a42351_AT22_excess_role_rejected(design, field):
    expected, value = design
    value['role'][field] = True
    with pytest.raises(Fault, match='^A4235_G1_DESIGN_INVALID$'):
        p.review_design(value, expected, now=150)


@pytest.mark.parametrize('field,bad', [
    ('scope', 'PRODUCTION_READ'), ('profile', 'approved'), ('consumed', True),
    ('nonce', '11111111-1111-4111-8111-111111111111'), ('issued_at', 151),
    ('expires_at', 150), ('expires_at', 10000), ('issuer', 'MOCK_SIGNER'),
    ('signature_verifier', 'VERIFIED'), ('persistent_consumption', 'VERIFIED'),
    ('allowlist', ('SELECT * FROM stock_daily',)),
])
def test_a42351_AT21_mock_grant_cannot_become_authority(design, field, bad):
    expected, value = design
    value['grant_design'][field] = bad
    with pytest.raises(Fault):
        p.review_design(value, expected, now=150)


@pytest.mark.parametrize('field,bad', [
    ('cached_plan_structure', 'VERIFIED'), ('c0_c1', 'C0_C1_PROVEN'),
    ('backend_cpu_seconds', 0.0), ('cleanup_status', 'CLEANUP_VERIFIED'),
    ('performance_eligible', True), ('execution_enabled', True),
    ('capacity_ready', True), ('attribution_authorized', True),
    ('production_read_authorized', True), ('unique_repair_candidate', 'C1'),
    ('capability_probe_status', 'READY'), ('unknown', 'SECRET_BUSINESS_DSN'),
])
def test_a42351_AT20_AT24_forged_ready_cpu_zero_and_unknown_rejected(design, field, bad):
    expected, value = design
    value[field] = bad
    with pytest.raises(Fault, match='^A4235_G1_DESIGN_INVALID$') as error:
        p.review_design(value, expected, now=150)
    assert 'SECRET_BUSINESS_DSN' not in str(error.value)


@pytest.mark.parametrize('field,bad', [('max_sql', 17), ('total_ms', 2001),
    ('per_sql_ms', 101), ('max_rows', 9), ('real_sql_executed', 1),
    ('effective_warmups', 16), ('effective_warmups', 32), ('approved', True)])
def test_a42351_AT21_budget_design_does_not_approve_execution(design, field, bad):
    expected, value = design
    value['budget'][field] = bad
    with pytest.raises(Fault):
        p.review_design(value, expected, now=150)


@pytest.fixture
def window():
    return dict(lookup_started_ms=10, lookup_finished_ms=400, stop_join_ms=2,
        ticks=[dict(started_ms=i * 250, wall_ms=1, sql_ms=1) for i in range(3)])


def test_a42351_AT25_long_window_model_is_not_a_physical_receipt(window):
    assert p.review_mock_window(window)['status'] == 'MODEL_ONLY_NOT_PROVEN'


@pytest.mark.parametrize('change', ['before', 'during', 'after', 'short', 'interval',
    'partial', 'sql_timeout', 'tick_timeout', 'join_timeout', 'sql_sum', 'too_many'])
def test_a42351_AT25_invalid_bracket_and_deadlines_fail_closed(window, change):
    value = copy.deepcopy(window)
    if change in ('before', 'during', 'after'):
        value['ticks'].pop({'before': 0, 'during': 1, 'after': 2}[change])
    elif change == 'short':
        value['lookup_finished_ms'] = 11
    elif change == 'interval':
        value['ticks'][1]['started_ms'] += 1
    elif change == 'partial':
        value['ticks'][1]['partial'] = True
    elif change in ('sql_timeout', 'sql_sum'):
        value['ticks'][1]['sql_ms'] = 101 if change == 'sql_timeout' else 2
    elif change == 'tick_timeout':
        value['ticks'][1]['wall_ms'] = 26
    elif change == 'join_timeout':
        value['stop_join_ms'] = 2001
    else:
        value['ticks'] = [dict(started_ms=i * 250, wall_ms=1, sql_ms=1) for i in range(9)]
    with pytest.raises(Fault, match='^A4235_G1_(BRACKET_UNCOVERED|WINDOW_INVALID)$'):
        p.review_mock_window(value)


@pytest.mark.parametrize('args,event', [([], 'push'), (['--execute'], 'workflow_dispatch'),
    (['--probe-synthetic'], 'push'), (['--G1'], 'workflow_dispatch'),
    (['--G2', '16'], 'push'), (['--G3', '128'], 'workflow_dispatch'),
    (['--token', 'SECRET_BUSINESS_DSN'], 'push')])
def test_a42351_AT26_every_cli_and_event_hard_denies(args, event):
    env = dict(os.environ, PYTHONPATH=str(ROOT), GITHUB_EVENT_NAME=event,
               DATABASE_URL='postgresql://SECRET_BUSINESS_DSN', PGHOST='SECRET_BUSINESS_DSN',
               A42351_APPROVED='true', A42351_TOKEN='MOCK_SIGNED')
    result = subprocess.run([sys.executable, '-m', 'scripts.a42351_g1_preflight_contract', *args],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 1 and not result.stderr
    assert 'SECRET_BUSINESS_DSN' not in result.stdout
    assert json.loads(result.stdout)['first_error'] == 'A4235_CAPABILITY_PROBE_NOT_AUTHORIZED'


def test_a42351_AT01_AT26_preflight_is_pure_and_has_no_real_entry():
    tree = ast.parse((ROOT / 'scripts/a42351_g1_preflight_contract.py').read_bytes())
    allowed = {'typing', 'pydantic', 'scripts.a4235_calibration_adapter_contract', 'json'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert {n.name for n in node.names} <= allowed
        if isinstance(node, ast.ImportFrom):
            assert node.module in allowed
    assert not hasattr(p, 'probe_synthetic') and not hasattr(p, 'execute')


@pytest.mark.parametrize('field,bad', [('head_sha', '2' * 40), ('run_id', '54321'),
                                     ('attempt', 2), ('source_sha256', 'e' * 64)])
def test_a42351_AT28_run_attempt_and_source_bind_to_independent_expected(design, field, bad):
    expected, value = design
    value['identity'][field] = bad
    value['grant_design']['identity'][field] = bad
    with pytest.raises(Fault, match='^A4235_G1_IDENTITY_MISMATCH$'):
        p.review_design(value, expected, now=150)


def test_a42351_AT01_baseline_and_boundaries_are_not_historical_rewrites():
    from scripts import a4235_capability_guard as guard
    from scripts.business_source_contract import HISTORICAL_SOURCE

    baseline = (ROOT / "docs/acceptance/a42351_baseline_and_red.md").read_text()
    assert guard.PATCH_BASE in baseline and "40150203524" in baseline and "40150203544" in baseline
    old_receipt = "docs/acceptance/a4235_baseline_freeze.md"
    assert (ROOT / old_receipt).read_bytes() == guard.git(
        ROOT, "show", f"{guard.PATCH_BASE}:{old_receipt}"
    )
    assert not guard.git(
        ROOT,
        "diff",
        "--name-only",
        guard.PATCH_BASE,
        HISTORICAL_SOURCE,
        "--",
        "backend",
        "config",
        "migrations",
        "frontend",
        ".github",
        "scripts/a42341_calibration_runner.py",
        "scripts/a42341_contract.py",
        "scripts/a42341_calibration_guard.py",
    )

    from scripts.business_source_contract import verify as verify_current_business

    assert len(verify_current_business()) == 64
