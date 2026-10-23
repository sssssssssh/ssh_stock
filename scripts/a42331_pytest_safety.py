"""Report redaction only: never changes test outcomes, exceptions, selection or coverage."""

import os
import re
import subprocess
from pathlib import Path

import pytest

from scripts.a42_artifacts import atomic
from scripts.a42331_ci_evidence import safe_identifier, sanitize_junit

ERRORS = []


def safe_error(error):
    original = getattr(error,'orig',error)
    name = type(original).__name__
    state = getattr(original,'sqlstate',None)
    code = getattr(error,'code',None)
    if code is None and isinstance(error,RuntimeError):
        message = str(error)
        code = message if re.fullmatch(r'A4233[1]?_[A-Z0-9_]{1,80}',message) else None
    return dict(error_type=name if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,80}',name)
                else 'REDACTED_ERROR_TYPE',
        sqlstate=state if isinstance(state,str) and re.fullmatch(r'[A-Z0-9]{5}',state) else None,
        failure_code=code if isinstance(code,str)
            and re.fullmatch(r'A4233[1]?_[A-Z0-9_]{1,80}',code) else 'A42331_TEST_FAILURE')


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    result = yield
    report = result.get_result()
    if report.failed:
        ERRORS.append(dict(phase=report.when,**safe_error(call.excinfo.value)))
        report.longrepr = 'A42331_TEST_FAILURE'
        report.sections = []


def pytest_collectreport(report):
    if report.failed:
        ERRORS.append(dict(phase='collect',error_type='CollectionError',sqlstate=None,
                           failure_code='A42331_COLLECTION_FAILURE'))
        report.longrepr = 'A42331_COLLECTION_FAILURE'
        report.sections = []


def pytest_unconfigure(config):
    path = getattr(config.option,'xmlpath',None)
    if path and Path(path).is_file():
        sanitize_junit(Path(path))
    name = safe_identifier(Path(path).stem if path else 'no-junit')
    atomic(Path('.codex_tmp/a42331-errors')/(name+'.json'),dict(
        schema_version='a42331.pytest-failures.v1',evidence_kind='DIAGNOSTIC_ONLY',
        head_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        run_id=os.environ.get('GITHUB_RUN_ID','local'),attempt=os.environ.get('GITHUB_RUN_ATTEMPT','1'),
        failures=ERRORS,capacity_ready=False,performance_eligible=False,
        production_read_authorized=False))
