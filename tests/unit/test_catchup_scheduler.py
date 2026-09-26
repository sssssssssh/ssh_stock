from datetime import date
from types import SimpleNamespace

import app.jobs.catchup_job as catchup_module
import app.jobs.scheduler as scheduler_module
import app.services.quality.analysis_readiness as analysis_readiness
import pytest
from app.jobs.catchup_job import (
    CatchUpJob,
    build_catchup_plan,
    classify_catchup_dates,
    is_analysis_complete,
)
from app.jobs.scheduler import (
    _research_sources_current,
    cron_trigger_kwargs,
    run_scheduled_basic_info,
    run_scheduled_catchup,
    run_scheduled_eod_retry,
)
from app.models.market_data import (
    MarketDaily,
    SectorFactorDaily,
    StockDaily,
    StockFactorDaily,
    StockStateDaily,
)
from app.services.quality.analysis_readiness import analysis_complete_dates


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
        analysis_readiness,
        "_open_trade_dates",
        lambda db, start, end: [date(2026, 9, 1), date(2026, 9, 2)],
    )
    monkeypatch.setattr(
        analysis_readiness,
        "is_analysis_complete",
        lambda db, trade_date, **kwargs: (
            trade_date == date(2026, 9, 2) and kwargs["algo_version"] == "v1.0"
        ),
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
        lambda db, trade_date, **kwargs: (
            checked_dates.append(trade_date) or SimpleNamespace(is_complete=True)
        ),
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
    monkeypatch.setattr(
        analysis_readiness, "analysis_strategy_hash", lambda strategy: "current_hash"
    )

    def count_matching(db, model, *criteria):
        text = " ".join(
            str(criterion.compile(compile_kwargs={"literal_binds": True})) for criterion in criteria
        )
        calls[model.__name__] = text
        if model is StockDaily:
            return 100
        if model is StockFactorDaily:
            return 0
        return 1

    monkeypatch.setattr(analysis_readiness, "_count_matching", count_matching)

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

    def classify(*args, **kwargs):
        events.append(("classify",))
        return raw_required_dates, analysis_required_dates

    monkeypatch.setattr(catchup_module, "classify_catchup_dates", classify)
    monkeypatch.setattr(catchup_module, "latest_raw_trade_date", lambda db: latest)

    job = CatchUpJob.__new__(CatchUpJob)
    job.db = SimpleNamespace(commit=lambda: events.append(("quality_commit",)))
    job.provider = object()
    job.settings = SimpleNamespace(strategy={}, algo_version="v1.1")
    job.ingestion = SimpleNamespace(
        sync_trade_calendar=lambda start, end: events.append(("calendar", start, end)),
        sync_stock_basic=lambda: events.append(("stock_basic",)),
    )
    job._sync_and_validate_raw_date = lambda current: events.append(("raw", current))
    job._run_analysis_repair = lambda start, end, mode: events.append(
        ("recalculate", start, end, mode)
    )
    job._refresh_raw_only = lambda current: events.append(("refresh", current))
    job._theme_repair_dates = lambda dates: []
    job._run_dirty_repair_if_needed = lambda: events.append(("dirty_repair",))
    return job, events


def test_catchup_refreshes_stock_basic_before_classifying_dates(monkeypatch) -> None:
    job, events = _configured_catchup_job(
        monkeypatch,
        open_dates=[date(2026, 9, 1)],
        raw_required_dates=[],
        analysis_required_dates=[],
        latest=None,
    )

    job.run(date(2026, 9, 1))

    assert [event[0] for event in events[:3]] == [
        "calendar",
        "stock_basic",
        "classify",
    ]


def test_catchup_stock_basic_failure_blocks_classify_raw_and_recalculation(
    monkeypatch,
) -> None:
    job, events = _configured_catchup_job(
        monkeypatch,
        open_dates=[date(2026, 9, 1)],
        raw_required_dates=[date(2026, 9, 1)],
        analysis_required_dates=[date(2026, 9, 1)],
        latest=date(2026, 9, 1),
    )

    def fail_stock_basic():
        events.append(("stock_basic_failed",))
        raise RuntimeError("stock_basic unavailable")

    job.ingestion.sync_stock_basic = fail_stock_basic

    with pytest.raises(RuntimeError, match="stock_basic unavailable"):
        job.run(date(2026, 9, 1))

    assert ("classify",) not in events
    assert not [event for event in events if event[0] in {"raw", "recalculate"}]


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

        def sync_stock_basic(self):
            events.append(("stock_basic",))

        def sync_daily(self, trade_date):
            inserted_rows.add((trade_date, "000003.SZ"))

        def sync_adj_factor(self, trade_date):
            return 1

        def sync_daily_basic(self, trade_date):
            return 1

        def sync_index_daily(self, trade_date):
            return 1

        def sync_stock_st(self, trade_date):
            return 0

        def sync_suspend_daily(self, trade_date):
            return 0

        def sync_stock_limit(self, trade_date):
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
    monkeypatch.setattr(
        catchup_module,
        "TradeStatusService",
        lambda db: SimpleNamespace(recalc=lambda *args: 1),
    )
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
    monkeypatch.setattr(
        analysis_readiness, "analysis_strategy_hash", lambda strategy: "current_hash"
    )
    counts = {
        StockDaily: 100,
        StockFactorDaily: 100,
        MarketDaily: 1,
        SectorFactorDaily: 3,
        StockStateDaily: 100,
    }
    monkeypatch.setattr(
        analysis_readiness,
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
    monkeypatch.setattr(
        analysis_readiness, "analysis_strategy_hash", lambda strategy: "current_hash"
    )
    counts = {
        StockDaily: 100,
        StockFactorDaily: 10,
        MarketDaily: 1,
        SectorFactorDaily: 3,
        StockStateDaily: 10,
    }
    monkeypatch.setattr(
        analysis_readiness,
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
    monkeypatch.setattr(
        scheduler_module,
        "create_queued_ingestion_job",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            scheduler_module.ActiveIngestionJobError("job-1", "backfill", "RUNNING")
        ),
    )

    executed = run_scheduled_catchup(object(), object(), date(2026, 9, 4))

    assert executed is False


def test_scheduler_enqueues_catchup_without_executing_it(monkeypatch) -> None:
    calls = []

    def enqueue(db, job_type, target_trade_date, **kwargs):
        calls.append((job_type, target_trade_date, kwargs))
        return object()

    monkeypatch.setattr(
        scheduler_module,
        "create_queued_ingestion_job",
        enqueue,
    )

    executed = run_scheduled_catchup(object(), object(), date(2026, 9, 4))

    assert executed is True
    assert calls[0][0:2] == ("catchup", date(2026, 9, 4))


def test_scheduler_runs_weekly_basic_refresh_with_existing_guard(monkeypatch) -> None:
    calls = []

    def fake_enqueue(db, job_type, target_trade_date, **kwargs):
        calls.append((job_type, kwargs["metadata"]["source"]))
        return object()

    monkeypatch.setattr(
        scheduler_module,
        "create_queued_ingestion_job",
        fake_enqueue,
    )

    assert run_scheduled_basic_info(object(), object()) is True
    assert calls == [("sync_basic", "scheduler")]


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

        def sync_stock_st(self, trade_date):
            calls.append(("stock_st", trade_date))

        def sync_suspend_daily(self, trade_date):
            calls.append(("suspend_d", trade_date))

        def sync_stock_limit(self, trade_date):
            calls.append(("stk_limit", trade_date))

        def sync_theme_daily(self, trade_date):
            calls.append(("theme_daily", trade_date))

        def sync_theme_optional_sources(self, trade_date):
            calls.append(("theme_optional", trade_date))

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
    job._sync_theme_raw_best_effort = lambda current, force=False: (
        calls.append(("theme_daily", current)),
        calls.append(("theme_optional", current)),
    )
    job.settings = SimpleNamespace(strategy={})
    monkeypatch.setattr(
        catchup_module,
        "TradeStatusService",
        lambda db: SimpleNamespace(
            recalc=lambda start, end: calls.append(("trade_status", start)) or 1
        ),
    )

    job._refresh_raw_only(date(2026, 9, 4))

    assert calls == [
        ("stock_st", date(2026, 9, 4)),
        ("suspend_d", date(2026, 9, 4)),
        ("daily", date(2026, 9, 4)),
        ("adj_factor", date(2026, 9, 4)),
        ("daily_basic", date(2026, 9, 4)),
        ("index_daily", date(2026, 9, 4)),
        ("stk_limit", date(2026, 9, 4)),
        ("trade_status", date(2026, 9, 4)),
        ("theme_daily", date(2026, 9, 4)),
        ("theme_optional", date(2026, 9, 4)),
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

        def sync_stock_st(self, trade_date):
            calls.append(("stock_st", trade_date))

        def sync_suspend_daily(self, trade_date):
            calls.append(("suspend_d", trade_date))

        def sync_stock_limit(self, trade_date):
            calls.append(("stk_limit", trade_date))

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
        ("stock_st", date(2026, 9, 2)),
        ("suspend_d", date(2026, 9, 2)),
        ("daily", date(2026, 9, 2)),
        ("adj_factor", date(2026, 9, 2)),
        ("daily_basic", date(2026, 9, 2)),
        ("index_daily", date(2026, 9, 2)),
        ("stk_limit", date(2026, 9, 2)),
    ]
    assert quality_calls == [(date(2026, 9, 2), True)]
    assert db.commits == 1


def test_catchup_defers_current_day_eod_not_ready(monkeypatch) -> None:
    target = date(2026, 9, 24)
    calls = []

    class FakeIngestion:
        def sync_stock_st(self, trade_date):
            calls.append("stock_st")

        def sync_suspend_daily(self, trade_date):
            calls.append("suspend_d")

        def sync_daily(self, trade_date):
            raise catchup_module.EodDataNotReadyError("EOD_NOT_READY")

    db = SimpleNamespace(rollback=lambda: calls.append("rollback"))
    job = CatchUpJob.__new__(CatchUpJob)
    job.db = db
    job.ingestion = FakeIngestion()
    monkeypatch.setattr(catchup_module, "business_today", lambda: target)

    assert job._sync_and_validate_raw_date(target) is False
    assert calls == ["stock_st", "suspend_d", "rollback"]


def test_catchup_historical_eod_not_ready_remains_error(monkeypatch) -> None:
    class FakeIngestion:
        def sync_stock_st(self, trade_date):
            pass

        def sync_suspend_daily(self, trade_date):
            pass

        def sync_daily(self, trade_date):
            raise catchup_module.EodDataNotReadyError("EOD_NOT_READY")

    job = CatchUpJob.__new__(CatchUpJob)
    job.db = SimpleNamespace(rollback=lambda: None)
    job.ingestion = FakeIngestion()
    monkeypatch.setattr(catchup_module, "business_today", lambda: date(2026, 9, 24))

    with pytest.raises(catchup_module.EodDataNotReadyError):
        job._sync_and_validate_raw_date(date(2026, 9, 23))


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


def test_historical_theme_repair_recalculates_to_latest_raw(monkeypatch) -> None:
    repair_date = date(2026, 9, 2)
    latest = date(2026, 9, 16)
    job, events = _configured_catchup_job(
        monkeypatch,
        open_dates=[repair_date, latest],
        raw_required_dates=[],
        analysis_required_dates=[],
        latest=latest,
    )
    job._theme_repair_dates = lambda dates: [repair_date]
    job._sync_theme_raw_best_effort = lambda current: events.append(
        ("theme_repair", current)
    ) or True

    job.run(latest)

    assert ("theme_repair", repair_date) in events
    assert ("recalculate", repair_date, latest, "catchup_analysis") in events


def test_research_sources_must_all_reach_expected_trade_date() -> None:
    expected = date(2026, 9, 24)

    assert _research_sources_current(expected, expected, expected, expected)
    assert not _research_sources_current(
        expected,
        expected,
        date(2026, 9, 23),
        expected,
    )
    assert not _research_sources_current(expected, expected, expected, None)


def test_eod_retry_queues_catchup_until_ready_then_research(monkeypatch) -> None:
    expected = date(2026, 9, 24)

    class Db:
        def __init__(self, values):
            self.values = list(values)

        def scalar(self, statement):
            return self.values.pop(0)

    events = []
    monkeypatch.setattr(
        scheduler_module,
        "run_scheduled_catchup",
        lambda db, provider, target: events.append(("catchup", target)) or True,
    )
    monkeypatch.setattr(
        scheduler_module,
        "run_scheduled_research",
        lambda db, target: events.append(("research", target)) or True,
    )

    assert run_scheduled_eod_retry(
        Db([expected, expected, date(2026, 9, 23), date(2026, 9, 23)]), expected
    )
    assert run_scheduled_eod_retry(Db([expected, expected, expected, expected]), expected)
    assert events == [("catchup", expected), ("research", expected)]


@pytest.mark.parametrize(
    ("core_complete", "opportunity_complete", "theme_repair_succeeds", "expected_recalc"),
    [
        (True, False, False, True),
        (True, True, False, False),
        (True, True, True, True),
        (False, False, False, True),
    ],
    ids=[
        "missing_opportunity_theme_repair_fails",
        "complete_opportunity_theme_repair_fails",
        "theme_repair_succeeds",
        "incomplete_core_theme_repair_fails",
    ],
)
def test_catchup_theme_repair_does_not_block_required_analysis(
    monkeypatch, core_complete, opportunity_complete, theme_repair_succeeds, expected_recalc
) -> None:
    trade_date = date(2026, 9, 21)
    job, events = _configured_catchup_job(
        monkeypatch,
        open_dates=[trade_date],
        raw_required_dates=[],
        analysis_required_dates=[],
        latest=trade_date,
    )
    job.settings.opportunity_config = {}
    monkeypatch.setattr(
        catchup_module,
        "check_raw_completeness",
        lambda *args, **kwargs: SimpleNamespace(is_complete=True),
    )
    monkeypatch.setattr(
        catchup_module,
        "is_analysis_complete",
        lambda *args, **kwargs: core_complete and opportunity_complete,
    )
    monkeypatch.setattr(catchup_module, "classify_catchup_dates", classify_catchup_dates)
    job._theme_repair_dates = lambda dates: [trade_date]
    job._sync_theme_raw_best_effort = lambda current: (
        events.append(("theme_repair", current)) or theme_repair_succeeds
    )

    plan = job.run(trade_date)

    assert plan.analysis_required_dates == (
        [] if core_complete and opportunity_complete else [trade_date]
    )
    assert ("theme_repair", trade_date) in events
    recalc_events = [event for event in events if event[0] == "recalculate"]
    assert recalc_events == (
        [("recalculate", trade_date, trade_date, "catchup_analysis")]
        if expected_recalc
        else []
    )
