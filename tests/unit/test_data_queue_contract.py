from datetime import date
from types import SimpleNamespace

import app.providers.tushare_provider as provider_module
import pytest
from app.core.config import _validate_data_queue_runtime
from app.providers.tushare_provider import TushareProvider
from app.services.job_execution import JobCancelled
from app.services.job_guard import request_fingerprint


def test_failed_dispatch_setup_always_clears_execution_context():
    from uuid import uuid4

    from app.models.job import JobRun
    from app.services.job_execution import current_execution
    from app.services.job_worker import execute_claimed_job
    from sqlalchemy.exc import OperationalError

    key, token = uuid4(), uuid4()
    job = JobRun(
        id=key,
        job_type="backfill",
        status="RUNNING",
        worker_id="worker",
        execution_token=token,
        job_metadata={},
    )
    original = OperationalError("synthetic", {}, OSError("disconnected"))

    class BrokenSession:
        info = {}
        reads = 0

        def get(self, *args):
            self.reads += 1
            if self.reads > 1:
                raise original
            return job

        def get_bind(self):
            return object()

        def commit(self):
            raise original

        def rollback(self):
            pass

        def execute(self, *args):
            raise original

    db = BrokenSession()
    execute_claimed_job(db, key, expected_worker="worker", expected_token=token)
    assert job.status == "RUNNING"
    assert current_execution.get() is None
    assert "data_task_timeouts" not in db.info


def test_fingerprint_is_stable_but_parameters_and_versions_matter():
    day = date(2026, 9, 1)
    left = {"start": day.isoformat(), "end": day.isoformat(), "dirty_range_ids": [2, 1]}
    right = {
        "source": "scheduler",
        "end": day.isoformat(),
        "start": day.isoformat(),
        "mode": "manual",
        "evaluate_signals": True,
        "dirty_range_ids": [1, 2],
    }
    baseline = request_fingerprint("recalculate", day, left)
    assert baseline == request_fingerprint("recalculate", day, right)
    assert baseline != request_fingerprint("recalculate", day, {**left, "evaluate_signals": False})
    assert baseline != request_fingerprint(
        "recalculate", day, {**left, "queue_identity": {"old": "v0"}}
    )
    assert request_fingerprint("sync_basic", None, {"source": "api"}) == request_fingerprint(
        "sync_basic", None, {"source": "scheduler", "progress_pct": 0}
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("data_queue_capacity", 0),
        ("data_lock_timeout_ms", True),
        ("data_statement_timeout_ms", -1),
        ("cancel_warning_seconds", "120"),
    ],
)
def test_invalid_queue_limits_fail_at_startup(key, value):
    with pytest.raises(ValueError, match=key):
        _validate_data_queue_runtime({"app": {"scheduler": {key: value}}})


def test_provider_retry_count_is_configurable_and_cancellation_stops_retry(monkeypatch):
    calls = []
    provider = object.__new__(TushareProvider)
    provider._safe_limits = {}
    provider._wait_for_rate_limit = lambda name: None

    def failed(**kwargs):
        calls.append("attempt")
        raise TimeoutError("synthetic timeout")

    provider._pro = SimpleNamespace(daily=failed)
    monkeypatch.setattr(
        provider_module,
        "get_settings",
        lambda: SimpleNamespace(
            app_config={
                "provider": {"tushare": {"max_attempts": 2, "retry_max_seconds": 1}},
            }
        ),
    )
    monkeypatch.setattr(TushareProvider._call.retry, "sleep", lambda seconds: None)
    with pytest.raises(TimeoutError):
        provider._call("daily")
    assert calls == ["attempt", "attempt"]
    calls.clear()

    def cancel():
        if calls:
            raise JobCancelled("JOB_CANCEL_REQUESTED")

    monkeypatch.setattr(provider_module, "checkpoint", cancel)
    with pytest.raises(JobCancelled):
        provider._call("daily")
    assert calls == ["attempt"]
