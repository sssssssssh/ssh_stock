"""Exact skip policy/provenance regressions outside the frozen legacy module."""

import json
import sys
import xml.etree.ElementTree as ET

import pytest

from scripts.a42331_ci_evidence import PHASES, collect, sanitize_junit
from tests.unit.test_a42331_ci_evidence import ROOT, prepare, xml

# Exact raw fixtures exercise the real collector, not a pre-approved safe result.
APPROVED_CLASS = 'tests.integration.test_r1_integration_linux_mock_domain.LinuxLabTests'
APPROVED_NAME = 'test_linux_success_term_kill_owned_child'
APPROVED_REASON = 'NOT_RUN/ENV_BLOCKED: no independently approved no-network Linux lab'


def skip_fixture(path, cases):
    path.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element('testsuite', tests=str(len(cases)), failures='0', errors='0',
                       skipped=str(sum(reason is not None for _, _, reason in cases)))
    for cls, name, reason in cases:
        case = ET.SubElement(suite, 'testcase', classname=cls, name=name, time='0.01')
        if reason is not None:
            node = ET.SubElement(case, 'skipped', type='pytest.skip')
            if reason != 'MISSING_ATTRIBUTE':
                node.set('message', reason)
            node.text = 'untrusted-location:17: untrusted-context'
    path.write_bytes(ET.tostring(suite, encoding='utf8', xml_declaration=True))


def policy_prepare(tmp_path, monkeypatch, cases):
    root, output = prepare(tmp_path, monkeypatch)
    xml(root/'.codex_tmp/a42331-targeted.xml')
    path = root/'.codex_tmp/m17_1_2-full.xml'
    skip_fixture(path, cases)
    return root, output, path


def policy_cli_exit(root, monkeypatch, *, outcomes=None, upstream='success'):
    from scripts.a42331_ci_evidence import main

    monkeypatch.chdir(root)
    monkeypatch.setattr(sys, 'argv', ['a42331_ci_evidence', 'collect'])
    monkeypatch.setenv('A42331_STEP_OUTCOMES', json.dumps(
        dict.fromkeys(PHASES, 'success') if outcomes is None else outcomes))
    monkeypatch.setenv('UPSTREAM_STATUS', upstream)
    with pytest.raises(SystemExit) as stopped:
        main()
    return stopped.value.code


def test_skip_AC02_AC14_exact_raw_approved_preserves_counts(tmp_path, monkeypatch):
    root, output, path = policy_prepare(tmp_path, monkeypatch,
        [(APPROVED_CLASS, APPROVED_NAME, APPROVED_REASON)])
    result = collect(root, output, outcomes=dict.fromkeys(PHASES, 'success'), upstream='success')
    assert result['status'] == 'COMPLETE' and result['evidence_complete']
    assert result['full_test_counts'] == dict(tests=1, failures=0, errors=0, skipped=1)
    assert result['skip_policy_status'] == 'PASS' and result['approved_skip_count'] == 1
    assert len(ET.parse(path).findall('.//skipped')) == 1
    assert APPROVED_REASON not in path.read_text()
    assert not any(result[k] for k in
                   ('capacity_ready', 'performance_eligible', 'production_read_authorized'))
    assert policy_cli_exit(root, monkeypatch) == 0


@pytest.mark.parametrize('cases', [
    [('unknown.Class', APPROVED_NAME, APPROVED_REASON)],
    [(APPROVED_CLASS, 'test_unknown', APPROVED_REASON)],
    [(APPROVED_CLASS, APPROVED_NAME, 'wrong')],
    [(APPROVED_CLASS, APPROVED_NAME, 'MISSING_ATTRIBUTE')],
    [(APPROVED_CLASS, APPROVED_NAME, APPROVED_REASON+' ')],
    [(APPROVED_CLASS, APPROVED_NAME, APPROVED_REASON), ('other.Class', 'test_x', 'wrong')],
    [(APPROVED_CLASS, APPROVED_NAME, APPROVED_REASON)]*2,
    [(APPROVED_CLASS, APPROVED_NAME, None),
     (APPROVED_CLASS, APPROVED_NAME, APPROVED_REASON)],
    [(APPROVED_CLASS+'private-password', APPROVED_NAME, 'private-password SQL')],
])
def test_skip_AC03_AC04_AC05_AC06_AC12_reject_raw(tmp_path, monkeypatch, cases):
    root, output, _ = policy_prepare(tmp_path, monkeypatch, cases)
    result = collect(root, output, outcomes=dict.fromkeys(PHASES, 'success'), upstream='success')
    assert result['status'] == 'INCOMPLETE' and result['evidence_complete']
    assert result['skip_policy_status'] == 'REJECT'
    assert result['first_failure_code'] == 'A42331_SKIP_POLICY_REJECTED'
    assert not any(result[k] for k in
                   ('capacity_ready', 'performance_eligible', 'production_read_authorized'))
    assert 'private-password' not in ''.join(p.read_text() for p in output.iterdir())
    assert policy_cli_exit(root, monkeypatch) == 1


def test_skip_AC13_pre_sanitized_missing_proof_never_id_only(tmp_path, monkeypatch):
    root, output, path = policy_prepare(tmp_path, monkeypatch,
        [(APPROVED_CLASS, APPROVED_NAME, APPROVED_REASON)])
    sanitize_junit(path)  # Plain sanitizer deliberately issues no provenance.
    result = collect(root, output, outcomes=dict.fromkeys(PHASES, 'success'), upstream='success')
    assert result['status'] == 'INCOMPLETE' and result['evidence_complete']
    assert result['skip_policy_status'] == 'REJECT'
    assert policy_cli_exit(root, monkeypatch) == 1


def test_skip_authenticated_plugin_handoff_repeat_and_tamper(tmp_path, monkeypatch):
    from scripts import a42331_ci_evidence as evidence
    root, output, path = policy_prepare(tmp_path, monkeypatch,
        [(APPROVED_CLASS, APPROVED_NAME, APPROVED_REASON)])
    evidence.sanitize_junit_for_pytest(path, root=root)
    first = collect(root, output, outcomes=dict.fromkeys(PHASES, 'success'), upstream='success')
    assert first['status'] == 'COMPLETE' and first['approved_skip_count'] == 1
    assert collect(root, output, outcomes=dict.fromkeys(PHASES, 'success'),
                   upstream='success')['status'] == 'COMPLETE'
    path.write_bytes(path.read_bytes().replace(b'time="0.01"', b'time="0.02"'))
    changed = collect(root, output, outcomes=dict.fromkeys(PHASES, 'success'), upstream='success')
    assert changed['skip_policy_status'] == 'REJECT' and changed['status'] == 'INCOMPLETE'


def test_skip_AC10_targeted_skip_always_rejects(tmp_path, monkeypatch):
    root, output, _ = policy_prepare(tmp_path, monkeypatch, [('tests.safe', 'test_ok', None)])
    skip_fixture(root/'.codex_tmp/a42331-targeted.xml',
                 [(APPROVED_CLASS, APPROVED_NAME, APPROVED_REASON)])
    result = collect(root, output, outcomes=dict.fromkeys(PHASES, 'success'), upstream='success')
    assert result['evidence_complete'] and result['status'] == 'INCOMPLETE'
    assert result['skip_policy_status'] == 'REJECT'
    assert policy_cli_exit(root, monkeypatch) == 1


def test_skip_old_pass_proof_cannot_survive_same_safe_bytes_new_input(tmp_path, monkeypatch):
    from scripts import a42331_ci_evidence as evidence
    root, output, path = policy_prepare(tmp_path, monkeypatch,
        [(APPROVED_CLASS, APPROVED_NAME, APPROVED_REASON)])
    evidence.sanitize_junit_for_pytest(path, root=root)
    assert evidence._decision(path, root, path.read_bytes())[1] == ('PASS', 1)
    prior = path.read_bytes()
    skip_fixture(path, [(APPROVED_CLASS, APPROVED_NAME, 'private-password SQL')])
    def broken(*_args, **_kwargs):
        raise OSError('private-password')
    monkeypatch.setattr(evidence, '_issue', broken)
    evidence.sanitize_junit_for_pytest(path, root=root)
    assert path.read_bytes() == prior  # Same safe content must NOT revive old PASS.
    result = collect(root, output, outcomes=dict.fromkeys(PHASES, 'success'), upstream='success')
    assert result['status'] == 'INCOMPLETE' and result['skip_policy_status'] == 'REJECT'


@pytest.mark.parametrize('mutation', ['mac', 'payload', 'missing', 'run', 'attempt', 'head'])
def test_skip_authenticated_proof_forgery_or_context_replay_rejected(
        tmp_path, monkeypatch, mutation):
    from scripts import a42331_ci_evidence as evidence
    root, output, path = policy_prepare(tmp_path, monkeypatch,
        [(APPROVED_CLASS, APPROVED_NAME, APPROVED_REASON)])
    evidence.sanitize_junit_for_pytest(path, root=root)
    assert evidence._decision(path, root, path.read_bytes())[1] == ('PASS', 1)
    directory = evidence._store(evidence._context(root), create=False)
    proof = evidence._proof_path(directory, '.codex_tmp/m17_1_2-full.xml')
    if mutation in ('mac', 'payload'):
        value = json.loads(proof.read_bytes())
        if mutation == 'mac':
            value['mac'] = '0'*64
        else:
            value['payload']['raw_sha256'] = '0'*64
        proof.write_text(json.dumps(value))
    elif mutation == 'missing':
        proof.unlink()  # Only this test's own proof, never a shared key.
    elif mutation == 'run':
        monkeypatch.setenv('GITHUB_RUN_ID', 'different-run')
    elif mutation == 'attempt':
        monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '999')
    else:
        monkeypatch.setattr(evidence.subprocess, 'check_output', lambda *a, **k: 'b'*40)
        monkeypatch.setenv('GITHUB_SHA', 'b'*40)
    result = collect(root, output, outcomes=dict.fromkeys(PHASES, 'success'), upstream='success')
    assert result['status'] == 'INCOMPLETE' and result['skip_policy_status'] == 'REJECT'
    assert result['full_test_counts']['skipped'] == 1


@pytest.mark.parametrize('kind', ['failure', 'error'])
def test_skip_AC07_success_with_actual_failure_or_error_rejects(tmp_path, monkeypatch, kind):
    root, output, path = policy_prepare(tmp_path, monkeypatch,
        [(APPROVED_CLASS, APPROVED_NAME, APPROVED_REASON)])
    tree = ET.parse(path)
    suite = tree.getroot()
    suite.set('failures' if kind == 'failure' else 'errors', '1')
    ET.SubElement(suite.find('testcase'), kind).text = 'private-password SQL'
    tree.write(path, encoding='utf8', xml_declaration=True)
    result = collect(root, output, outcomes=dict.fromkeys(PHASES, 'success'), upstream='success')
    assert result['status'] == 'INCOMPLETE' and not result['evidence_complete']
    assert result['full_test_counts']['failures' if kind == 'failure' else 'errors'] == 1
    assert 'private-password' not in ''.join(p.read_text() for p in output.iterdir())
    assert policy_cli_exit(root, monkeypatch) == 1


@pytest.mark.parametrize('bad', ['skip-count', 'tests-count', 'missing', 'xml', 'doctype',
                                  'utf16-entity', 'too-large'])
def test_skip_AC08_AC09_invalid_mandatory_evidence_fails_closed(tmp_path, monkeypatch, bad):
    root, output, path = policy_prepare(tmp_path, monkeypatch,
        [(APPROVED_CLASS, APPROVED_NAME, APPROVED_REASON)])
    raw = path.read_bytes()
    if bad == 'missing':
        path.unlink()
    else:
        changed = {
            'skip-count': raw.replace(b'skipped="1"', b'skipped="0"'),
            'tests-count': raw.replace(b'tests="1"', b'tests="2"'),
            'xml': b'<broken>',
            'doctype': b'<!DOCTYPE x [<!ENTITY y "private-password">]><testsuites/>',
            'utf16-entity': (
                '<!DOCTYPE x [<!ENTITY y "private-password">]><testsuites/>'.encode('utf16')),
        }
        path.write_bytes(b'x'*50_000_001 if bad == 'too-large' else changed[bad])
    result = collect(root, output, outcomes=dict.fromkeys(PHASES, 'success'), upstream='success')
    assert result['status'] == 'INCOMPLETE' and not result['evidence_complete']
    assert result['first_failure_code'] == 'A42331_SAFE_EVIDENCE_INCOMPLETE'
    assert 'private-password' not in (output/'failure.json').read_text()
    assert policy_cli_exit(root, monkeypatch) == 1


def test_skip_AC15_original_lab_permission_and_bridge_stay_denied():
    import ast

    from scripts.r1_real_root_protocol import Refused, real_execution_bridge
    source = ROOT/'tests/integration/test_r1_integration_linux_mock_domain.py'
    tree = ast.parse(source.read_text())
    permission = next(n for n in tree.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'REVIEWED_LAB_PERMIT'
                              for t in n.targets))
    assert ast.literal_eval(permission.value) is None
    with pytest.raises(Refused, match='^R1_REAL_EXECUTION_NOT_AUTHORIZED$'):
        real_execution_bridge(authorized=True)


@pytest.mark.parametrize('where', ['classname', 'name'])
def test_skip_AC12_private_identifier_shaped_text_is_not_exported(tmp_path, monkeypatch, where):
    secret = 'OFFLINEPRIVATEPASSWORD'
    cls = secret if where == 'classname' else APPROVED_CLASS
    name = secret if where == 'name' else APPROVED_NAME
    root, output, path = policy_prepare(tmp_path, monkeypatch, [(cls, name, APPROVED_REASON)])
    result = collect(root, output, outcomes=dict.fromkeys(PHASES, 'success'), upstream='success')
    assert result['status'] == 'INCOMPLETE' and result['skip_policy_status'] == 'REJECT'
    assert secret not in ''.join(p.read_text() for p in output.iterdir())
    first = sanitize_junit(path)
    assert sanitize_junit(path) == first


def test_skip_AC11_failed_suite_cli_keeps_complete_failure_receipt(tmp_path,monkeypatch):
    root,output = prepare(tmp_path,monkeypatch)
    xml(root/'.codex_tmp/a42331-targeted.xml')
    xml(root/'.codex_tmp/m17_1_2-full.xml',failures=1)
    outcomes = dict.fromkeys(PHASES,'skipped') | dict(targeted='success',full_tests='failure')
    result = collect(root,output,outcomes=outcomes,upstream='failure')
    assert result['status'] == 'INCOMPLETE' and result['evidence_complete']
    assert result['steps']['runtime_browser'] == 'skipped'
    assert result['full_test_counts']['failures'] == 1
    assert (output/'m17_1_2-full.xml').is_file()
    assert json.loads((output/'failure.json').read_text()) == result
    assert policy_cli_exit(root, monkeypatch, outcomes=outcomes, upstream='failure') == 0


def test_skip_AC01_zero_skip_cli_success_and_real_failures_preserved(tmp_path,monkeypatch):
    root,output = prepare(tmp_path,monkeypatch)
    for name in ('a42331-targeted.xml','m17_1_2-full.xml'):
        xml(root/'.codex_tmp'/name)
    result = collect(root,output,outcomes=dict.fromkeys(PHASES,'success'),upstream='success')
    assert result['status'] == 'COMPLETE' and result['evidence_complete']
    assert policy_cli_exit(root, monkeypatch) == 0
    xml(root/'.codex_tmp/m17_1_2-full.xml',failures=1)
    result = collect(root,output,outcomes=dict.fromkeys(PHASES,'success'),upstream='success')
    assert not result['evidence_complete'] and result['status'] == 'INCOMPLETE'
