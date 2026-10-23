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


def test_success_requires_real_full_counts_and_never_hides_failures(tmp_path,monkeypatch):
    root,output = prepare(tmp_path,monkeypatch)
    for name in ('a42331-targeted.xml','m17_1_2-full.xml'):
        xml(root/'.codex_tmp'/name)
    result = collect(root,output,outcomes=dict.fromkeys(PHASES,'success'),upstream='success')
    assert result['status'] == 'COMPLETE' and result['evidence_complete']
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
        capture_output=True,text=True,timeout=30)
    assert result.returncode == 1, result.stdout
    assert 'private-password' not in result.stdout+result.stderr+target.read_text()
    assert len(ET.parse(target).findall('.//testcase')) == 2
    assert len(ET.parse(target).findall('.//failure')) == 1
    assert safe_error(RuntimeError('private-password'))['failure_code'] == 'A42331_TEST_FAILURE'


def current():
    return yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())


def test_only_exact_reviewed_test_job_changes_and_every_gate_stays_frozen():
    value = current()
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
    assert required['if'] == 'always()' and required['with']['if-no-files-found'] == 'error'
