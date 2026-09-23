from datetime import date
from types import SimpleNamespace

import app.jobs.backfill_job as backfill_module
import app.services.ingestion.service as ingestion_module
import pandas as pd
import pytest
from app.jobs.backfill_job import BackfillJob
from app.services.ingestion.service import EodDataNotReadyError, IngestionService


class _EmptyDailyProvider:
    def get_daily(self, trade_date: date) -> pd.DataFrame:
        return pd.DataFrame()


class _Db:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_current_empty_daily_raises_eod_not_ready(monkeypatch) -> None:
    today = date(2026, 9, 23)
    monkeypatch.setattr(ingestion_module, "business_today", lambda: today)
    db = _Db()

    with pytest.raises(EodDataNotReadyError, match="EOD_NOT_READY"):
        IngestionService(db, _EmptyDailyProvider()).sync_daily(today)

    assert db.commits == 0
    assert db.rollbacks == 1


def test_historical_empty_daily_remains_quality_error(monkeypatch) -> None:
    today = date(2026, 9, 23)
    historical = date(2026, 9, 4)
    quality = []
    monkeypatch.setattr(ingestion_module, "business_today", lambda: today)
    monkeypatch.setattr(
        ingestion_module, "expected_stock_daily_codes", lambda *args: {"000001.SZ"}
    )
    monkeypatch.setattr(
        ingestion_module,
        "persist_coverage_result",
        lambda db, result, **kwargs: quality.append((result, kwargs)),
    )
    db = _Db()

    with pytest.raises(ValueError, match="DAILY_EMPTY"):
        IngestionService(db, _EmptyDailyProvider()).sync_daily(historical)

    assert quality[0][0].status == "ERROR"
    assert quality[0][1]["extra_issue_codes"]["raw_issues"] == ["DAILY_EMPTY"]


def test_backfill_defers_current_eod_and_keeps_completed_history(monkeypatch) -> None:
    historical = date(2026, 9, 22)
    today = date(2026, 9, 23)
    calendar = pd.DataFrame([
        {"cal_date": "20260922", "is_open": 1, "exchange": "SSE"},
        {"cal_date": "20260923", "is_open": 1, "exchange": "SSE"},
    ])

    class Result:
        def scalar_one(self):
            return 1

    class Db(_Db):
        def execute(self, statement):
            return Result()

    class Provider:
        def get_trade_calendar(self, start, end):
            return calendar

    class Detail:
        status = "ERROR"
        is_acceptable = False

    class Completeness:
        def __init__(self, trade_date, complete):
            self.trade_date = trade_date
            self.is_complete = complete
            self.stock_daily = SimpleNamespace(is_acceptable=complete)
            self.index_daily = SimpleNamespace(status="PASS" if complete else "ERROR")

        def dataset(self, name):
            return SimpleNamespace(
                status="PASS" if self.is_complete else "ERROR",
                is_acceptable=self.is_complete,
            )

        def as_metadata(self):
            return {"current_day_datasets": {}}

    class FakeIngestion:
        def sync_theme_daily(self, trade_date):
            return 0

        def sync_theme_optional_sources(self, trade_date):
            return {}

        def sync_stock_st(self, trade_date, job_id=None):
            return 1

        def sync_suspend_daily(self, trade_date, job_id=None):
            return 1

        def sync_daily(self, trade_date, job_id=None):
            raise EodDataNotReadyError("EOD_NOT_READY")

        def __getattr__(self, name):
            raise AssertionError(f"dataset after current daily must not run: {name}")

    updates = []
    monkeypatch.setattr(backfill_module, "ensure_stock_basic_ready", lambda db: None)
    monkeypatch.setattr(backfill_module, "_any_index_daily_incomplete", lambda *args: False)
    monkeypatch.setattr(
        backfill_module, "upsert_rows", lambda db, model, rows, keys: len(rows)
    )
    monkeypatch.setattr(
        backfill_module,
        "check_raw_completeness",
        lambda db, trade_date, **kwargs: Completeness(
            trade_date, trade_date == historical
        ),
    )
    monkeypatch.setattr(
        backfill_module, "update_job", lambda db, job, **kwargs: updates.append(kwargs)
    )
    db = Db()
    runner = BackfillJob(db, Provider())
    runner.ingestion = FakeIngestion()
    job = SimpleNamespace(id="job-id")

    runner.run(historical, today, job=job)

    final = updates[-1]
    assert final["status"] == "SUCCESS"
    assert final["step"] == "175 raw sync complete; current EOD deferred"
    assert final["metadata"]["deferred_trade_date"] == "2026-09-23"
    assert final["metadata"]["deferred_reason"] == "EOD_NOT_READY"
    assert final["metadata"]["completed_open_days"] == 1
    assert final["metadata"]["open_days"] == 2
    assert final["metadata"]["progress_pct"] < 100
    assert db.rollbacks == 0


def test_backfill_full_completion_reports_one_hundred_percent(monkeypatch) -> None:
    target = date(2026, 9, 22)
    calendar = pd.DataFrame([
        {"cal_date": "20260922", "is_open": 1, "exchange": "SSE"},
    ])

    class Result:
        def scalar_one(self):
            return 1

    class Db(_Db):
        def execute(self, statement):
            return Result()

    class Provider:
        def get_trade_calendar(self, start, end):
            return calendar

    class Completeness:
        trade_date = target
        is_complete = True
        stock_daily = SimpleNamespace(is_acceptable=True)
        index_daily = SimpleNamespace(status="PASS")

        def dataset(self, name):
            return SimpleNamespace(status="PASS", is_acceptable=True)

        def as_metadata(self):
            return {"current_day_datasets": {}}

    class FakeIngestion:
        def sync_theme_daily(self, trade_date):
            return 0

        def sync_theme_optional_sources(self, trade_date):
            return {}

    updates = []
    monkeypatch.setattr(backfill_module, "ensure_stock_basic_ready", lambda db: None)
    monkeypatch.setattr(backfill_module, "_any_index_daily_incomplete", lambda *args: False)
    monkeypatch.setattr(
        backfill_module, "upsert_rows", lambda db, model, rows, keys: len(rows)
    )
    monkeypatch.setattr(
        backfill_module,
        "check_raw_completeness",
        lambda db, trade_date, **kwargs: Completeness(),
    )
    monkeypatch.setattr(
        backfill_module, "update_job", lambda db, job, **kwargs: updates.append(kwargs)
    )
    runner = BackfillJob(Db(), Provider())
    runner.ingestion = FakeIngestion()

    runner.run(target, target, job=SimpleNamespace(id="job-id"))

    final = updates[-1]
    assert final["status"] == "SUCCESS"
    assert final["step"] == "180 raw sync complete"
    assert final["metadata"]["stage"] == "success"
    assert final["metadata"]["completed_open_days"] == 1
    assert final["metadata"]["open_days"] == 1
    assert final["metadata"]["progress_pct"] == 100
