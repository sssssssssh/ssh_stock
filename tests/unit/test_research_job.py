from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import app.jobs.research_job as research_job
import app.jobs.scheduler as scheduler_module
import pytest


def test_research_job_processes_batches_and_records_progress(monkeypatch) -> None:
    monkeypatch.setattr(research_job, "research_can_run", lambda db: True)
    settings = SimpleNamespace(research_config={"batch_trade_days": 20})
    monkeypatch.setattr(research_job, "get_settings", lambda: settings)
    monkeypatch.setattr(
        research_job,
        "trade_batches",
        lambda db, start, end, size: iter([[date(2026, 1, 2)], [date(2026, 1, 5)]]),
    )
    calls = []
    monkeypatch.setattr(
        research_job,
        "evaluate_opportunity_batch",
        lambda *args: {
            "base_rows": 3,
            "eval_rows": 3,
            "entry_nonexecutable": 1,
            "benchmark_missing": 1,
        },
    )
    monkeypatch.setattr(
        research_job,
        "evaluate_theme_batch",
        lambda *args: {
            "base_rows": 2,
            "eval_rows": 2,
            "benchmark_missing": 0,
        },
    )
    monkeypatch.setattr(
        research_job,
        "evaluate_transition_batch",
        lambda *args: {
            "base_rows": 3,
            "eval_rows": 1,
        },
    )
    monkeypatch.setattr(research_job, "update_job", lambda db, job, **kwargs: calls.append(kwargs))
    job = SimpleNamespace(job_metadata={"start": "2026-01-01", "end": "2026-01-05"})

    totals = research_job.run_research_eval(object(), job)

    assert totals["opportunity_rows"] == 6
    assert totals["theme_rows"] == 4
    assert totals["transition_rows"] == 2
    assert calls[-1]["status"] == "SUCCESS"
    assert calls[-1]["metadata"]["progress_pct"] == 100
    assert calls[-1]["metadata"]["warnings"] == ["BENCHMARK_DATA_MISSING"]


def test_research_job_rejects_positive_input_without_eval(monkeypatch) -> None:
    monkeypatch.setattr(research_job, "research_can_run", lambda db: True)
    monkeypatch.setattr(
        research_job,
        "get_settings",
        lambda: SimpleNamespace(research_config={"batch_trade_days": 20}),
    )
    monkeypatch.setattr(research_job, "trade_batches", lambda *args: iter([[date(2026, 1, 2)]]))
    monkeypatch.setattr(
        research_job,
        "evaluate_opportunity_batch",
        lambda *args: {
            "base_rows": 2,
            "eval_rows": 0,
            "entry_nonexecutable": 0,
            "benchmark_missing": 0,
        },
    )
    monkeypatch.setattr(research_job, "update_job", lambda *args, **kwargs: None)
    job = SimpleNamespace(
        job_metadata={
            "start": "2026-01-02",
            "end": "2026-01-02",
            "opportunity_only": True,
        }
    )
    with pytest.raises(RuntimeError, match="input rows > 0"):
        research_job.run_research_eval(object(), job)


def test_research_queue_validates_range_and_modes_before_writing() -> None:
    with pytest.raises(ValueError, match="start must be"):
        research_job.queue_research_eval(object(), date(2026, 2, 1), date(2026, 1, 1))
    with pytest.raises(ValueError, match="only one"):
        research_job.queue_research_eval(
            object(),
            date(2026, 1, 1),
            date(2026, 2, 1),
            theme_only=True,
            opportunity_only=True,
        )


def test_scheduled_research_uses_last_65_open_days_without_tushare(monkeypatch) -> None:
    dates = [date(2026, 9, 21), date(2026, 9, 18), date(2026, 6, 18)]
    db = SimpleNamespace(
        scalar=lambda statement: 0 if "job_run" in str(statement) else dates[0],
        execute=lambda statement: SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: dates)
        ),
    )
    calls = []
    monkeypatch.setattr(scheduler_module, "recover_stale_research_jobs", lambda db: 0)
    monkeypatch.setattr(scheduler_module, "research_can_run", lambda db: True)
    monkeypatch.setattr(
        scheduler_module,
        "queue_research_eval",
        lambda db, start, end, **kwargs: calls.append((start, end, kwargs)),
    )
    assert scheduler_module.run_scheduled_research(db, dates[0]) is True
    assert calls == [(dates[-1], dates[0], {"mode": "scheduler"})]


def test_scheduled_research_skips_busy_production_and_recovers_stale(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        scheduler_module, "recover_stale_research_jobs", lambda db: calls.append("recover")
    )
    monkeypatch.setattr(scheduler_module, "research_can_run", lambda db: False)
    monkeypatch.setattr(
        scheduler_module, "queue_research_eval", lambda *args, **kwargs: calls.append("queue")
    )
    assert scheduler_module.run_scheduled_research(object(), date(2026, 9, 22)) is False
    assert calls == ["recover"]


def test_scheduler_requeues_after_recovering_stale_research(monkeypatch) -> None:
    now = datetime.now(UTC)
    job = SimpleNamespace(
        job_type="RESEARCH_EVAL", status="RUNNING",
        started_at=now - timedelta(hours=2),
        heartbeat_at=now - timedelta(minutes=30),
        finished_at=None, error_message=None,
    )
    dates = [date(2026, 9, 21), date(2026, 9, 18)]

    class Db:
        def execute(self, statement):
            rows = [job] if "job_run" in str(statement) and job.status == "RUNNING" else dates
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

        def scalar(self, statement):
            if "job_run" in str(statement):
                return int(job.status in {"QUEUED", "RUNNING"})
            return dates[0]

        def add(self, value):
            pass

        def commit(self):
            pass

    calls = []
    monkeypatch.setattr(
        scheduler_module, "queue_research_eval", lambda *args, **kwargs: calls.append(args)
    )
    assert scheduler_module.run_scheduled_research(Db(), dates[0]) is True
    assert job.status == "FAILED"
    assert len(calls) == 1


def test_research_worker_defers_when_production_queued_after_claim(monkeypatch) -> None:
    monkeypatch.setattr(research_job, "research_can_run", lambda db: False)

    class Db:
        def __init__(self):
            self.commits = 0

        def add(self, job):
            pass

        def commit(self):
            self.commits += 1

    db = Db()
    job = SimpleNamespace(
        status="RUNNING", step="claimed", worker_id="worker-a",
        heartbeat_at=date(2026, 9, 22),
    )
    assert research_job.run_research_eval(db, job) == {}
    assert (job.status, job.step, job.worker_id, job.heartbeat_at) == (
        "QUEUED", "waiting for production jobs", None, None
    )
    assert db.commits == 1
