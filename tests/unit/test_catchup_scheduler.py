from datetime import date
from types import SimpleNamespace

import app.jobs.catchup_job as catchup_module
import app.jobs.scheduler as scheduler_module
from app.jobs.catchup_job import CatchUpJob, analysis_complete_dates, build_catchup_plan
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
        raw_required_dates=[],
        analysis_required_dates=[date(2026, 9, 3), date(2026, 9, 4)],
        max_catchup_trade_days=20,
        refresh_recent_trade_days=2,
    )

    assert plan.skipped is False
    assert plan.required_dates == [date(2026, 9, 3), date(2026, 9, 4)]
    assert plan.raw_required_dates == []
    assert plan.analysis_required_dates == [date(2026, 9, 3), date(2026, 9, 4)]
    assert plan.refresh_dates == [date(2026, 9, 3), date(2026, 9, 4)]


def test_catchup_plan_includes_recent_raw_error_before_latest_complete() -> None:
    open_dates = [
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
    ]

    plan = build_catchup_plan(
        open_dates=open_dates,
        raw_required_dates=[date(2026, 9, 2)],
        analysis_required_dates=[],
        max_catchup_trade_days=20,
        refresh_recent_trade_days=0,
    )

    assert plan.skipped is False
    assert plan.required_dates == [date(2026, 9, 2)]
    assert plan.raw_required_dates == [date(2026, 9, 2)]
    assert plan.analysis_required_dates == []


def test_catchup_plan_identifies_middle_analysis_gap() -> None:
    open_dates = [
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
    ]

    plan = build_catchup_plan(
        open_dates=open_dates,
        raw_required_dates=[],
        analysis_required_dates=[date(2026, 9, 2)],
        max_catchup_trade_days=20,
        refresh_recent_trade_days=0,
    )

    assert plan.skipped is False
    assert plan.raw_required_dates == []
    assert plan.analysis_required_dates == [date(2026, 9, 2)]


def test_catchup_plan_skips_when_missing_exceeds_limit() -> None:
    open_dates = [date(2026, 9, day) for day in range(1, 8)]

    plan = build_catchup_plan(
        open_dates=open_dates,
        raw_required_dates=[],
        analysis_required_dates=open_dates,
        max_catchup_trade_days=3,
        refresh_recent_trade_days=2,
    )

    assert plan.skipped is True
    assert len(plan.required_dates) == 7
    assert "max_catchup_trade_days=3" in str(plan.reason)


def test_analysis_complete_dates_require_current_algo_version(monkeypatch) -> None:
    lookup = {
        "StockFactorDaily": {date(2026, 9, 2)},
        "MarketDaily": {date(2026, 9, 2)},
        "SectorFactorDaily": {date(2026, 9, 2)},
    }

    monkeypatch.setattr(
        catchup_module,
        "_dates_with_rows",
        lambda db, model, column, start, end: lookup[model.__name__],
    )

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return [date(2026, 9, 1)]

    class FakeDb:
        def execute(self, stmt):
            assert "v1.0" in str(stmt.compile(compile_kwargs={"literal_binds": True}))
            return FakeResult()

    completed = analysis_complete_dates(
        FakeDb(),
        date(2026, 9, 1),
        date(2026, 9, 3),
        algo_version="v1.0",
    )

    assert completed == set()


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


def test_raw_refresh_uses_raw_only_ingestion_methods(monkeypatch) -> None:
    calls = []

    class FakeIngestion:
        def sync_daily(self, trade_date):
            calls.append(("daily", trade_date))

        def sync_adj_factor(self, trade_date):
            calls.append(("adj_factor", trade_date))

        def sync_daily_basic(self, trade_date):
            calls.append(("daily_basic", trade_date))

        def sync_index_daily(self, trade_date):
            calls.append(("index_daily", trade_date))

    monkeypatch.setattr(
        catchup_module,
        "check_raw_completeness",
        lambda *args, **kwargs: SimpleNamespace(
            overall_status="PASS",
            as_metadata=lambda: {"current_day_datasets": {}},
        ),
    )
    db = SimpleNamespace(commits=0, commit=lambda: setattr(db, "commits", db.commits + 1))
    job = CatchUpJob.__new__(CatchUpJob)
    job.db = db
    job.ingestion = FakeIngestion()
    job.settings = SimpleNamespace(strategy={})

    job._refresh_raw_only(date(2026, 9, 4))

    assert calls == [
        ("daily", date(2026, 9, 4)),
        ("adj_factor", date(2026, 9, 4)),
        ("daily_basic", date(2026, 9, 4)),
        ("index_daily", date(2026, 9, 4)),
    ]
    assert db.commits == 1


def test_dirty_repair_not_run_without_open_dirty_ranges(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(catchup_module, "open_dirty_ranges", lambda db: [])
    monkeypatch.setattr(
        catchup_module,
        "run_recalculation",
        lambda *args, **kwargs: calls.append(args),
    )
    job = CatchUpJob.__new__(CatchUpJob)
    job.db = object()

    job._run_dirty_repair_if_needed()

    assert calls == []


def test_dirty_repair_runs_from_earliest_dirty_to_latest_raw(monkeypatch) -> None:
    dirty_ranges = [
        SimpleNamespace(id=1, dirty_start_date=date(2026, 9, 2)),
        SimpleNamespace(id=2, dirty_start_date=date(2026, 9, 1)),
    ]
    created_jobs = []
    recalc_calls = []
    monkeypatch.setattr(catchup_module, "open_dirty_ranges", lambda db: dirty_ranges)
    monkeypatch.setattr(catchup_module, "latest_raw_trade_date", lambda db: date(2026, 9, 4))

    def fake_start_job(db, *args, **kwargs):
        job = SimpleNamespace(id="job-1")
        created_jobs.append((args, kwargs))
        return job

    monkeypatch.setattr(catchup_module, "start_job", fake_start_job)
    monkeypatch.setattr(
        catchup_module,
        "run_recalculation",
        lambda *args, **kwargs: recalc_calls.append((args, kwargs)),
    )
    job = CatchUpJob.__new__(CatchUpJob)
    job.db = object()

    job._run_dirty_repair_if_needed()

    assert created_jobs
    args, kwargs = recalc_calls[0]
    assert args[2] == date(2026, 9, 1)
    assert args[3] == date(2026, 9, 4)
    assert kwargs["mode"] == "dirty_repair"
    assert kwargs["dirty_ranges"] == dirty_ranges
