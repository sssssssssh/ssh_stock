"""Bounded real pytest subprocesses; no database, Worker or Actions execution."""

import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts.a42331_ci_evidence import PHASES, collect, sanitize_junit

ROOT = Path(__file__).resolve().parents[2]
SECRET = "OFFLINE_PRIVATE_SENTINEL"


def child(tmp_path, source, *, corrupt=False):
    test = tmp_path / "test_probe.py"
    test.write_text(source)
    xml = tmp_path / "r1_v2_probe.xml"
    extra = []
    environment = os.environ.copy()
    if corrupt:
        (tmp_path / "corrupt_junit.py").write_text(
            'import pytest\nfrom pathlib import Path\n'
            '@pytest.hookimpl(trylast=True)\n'
            'def pytest_sessionfinish(session):\n'
            ' Path(session.config.option.xmlpath).write_text("<broken>")\n')
        extra = ["-p", "corrupt_junit"]
        environment["PYTHONPATH"] = str(tmp_path) + os.pathsep + str(ROOT)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "scripts.a42331_pytest_safety",
         *extra,
         "--noconftest", "--override-ini=addopts=", "--tb=no", "--show-capture=no", "-rN",
         str(test), "--junitxml=" + str(xml)], cwd=ROOT,
        env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
    return result, xml


@pytest.mark.parametrize("bad_subtest", [False, True])
def test_real_subtests_have_independent_xml_nodes_without_forgiving_counts(tmp_path, bad_subtest):
    source = ('import unittest\nclass Probe(unittest.TestCase):\n'
              ' def test_subtests(self):\n  for i in range(2):\n'
              f'   with self.subTest(i=i): self.assertTrue({not bad_subtest!r})\n'
              'def test_fail():\n raise RuntimeError("' + SECRET + '")\n')
    result, xml = child(tmp_path, source)
    assert result.returncode == 1
    assert "A42331_JUNIT_SANITIZATION_FAILED" not in result.stderr
    receipt = sanitize_junit(xml)
    cases = ET.parse(xml).findall(".//testcase")
    assert receipt["counts"]["tests"] == len(cases) == 4
    assert receipt["counts"]["failures"] == (3 if bad_subtest else 1)
    assert SECRET not in result.stdout + result.stderr + xml.read_text()


def test_failed_subprocess_retains_receipt_and_failure_with_exact_identity(tmp_path, monkeypatch):
    result, xml = child(tmp_path, 'def test_ok():\n assert True\n'
                        'def test_fail():\n raise RuntimeError("' + SECRET + '")\n')
    assert result.returncode == 1
    raw_hash = hashlib.sha256(xml.read_bytes()).hexdigest()
    receipt = ROOT / ".codex_tmp/a42331-errors/r1_v2_probe.json"
    evidence = json.loads(receipt.read_text())
    assert evidence["failures"][0]["error_type"] == "RuntimeError"
    assert evidence["junit_sanitized"] is True
    assert evidence["failures"][0]["test_identity_sha256"]
    monkeypatch.setattr("scripts.a42331_ci_evidence.subprocess.check_output",
                        lambda *a, **k: "a"*40)
    monkeypatch.setenv("GITHUB_SHA", "a"*40)
    for name in ("m17_1_2-full.xml", "a42331-targeted.xml"):
        dest = tmp_path / ".codex_tmp" / name
        dest.parent.mkdir(exist_ok=True)
        dest.write_bytes(xml.read_bytes())
    output = tmp_path / "a42331-ci"
    value = collect(tmp_path, output, outcomes=dict.fromkeys(PHASES, "skipped") |
                    {"full_tests": "failure", "targeted": "failure"}, upstream="failure")
    assert value["evidence_complete"] is True and value["status"] == "INCOMPLETE"
    assert value["full_test_counts"] == dict(tests=2, failures=1, errors=0, skipped=0)
    assert raw_hash == value["files"]["m17_1_2-full.xml"]["sha256"]
    for path in [*receipt.parent.glob("*.json"), *output.iterdir()]:
        assert SECRET not in path.read_text()


def test_corrupt_junit_cannot_suppress_original_failure_receipt(tmp_path):
    result, _ = child(tmp_path,
        'def test_fail():\n raise RuntimeError("'+SECRET+'")\n', corrupt=True)
    assert result.returncode != 0
    assert "A42331_JUNIT_SANITIZATION_FAILED" in result.stderr
    evidence = json.loads((ROOT / ".codex_tmp/a42331-errors/r1_v2_probe.json").read_text())
    assert evidence["junit_sanitized"] is False
    assert evidence["failures"][0]["error_type"] == "RuntimeError"
    assert SECRET not in result.stdout + result.stderr + json.dumps(evidence)


@pytest.mark.parametrize("source", [
    "import no_such_offline_module\n",
    'import pytest\n@pytest.fixture\ndef bad():\n raise RuntimeError("'+SECRET+'")\n'
    'def test_setup(bad):\n pass\n',
    'import pytest\n@pytest.fixture\ndef bad():\n yield\n raise RuntimeError("'+SECRET+'")\n'
    'def test_teardown(bad):\n pass\n',
])
def test_collection_setup_teardown_failures_preserved(tmp_path, source):
    result, xml = child(tmp_path, source)
    assert result.returncode in (1, 2)
    receipt = sanitize_junit(xml)
    assert receipt["counts"]["errors"] == 1
    assert SECRET not in result.stdout + result.stderr + xml.read_text()


def test_multiple_suites_properties_parameters_and_repeated_export(tmp_path):
    xml = tmp_path / "tests.xml"
    suite = ('<testsuite tests="2" failures="1" errors="0" skipped="1">'
             '<properties><property name="private" value="'+SECRET+'"/></properties>'
             '<testcase name="test_x['+SECRET+']"><failure>'+SECRET+'</failure>'
             '<system-out>'+SECRET+'</system-out></testcase><testcase><skipped/>'
             '</testcase></testsuite>')
    xml.write_text('<testsuites>'+suite+suite+'</testsuites>')
    receipt = sanitize_junit(xml)
    assert receipt["counts"] == dict(tests=4, failures=2, errors=0, skipped=2)
    assert receipt == sanitize_junit(xml)
    assert SECRET not in xml.read_text()


@pytest.mark.parametrize("raw", [b"", b"<testsuites>",
    b'<!DOCTYPE x [<!ENTITY y "private">]><testsuites/>',
    b'<testsuite tests="9" failures="0" errors="0" skipped="0"><testcase/></testsuite>'])
def test_bad_or_forged_xml_still_fails_closed(tmp_path, raw):
    xml = tmp_path / "tests.xml"
    xml.write_bytes(raw)
    with pytest.raises(RuntimeError, match="A42331_JUNIT_"):
        sanitize_junit(xml)


@pytest.mark.parametrize('approved', [True, False])
def test_skip_real_plugin_to_real_collect_cli_authenticated_handoff(tmp_path, approved):
    # A private synthetic package supplies the exact full-suite ID. Both safety
    # plugins stay enabled; no business conftest, lab permit, OS domain or DB.
    from tests.unit.test_a42331_ci_evidence import APPROVED_REASON, skip_fixture

    lab = tmp_path/'lab'
    source = lab/'tests/integration/test_r1_integration_linux_mock_domain.py'
    source.parent.mkdir(parents=True)
    (lab/'tests/__init__.py').write_text('')
    (lab/'tests/integration/__init__.py').write_text('')
    reason = APPROVED_REASON if approved else SECRET
    source.write_text('import unittest\nclass LinuxLabTests(unittest.TestCase):\n'
        ' def test_linux_success_term_kill_owned_child(self):\n'
        '  self.skipTest('+repr(reason)+')\n')
    xml = lab/'.codex_tmp/m17_1_2-full.xml'
    xml.parent.mkdir()
    env = {k:v for k,v in os.environ.items() if not any(word in k.upper() for word in
        ('DATABASE_URL', 'TOKEN', 'SECRET', 'PASSWORD', 'PGHOST', 'PGPORT', 'PGUSER', 'PGPASS'))}
    env.update(PYTHONPATH=str(ROOT), GIT_DIR=str(ROOT/'.git'), GIT_WORK_TREE=str(ROOT),
               PYTHONDONTWRITEBYTECODE='1')
    args = [sys.executable, '-B', '-m', 'pytest', '-p', 'scripts.source_contract_pytest',
            '-p', 'scripts.a42331_pytest_safety', '--noconftest', '--tb=no', '--show-capture=no',
            '-rN', '-q', str(source), '--junitxml='+str(xml)]
    child_result = subprocess.run(args, cwd=lab, env=env, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=30)
    assert child_result.returncode == 0
    assert len(ET.parse(xml).findall('.//skipped')) == 1
    assert reason not in xml.read_text()
    skip_fixture(lab/'.codex_tmp/a42331-targeted.xml', [('tests.safe', 'test_ok', None)])
    env.update(A42331_STEP_OUTCOMES=json.dumps(dict.fromkeys(PHASES, 'success')),
               UPSTREAM_STATUS='success')
    result = subprocess.run([sys.executable, '-B', '-m', 'scripts.a42331_ci_evidence', 'collect'],
        cwd=lab, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
    assert result.returncode == (0 if approved else 1)
    value = json.loads((lab/'.codex_tmp/a42331-ci/failure.json').read_text())
    assert value['evidence_complete'] is True
    assert value['status'] == ('COMPLETE' if approved else 'INCOMPLETE')
    assert value['skip_policy_status'] == ('PASS' if approved else 'REJECT')
    assert value['full_test_counts'] == dict(tests=1, failures=0, errors=0, skipped=1)
    assert value['approved_skip_count'] == int(approved)
    assert value['full_skip_proof_source'] == 'AUTHENTICATED_PRIOR_SANITIZER'
    assert not any(value[k] for k in ('capacity_ready', 'performance_eligible',
                                     'production_read_authorized'))
    assert SECRET not in child_result.stdout+child_result.stderr+result.stdout+result.stderr
    assert SECRET not in ''.join(p.read_text() for p in (lab/'.codex_tmp/a42331-ci').iterdir())
