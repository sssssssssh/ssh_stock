from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import app.jobs.research_job as research_job
import app.jobs.scheduler as scheduler_module
import pytest
from app.core.config import get_settings
from app.services.job_guard import ResearchQueueConflictError


def test_research_job_processes_batches_and_records_progress(monkeypatch) -> None:
    monkeypatch.setattr(research_job, "research_can_run", lambda db: True)
    settings = get_settings()
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
            "deleted_rows": 2,
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
            "deleted_rows": 1,
            "benchmark_missing": 0,
        },
    )
    monkeypatch.setattr(
        research_job,
        "evaluate_transition_batch",
        lambda *args: {
            "base_rows": 3,
            "eval_rows": 1,
            "deleted_rows": 3,
        },
    )
    monkeypatch.setattr(research_job, "update_job", lambda db, job, **kwargs: calls.append(kwargs))
    job = SimpleNamespace(job_metadata={
        "start": "2026-01-01", "end": "2026-01-05",
        **research_job.current_research_identity(settings),
    })

    totals = research_job.run_research_eval(object(), job)

    assert totals["opportunity_rows"] == 6
    assert totals["theme_rows"] == 4
    assert totals["transition_rows"] == 2
    assert totals["opportunity_deleted_rows"] == 4
    assert totals["theme_deleted_rows"] == 2
    assert totals["transition_deleted_rows"] == 6
    assert calls[-1]["status"] == "SUCCESS"
    assert calls[-1]["metadata"]["progress_pct"] == 100
    assert calls[-1]["metadata"]["warnings"] == ["BENCHMARK_DATA_MISSING"]


def test_research_job_rejects_positive_input_without_eval(monkeypatch) -> None:
    monkeypatch.setattr(research_job, "research_can_run", lambda db: True)
    settings = get_settings()
    monkeypatch.setattr(research_job, "get_settings", lambda: settings)
    monkeypatch.setattr(research_job, "trade_batches", lambda *args: iter([[date(2026, 1, 2)]]))
    monkeypatch.setattr(
        research_job,
        "evaluate_opportunity_batch",
        lambda *args: {
            "base_rows": 2,
            "eval_rows": 0,
            "deleted_rows": 0,
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
            **research_job.current_research_identity(settings),
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


@pytest.mark.parametrize("status", ("QUEUED", "RUNNING"))
def test_research_queue_rejects_active_job_atomically(monkeypatch, status) -> None:
    active = SimpleNamespace(
        status=status, started_at=datetime.now(UTC), heartbeat_at=datetime.now(UTC)
    )
    db = _QueueDb([active])
    created = []
    monkeypatch.setattr(research_job, "start_job", lambda *args, **kwargs: created.append(args))

    with pytest.raises(ResearchQueueConflictError, match="active research"):
        research_job.queue_research_eval(db, date(2026, 5, 1), date(2026, 5, 10))

    assert created == []
    assert db.rollbacks == 1


def test_research_queue_recovers_stale_and_stores_lineage_metadata(monkeypatch) -> None:
    stale = SimpleNamespace(
        status="RUNNING", started_at=datetime.now(UTC) - timedelta(hours=2),
        heartbeat_at=datetime.now(UTC) - timedelta(hours=1),
        finished_at=None, error_message=None,
    )
    db = _QueueDb([stale])
    captured = []
    monkeypatch.setattr(
        research_job, "start_job",
        lambda *args, **kwargs: captured.append(kwargs) or SimpleNamespace(id="new-job"),
    )

    job = research_job.queue_research_eval(db, date(2026, 5, 1), date(2026, 5, 10))

    assert job.id == "new-job"
    assert stale.status == "FAILED"
    assert db.commits == 0
    metadata = captured[0]["metadata"]
    assert metadata["source_strategy_config_hash"] == metadata["strategy_config_hash"]
    assert set(research_job.RESEARCH_IDENTITY_KEYS) <= metadata.keys()
    assert metadata["opportunity_deleted_rows"] == 0
    assert metadata["theme_deleted_rows"] == 0
    assert metadata["transition_deleted_rows"] == 0


def test_research_queue_uses_postgresql_advisory_lock(monkeypatch) -> None:
    db = _QueueDb([], dialect="postgresql")
    monkeypatch.setattr(
        research_job, "start_job", lambda *args, **kwargs: SimpleNamespace(id="new-job")
    )

    research_job.queue_research_eval(db, date(2026, 5, 1), date(2026, 5, 10))

    assert "pg_advisory_xact_lock" in str(db.statements[0])
    assert "job_run" in str(db.statements[1])


def test_manual_research_queue_rejects_active_production(monkeypatch) -> None:
    db = _QueueDb([], production_busy=True)
    monkeypatch.setattr(
        research_job, "start_job",
        lambda *args, **kwargs: pytest.fail("busy production must prevent enqueue"),
    )
    with pytest.raises(ResearchQueueConflictError, match="production job"):
        research_job.queue_research_eval(db, date(2026, 5, 1), date(2026, 5, 10))
    assert db.rollbacks == 1


def test_stale_recovery_survives_production_conflict(monkeypatch) -> None:
    stale = SimpleNamespace(
        status="RUNNING", started_at=datetime.now(UTC) - timedelta(hours=2),
        heartbeat_at=datetime.now(UTC) - timedelta(hours=1),
        finished_at=None, error_message=None,
    )
    db = _QueueDb([stale], production_busy=True)
    monkeypatch.setattr(
        research_job, "start_job",
        lambda *args, **kwargs: pytest.fail("production conflict must prevent enqueue"),
    )
    with pytest.raises(ResearchQueueConflictError, match="production job"):
        research_job.queue_research_eval(db, date(2026, 5, 1), date(2026, 5, 10))
    assert stale.status == "FAILED"
    assert db.commits == 1
    assert db.rollbacks == 0


@pytest.mark.parametrize("changed", ("strategy", "research_config", "algo_version"))
def test_research_identity_drift_fails_before_trade_batches(monkeypatch, changed) -> None:
    queued_settings = get_settings().model_copy(deep=True)
    queued = research_job.current_research_identity(queued_settings)
    current_settings = queued_settings.model_copy(deep=True)
    if changed == "strategy":
        current_settings.strategy.setdefault("trend", {})["identity_test"] = "changed"
    elif changed == "research_config":
        current_settings.research_config["identity_test"] = "changed"
    else:
        current_settings.algo_version = "changed"
    monkeypatch.setattr(research_job, "get_settings", lambda: current_settings)
    monkeypatch.setattr(research_job, "research_can_run", lambda db: True)
    monkeypatch.setattr(
        research_job, "trade_batches",
        lambda *args: pytest.fail("drifted job must not load trade batches"),
    )
    monkeypatch.setattr(
        research_job, "evaluate_opportunity_batch",
        lambda *args: pytest.fail("drifted job must not evaluate"),
    )
    updates = []
    monkeypatch.setattr(
        research_job, "update_job", lambda db, job, **kwargs: updates.append(kwargs)
    )
    job = SimpleNamespace(job_metadata={
        "start": "2026-01-02", "end": "2026-01-02", **queued,
    })
    assert research_job.run_research_eval(object(), job) == {}
    assert updates[0]["status"] == "FAILED"
    assert updates[0]["step"] == "research identity changed since queue"
    assert "RESEARCH_IDENTITY_CHANGED_SINCE_QUEUE" in updates[0]["error_message"]
    assert updates[0]["metadata"]["strategy_config_hash"] == queued["strategy_config_hash"]
    assert updates[0]["metadata"]["identity_changed_fields"]


class _QueueDb:
    def __init__(self, jobs, dialect="sqlite", production_busy=False):
        self.jobs = jobs
        self.dialect = dialect
        self.production_busy = production_busy
        self.statements = []
        self.rollbacks = 0
        self.commits = 0

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name=self.dialect))

    def execute(self, statement):
        self.statements.append(statement)
        rows = [job for job in self.jobs if job.status in {"QUEUED", "RUNNING"}]
        return SimpleNamespace(
            scalar_one=lambda: None,
            scalars=lambda: SimpleNamespace(all=lambda: rows),
        )

    def scalar(self, statement):
        if "count(" in str(statement):
            return int(self.production_busy)
        return next((job for job in self.jobs if job.status in {"QUEUED", "RUNNING"}), None)

    def add(self, job):
        pass

    def rollback(self):
        self.rollbacks += 1

    def commit(self):
        self.commits += 1


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


def test_scheduled_research_completed_is_identity_and_source_aware() -> None:
    statements = []

    class Db:
        def scalar(self, statement):
            statements.append(statement)
            return 1

    target = date(2026, 9, 25)
    assert scheduler_module.scheduled_research_completed(Db(), target, get_settings()) is True
    sql = str(statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "SUCCESS" in sql
    assert "scheduler" in sql
    assert "research_eval_version" in sql
    assert "target_trade_date" in sql


def test_research_refresh_lookback_covers_next_open_h60_and_delay5() -> None:
    settings = get_settings().model_copy(deep=True)
    settings.research_config["refresh_lookback_trade_days"] = 1
    assert scheduler_module.research_refresh_lookback(settings) == 66


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
