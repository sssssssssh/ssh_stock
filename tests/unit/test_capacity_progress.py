"""Diagnostic checkpoints never constitute release evidence."""

import json

import pytest
from sqlalchemy.exc import OperationalError

from scripts import data_publication_capacity_v12 as capacity
from scripts.a42_artifacts import JobCancelled, atomic, header
from scripts.a42_receipt_contract import ReceiptError, merge_capacity


def progress(tmp_path):
    return capacity.CapacityProgress(tmp_path/"capacity.progress.json", header("capacity-L2"))


def test_atomic_bounded_progress_tracks_actual_completed_calls_not_expected_rows(tmp_path):
    checkpoint = progress(tmp_path)
    checkpoint.begin_level(5000, 20, "L2")
    checkpoint.begin_table("stock_factor_daily")
    with checkpoint.phase("workspace_upsert"):
        checkpoint.data["tables"]["stock_factor_daily"]["rows"] = 500
    checkpoint.finish_table()
    data = json.loads(checkpoint.path.read_text())
    assert data["artifact_kind"] == "DIAGNOSTIC_ONLY" and data["status"] == "INCOMPLETE"
    assert data["stocks"] == 5000 and data["days"] == 20
    assert data["completed_table_count"] == 1
    assert data["tables"]["stock_factor_daily"]["rows"] == 500
    assert data["tables"]["stock_factor_daily"]["operations"]["workspace_upsert"]["count"] == 1
    assert data["last_checkpoint_at"] and data["head_sha"] and data["attempt"]
    assert not list(tmp_path.glob("*.tmp"))


def test_per_row_payload_timing_never_writes_per_row_files(tmp_path, monkeypatch):
    checkpoint = progress(tmp_path)
    checkpoint.begin_table("stock_factor_daily")
    from scripts import a42_artifacts

    writes = []
    monkeypatch.setattr(a42_artifacts, "atomic", lambda *args: writes.append(args))
    for _ in range(1000):
        with checkpoint.phase("payload", persist=False):
            pass
    assert writes == []
    assert checkpoint.data["tables"]["stock_factor_daily"]["operations"]["payload"]["count"] == 1000


@pytest.mark.parametrize("error", [JobCancelled(), KeyboardInterrupt(),
    OperationalError("PRIVATE_SQL", {"password": "PRIVATE_BIND"}, RuntimeError("PRIVATE_DSN"))])
def test_exception_keeps_failed_operation_and_formal_receipt_incomplete(
    tmp_path, monkeypatch, error
):
    monkeypatch.delenv("A421_CAPACITY_BUDGET_MINUTES", raising=False)
    monkeypatch.setattr("scripts.a42_artifacts.install_signals", lambda: None)

    def interrupted(args, result):
        args.progress = capacity.CapacityProgress(args.output.with_suffix(".progress.json"), result)
        args.progress.begin_level(5000, 20, "L2")
        args.progress.begin_table("stock_factor_daily")
        with args.progress.phase("workspace_upsert"):
            raise error

    monkeypatch.setattr(capacity, "run_cli", interrupted)
    path = tmp_path/"capacity.json"
    with pytest.raises(SystemExit, match="1"):
        capacity.main(["--confirm-synthetic", "--level", "L2", "--output", str(path)])
    formal = json.loads(path.read_text())
    sidecar = json.loads(path.with_suffix(".progress.json").read_text())
    assert formal["status"] == sidecar["status"] == "INCOMPLETE"
    assert formal["completed_groups"] == 0 and formal["results"] == []
    assert sidecar["first_failure"]["phase"] == "workspace_upsert"
    assert sidecar["completed_table_count"] == 0
    assert sidecar["tables"]["stock_factor_daily"]["rows"] == 0
    assert sidecar["terminal_failure"]["budget_exhausted"] is False
    assert "PRIVATE" not in path.read_text() + path.with_suffix(".progress.json").read_text()


def test_cleanup_error_keeps_first_failure_separate_from_terminal_sqlstate(tmp_path):
    checkpoint = progress(tmp_path)
    try:
        try:
            with checkpoint.phase("workspace_upsert"):
                raise JobCancelled()
        finally:
            original = RuntimeError("PRIVATE_CONNECTION")
            original.sqlstate = "08006"
            raise OperationalError("PRIVATE_SQL", {"token": "PRIVATE_TOKEN"}, original)
    except OperationalError as error:
        error.a421_budget_exhausted = True  # Only the deadline wrapper sets this in actual CLI.
        checkpoint.fail(error)
    data = json.loads(checkpoint.path.read_text())
    assert data["first_failure"]["failure_type"] == "JobCancelled"
    assert data["terminal_failure"]["failure_type"] == "OperationalError"
    assert data["terminal_failure"]["sqlstate"] == "08006"
    assert data["terminal_failure"]["failure_code"] == "RESOURCE_DEFERRED"
    assert "PRIVATE" not in checkpoint.path.read_text()


@pytest.mark.parametrize("status", ["INCOMPLETE", "COMPLETE", "DIAGNOSTIC_FINISHED"])
def test_progress_cannot_pass_merge_even_if_status_is_forged_or_duplicated(tmp_path, status):
    checkpoint = progress(tmp_path)
    checkpoint.data.update(status=status, level="L2", expected_groups=1, completed_groups=1)
    with pytest.raises(ReceiptError):
        merge_capacity([checkpoint.data, checkpoint.data], head=checkpoint.data["head_sha"],
                       attempt=checkpoint.data["attempt"], model_hash=checkpoint.data["model_hash"])


def test_stale_progress_is_not_overwritten_and_cannot_create_fresh_success(tmp_path):
    checkpoint = progress(tmp_path)
    atomic(checkpoint.path, {"status": "COMPLETE", "head_sha": "stale"})
    with pytest.raises(ReceiptError, match="ALREADY_EXISTS"):
        progress(tmp_path)
    assert json.loads(checkpoint.path.read_text())["head_sha"] == "stale"


def test_reused_output_cannot_leave_an_old_complete_formal_receipt(tmp_path, monkeypatch):
    checkpoint = progress(tmp_path)
    path = tmp_path/"capacity.json"
    atomic(path, {"status": "COMPLETE", "head_sha": "stale"})
    monkeypatch.setattr("scripts.a42_artifacts.install_signals", lambda: None)
    monkeypatch.setattr("scripts.a42_artifacts.isolation", lambda: {})
    with pytest.raises(SystemExit, match="1"):
        capacity.main(["--confirm-synthetic", "--level", "L2", "--output", str(path)])
    assert json.loads(path.read_text())["status"] == "INCOMPLETE"
    assert json.loads(path.read_text())["completed_groups"] == 0
    assert checkpoint.path.is_file()


def test_diagnostic_file_retries_are_bounded_and_do_not_retry_database_work(tmp_path, monkeypatch):
    from scripts import a42_artifacts

    checkpoint = progress(tmp_path)
    original = a42_artifacts.atomic
    calls = []

    def blocked(*args, **kwargs):
        calls.append(True)
        if len(calls) < 3:
            raise PermissionError()
        return original(*args, **kwargs)

    checkpoint.replace_attempts = 5
    monkeypatch.setattr(a42_artifacts, "atomic", blocked)
    monkeypatch.setattr(capacity.time, "sleep", lambda seconds: None)
    checkpoint.flush(force=True)
    assert len(calls) == 3
    calls.clear()
    def denied(*args, **kwargs):
        calls.append(True)
        raise PermissionError()
    monkeypatch.setattr(a42_artifacts, "atomic", denied)
    with pytest.raises(PermissionError):
        checkpoint.flush(force=True)
    assert len(calls) == 5


def test_diagnostic_io_failure_never_prevents_resource_cleanup(tmp_path, monkeypatch):
    from contextlib import contextmanager

    checkpoint = progress(tmp_path)
    closed = []

    @contextmanager
    def resource():
        try:
            yield "opened"
        finally:
            closed.append(True)

    with pytest.raises(PermissionError):
        with checkpoint.lifecycle(resource(), "candidate_create", "candidate_cleanup") as value:
            assert value == "opened"
            def denied(**kwargs):
                raise PermissionError()
            monkeypatch.setattr(checkpoint, "flush", denied)
    assert closed == [True]
    assert checkpoint.stack == []
    assert checkpoint.data["first_failure"]["phase"] == "candidate_cleanup"


def test_resource_is_registered_before_entry_checkpoint_can_fail(tmp_path, monkeypatch):
    from contextlib import contextmanager

    checkpoint = progress(tmp_path)
    closed = []

    @contextmanager
    def resource():
        def denied(**kwargs):
            raise PermissionError()
        monkeypatch.setattr(checkpoint, "flush", denied)
        try:
            yield "opened"
        finally:
            closed.append(True)

    with pytest.raises(PermissionError):
        with checkpoint.lifecycle(resource(), "candidate_create", "candidate_cleanup"):
            pytest.fail("entry checkpoint failure must stop the workload")
    assert closed == [True]
    assert checkpoint.stack == []


def test_formal_l2_load_and_publication_protocol_remain_frozen():
    # The existing AST gate compares the entire run_level to 02c69c6, including
    # upsert batch=500, per-day commits, both rollback probes and reader threads.
    from scripts.a42_ci_contract import CAPACITY_LEVELS

    stocks, days = CAPACITY_LEVELS["L2"]
    assert (stocks, days) == (5000, 20)
    assert days*(6*stocks+min(50, stocks)+min(100, stocks)+2) == 603040
