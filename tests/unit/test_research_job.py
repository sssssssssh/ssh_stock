from datetime import date
from types import SimpleNamespace

import app.jobs.research_job as research_job
import app.jobs.scheduler as scheduler_module
import pytest


def test_research_job_processes_batches_and_records_progress(monkeypatch) -> None:
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
    monkeypatch.setattr(
        scheduler_module,
        "queue_research_eval",
        lambda db, start, end, **kwargs: calls.append((start, end, kwargs)),
    )
    assert scheduler_module.run_scheduled_research(db, dates[0]) is True
    assert calls == [(dates[-1], dates[0], {"mode": "scheduler"})]
