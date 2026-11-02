"""R2 observer snapshots cannot mutate the recorder across threads."""

from app.services.execution_diagnostics import ExecutionDiagnostics


def test_snapshot_recent_events_are_detached_from_internal_state():
    recorder = ExecutionDiagnostics()
    recorder.record("trade_status.compute", "compute", 0.1)
    report = recorder.snapshot()
    report["recent"][0]["name"] = "PRIVATE_MUTATION"
    assert recorder.snapshot()["recent"][0]["name"] == "trade_status.compute"


def test_concurrent_snapshots_and_invalid_labels_keep_metrics_bounded():
    from concurrent.futures import ThreadPoolExecutor

    from app.services.execution_diagnostics import active_diagnostics, record_duration

    recorder = ExecutionDiagnostics()

    def write():
        token = active_diagnostics.set(recorder)
        try:
            for _ in range(1000):
                record_duration("trade_status.compute", "compute", 0.001)
                record_duration("PRIVATE_LABEL", "compute", 1)
        finally:
            active_diagnostics.reset(token)

    def read():
        for _ in range(100):
            snapshot = recorder.snapshot()
            assert len(snapshot["phases"]) <= 128 and len(snapshot["recent"]) <= 32
            for row in snapshot["recent"]:
                row["name"] = "MUTATED_OUTSIDE_LOCK"

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(write), pool.submit(read)]
        for future in futures:
            future.result(timeout=30)
    final = recorder.snapshot()
    assert final["phases"][0]["calls"] == 1000 and final["dropped_metrics"] == 1000
    assert all(row["name"] == "trade_status.compute" for row in final["recent"])
