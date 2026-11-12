"""Safe CI assertion location contract; no PG17, worker, or network."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import a42331_pytest_safety as safety

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "tests/integration/test_a4233_observer_pg17.py"


def fake_case(line, *, nodeid=safety._SAFE_OBSERVER_NODEID, error=AssertionError,
              function=safety._SAFE_OBSERVER_FUNCTION, path=TARGET):
    entry = SimpleNamespace(
        lineno=line - 1,
        path=path,
        frame=SimpleNamespace(code=SimpleNamespace(co_name=function)),
    )
    item = SimpleNamespace(nodeid=nodeid)
    call = SimpleNamespace(excinfo=SimpleNamespace(type=error, traceback=[entry]))
    return item, call


@pytest.mark.parametrize(("line", "expected"), [
    (128, "A_TABLE_PRIVILEGE"),
    (131, "B_ROLE_ATTRIBUTES"),
    (135, "C_OBSERVER_STATUS"),
    (134, "UNKNOWN"),
    (129, "UNKNOWN"),
])
def test_reviewed_assertion_line_maps_only_to_finite_site(line, expected):
    assert safety.safe_assertion_site(*fake_case(line)) == expected


def test_target_source_matches_reviewed_git_blob():
    raw = TARGET.read_bytes().replace(b"\r\n", b"\n")
    header = ("blob " + str(len(raw)) + "\0").encode("ascii")
    assert hashlib.sha1(header + raw).hexdigest() == safety._SAFE_OBSERVER_BLOB


@pytest.mark.parametrize("changes", [
    {"nodeid": "tests/unit/test_secret.py::test_fail"},
    {"error": RuntimeError},
    {"function": "wrong_test_function"},
    {"path": ROOT / "tests/unit/test_a42331_ci_evidence.py"},
])
def test_wrong_target_is_always_unknown(changes):
    assert safety.safe_assertion_site(*fake_case(128, **changes)) == "UNKNOWN"


def test_no_traceback_or_source_drift_stays_unknown(monkeypatch):
    item, call = fake_case(128)
    call.excinfo.traceback = []
    assert safety.safe_assertion_site(item, call) == "UNKNOWN"
    item, call = fake_case(128)
    monkeypatch.setattr(safety, "_SAFE_OBSERVER_BLOB", "0" * 40)
    assert safety.safe_assertion_site(item, call) == "UNKNOWN"


def test_terminal_summary_prints_only_preapproved_label():
    printed = []
    reporter = SimpleNamespace(write_line=printed.append)
    try:
        safety.ERRORS[:] = [
            {"assertion_site": "B_ROLE_ATTRIBUTES", "error_type": "AssertionError"},
            {"assertion_site": "private password SQL", "error_type": "AssertionError"},
            {"assertion_site": "UNKNOWN", "error_type": "AssertionError"},
        ]
        safety.pytest_terminal_summary(reporter)
        assert printed == ["A42331_SAFE_ASSERTION_SITE=B_ROLE_ATTRIBUTES"]
    finally:
        safety.ERRORS.clear()
