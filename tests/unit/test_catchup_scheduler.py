from datetime import date
from types import SimpleNamespace

import app.jobs.catchup_job as catchup_module
import app.jobs.scheduler as scheduler_module
import pytest
from app.jobs.catchup_job import (
    CatchUpJob,
    analysis_complete_dates,
    build_catchup_plan,
    classify_catchup_dates,
    is_analysis_complete,
)
from app.jobs.scheduler import cron_trigger_kwargs, run_scheduled_catchup
from app.models.market_data import (
    MarketDaily,
    SectorFactorDaily,
    StockDaily,
    StockFactorDaily,
    StockStateDaily,
)


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


def test_catchup_plan_excludes_repaired_raw_dates_from_recent_refresh() -> None:
    open_dates = [
        date(2026, 9, 6),
        date(2026, 9, 7),
        date(2026, 9, 8),
    ]

    plan = build_catchup_plan(
        open_dates=open_dates,
        raw_required_dates=[date(2026, 9, 8)],
        analysis_required_dates=[],
        max_catchup_trade_days=20,
        refresh_recent_trade_days=2,
    )

    assert plan.refresh_dates == [date(2026, 9, 7)]


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
    monkeypatch.setattr(
        catchup_module,
        "_open_trade_dates",
        lambda db, start, end: [date(2026, 9, 1), date(2026, 9, 2)],
    )
    monkeypatch.setattr(
        catchup_module,
        "is_analysis_complete",
        lambda db, trade_date, **kwargs: trade_date == date(2026, 9, 2)
        and kwargs["algo_version"] == "v1.0",
    )
    completed = analysis_complete_dates(
        object(),
        date(2026, 9, 1),
        date(2026, 9, 3),
        algo_version="v1.0",
    )

    assert completed == {date(2026, 9, 2)}


def test_classify_catchup_raw_error_does_not_enter_analysis(monkeypatch) -> None:
    raw = {
        date(2026, 9, 1): SimpleNamespace(is_complete=False),
        date(2026, 9, 2): SimpleNamespace(is_complete=True),
    }
    analysis_calls = []

    monkeypatch.setattr(
        catchup_module,
        "check_raw_completeness",
        lambda db, trade_date, **kwargs: raw[trade_date],
    )
    monkeypatch.setattr(
        catchup_module,
        "is_analysis_complete",
        lambda db, trade_date, **kwargs: analysis_calls.append(trade_date) or False,
    )

    raw_required, analysis_required = classify_catchup_dates(
        object(),
        [date(2026, 9, 1), date(2026, 9, 2)],
        strategy={},
        algo_version="v1.0",
    )

    assert raw_required == [date(2026, 9, 1)]
    assert analysis_required == [date(2026, 9, 2)]
    assert analysis_calls == [date(2026, 9, 2)]


def test_classify_catchup_raw_pass_analysis_complete_skips(monkeypatch) -> None:
    monkeypatch.setattr(
        catchup_module,
        "check_raw_completeness",
        lambda *args, **kwargs: SimpleNamespace(is_complete=True),
    )
    monkeypatch.setattr(catchup_module, "is_analysis_complete", lambda *args, **kwargs: True)

    raw_required, analysis_required = classify_catchup_dates(
        object(),
        [date(2026, 9, 1)],
        strategy={},
        algo_version="v1.0",
    )

    assert raw_required == []
    assert analysis_required == []


def test_catchup_candidate_window_ignores_older_history(monkeypatch) -> None:
    open_dates = [date(2026, 8, day) for day in range(1, 26)]
    checked_dates = []

    monkeypatch.setattr(
        catchup_module,
        "check_raw_completeness",
        lambda db, trade_date, **kwargs: checked_dates.append(trade_date)
        or SimpleNamespace(is_complete=True),
    )
    monkeypatch.setattr(catchup_module, "is_analysis_complete", lambda *args, **kwargs: True)

    classify_catchup_dates(
        object(),
        catchup_module._candidate_catchup_dates(open_dates, max_trade_days=20),
        strategy={},
        algo_version="v1.0",
    )

    assert checked_dates == open_dates[-20:]
    assert date(2026, 8, 1) not in checked_dates


def test_is_analysis_complete_rejects_old_config_hash(monkeypatch) -> None:
    calls = {}
    monkeypatch.setattr(catchup_module, "config_hash", lambda strategy: "current_hash")

    def count_matching(db, model, *criteria):
        text = " ".join(
            str(criterion.compile(compile_kwargs={"literal_binds": True}))
            for criterion in criteria
        )
        calls[model.__name__] = text
        if model is StockDaily:
            return 100
        if model is StockFactorDaily:
            return 0
        return 1

    monkeypatch.setattr(catchup_module, "_count_matching", count_matching)

    complete = is_analysis_complete(
        object(),
        date(2026, 9, 1),
        strategy={},
        algo_version="v1.0",
    )

    assert complete is False
    assert "factor_v1" in calls["StockFactorDaily"]
    assert "current_hash" in calls["StockFactorDaily"]


def _configured_catchup_job(
    monkeypatch,
    *,
    open_dates: list[date],
    raw_required_dates: list[date],
    analysis_required_dates: list[date],
    latest: date | None,
    refresh_recent_trade_days: int = 0,
):
    events = []
    scheduler_values = {
        "max_catchup_trade_days": 20,
        "refresh_recent_trade_days": refresh_recent_trade_days,
    }
    monkeypatch.setattr(
        catchup_module,
        "scheduler_setting",
        lambda key, default: scheduler_values.get(key, default),
    )
    monkeypatch.setattr(
        catchup_module,
        "_open_trade_dates",
        lambda db, start, end: open_dates,
    )
    monkeypatch.setattr(
        catchup_module,
        "classify_catchup_dates",
        lambda *args, **kwargs: (raw_required_dates, analysis_required_dates),
    )
    monkeypatch.setattr(catchup_module, "latest_raw_trade_date", lambda db: latest)

    job = CatchUpJob.__new__(CatchUpJob)
    job.db = SimpleNamespace(commit=lambda: events.append(("quality_commit",)))
    job.provider = object()
    job.settings = SimpleNamespace(strategy={}, algo_version="v1.0")
    job.ingestion = SimpleNamespace(
        sync_trade_calendar=lambda start, end: events.append(("calendar", start, end))
    )
    job._sync_and_validate_raw_date = lambda current: events.append(("raw", current))
    job._run_analysis_repair = lambda start, end, mode: events.append(
        ("recalculate", start, end, mode)
    )
    job._refresh_raw_only = lambda current: events.append(("refresh", current))
    job._run_dirty_repair_if_needed = lambda: events.append(("dirty_repair",))
    return job, events


def test_catchup_historical_raw_gap_repairs_raw_then_recalculates_to_latest(
    monkeypatch,
) -> None:
    open_dates = [date(2026, 9, day) for day in range(1, 5)]
    job, events = _configured_catchup_job(
        monkeypatch,
        open_dates=open_dates,
        raw_required_dates=[date(2026, 9, 2)],
        analysis_required_dates=[],
        latest=date(2026, 9, 4),
    )

    job.run(date(2026, 9, 4))

    assert ("raw", date(2026, 9, 2)) in events
    assert ("recalculate", date(2026, 9, 2), date(2026, 9, 4), "catchup_analysis") in events
    assert events.index(("raw", date(2026, 9, 2))) < events.index(
        ("recalculate", date(2026, 9, 2), date(2026, 9, 4), "catchup_analysis")
    )


def test_catchup_raw_and_analysis_gaps_use_one_unified_recalculation(monkeypatch) -> None:
    open_dates = [date(2026, 9, day) for day in range(1, 9)]
    job, events = _configured_catchup_job(
        monkeypatch,
        open_dates=open_dates,
        raw_required_dates=[date(2026, 9, 2)],
        analysis_required_dates=[date(2026, 9, 5)],
        latest=date(2026, 9, 8),
        refresh_recent_trade_days=2,
    )

    job.run(date(2026, 9, 8))

    recalculate_events = [event for event in events if event[0] == "recalculate"]
    assert recalculate_events == [
        ("recalculate", date(2026, 9, 2), date(2026, 9, 8), "catchup_analysis")
    ]
    assert events.index(recalculate_events[0]) < events.index(("refresh", date(2026, 9, 7)))
    assert events[-1] == ("dirty_repair",)


def test_catchup_analysis_gap_does_not_access_tushare_raw(monkeypatch) -> None:
    open_dates = [date(2026, 9, day) for day in range(1, 9)]
    job, events = _configured_catchup_job(
        monkeypatch,
        open_dates=open_dates,
        raw_required_dates=[],
        analysis_required_dates=[date(2026, 9, 5)],
        latest=date(2026, 9, 8),
    )

    job.run(date(2026, 9, 8))

    assert not [event for event in events if event[0] == "raw"]
    assert ("recalculate", date(2026, 9, 5), date(2026, 9, 8), "catchup_analysis") in events


def test_catchup_raw_error_commits_evidence_and_blocks_recalculation(monkeypatch) -> None:
    job, events = _configured_catchup_job(
        monkeypatch,
        open_dates=[date(2026, 9, day) for day in range(1, 5)],
        raw_required_dates=[date(2026, 9, 2)],
        analysis_required_dates=[],
        latest=date(2026, 9, 4),
    )

    def fail_raw_repair(current):
        job.db.commit()
        raise catchup_module.DataQualityError(f"raw completeness failed: {current}")

    job._sync_and_validate_raw_date = fail_raw_repair

    with pytest.raises(catchup_module.DataQualityError, match="raw completeness failed"):
        job.run(date(2026, 9, 4))

    assert ("quality_commit",) in events
    assert not [event for event in events if event[0] == "recalculate"]


def test_new_raw_insert_without_dirty_range_still_recalculates_forward(monkeypatch) -> None:
    job, events = _configured_catchup_job(
        monkeypatch,
        open_dates=[date(2026, 9, day) for day in range(1, 5)],
        raw_required_dates=[date(2026, 9, 2)],
        analysis_required_dates=[],
        latest=date(2026, 9, 4),
    )
    inserted_rows = set()

    class InsertOnlyIngestion:
        def sync_trade_calendar(self, start, end):
            events.append(("calendar", start, end))

        def sync_daily(self, trade_date):
            inserted_rows.add((trade_date, "000003.SZ"))

        def sync_adj_factor(self, trade_date):
            return 1

        def sync_daily_basic(self, trade_date):
            return 1

        def sync_index_daily(self, trade_date):
            return 1

    monkeypatch.setattr(
        catchup_module,
        "check_raw_completeness",
        lambda *args, **kwargs: SimpleNamespace(
            overall_status="PASS",
            as_metadata=lambda: {"current_day_datasets": {}},
        ),
    )
    job.ingestion = InsertOnlyIngestion()
    job._sync_and_validate_raw_date = CatchUpJob._sync_and_validate_raw_date.__get__(job)

    job.run(date(2026, 9, 4))

    assert inserted_rows == {(date(2026, 9, 2), "000003.SZ")}
    assert ("recalculate", date(2026, 9, 2), date(2026, 9, 4), "catchup_analysis") in events
    assert events[-1] == ("dirty_repair",)


def test_catchup_recalculation_fails_when_latest_raw_date_is_missing(monkeypatch) -> None:
    job, events = _configured_catchup_job(
        monkeypatch,
        open_dates=[date(2026, 9, 2)],
        raw_required_dates=[],
        analysis_required_dates=[date(2026, 9, 2)],
        latest=None,
    )

    with pytest.raises(RuntimeError, match="no stock_daily data available"):
        job.run(date(2026, 9, 2))

    assert not [event for event in events if event[0] == "recalculate"]


def test_is_analysis_complete_requires_versions_hash_and_pass_coverage(monkeypatch) -> None:
    monkeypatch.setattr(catchup_module, "config_hash", lambda strategy: "current_hash")
    counts = {
        StockDaily: 100,
        StockFactorDaily: 100,
        MarketDaily: 1,
        SectorFactorDaily: 3,
        StockStateDaily: 100,
    }
    monkeypatch.setattr(
        catchup_module,
        "_count_matching",
        lambda db, model, *criteria: counts[model],
    )

    complete = is_analysis_complete(
        object(),
        date(2026, 9, 1),
        strategy={},
        algo_version="v1.0",
    )

    assert complete is True


def test_is_analysis_complete_rejects_low_factor_or_state_coverage(monkeypatch) -> None:
    monkeypatch.setattr(catchup_module, "config_hash", lambda strategy: "current_hash")
    counts = {
        StockDaily: 100,
        StockFactorDaily: 10,
        MarketDaily: 1,
        SectorFactorDaily: 3,
        StockStateDaily: 10,
    }
    monkeypatch.setattr(
        catchup_module,
        "_count_matching",
        lambda db, model, *criteria: counts[model],
    )

    complete = is_analysis_complete(
        object(),
        date(2026, 9, 1),
        strategy={},
        algo_version="v1.0",
    )

    assert complete is False


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


def test_raw_sync_quality_error_commits_before_raise(monkeypatch) -> None:
    calls = []
    quality_calls = []

    class FakeIngestion:
        def sync_daily(self, trade_date):
            calls.append(("daily", trade_date))

        def sync_adj_factor(self, trade_date):
            calls.append(("adj_factor", trade_date))

        def sync_daily_basic(self, trade_date):
            calls.append(("daily_basic", trade_date))

        def sync_index_daily(self, trade_date):
            calls.append(("index_daily", trade_date))

    def raw_quality(db, trade_date, **kwargs):
        quality_calls.append((trade_date, kwargs["persist"]))
        return SimpleNamespace(
            overall_status="ERROR",
            as_metadata=lambda: {"current_day_datasets": {"stock_daily": "ERROR"}},
        )

    monkeypatch.setattr(catchup_module, "check_raw_completeness", raw_quality)
    db = SimpleNamespace(commits=0, commit=lambda: setattr(db, "commits", db.commits + 1))
    job = CatchUpJob.__new__(CatchUpJob)
    job.db = db
    job.ingestion = FakeIngestion()
    job.settings = SimpleNamespace(strategy={})

    with pytest.raises(catchup_module.DataQualityError, match="raw completeness failed"):
        job._sync_and_validate_raw_date(date(2026, 9, 2))

    assert calls == [
        ("daily", date(2026, 9, 2)),
        ("adj_factor", date(2026, 9, 2)),
        ("daily_basic", date(2026, 9, 2)),
        ("index_daily", date(2026, 9, 2)),
    ]
    assert quality_calls == [(date(2026, 9, 2), True)]
    assert db.commits == 1


def test_dirty_repair_not_run_without_open_dirty_ranges(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(catchup_module, "repairable_dirty_ranges", lambda *args, **kwargs: [])
    monkeypatch.setattr(catchup_module, "unresolved_dirty_ranges", lambda db: [])
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
        SimpleNamespace(id=1, status="FAILED", retry_count=1, dirty_start_date=date(2026, 9, 2)),
        SimpleNamespace(id=2, status="OPEN", retry_count=0, dirty_start_date=date(2026, 9, 1)),
    ]
    created_jobs = []
    recalc_calls = []
    monkeypatch.setattr(
        catchup_module,
        "repairable_dirty_ranges",
        lambda *args, **kwargs: dirty_ranges,
    )
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


def test_dirty_repair_does_not_retry_failed_at_limit(monkeypatch) -> None:
    recalc_calls = []
    monkeypatch.setattr(catchup_module, "repairable_dirty_ranges", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        catchup_module,
        "unresolved_dirty_ranges",
        lambda db: [
            SimpleNamespace(
                id=1,
                status="FAILED",
                retry_count=3,
                dirty_start_date=date(2026, 9, 1),
            )
        ],
    )
    monkeypatch.setattr(
        catchup_module,
        "run_recalculation",
        lambda *args, **kwargs: recalc_calls.append((args, kwargs)),
    )
    job = CatchUpJob.__new__(CatchUpJob)
    job.db = object()

    job._run_dirty_repair_if_needed()

    assert recalc_calls == []
