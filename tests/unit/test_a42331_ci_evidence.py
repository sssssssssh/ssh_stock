"""Failure/success/skip evidence without databases, network or test outcome changes."""

import copy
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from scripts.a42331_ci_contract import BASELINE, normalize_test_job
from scripts.a42331_ci_evidence import PHASES, collect, sanitize_junit
from scripts.a42331_pytest_safety import safe_error

ROOT = Path(__file__).resolve().parents[2]


def xml(path, *, failures=0, errors=0, skipped=0):
    path.parent.mkdir(parents=True,exist_ok=True)
    states = '<failure>postgresql://secret sql parameters</failure>'*failures
    states += '<error>private password</error>'*errors+'<skipped>private</skipped>'*skipped
    path.write_text(f'<testsuites><testsuite tests="1" failures="{failures}" errors="{errors}" '
        f'skipped="{skipped}" hostname="private">'
        '<properties><property value="secret"/></properties>'
        '<testcase classname="tests.unit.test_safe" name="test_case[private-token]" time="0.01">'
        f'{states}<system-out>private rows</system-out></testcase></testsuite></testsuites>')


@pytest.mark.parametrize('state',[{},dict(failures=1),dict(errors=1),dict(skipped=1)])
def test_full_junit_status_counts_retained_but_secrets_removed(tmp_path,state):
    path = tmp_path/'tests.xml'
    xml(path,**state)
    receipt = sanitize_junit(path)
    assert receipt['counts'] == dict(tests=1,failures=0,errors=0,skipped=0,**{}) | state
    safe = path.read_text()
    assert all(s not in safe for s in ('private','secret','password','system-out','properties'))
    assert len(ET.fromstring(safe).findall('.//testcase')) == 1
    assert sanitize_junit(path) == receipt  # Canonical, stable hash on repeated safe exports.


@pytest.mark.parametrize('content',[
    'not xml','<!DOCTYPE a [<!ENTITY b "private">]><testsuites/>',
    '<testsuite tests="2" failures="0" errors="0" skipped="0"><testcase/></testsuite>',
    '<testsuites/>',
])
def test_corrupt_or_forged_junit_fails_closed_without_source_text(tmp_path,content):
    path = tmp_path/'tests.xml'
    path.write_text(content)
    with pytest.raises(RuntimeError,match='^A42331_JUNIT_[A-Z_]+$'):
        sanitize_junit(path)


def prepare(tmp_path, monkeypatch):
    # Git identity remains actual repository identity, but files live in a fresh isolated tmpdir.
    monkeypatch.setattr('scripts.a42331_ci_evidence.subprocess.check_output',
                        lambda *a,**k: 'a'*40)
    monkeypatch.setenv('GITHUB_SHA','a'*40)
    return tmp_path, tmp_path/'safe'


def test_failed_full_suite_keeps_complete_failure_receipt_and_skipped_phases(tmp_path,monkeypatch):
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


def test_success_requires_real_full_counts_and_never_hides_failures(tmp_path,monkeypatch):
    root,output = prepare(tmp_path,monkeypatch)
    for name in ('a42331-targeted.xml','m17_1_2-full.xml'):
        xml(root/'.codex_tmp'/name)
    result = collect(root,output,outcomes=dict.fromkeys(PHASES,'success'),upstream='success')
    assert result['status'] == 'COMPLETE' and result['evidence_complete']
    assert policy_cli_exit(root, monkeypatch) == 0
    xml(root/'.codex_tmp/m17_1_2-full.xml',failures=1)
    result = collect(root,output,outcomes=dict.fromkeys(PHASES,'success'),upstream='success')
    assert not result['evidence_complete'] and result['status'] == 'INCOMPLETE'


def test_missing_mandatory_junit_still_emits_fixed_failure_receipt(tmp_path,monkeypatch):
    root,output = prepare(tmp_path,monkeypatch)
    result = collect(root,output,outcomes=dict.fromkeys(PHASES,'failure'),upstream='failure')
    assert not result['evidence_complete']
    assert result['first_failure_code'] == 'A42331_SAFE_EVIDENCE_INCOMPLETE'
    assert (output/'failure.json').is_file()


def test_reporting_plugin_preserves_failed_exit_and_sanitizes_all_cases(tmp_path):
    # This tiny child pytest is deliberately red. It does not rerun any project workload.
    source = tmp_path/'test_probe.py'
    source.write_text('def test_ok():\n    assert True\n\ndef test_fail():\n'
                      '    raise RuntimeError("private-password sql parameters")\n')
    target = tmp_path/'tests.xml'
    result = subprocess.run([sys.executable,'-m','pytest','-p','scripts.a42331_pytest_safety',
        '--noconftest','--override-ini=addopts=','--tb=no','--show-capture=no','-rN',
        str(source),'--junitxml='+str(target)],cwd=ROOT,env=os.environ.copy(),
        stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=30)
    assert result.returncode == 1, result.stdout
    assert 'private-password' not in result.stdout+result.stderr+target.read_text()
    assert len(ET.parse(target).findall('.//testcase')) == 2
    assert len(ET.parse(target).findall('.//failure')) == 1
    assert safe_error(RuntimeError('private-password'))['failure_code'] == 'A42331_TEST_FAILURE'


def current():
    return yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())


def test_only_exact_reviewed_test_job_changes_and_every_gate_stays_frozen():
    value = current()
    from scripts.ci_opt_contract import restore

    value = restore('ci.yml', value)
    value['jobs']['test'] = normalize_test_job(value['jobs']['test'])
    before = yaml.safe_load(subprocess.check_output(
        ['git','show',BASELINE+':.github/workflows/ci.yml'],cwd=ROOT))
    assert value == before


@pytest.mark.parametrize('mutation',['coverage','skip','gate','timeout'])
def test_unreviewed_test_job_changes_are_rejected(mutation):
    job = copy.deepcopy(current()['jobs']['test'])
    step = next(s for s in job['steps'] if s.get('id') == 'full_tests')
    if mutation == 'coverage':
        step['run'] = step['run'].replace('under=70','under=1')
    elif mutation == 'skip':
        step['if'] = 'false'
    elif mutation == 'gate':
        step['continue-on-error'] = True
    else:
        job['timeout-minutes'] = 1
    with pytest.raises(RuntimeError,match='A42331_UNREVIEWED_CI_TEST_JOB'):
        normalize_test_job(job)


def test_skipped_optional_uploads_are_guarded_and_mandatory_evidence_not_optional():
    steps = current()['jobs']['test']['steps']
    uploads = {s['with']['name']:s for s in steps if s.get('uses') == 'actions/upload-artifact@v4'}
    for name,phase in [('data-queue-container-acceptance','data_queue'),
                       ('runtime-reliability-synthetic-browser','runtime_browser')]:
        assert 'steps.'+phase+'.outcome' in uploads[name]['if']
        assert "'success' && 'error' || 'ignore'" in uploads[name]['with']['if-no-files-found']
    required = next(s for name,s in uploads.items() if name.startswith('a42331-safe-ci-'))
    from scripts.ci_opt_contract import guarded

    assert required['if'] == guarded('always()')
    assert required['with']['if-no-files-found'] == 'error'


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
