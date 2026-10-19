from uuid import uuid4

import pytest
from app.services import calculation_progress as module
from app.services.calculation_progress import (
    CalculationProgress,
    ProgressStep,
    current_progress,
    run_calculation,
)


@pytest.fixture
def recorder():
    value = CalculationProgress()
    token = current_progress.set(value)
    try:
        yield value
    finally:
        current_progress.reset(token)


def test_snapshots_keep_real_advancement_separate_from_waiting_and_are_bounded(recorder):
    step = ProgressStep("stock_trade_status_daily", "candidate", total_rows=1000, batch_count=2)
    step.report("lookup_candidate", batch_index=1)
    assert recorder.snapshot()["advanced_at"] is None
    step.report("batch_complete", batch_index=1, completed_rows=500, advanced=True)
    advanced = recorder.snapshot()["advanced_at"]
    for _ in range(30):
        step.report("lookup_published", batch_index=2, completed_rows=500)
    snapshot = recorder.snapshot()
    assert snapshot["completed_rows"] == 500
    assert snapshot["batch_index"] == 2
    assert snapshot["advanced_at"] == advanced
    assert len(snapshot["recent_events"]) == 12
    snapshot["recent_events"].clear()
    snapshot["completed_rows"] = 999
    assert len(recorder.snapshot()["recent_events"]) == 12
    assert recorder.snapshot()["completed_rows"] == 500


def test_operation_elapsed_is_preserved_after_completion(monkeypatch, recorder):
    clock = [10.0]
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    step = ProgressStep("trade_status.compute", "compute")
    step.report("compute")
    clock[0] = 130.0
    step.report("complete", completed_rows=15, advanced=True)
    assert recorder.snapshot()["operation_elapsed_seconds"] == 120.0
    assert recorder.snapshot()["elapsed_seconds"] == 120.0


def test_calculation_wrapper_preserves_results_and_original_exception(recorder):
    expected = [object()]
    assert run_calculation("factors.compute", lambda: expected) is expected
    assert recorder.snapshot()["completed_rows"] == 1
    error = RuntimeError("PRIVATE_ERROR_SENTINEL")

    def fail():
        raise error

    with pytest.raises(RuntimeError) as caught:
        run_calculation("factors.compute", fail)
    assert caught.value is error
    assert recorder.snapshot()["phase"] == "failed"
    assert "PRIVATE_ERROR_SENTINEL" not in str(recorder.snapshot())


@pytest.mark.parametrize("name,kind", [("secret URL", "read"), ("a" * 81, "read"),
                                      ("valid_name", "PRIVATE_KIND")])
def test_only_fixed_safe_log_labels_are_accepted(name, kind):
    with pytest.raises(ValueError, match="LABEL_INVALID"):
        ProgressStep(name, kind)


def test_heartbeat_reports_waiting_without_manufacturing_progress(monkeypatch, recorder):
    from app.services import job_worker

    step = ProgressStep("stock_trade_status_daily", "candidate", total_rows=1000, batch_count=2)
    step.report("batch_complete", completed_rows=500, batch_index=1, advanced=True)
    step.report("lookup_published", completed_rows=500, batch_index=2)
    snapshots = []

    class Db:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class Stop:
        count = 0

        def wait(self, seconds):
            self.count += 1
            return self.count > 2

    monkeypatch.setattr(job_worker, "SessionLocal", Db)
    monkeypatch.setattr(job_worker, "touch_job_heartbeat",
                        lambda *a, **kw: snapshots.append(kw["calculation_progress"]) or True)
    job_worker._run_heartbeat_loop(uuid4(), "test", Stop(), execution_token=uuid4(),
                                   interval_seconds=0.01, progress=recorder)
    assert len(snapshots) == 2
    assert snapshots[0] == snapshots[1]
    assert snapshots[0]["phase"] == "lookup_published"
    assert snapshots[0]["completed_rows"] == 500
