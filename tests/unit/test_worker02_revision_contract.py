"""Privacy, degraded communication and immutable recovery approval boundaries."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from app.services.worker_observation import (
    HeartbeatHealth,
    fingerprint,
    heartbeat_health_payload,
)


def test_lease_success_and_progress_failure_are_separate_facts():
    health = HeartbeatHealth()
    error = RuntimeError("PRIVATE")
    error.heartbeat_phase = "progress_update"
    confirmed = [dict(phase="lease_update", outcome="OK", rowcount=1),
                 dict(phase="lease_commit", outcome="OK")]
    health.observe(confirmed, error)
    first = health.snapshot()
    assert first["state"] == "HEARTBEAT_DEGRADED" and first["last_confirmed_at"]
    assert first["consecutive_failures"] == 1 and not first["computation_success_proven"]
    error.heartbeat_phase = "lease_commit"
    health.observe([dict(phase="lease_commit", outcome="FAILED")], error)
    assert health.snapshot()["last_confirmed_at"] == first["last_confirmed_at"]
    assert health.snapshot()["consecutive_failures"] == 2
    health.observe(confirmed)
    assert health.snapshot()["state"] == "COMMUNICATION_CONFIRMED"
    assert health.snapshot()["consecutive_failures"] == 0


def test_unknown_lease_ack_never_manufactures_confirmed_communication():
    health = HeartbeatHealth()
    error = RuntimeError("PRIVATE")
    error.heartbeat_phase = "lease_commit"
    health.observe([dict(phase="lease_commit", outcome="FAILED")], error)
    assert health.snapshot()["last_confirmed_at"] is None
    assert health.snapshot()["state"] == "HEARTBEAT_DEGRADED"


def test_zero_row_ownership_cas_commit_is_not_a_successful_lease():
    health = HeartbeatHealth()
    health.observe([dict(phase="lease_update", outcome="OK", rowcount=0),
                    dict(phase="lease_commit", outcome="OK")])
    assert health.snapshot()["last_confirmed_at"] is None


def test_api_stale_and_generation_mismatch_do_not_claim_computation_or_mutate():
    token = uuid4()
    metadata = {"heartbeat_health": {"state": "COMMUNICATION_CONFIRMED",
        "execution_fingerprint": fingerprint(uuid4()), "consecutive_failures": 0}}
    job = NS(status="RUNNING", execution_token=token, job_metadata=metadata,
             heartbeat_at=datetime.now(UTC)-timedelta(hours=1))
    result = heartbeat_health_payload(job, True)
    assert result["state"] == "HEARTBEAT_DEGRADED"
    assert result["consecutive_failures"] is None
    assert not result["computation_success_proven"] and job.job_metadata is metadata


def test_opt_in_is_independent_and_unmeasured_is_not_zero():
    from app.core.config import Settings
    from app.services.execution_diagnostics import ExecutionDiagnostics

    assert Settings(_env_file=None).worker_diagnostics_enabled is False
    assert set(ExecutionDiagnostics().snapshot()["coverage"].values()) == {"NOT_INSTRUMENTED"}


@pytest.mark.parametrize("name,seconds,rows", [
    ("private_secret", 1, 1), ("trade_status.compute", float("nan"), 1),
    ("trade_status.compute", -1, 1), ("trade_status.compute", 1, -1),
])
def test_observation_rejects_unregistered_labels_and_invalid_numeric_evidence(name, seconds, rows):
    from app.services.execution_diagnostics import ExecutionDiagnostics

    recorder = ExecutionDiagnostics()
    with pytest.raises(ValueError):
        recorder.record(name, "compute", seconds, rows=rows)
    assert recorder.snapshot()["phases"] == []


def test_cardinality_overflow_is_visible_and_does_not_change_calculation():
    from app.services.execution_diagnostics import ALLOWED_NAMES, ExecutionDiagnostics

    recorder = ExecutionDiagnostics()
    for name in sorted(ALLOWED_NAMES)[:150]:
        recorder.record(name, "compute", 1.0)
    snapshot = recorder.snapshot()
    assert len(snapshot["phases"]) == 128 and len(snapshot["recent"]) == 32
    assert snapshot["dropped_metrics"] == 22
