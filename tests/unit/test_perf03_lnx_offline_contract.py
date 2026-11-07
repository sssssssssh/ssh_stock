"""Artificial evidence only: no application or database fixtures."""

import ast
import copy
import hashlib
import sys
from pathlib import Path

import pytest

from scripts import perf03_lnx_offline_contract as c


def test_protocol_cannot_grant_execution():
    protocol = c.protocol()
    assert protocol['measurement']['root_seconds'] == 180
    assert protocol['measurement']['full_six_arm_window_seconds'] == 2700
    assert not any(c.AUTHORIZATION.values())
    assert c.validate_protocol(protocol) is None


def test_three_mock_pairs_are_arithmetic_only():
    receipts = [c.mock_receipt(arm, wall='100' if arm.startswith('OFF') else '103')
                for arm in c.ORDER]
    result = c.statistics(receipts)
    assert result['mock_overhead_percent'] == '3'
    assert result['arithmetic_threshold_met'] is True
    assert result['p95'] is None
    assert result['REAL_MEASUREMENT'] is False


@pytest.mark.parametrize('arm', ['OFF0', 'ON4', '--real', '../OFF1'])
def test_bad_arm_refused(arm):
    with pytest.raises(c.Refused):
        c.mock_receipt(arm)


def six():
    return [c.mock_receipt(arm, wall='100' if arm.startswith('OFF') else '103')
            for arm in c.ORDER]


@pytest.mark.parametrize('on,expected', [('102.99', True), ('103', True), ('103.01', False),
                                        ('150', False), ('0', True)])
def test_arithmetic_boundary_no_real_eligibility(on, expected):
    receipts = six()
    for r in receipts[1::2]:
        r['metrics']['root_wall_ms'] = on
    result = c.statistics(receipts)
    assert result['arithmetic_threshold_met'] is expected
    assert result['PERFORMANCE_ELIGIBILITY'] == 'NOT_CLAIMED'
    assert result['R1_STATUS'] == 'PARTIAL'
    assert not any(result['authorization'].values())
    assert len(result['raw_receipts']) == 6
    assert len(result['groups']['OFF']['values']) == 3
    assert result['groups']['OFF']['stddev'] == '0'


@pytest.mark.parametrize('mutate', [
    lambda rs: rs.pop(), lambda rs: rs.append(copy.deepcopy(rs[0])),
    lambda rs: rs.reverse(), lambda rs: rs.__setitem__(1, copy.deepcopy(rs[0])),
    lambda rs: rs[1]['identity'].update(source_sha='f'*40),
    lambda rs: rs[1]['identity'].update(source_tree_sha='f'*40),
    lambda rs: rs[1]['identity'].update(run_id='SYNTHETIC_OTHER'),
    lambda rs: rs[1]['identity'].update(mock_protocol_sha256='f'*64),
    lambda rs: rs[1]['identity'].update(dataset_sha256='f'*64),
    lambda rs: rs[1]['identity'].update(configuration_sha256='f'*64),
    lambda rs: rs[1].update(switch_label='OFF'),
    lambda rs: rs[1].update(pair_index=True),
    lambda rs: [r['metrics'].update(root_wall_ms='0') for r in rs[::2]],
    lambda rs: rs[1].update(job_state='FAILED', publication_state='ABORTED'),
    lambda rs: rs[1].update(phase='INCOMPLETE', final_receipt_status='INCOMPLETE'),
    lambda rs: rs[1]['authorization'].update(real_pg_executed=True),
    lambda rs: rs[1]['metrics'].update(synthetic=False),
    lambda rs: rs[1]['metrics'].update(p95=123),
])
def test_statistics_reject_incomplete_or_spliced_evidence(mutate):
    receipts = six()
    mutate(receipts)
    with pytest.raises(c.Refused):
        c.statistics(receipts)


@pytest.mark.parametrize('bad', ['NaN', 'Infinity', '-1', '1e9', '', 1, True,
                                float('nan'), float('inf'), None])
def test_bad_metric_input(bad):
    receipt = c.mock_receipt('OFF1')
    receipt['metrics']['root_wall_ms'] = bad
    with pytest.raises(c.Refused):
        c.validate_receipt(receipt)


@pytest.mark.parametrize('mutate', [
    lambda r: r.update(schema='biz-perf-03-a-r1.verification.v1'),
    lambda r: r.update(evidence_kind='DIAGNOSTIC_ONLY'),
    lambda r: r.update(execution_platform='Linux'),
    lambda r: r.update(runtime_identity='PG17'),
    lambda r: r.update(token='secret'),
    lambda r: r.update(tool_version=True),
    lambda r: r['identity'].update(worktree_state='CLEAN'),
    lambda r: r['identity'].update(source_sha='not-a-sha'),
    lambda r: r['identity'].update(run_id='41991816127'),
    lambda r: r['protocol']['business_seed'].update(symbols=4),
    lambda r: r['protocol']['measurement'].update(root_seconds=181),
    lambda r: r['timestamps'].reverse(),
    lambda r: r['supervision'].update(phases=['ROOT']),
    lambda r: r['supervision'].update(deadlines_seconds=[180,180,60]),
    lambda r: r.update(first_failure='MOCK_ERROR'),
    lambda r: r.update(first_failure='MOCK_SECOND', failure_reason=['MOCK_FIRST']),
    lambda r: r.update(failure_reason=['postgresql://secret']),
    lambda r: r.update(cleanup_state='INCOMPLETE'),
    lambda r: r.update(child_exit_code=3221225477),
    lambda r: r['business_snapshot']['tables']['artificial_result']['rows'][0].update(
        optional='/Users/private/token'),
    lambda r: r['business_snapshot']['tables']['artificial_result']['rows'][0].update(
        optional='SELECT * FROM sensitive;'),
    lambda r: r['business_snapshot']['tables']['artificial_result']['rows'][0].update(
        optional='https://example.com'),
    lambda r: r['business_snapshot']['tables']['artificial_result']['rows'][0].update(
        optional='SELECT secret'),
    lambda r: r['business_snapshot']['tables']['artificial_result']['rows'][0].update(
        optional='private token'),
])
def test_receipt_unsafe_or_contradictory_rejected(mutate):
    receipt = c.mock_receipt('OFF1')
    mutate(receipt)
    with pytest.raises(c.Refused):
        c.seal(receipt)


def test_seal_is_detached_canonical_and_detects_tampering():
    receipt = c.mock_receipt('OFF1')
    sealed = c.seal(receipt)
    assert c.canonical(sealed) == c.canonical(c.seal(copy.deepcopy(receipt)))
    receipt['metrics']['root_wall_ms'] = '999'
    assert c.unseal(sealed)['metrics']['root_wall_ms'] == '100'
    sealed['receipt']['metrics']['root_wall_ms'] = '999'
    with pytest.raises(c.Refused):
        c.unseal(sealed)


@pytest.mark.parametrize('raw', [b'{', b'{"a":1,"a":2}', b'{"a":NaN}', b'\xff',
                                b' ' * (c.MAX_BYTES+1)],
                         ids=['broken', 'duplicate', 'nan', 'encoding', 'oversize'])
def test_untrusted_json_refused(raw):
    with pytest.raises(c.Refused):
        c.load(raw)


def test_modules_are_standard_library_and_have_no_real_adapter():
    forbidden = ('app', 'sqlalchemy', 'psycopg', 'scripts.v14_test_database',
                 'scripts.performance_diagnostics_overhead')
    assert not any(name == prefix or name.startswith(prefix + '.')
                   for name in sys.modules for prefix in forbidden)
    root = Path(__file__).resolve().parents[2]
    allowed = {'argparse', 'copy', 'hashlib', 'json', 're', 'statistics', 'uuid', 'datetime',
               'decimal', 'os', 'stat', 'subprocess', 'sys', 'tempfile', 'time', 'pathlib',
               'scripts'}
    for name in ('contract', 'supervisor'):
        path = root / f'scripts/perf03_lnx_offline_{name}.py'
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(n.name in allowed for n in node.names)
            if isinstance(node, ast.ImportFrom):
                assert node.module in allowed
                if node.module == 'scripts':
                    assert [n.name for n in node.names] == ['perf03_lnx_offline_contract']
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {'eval', 'exec', '__import__'}
    child = ast.parse((root / 'scripts/perf03_lnx_mock_child.py').read_text())
    for node in ast.walk(child):
        if isinstance(node, ast.Import):
            assert all(n.name in {'argparse', 'os', 'time'} for n in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module == 'scripts'
            assert [n.name for n in node.names] == ['perf03_lnx_offline_contract']


def test_old_evidence_bytes_unchanged():
    root = Path(__file__).resolve().parents[2] / 'docs/acceptance'
    expected = HISTORICAL_HASHES
    for name, sha in expected.items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == sha


@pytest.mark.parametrize('key', ['arm_id', 'phase', 'job_state', 'metrics', 'supervision'])
def test_wrong_container_types_refused(key):
    receipt = c.mock_receipt('OFF1')
    receipt[key] = []
    with pytest.raises(c.Refused):
        c.seal(receipt)


def test_statistics_does_not_hide_slow_or_different_input_pair():
    receipts = six()
    receipts[5]['metrics']['root_wall_ms'] = '9999'
    result = c.statistics(receipts)
    assert result['groups']['ON']['maximum'] == '9999'
    assert result['raw_receipts'][5]['metrics']['root_wall_ms'] == '9999'
    for receipt in receipts[4:]:
        receipt['business_snapshot']['tables']['artificial_result']['rows'][0]['quantity'] = 3
    with pytest.raises(c.Refused):
        c.statistics(receipts)


def test_replacement_with_recomputed_hash_requires_independent_expected_digest():
    sealed = c.seal(c.mock_receipt('OFF1'))
    original = sealed['sha256']
    sealed['receipt']['metrics']['root_wall_ms'] = '999'
    sealed['sha256'] = c.digest(sealed['receipt'])
    with pytest.raises(c.Refused, match='MOCK_EXPECTED_DIGEST_MISMATCH'):
        c.unseal(sealed, expected_sha256=original)


HISTORICAL_HASHES = {
    'biz_perf_03_a_r1/localization.json':
        'e8f88e1f533b2582fef1bd9b662663e978bd81884119c54cc1d2bc486139af45',
    'biz_perf_03_a_r1/verification.json':
        'dd12afd70a784e48ee3b9ba80e314a7f057915e980df96e19e3506f636b3d056',
    'biz_perf_03_a/root_overhead.json':
        'a21e1e4dfe1102383cf860c957faab218c6d61079328dcbdf66800cade101725',
    'biz_perf_03_a/offline_overhead.json':
        '89c3c2ea6e13cce9ba56cccdf0ee5ac7c60a081ede1917aba8b46d86f2b50f7f',
}


@pytest.mark.parametrize('state', ['TIMED_OUT', 'CRASHED', 'FAILED',
                                  'CLEANUP_UNCERTAIN', 'EVIDENCE_UNAVAILABLE'])
@pytest.mark.parametrize('entry', ['validate', 'seal', 'unseal', 'parity', 'statistics'])
def test_rev1_false_failure_states_rejected_everywhere(state, entry):
    receipts = six()
    receipt = receipts[1]
    receipt['phase'] = receipt['final_receipt_status'] = state
    # Still zero exit, complete cleanup, no first error: this is NOT a valid failure.
    if entry == 'parity':
        assert c.parity(receipts[0], receipt)['status'] == 'MOCK_PARITY_REJECTED'
        return
    with pytest.raises(c.Refused):
        if entry == 'validate':
            c.validate_receipt(receipt)
        elif entry == 'seal':
            c.seal(receipt)
        elif entry == 'unseal':
            sealed = c.seal(c.mock_receipt('ON1'))
            sealed['receipt'] = receipt
            sealed['sha256'] = c.digest(receipt)
            c.unseal(sealed)
        else:
            c.statistics(receipts)


def rev1_observed_receipt(state, reason):
    r = c.mock_receipt('OFF1')
    r.update(phase=state, final_receipt_status=state, first_failure=reason,
             failure_reason=[reason])
    r['supervision'].update(parent_verified=True, child_reaped=True, process_cleanup='REAPED',
        timeline=[dict(phase=p, began=str(i), deadline=str(i+1),
                       ended=str(i)+'.1', complete=True)
                  for i, p in enumerate(('SETUP', 'ROOT', 'CLEANUP'))])
    return r


@pytest.mark.parametrize('state,reason', [
    ('TIMED_OUT', 'MOCK_PHASE_TIMEOUT'), ('CRASHED', 'MOCK_CHILD_EXIT'),
    ('FAILED', 'MOCK_ALL_FINE'), ('CLEANUP_UNCERTAIN', 'MOCK_CLEANUP_FAILED'),
    ('EVIDENCE_UNAVAILABLE', 'MOCK_EVIDENCE_UNAVAILABLE')])
def test_rev1_error_code_alone_cannot_prove_failure(state, reason):
    r = rev1_observed_receipt(state, reason)
    if state == 'EVIDENCE_UNAVAILABLE':
        r['supervision']['archive_verified'] = True
    with pytest.raises(c.Refused):
        c.validate_receipt(r)


@pytest.mark.parametrize('outcome', ['SUCCESS', 'FAILED', 'CANCELLED', 'UNKNOWN_ACK'])
def test_rev1_legitimate_business_states_still_roundtrip(outcome):
    r = c.mock_receipt('OFF1', outcome=outcome)
    assert c.unseal(c.seal(r)) == r
    assert not any(r['authorization'].values())


def test_rev1_legitimate_not_started_prefix_and_tool_failure():
    prefix = c.mock_receipt('OFF1')
    prefix.update(phase='INCOMPLETE', final_receipt_status='INCOMPLETE',
                  child_exit_code=None, cleanup_state='NOT_ASSESSED')
    prefix['supervision']['phases'] = []
    assert c.unseal(c.seal(prefix)) == prefix
    failed = rev1_observed_receipt('FAILED', 'MOCK_EVIDENCE_INVALID')
    assert c.unseal(c.seal(failed)) == failed
    left = c.mock_receipt('ON1')
    assert c.parity(failed, left)['status'] == 'MOCK_PARITY_REJECTED'


def test_rev1_incomplete_prefix_cannot_lie_about_full_success_or_parent_state():
    r = c.mock_receipt('OFF1')
    r['phase'] = r['final_receipt_status'] = 'INCOMPLETE'
    with pytest.raises(c.Refused):
        c.seal(r)
    r = c.mock_receipt('OFF1')
    r['supervision']['child_reaped'] = True
    with pytest.raises(c.Refused):
        c.seal(r)


@pytest.mark.parametrize('state,reason', [
    ('TIMED_OUT', 'MOCK_PHASE_TIMEOUT'), ('CRASHED', 'MOCK_CHILD_EXIT'),
    ('CLEANUP_UNCERTAIN', 'MOCK_CLEANUP_FAILED'),
    ('EVIDENCE_UNAVAILABLE', 'MOCK_EVIDENCE_UNAVAILABLE')])
def test_rev1_legitimate_failure_evidence_roundtrips(state, reason):
    r = rev1_observed_receipt(state, reason)
    if state == 'TIMED_OUT':
        r['supervision']['phases'] = ['SETUP', 'ROOT']
        r['supervision']['timeline'][-1].update(complete=False, ended='3.1')
        r['supervision']['observed_elapsed_seconds'] = '3.1'
        r.update(child_exit_code=-9, cleanup_state='NOT_ASSESSED')
    elif state == 'CRASHED':
        r.update(child_exit_code=139, cleanup_state='NOT_ASSESSED')
    elif state == 'CLEANUP_UNCERTAIN':
        r['cleanup_state'] = 'INCOMPLETE'
    assert c.unseal(c.seal(r)) == r
