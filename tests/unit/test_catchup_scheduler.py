from datetime import date
from types import SimpleNamespace

import app.jobs.scheduler as scheduler_module
from app.jobs.catchup_job import build_catchup_plan
from app.jobs.scheduler import cron_trigger_kwargs, run_scheduled_catchup


def test_catchup_plan_runs_missing_and_recent_refresh_dates() -> None:
    open_dates = [
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
        date(2026, 9, 4),
    ]

    plan = build_catchup_plan(
        open_dates=open_dates,
        latest_completed_date=date(2026, 9, 2),
        raw_incomplete_dates=[],
        max_catchup_trade_days=20,
        refresh_recent_trade_days=2,
    )

    assert plan.skipped is False
    assert plan.required_dates == [date(2026, 9, 3), date(2026, 9, 4)]
    assert plan.refresh_dates == [date(2026, 9, 3), date(2026, 9, 4)]
    assert plan.run_dates == [date(2026, 9, 3), date(2026, 9, 4)]


def test_catchup_plan_includes_recent_raw_error_before_latest_complete() -> None:
    open_dates = [
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
    ]

    plan = build_catchup_plan(
        open_dates=open_dates,
        latest_completed_date=date(2026, 9, 3),
        raw_incomplete_dates=[date(2026, 9, 2)],
        max_catchup_trade_days=20,
        refresh_recent_trade_days=0,
    )

    assert plan.skipped is False
    assert plan.required_dates == [date(2026, 9, 2)]
    assert plan.run_dates == [date(2026, 9, 2)]


def test_catchup_plan_skips_when_missing_exceeds_limit() -> None:
    open_dates = [date(2026, 9, day) for day in range(1, 8)]

    plan = build_catchup_plan(
        open_dates=open_dates,
        latest_completed_date=None,
        raw_incomplete_dates=[],
        max_catchup_trade_days=3,
        refresh_recent_trade_days=2,
    )

    assert plan.skipped is True
    assert len(plan.required_dates) == 7
    assert "max_catchup_trade_days=3" in str(plan.reason)


def test_scheduler_cron_converts_crontab_weekdays_to_apscheduler_names() -> None:
    kwargs = cron_trigger_kwargs("10 18 * * 1-5")

    assert kwargs["minute"] == "10"
    assert kwargs["hour"] == "18"
    assert kwargs["day_of_week"] == "mon-fri"


def test_scheduler_skips_when_active_job_exists(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(scheduler_module, "recover_stale_ingestion_jobs", lambda db: 0)
    monkeypatch.setattr(
        scheduler_module,
        "find_active_ingestion_job",
        lambda db, recover_stale=False: SimpleNamespace(
            id="job-1",
            job_type="backfill",
            status="RUNNING",
        ),
    )

    class FakeCatchUpJob:
        def __init__(self, db, provider):
            self.db = db
            self.provider = provider

        def run(self, target_date):
            calls.append(target_date)

    monkeypatch.setattr(scheduler_module, "CatchUpJob", FakeCatchUpJob)

    executed = run_scheduled_catchup(object(), object(), date(2026, 9, 4))

    assert executed is False
    assert calls == []


def test_scheduler_runs_catchup_when_no_active_job(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(scheduler_module, "recover_stale_ingestion_jobs", lambda db: 0)
    monkeypatch.setattr(
        scheduler_module,
        "find_active_ingestion_job",
        lambda db, recover_stale=False: None,
    )

    class FakeCatchUpJob:
        def __init__(self, db, provider):
            self.db = db
            self.provider = provider

        def run(self, target_date):
            calls.append(target_date)

    monkeypatch.setattr(scheduler_module, "CatchUpJob", FakeCatchUpJob)

    executed = run_scheduled_catchup(object(), object(), date(2026, 9, 4))

    assert executed is True
    assert calls == [date(2026, 9, 4)]
