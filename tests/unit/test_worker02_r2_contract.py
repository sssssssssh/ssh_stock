"""R2 observer snapshots cannot mutate the recorder across threads."""

from app.services.execution_diagnostics import ExecutionDiagnostics


def test_snapshot_recent_events_are_detached_from_internal_state():
    recorder = ExecutionDiagnostics()
    recorder.record("trade_status.compute", "compute", 0.1)
    report = recorder.snapshot()
    report["recent"][0]["name"] = "PRIVATE_MUTATION"
    assert recorder.snapshot()["recent"][0]["name"] == "trade_status.compute"
