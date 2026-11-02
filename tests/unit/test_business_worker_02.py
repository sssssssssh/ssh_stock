"""Low-cost regressions supplement, never substitute for real PG17 evidence."""

from uuid import uuid4

import pytest
from app.cli import cli
from app.services import job_worker
from app.services.execution_diagnostics import ExecutionDiagnostics, active_diagnostics, operation
from typer.testing import CliRunner


@pytest.mark.parametrize("args", [[], ["--job-id", "bad", "--dry-run"],
                                 ["--job-id", str(uuid4())],
                                 ["--job-id", str(uuid4()), "--dry-run", "--force"]])
def test_reconcile_rejects_missing_invalid_or_write_arguments_without_connection(monkeypatch, args):
    def forbidden():
        pytest.fail("Invalid/recovery CLI input must not acquire any database")

    monkeypatch.setattr("app.cli.SessionLocal", forbidden)
    assert CliRunner().invoke(cli, ["reconcile", *args]).exit_code != 0


def test_continuous_heartbeat_failures_count_but_never_release_or_kill(monkeypatch):
    from sqlalchemy.exc import OperationalError

    class Stop:
        count = 0

        def wait(self, _):
            self.count += 1
            return self.count > 3

    def unavailable():
        raise OperationalError("synthetic", {}, RuntimeError("PRIVATE_DSN_AND_PARAMS"))

    logs = []
    monkeypatch.setattr(job_worker, "SessionLocal", unavailable)
    monkeypatch.setattr(job_worker.logger, "error", lambda fmt, *args: logs.append(
        fmt.format(*args)))
    job_worker._run_heartbeat_loop(uuid4(), "synthetic", Stop(), interval_seconds=1)
    assert len(logs) == 3
    for i, message in enumerate(logs, 1):
        assert f"consecutive_failures={i}" in message
        assert "phase=session_acquire" in message
        assert "PRIVATE_DSN_AND_PARAMS" not in message


def test_diagnostics_keep_first_exception_and_bounded_safe_fields():
    recorder = ExecutionDiagnostics()
    token = active_diagnostics.set(recorder)
    original = RuntimeError("PRIVATE_SOURCE_DATA")
    try:
        with pytest.raises(RuntimeError) as caught, operation("trade_status.compute", "compute"):
            raise original
        assert caught.value is original
        for _ in range(50):
            with operation("trade_status.compute", "compute"):
                pass
    finally:
        active_diagnostics.reset(token)
    assert len(recorder.recent) == 32
    assert recorder.totals[("trade_status.compute", "compute")]["failures"] == 1
    assert "PRIVATE_SOURCE_DATA" not in str(recorder.snapshot())


def test_actual_heartbeat_sql_never_uses_stale_progress_to_overwrite_new_metadata():
    from datetime import UTC, datetime

    from app.repositories.job_run import touch_job_heartbeat
    from sqlalchemy.dialects import postgresql

    class Db:
        sql = []

        def execute(self, statement):
            from types import SimpleNamespace

            self.sql.append(str(statement.compile(dialect=postgresql.dialect())))
            return SimpleNamespace(rowcount=1)

        def commit(self):
            self.sql.append("COMMIT")

    db = Db()
    touch_job_heartbeat(db, uuid4(), "synthetic", execution_token=uuid4(),
                        calculation_progress={"updated_at": datetime.now(UTC).isoformat()})
    lease = next(i for i, query in enumerate(db.sql) if "heartbeat_at=" in query)
    progress = next(i for i, query in enumerate(db.sql) if "job_metadata=" in query)
    assert "job_metadata" not in db.sql[lease]
    assert db.sql[lease+1] == "COMMIT" and progress > lease+1
    assert "CASE WHEN" in db.sql[progress] and "execution_token" in db.sql[progress]


def test_insufficient_memory_keeps_full_scale_and_all_rounds_unmeasured(monkeypatch):
    from app.services import calculation_memory as memory

    from scripts.business_worker_resource_preflight import resource_preflight

    monkeypatch.setattr(memory, "available_memory_bytes", lambda: 2 * 1024**3)
    monkeypatch.setattr(memory, "process_memory_bytes", lambda: (100, 200))
    result = resource_preflight()
    assert result["status"] == "RESOURCE_DEFERRED"
    assert result["target_rows"] == 1_443_097 and result["planned_rounds"] == 3
    assert result["rows_measured"] == result["rounds_completed"] == 0
    assert result["database_contacted"] is False


def test_diagnostic_intervals_separate_phase_cost_without_changing_result(monkeypatch):
    from app.services import calculation_progress as progress

    clock = [0.0]
    monkeypatch.setattr(progress, "monotonic", lambda: clock[0])
    recorder = ExecutionDiagnostics()
    token = active_diagnostics.set(recorder)
    try:
        step = progress.ProgressStep("stock_trade_status_daily", "candidate")
        step.report("lookup_candidate")
        clock[0] = 7
        step.report("lookup_published")
        clock[0] = 7.5
        step.report("prepare")
        clock[0] = 9
        step.report("store")
        clock[0] = 12
        step.report("complete")
    finally:
        active_diagnostics.reset(token)
    measured = {phase: value["seconds"] for (_, phase), value in recorder.totals.items()}
    assert measured == dict(lookup_candidate=7, lookup_published=0.5, prepare=1.5, store=3)
