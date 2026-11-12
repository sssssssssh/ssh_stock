"""Report redaction only: never changes test outcomes, exceptions, selection or coverage."""

import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

from scripts.a42_artifacts import atomic
from scripts.a42331_ci_evidence import safe_identifier, sanitize_junit_for_pytest

ERRORS = []


def pytest_sessionstart(session):
    ERRORS.clear()


class SubtestJUnit:
    """pytest 9 counts subreports but coalesces their XML nodes unless finalized.

    Finalize each real subreport *after* the native XML hook. Do not alter any
    outcome, counter, node ID, exception or selection. Strict sanitizer stays intact.
    This adapter is version-specific and covered by real child pytest regressions.
    """

    def __init__(self, config):
        self.config = config

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_logreport(self, report):
        from _pytest.junitxml import xml_key

        subtest = type(report).__module__ == "_pytest.subtests" and hasattr(report, "context")
        if subtest and report.failed:
            report.longrepr = "A42331_TEST_FAILURE"
            report.sections = []
        yield
        xml = self.config.stash.get(xml_key, None)
        if subtest and xml is not None:
            xml.finalize(report)
            # Native teardown must not finalize the same subreport a second time.
            xml.open_reports[:] = [r for r in xml.open_reports if r is not report]


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    config.pluginmanager.register(SubtestJUnit(config), "a42331-subtest-junit")


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


_SAFE_OBSERVER_NODEID = (
    "tests/integration/test_a4233_observer_pg17.py::"
    "test_real_pg17_observer_role_has_no_business_data_or_maintenance_privileges"
)
_SAFE_OBSERVER_BLOB = "1655f824271a7abc2eda1017a04c2f5fd5175262"
_SAFE_OBSERVER_FUNCTION = "test_real_pg17_observer_role_has_no_business_data_or_maintenance_privileges"
_SAFE_OBSERVER_LINES = {
    128: "A_TABLE_PRIVILEGE",
    131: "B_ROLE_ATTRIBUTES",
    135: "C_OBSERVER_STATUS",
}


def safe_assertion_site(item, call):
    """Only a reviewed test's verified source line can produce a fixed safe site."""
    try:
        if item.nodeid != _SAFE_OBSERVER_NODEID:
            return "UNKNOWN"
        info = call.excinfo
        if info is None or info.type is not AssertionError:
            return "UNKNOWN"
        source = (Path(__file__).resolve().parents[1] /
                  "tests/integration/test_a4233_observer_pg17.py").resolve()
        raw = source.read_bytes().replace(b"\r\n", b"\n")
        header = ("blob " + str(len(raw)) + "\0").encode("ascii")
        if hashlib.sha1(header + raw).hexdigest() != _SAFE_OBSERVER_BLOB:
            return "UNKNOWN"
        for entry in reversed(list(info.traceback)):
            if (entry.frame.code.co_name == _SAFE_OBSERVER_FUNCTION
                    and Path(entry.path).resolve() == source):
                return _SAFE_OBSERVER_LINES.get(entry.lineno + 1, "UNKNOWN")
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    return "UNKNOWN"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    result = yield
    report = result.get_result()
    if report.failed:
        entry = dict(phase=report.when, **safe_error(call.excinfo.value),
                     test_identity_sha256=hashlib.sha256(item.nodeid.encode()).hexdigest(),
                     assertion_site=safe_assertion_site(item, call))
        ERRORS.append(entry)
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
    name = safe_identifier(Path(path).stem if path else 'no-junit')
    sanitized = False
    try:
        if path:
            sanitize_junit_for_pytest(Path(path), root=Path.cwd())
            sanitized = True
    finally:
        # The bounded first-error evidence survives even if XML validation fails.
        # No exception value, traceback, parameter, SQL or failed XML is copied.
        atomic(Path('.codex_tmp/a42331-errors')/(name+'.json'),dict(
            schema_version='a42331.pytest-failures.v1',evidence_kind='DIAGNOSTIC_ONLY',
            head_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            run_id=os.environ.get('GITHUB_RUN_ID','local'),
            attempt=os.environ.get('GITHUB_RUN_ATTEMPT','1'),
            failures=ERRORS,junit_sanitized=sanitized,capacity_ready=False,
            performance_eligible=False,production_read_authorized=False))


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(terminalreporter):
    # Only finite, reviewed labels are visible. No traceback or exception text.
    for entry in ERRORS:
        if entry.get("assertion_site") in _SAFE_OBSERVER_LINES.values():
            terminalreporter.write_line("A42331_SAFE_ASSERTION_SITE=" + entry["assertion_site"])
