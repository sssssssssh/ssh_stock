"""Offline regression for the progress-to-terminal evidence boundary."""

import ast
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import biz_perf_03_b_once as b
from scripts.business_sql_snapshot import RootCounts, build, validate, validate_pair


def snapshot(counts=None):
    return build(counts or {"SELECT": 5693, "UPDATE": 86, "DROP": 10},
                 head_sha="a" * 40, root_job_id="00000000-0000-0000-0000-000000000001",
                 started=10, ended=20)


def pair():
    snap = snapshot()
    return (dict(phase="result", failure_code=None, sql_counts=snap["counts"], sql_snapshot=snap),
            dict(head_sha=snap["head_sha"], root_job_id=snap["root_job_id"], sql_snapshot=snap,
                 root=dict(sql_counts=snap["counts"], job_status="SUCCESS",
                           publication_state="PUBLISHED")))


def test_terminal_emit_replaces_old_progress_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "network_inode", lambda: 99)
    channel = b.Channel(tmp_path / "phase.json")
    channel.begin_root()
    channel.emit("root", sql_counts={"SELECT": 5685, "UPDATE": 83})
    source = ast.parse(Path("scripts/business_recalc_measure.py").read_text())
    calls = [node for node in ast.walk(source) if isinstance(node, ast.Expr)
             and isinstance(node.value, ast.Call)
             and ast.unparse(node.value.func) == "channel.emit"
             and node.value.args and ast.literal_eval(node.value.args[0]) == "result"]
    assert len(calls) == 1
    terminal_counts = {"SELECT": 5693, "UPDATE": 86, "DROP": 10}
    # Execute the actual terminal emission, without importing the business app or a DB.
    exec(compile(ast.Module(body=calls, type_ignores=[]), "terminal", "exec"), {
        "channel": channel, "sql_snapshot": snapshot(terminal_counts),
    })
    assert b.read_json(channel.path)["sql_counts"] == terminal_counts


def test_freeze_excludes_later_verification_and_keeps_worker_cleanup():
    counts = RootCounts()
    for op in ("SELECT", "UPDATE", "DROP"):
        assert counts.begin(op)
        counts.end()
    frozen = counts.freeze()
    assert not counts.begin("SELECT")
    assert counts.copy() == frozen == {"SELECT": 1, "UPDATE": 1, "DROP": 1}
    frozen["SELECT"] = 99
    assert counts.copy()["SELECT"] == 1
    with pytest.raises(ValueError):
        counts.freeze()


def test_pending_cursor_execution_cannot_be_frozen_as_complete():
    counts = RootCounts()
    counts.begin("SELECT")
    with pytest.raises(ValueError):
        counts.freeze()
    counts.end()
    assert counts.freeze() == {"SELECT": 1}


def test_final_pair_is_equal_and_does_not_add_observer_controls():
    phase, measurement = pair()
    measurement["observer_control_sql_calls"] = 35
    validate_pair(phase, measurement)
    assert measurement["sql_snapshot"]["total"] == 5789
    with pytest.raises(ValueError):
        validate_pair(phase, measurement, expected_head="b" * 40)


@pytest.mark.parametrize("field,value", [
    ("snapshot_id", "0" * 64), ("head_sha", "wrong"), ("root_job_id", "wrong"),
    ("scope", "cleanup"), ("source", "driver"), ("version", "unknown"),
    ("complete", False), ("total", 0), ("counts", {"SELECT": -1}),
    ("counts", {"SELECT": 1.5}), ("counts", {"SELECT": True}),
    ("ended_monotonic_seconds", float("nan")), ("started_monotonic_seconds", 21),
])
def test_invalid_snapshot_refused(field, value):
    snap = snapshot()
    snap[field] = value
    with pytest.raises(ValueError):
        validate(snap)


@pytest.mark.parametrize("mutation", [
    lambda p, m: p.pop("sql_snapshot"), lambda p, m: m.pop("sql_snapshot"),
    lambda p, m: p.update(sql_counts={"SELECT": 1}),
    lambda p, m: m["root"].update(sql_counts={"SELECT": 1}),
    lambda p, m: m.update(head_sha="b" * 40),
    lambda p, m: m.update(root_job_id="00000000-0000-0000-0000-000000000002"),
    lambda p, m: p.update(phase="root"), lambda p, m: p.update(failure_code="BIZ03_CANCELLED"),
    lambda p, m: m["root"].update(job_status="CANCELLED"),
    lambda p, m: m["root"].update(job_status="FAILED"),
    lambda p, m: m["root"].update(publication_state="PREPARING"),
])
def test_incomplete_or_mismatched_pair_refused(mutation):
    phase, measurement = pair()
    mutation(phase, measurement)
    with pytest.raises(ValueError):
        validate_pair(phase, measurement)


def test_failure_retains_progress_without_terminal_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "network_inode", lambda: 99)
    channel = b.Channel(tmp_path / "phase.json")
    channel.begin_root()
    channel.emit("root", sql_counts={"SELECT": 3})
    channel.fail("BIZ03_CANCELLED")
    value = b.read_json(channel.path)
    assert value["phase"] == "failure" and value["sql_counts"] == {"SELECT": 3}
    assert "sql_snapshot" not in value
    with pytest.raises(b.Refused):
        channel.emit("result", sql_counts=snapshot()["counts"], sql_snapshot=snapshot())


def test_concurrent_connections_count_once_and_freeze_copy():
    counter = RootCounts()

    def call(_):
        assert counter.begin("SELECT")
        counter.end()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(call, range(1000)))
    assert counter.freeze() == {"SELECT": 1000}


def test_actual_control_hook_never_increments_root_counter():
    from scripts.business_candidate_observer import CandidateObserver

    counts = RootCounts()
    observer = CandidateObserver.__new__(CandidateObserver)
    observer.stack, observer.metrics, observer.control_sql_calls = [], {}, 0
    executed = []
    observer.control(SimpleNamespace(execute=executed.append), "SET synthetic=off")
    assert executed == ["SET synthetic=off"]
    assert observer.control_sql_calls == 1
    assert counts.freeze() == {}


def test_actual_harness_freeze_precedes_independent_verification():
    source = Path("scripts/business_recalc_measure.py").read_text()
    assert source.index("execute_claimed_job(db, identity") < source.index("counts.freeze()")
    assert source.index("counts.freeze()") < source.index("db.expire_all()")
    assert source.index("db.expire_all()") < source.index('report["tables"] = {}')


def test_legacy_parse_remains_available_but_cannot_grant_current_completion():
    phase, measurement = pair()
    del measurement["sql_snapshot"]
    b.validate_document("measurement.json", {**measurement, "plans": []})
    with pytest.raises(ValueError):
        validate_pair(phase, measurement)


def test_archive_rejects_mismatched_terminal_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "arm_deadline", lambda *a, **kw: None)
    env = dict(BIZ03_T0_NS="100000000000", GITHUB_SHA="a" * 40,
               GITHUB_RUN_ID="123", GITHUB_RUN_ATTEMPT="1", GITHUB_JOB="evidence")
    lab = b.Lab(env, b.protocol(), tmp_path, clock=lambda: 120)
    phase, measurement = pair()
    measurement["root"]["sql_counts"] = {"SELECT": 1}
    lab.receipt.update(status="MEASURED_CLEANUP_PENDING", root_attempts=1,
                       cleanup="COMPLETE", cleanup_finished_seconds=19, last_phase=phase)
    b.write_json(tmp_path / "public/measurement.json", measurement)
    assert not lab.finish_archive({"head_sha": env["GITHUB_SHA"]})
    assert lab.receipt["status"] == "INCOMPLETE"
