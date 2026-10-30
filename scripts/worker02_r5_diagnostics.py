"""Opt-in pytest evidence for two R4 failures; never changes a test outcome to PASS."""

import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections import deque
from datetime import date, datetime
from pathlib import Path

import pytest

from scripts.a42_artifacts import atomic

WATCH = frozenset((
    "tests/integration/test_a4233_observer_pg17.py::"
    "test_real_pg17_observer_role_has_no_business_data_or_maintenance_privileges",
    "tests/integration/test_tail_stability_pg17_a4232.py::"
    "test_conditional_table_control_is_limited_to_new_synthetic_relations",
))
TABLES = ("stock_opportunity_daily", "signal_forward_eval", "stock_trade_status_daily",
          "data_publication_row")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def safe_node(node):
    name = node.split("[", 1)[0].replace("\\", "/")
    return {"node": name if re.fullmatch(r"[A-Za-z0-9_./:-]+", name) else "UNSAFE_NODE",
            "identity_sha256": hashlib.sha256(node.encode()).hexdigest()}


def finite(value):
    if type(value) is int:
        return value if -(2**63) <= value < 2**63 else None
    return value if type(value) is float and math.isfinite(value) else None


def observation(value):
    if not isinstance(value, dict):
        return None
    result = {k: value.get(k) if type(value.get(k)) is bool else None for k in (
        "physical_verified", "restricted_readonly_verified", "worker_started", "worker_joined",
        "cleanup_complete")}
    state = value.get("status")
    result["status"] = state if state in (
        "COMPLETE_CONTRACT", "INCOMPLETE_OBSERVABILITY") else "UNCONFIRMED"
    code = value.get("first_failure_code")
    result["first_failure_code"] = code if isinstance(code, str) and re.fullmatch(
        r"A4233_[A-Z0-9_]{1,80}", code) else None
    ticks = value.get("ticks")
    result["tick_count"] = len(ticks) if isinstance(ticks, list) and len(ticks) <= 8 else None
    failed = value.get("failed_tick")
    windows = failed.get("windows", []) if isinstance(failed, dict) else []
    result["failed_windows"] = [
        {"view": w.get("view") if w.get("view") in ("activity", "tables", "indexes", "io")
         else "OTHER", "wall_ms": finite(w.get("wall_ms"))}
        for w in windows[:8] if isinstance(w, dict)] if isinstance(windows, list) else []
    return result


def statistics(value):
    if not isinstance(value, dict):
        return None
    samples = []
    if "preflight_attempts" not in value:
        return {"samples": None, "status": "NOT_INSTRUMENTED"}
    attempts = value["preflight_attempts"]
    if not isinstance(attempts, list):
        return {"samples": None, "status": "INVALID_EVIDENCE"}
    for attempt in attempts[:2]:
        if not isinstance(attempt, dict) or not isinstance(attempt.get("snapshots"), list):
            continue
        for sample in attempt["snapshots"][:4]:
            if not isinstance(sample, dict):
                continue
            relations = []
            raw = sample.get("relations", [])
            if not isinstance(raw, list):
                return {"samples": None, "status": "INVALID_EVIDENCE"}
            for row in raw[:4]:
                if not isinstance(row, dict) or row.get("relname") not in TABLES:
                    continue
                clean = {"table": row["relname"], **{k: finite(row.get(k)) for k in (
                    "reltuples", "relpages", "statistic_count")}}
                for key in ("last_analyze", "last_autoanalyze"):
                    stamp = row.get(key)
                    clean[key] = stamp.isoformat() if isinstance(stamp, (date, datetime)) else None
                sha = row.get("statistic_sha256")
                clean["statistic_sha256"] = sha if isinstance(sha, str) and re.fullmatch(
                    r"[0-9a-f]{64}", sha) else None
                relations.append(clean)
            samples.append({"controlled": attempt.get("table_autovacuum_disabled") is True,
                "valid": attempt.get("valid") if type(attempt.get("valid")) is bool else None,
                "active_autovacuum_workers": finite(sample.get("active_autovacuum_workers")),
                "relations": relations})
    return {"samples": samples, "status": "RECORDED"}


def database_snapshot(item):
    """Separate read-only connection; never changes a fixture's pooled session."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    from scripts.v14_test_database import verified_test_url

    observer = item.funcargs.get("observer_pg17")
    stability = item.funcargs.get("tiny_stability_database")
    if not observer and not stability:
        return {"status": "NOT_INSTRUMENTED"}
    engine = observer[0] if observer else stability[2]
    url = engine.url
    if (url.host not in ("127.0.0.1", "localhost") or not re.fullmatch(
            r"v14_[0-9a-f]{32}_test", url.database or "")):
        return {"status": "UNCONFIRMED_TARGET"}
    parent = verified_test_url()
    if (url.host, url.port) != (parent.host, parent.port):
        return {"status": "UNCONFIRMED_TARGET"}
    reader = create_engine(url, poolclass=NullPool, hide_parameters=True,
        isolation_level="AUTOCOMMIT", connect_args={"options":
            "-c default_transaction_read_only=on -c statement_timeout=500ms -c lock_timeout=100ms"})
    try:
        with reader.connect() as db:
            marker = db.scalar(text("SELECT current_setting('v14.test_instance',true)"))
            system = str(db.scalar(text("SELECT system_identifier FROM pg_control_system()")))
            if (marker != os.environ.get("V14_TEST_INSTANCE")
                    or system != os.environ.get("V14_TEST_SYSTEM_IDENTIFIER")):
                return {"status": "UNCONFIRMED_TARGET"}
            settings = dict(db.execute(text("SELECT name,setting FROM pg_settings WHERE name IN "
                "('transaction_read_only','statement_timeout','lock_timeout','autovacuum',"
                "'stats_fetch_consistency') ORDER BY name")).all())
            roles = []
            for role in observer[1][:2] if observer else ():
                if not re.fullmatch(r"a4233_(?:ob|no_stats)_[0-9a-f]{32}", role):
                    return {"status": "UNCONFIRMED_ROLE_IDENTITY"}
                stats = db.scalar(text("SELECT pg_has_role(:role,'pg_read_all_stats','MEMBER')"),
                                  {"role": role})
                privileges = {name: db.scalar(text("SELECT has_table_privilege(:role,:table,"
                    "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,MAINTAIN')"),
                    {"role": role, "table": "public." + name}) for name in TABLES}
                roles.append({"role_sha256": digest(role), "read_all_stats": stats,
                              "business_privileges": privileges})
            return {"status": "RECORDED_READ_ONLY", "settings": settings, "roles": roles,
                "idle_in_transaction": db.scalar(text("SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname=current_database() AND state='idle in transaction'"))}
    finally:
        reader.dispose()


def context(item):
    result = {"fixtures": [n for n in item.fixturenames if re.fullmatch(r"[A-Za-z0-9_]+", n)],
              "python_hash_seed": "NOT_RECORDED", "contexts": {}}
    seed = os.environ.get("PYTHONHASHSEED", "")
    if seed == "random" or re.fullmatch(r"[0-9]{1,10}", seed):
        result["python_hash_seed"] = seed
    for module, name in (("app.services.execution_diagnostics", "active_diagnostics"),
                         ("app.services.calculation_policy", "active_policy"),
                         ("app.services.job_execution", "current_execution")):
        loaded = sys.modules.get(module)
        variable = getattr(loaded, name, None)
        try:
            state = "NOT_INSTRUMENTED" if variable is None else (
                "SET" if variable.get() is not None else "UNSET")
        except Exception:
            state = "UNCONFIRMED_CONTEXT"
        result["contexts"][name] = state
    settings = sys.modules.get("app.core.config")
    getter = getattr(settings, "get_settings", None)
    cache_info = getattr(getter, "cache_info", None)
    try:
        result["settings_cache"] = cache_info()._asdict() if callable(cache_info) else None
    except Exception:
        result["settings_cache"] = "UNCONFIRMED_CACHE"
    try:
        result["database"] = database_snapshot(item)
    except Exception:
        result["database"] = {"status": "UNCONFIRMED_SNAPSHOT_FAILURE"}
    return result


class Evidence:
    def __init__(self, directory):
        self.directory = directory
        self.previous = deque(maxlen=16)
        self.active = {}
        self.capture_failed = False

    def write(self, name, value):
        try:
            atomic(self.directory / name, value)
        except Exception:
            self.capture_failed = True

    def pytest_collection_finish(self, session):
        order = [safe_node(item.nodeid) for item in session.items]
        self.write("collection.json", {"schema": "worker02.r5.collection.v1",
            "order": order, "order_sha256": digest(order), "nodes": len(order)})

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(self, item):
        if item.nodeid in WATCH:
            self.active[item.nodeid] = {"schema": "worker02.r5.context.v1",
                "node": safe_node(item.nodeid), "previous": list(self.previous),
                "before": context(item), "observation": None, "statistics": None}
        yield

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        yield
        if item.nodeid not in WATCH:
            if call.when == "teardown":
                self.previous.append(safe_node(item.nodeid))
            return
        record = self.active.setdefault(item.nodeid, {"schema": "worker02.r5.context.v1",
            "node": safe_node(item.nodeid), "previous": list(self.previous)})
        record[call.when] = "FAILED" if call.excinfo is not None else "PASSED"
        if call.when == "call":
            record["after"] = context(item)
            if call.excinfo is not None:
                record["first_error_type"] = type(call.excinfo.value).__name__
                record["statistics"] = statistics(getattr(call.excinfo.value,"a4232_drift",None))
                record["trace"] = [{"file": Path(e.path).name, "line": e.lineno + 1,
                    "function": e.name} for e in call.excinfo.traceback][-16:]
                for entry in call.excinfo.traceback:
                    value = entry.frame.f_locals.get("result")
                    if isinstance(value, dict) and "first_failure_code" in value:
                        record["observation"] = observation(value)
        self.write(digest(item.nodeid)[:20] + ".json", record)
        if call.when == "teardown":
            self.previous.append(safe_node(item.nodeid))

    def pytest_sessionfinish(self, session, exitstatus):
        try:
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], timeout=5,
                cwd=getattr(getattr(session, "config", None), "rootpath", None),
                stderr=subprocess.DEVNULL, text=True).strip()
        except (OSError, subprocess.SubprocessError):
            sha = None
        self.write("result.json", {"schema": "worker02.r5.result.v1",
            "source_sha": sha if sha and re.fullmatch(r"[0-9a-f]{40}", sha) else None,
            "original_exitstatus": int(exitstatus), "watched_nodes": len(self.active),
            "capture_failed": self.capture_failed, "qualifies": False})
        if self.capture_failed and int(exitstatus) == 0:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_addoption(parser):
    parser.addoption("--r5-evidence-dir",
                     help="Opt-in read-only R5 test diagnostics under .codex_tmp")


def pytest_configure(config):
    option = config.getoption("--r5-evidence-dir")
    if option is None:
        return
    root = Path(config.rootpath).resolve()
    directory = (root / option).resolve()
    if not directory.is_relative_to(root / ".codex_tmp"):
        raise pytest.UsageError("R5_EVIDENCE_DIRECTORY_OUTSIDE_TEST_ARTIFACTS")
    if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
        raise pytest.UsageError("R5_EVIDENCE_DIRECTORY_NOT_EMPTY")
    config.pluginmanager.register(Evidence(directory), "worker02-r5-evidence")
