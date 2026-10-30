"""Diagnostics must not weaken failure, write test data or export private values."""

import json
import math
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from scripts import worker02_r5_diagnostics as diag

ROOT = Path(__file__).resolve().parents[2]


def test_node_parameters_are_hashed_never_exported():
    node = diag.safe_node("tests/test_x.py::test_y[PRIVATE_DSN_PASSWORD]")
    assert node["node"] == "tests/test_x.py::test_y"
    assert "PRIVATE" not in json.dumps(node)
    assert node != diag.safe_node("tests/test_x.py::test_y[another-case]")


def test_observation_keeps_failure_facts_but_rejects_arbitrary_fields():
    raw = {"status": "INCOMPLETE_OBSERVABILITY", "first_failure_code": "A4233_SQL_TIMEOUT",
        "physical_verified": True, "restricted_readonly_verified": False,
        "ticks": [{"private": "PRIVATE_DSN"}], "worker_joined": True,
        "password": "PRIVATE_PASSWORD", "failed_tick": {"windows": [
            {"view": "activity", "wall_ms": 101, "query": "PRIVATE_SQL"}]}}
    clean = diag.observation(raw)
    assert clean["status"] == raw["status"]
    assert clean["first_failure_code"] == "A4233_SQL_TIMEOUT"
    assert clean["restricted_readonly_verified"] is False
    assert clean["cleanup_complete"] is None
    assert clean["tick_count"] == 1
    assert clean["failed_windows"] == [{"view": "activity", "wall_ms": 101}]
    assert "PRIVATE" not in json.dumps(clean)
    assert raw["password"] == "PRIVATE_PASSWORD"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "PRIVATE", 10**1000])
def test_invalid_metrics_do_not_become_zero(value):
    assert diag.finite(value) is None
    assert diag.finite(0) == 0


def test_statistics_preserves_real_timestamp_drift_without_raw_settings():
    timestamp = datetime(2026, 10, 29, tzinfo=UTC)
    sample = {"relations": [{"relname": "stock_trade_status_daily", "reltuples": 4,
        "relpages": 1, "statistic_count": 12, "last_analyze": timestamp,
        "statistic_sha256": "a" * 64, "private": "PRIVATE"}],
        "active_autovacuum_workers": 1, "settings": {"password": "PRIVATE"}}
    value = {"preflight_attempts": [{"table_autovacuum_disabled": False,
        "valid": False, "snapshots": [sample] * 8}] * 4, "private": "PRIVATE"}
    clean = diag.statistics(value)
    assert len(clean["samples"]) == 8
    row = clean["samples"][0]
    assert row["active_autovacuum_workers"] == 1 and row["valid"] is False
    assert row["relations"][0]["last_analyze"] == timestamp.isoformat()
    assert "PRIVATE" not in json.dumps(clean)
    assert diag.statistics({"preflight_attempts": "PRIVATE"})["status"] == "INVALID_EVIDENCE"
    sample["relations"] = None
    assert diag.statistics(value)["status"] == "INVALID_EVIDENCE"


@pytest.mark.parametrize("url", ["postgresql://x@public.example/business",
                                "postgresql://x@127.0.0.1/business"])
def test_non_owned_target_refuses_before_any_connection(monkeypatch, url):
    from sqlalchemy.engine import make_url

    monkeypatch.setattr("sqlalchemy.create_engine", lambda *a, **kw: pytest.fail("No connection"))
    item = NS(funcargs={"observer_pg17": (NS(url=make_url(url)), [])})
    assert diag.database_snapshot(item) == {"status": "UNCONFIRMED_TARGET"}


def test_snapshot_failure_is_explicit_and_does_not_export_exception(monkeypatch):
    def unavailable(_):
        raise RuntimeError("PRIVATE_DSN_AND_PASSWORD")

    monkeypatch.setattr(diag, "database_snapshot", unavailable)
    value = diag.context(NS(funcargs={}, fixturenames=["safe", "PRIVATE://bad"]))
    assert value["database"]["status"] == "UNCONFIRMED_SNAPSHOT_FAILURE"
    assert "PRIVATE" not in json.dumps(value)


def test_artifact_failure_cannot_result_in_a_successful_session(monkeypatch, tmp_path):
    def unavailable(*_):
        raise OSError("PRIVATE_PATH")

    monkeypatch.setattr(diag, "atomic", unavailable)
    evidence = diag.Evidence(tmp_path)
    session = NS(exitstatus=0)
    evidence.pytest_sessionfinish(session, 0)
    assert evidence.capture_failed and session.exitstatus == pytest.ExitCode.TESTS_FAILED
    session.exitstatus = pytest.ExitCode.INTERRUPTED
    evidence.pytest_sessionfinish(session, pytest.ExitCode.INTERRUPTED)
    assert session.exitstatus == pytest.ExitCode.INTERRUPTED


@pytest.mark.parametrize("directory", ["outside", "../outside"])
def test_evidence_path_cannot_escape_test_artifacts(tmp_path, directory):
    config = NS(rootpath=tmp_path, getoption=lambda _: directory)
    with pytest.raises(pytest.UsageError, match="OUTSIDE_TEST_ARTIFACTS"):
        diag.pytest_configure(config)


def test_evidence_must_not_overwrite_old_results(tmp_path):
    folder = tmp_path / ".codex_tmp" / "run"
    folder.mkdir(parents=True)
    (folder / "result.json").write_text("old immutable evidence", encoding="utf-8")
    with pytest.raises(pytest.UsageError, match="NOT_EMPTY"):
        diag.pytest_configure(NS(rootpath=tmp_path, getoption=lambda _: str(folder)))
    assert (folder / "result.json").read_text() == "old immutable evidence"


def test_default_plugin_is_disabled():
    diag.pytest_configure(NS(getoption=lambda _: None))


def test_real_pytest_failure_is_not_rewritten_by_diagnostics(tmp_path):
    path, function = sorted(diag.WATCH)[0].split("::")
    test = tmp_path / path
    test.parent.mkdir(parents=True)
    test.write_text(f"def {function}():\n    assert False, 'PRIVATE_FAILURE_TEXT'\n",
                    encoding="utf-8")
    environment = dict(os.environ, PYTHONPATH=str(ROOT), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    result = subprocess.run([sys.executable, "-m", "pytest", "-p",
        "scripts.worker02_r5_diagnostics", "--r5-evidence-dir=.codex_tmp/run", "--tb=no", "-q"],
        cwd=tmp_path, env=environment, capture_output=True, timeout=30)
    assert result.returncode == 1
    report = json.loads((tmp_path / ".codex_tmp/run/result.json").read_text())
    assert report["original_exitstatus"] == 1 and report["watched_nodes"] == 1
    records = [p for p in (tmp_path / ".codex_tmp/run").glob("*.json")
               if p.name not in {"collection.json", "result.json"}]
    record = json.loads(records[0].read_text())
    assert record["call"] == "FAILED" and record["first_error_type"] == "AssertionError"
    assert "PRIVATE_FAILURE_TEXT" not in records[0].read_text()
    assert not report["qualifies"]


def test_finite_zero_and_nan_are_not_conflated():
    assert diag.finite(0.0) == 0.0
    assert diag.finite(math.nan) is None


def test_cache_probe_failure_does_not_mask_the_test_or_export_exception(monkeypatch):
    def unavailable():
        raise RuntimeError("PRIVATE_CACHE_DETAIL")

    monkeypatch.setattr("app.core.config.get_settings", NS(cache_info=unavailable))
    result = diag.context(NS(funcargs={}, fixturenames=[]))
    assert result["settings_cache"] == "UNCONFIRMED_CACHE"
    assert "PRIVATE" not in json.dumps(result)


def test_source_identity_uses_collected_project_not_invocation_directory(monkeypatch, tmp_path):
    def git(command, **kwargs):
        assert command == ["git", "rev-parse", "HEAD"]
        assert kwargs["cwd"] == tmp_path / "collected-project"
        return "a" * 40 + "\n"

    monkeypatch.setattr(diag.subprocess, "check_output", git)
    evidence = diag.Evidence(tmp_path / "output")
    evidence.pytest_sessionfinish(NS(config=NS(rootpath=tmp_path / "collected-project")), 0)
    result = json.loads((tmp_path / "output/result.json").read_text())
    assert result["source_sha"] == "a" * 40 and not result["qualifies"]
