from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import app.jobs.backfill_job as backfill_job_module
import app.jobs.daily_job as daily_job_module
import pandas as pd
import pytest
from app.jobs.backfill_job import BackfillJob
from app.jobs.daily_job import DailyJob
from app.services.quality.daily_quality import DataQualityError


class _FakeDb:
    def add(self, row):
        return None

    def commit(self):
        return None

    def refresh(self, row):
        return None

    def rollback(self):
        return None


class _FakeIngestion:
    def __init__(self, db, provider):
        self.db = db
        self.provider = provider
        self.calls = getattr(provider, "calls", None)

    def _record(self, name: str) -> None:
        if self.calls is not None:
            self.calls.append(name)

    def sync_trade_calendar(self, start, end):
        self._record("trade_calendar")
        return 1

    def sync_stock_basic(self):
        self._record("stock_basic")
        return 1

    def sync_daily(self, trade_date, job_id=None):
        self._record("daily")
        return 1

    def sync_adj_factor(self, trade_date, job_id=None):
        self._record("adj_factor")
        return 1

    def sync_daily_basic(self, trade_date, job_id=None):
        self._record("daily_basic")
        return 1

    def sync_index_daily(self, trade_date, job_id=None):
        self._record("index_daily")
        return 1

    def sync_index_daily_range(self, start, end, job_id=None):
        self._record("index_daily_range")
        return 1

    def sync_sector_metadata(self):
        self._record("sector_metadata")
        return 1

    def sync_sector_members(self):
        self._record("sector_members")
        return 1


class _FakeScalarService:
    def __init__(self, db):
        self.db = db

    def recalc(self, *args, **kwargs):
        return 1


class _FakeTrendService:
    def __init__(self, db):
        self.db = db

    def recalc(self, *args, **kwargs):
        return {"states": 1, "signals": 0}


class _FakeProvider:
    def get_trade_calendar(self, start, end):
        return pd.DataFrame([{"cal_date": "20260105", "is_open": 1}])


def _job(job_type: str = "daily") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        job_type=job_type,
        target_trade_date=date(2026, 1, 5),
        started_at=None,
        finished_at=None,
        status="QUEUED",
        step=None,
        row_count=0,
        error_message=None,
        job_metadata={},
    )


def _cross_error(*args, **kwargs):
    return SimpleNamespace(has_error=True, error_datasets=["factor_vs_daily"])


def _cross_pass(*args, **kwargs):
    return SimpleNamespace(has_error=False, error_datasets=[])


def _raw_complete(index_status: str = "PASS", is_complete: bool = True):
    dataset = SimpleNamespace(status="PASS", is_acceptable=True)
    index = SimpleNamespace(status=index_status, is_acceptable=index_status == "PASS")
    return SimpleNamespace(
        is_complete=is_complete,
        stock_daily=dataset,
        adj_factor=dataset,
        daily_basic=dataset,
        index_daily=index,
        dataset=lambda name: index if name == "index_daily" else dataset,
        as_metadata=lambda: {
            "current_day_datasets": {
                "stock_daily": "PASS",
                "adj_factor": "PASS",
                "daily_basic": "PASS",
                "index_daily": index_status,
            },
            "error_dataset_count": 0 if index_status == "PASS" else 1,
        },
    )


def test_daily_job_fails_on_cross_table_error(monkeypatch) -> None:
    monkeypatch.setattr(daily_job_module, "IngestionService", _FakeIngestion)
    monkeypatch.setattr(daily_job_module, "trade_calendar_open_status", lambda *args: True)
    monkeypatch.setattr(daily_job_module, "FactorService", _FakeScalarService)
    monkeypatch.setattr(daily_job_module, "MarketService", _FakeScalarService)
    monkeypatch.setattr(daily_job_module, "SectorService", _FakeScalarService)
    monkeypatch.setattr(daily_job_module, "TrendService", _FakeTrendService)
    monkeypatch.setattr(daily_job_module, "record_cross_table_quality", _cross_error)
    job = _job()

    with pytest.raises(DataQualityError):
        DailyJob(_FakeDb(), object()).run(date(2026, 1, 5), job=job)

    assert job.status == "FAILED"
    assert "cross table quality failed" in job.error_message


def test_daily_job_does_not_sync_sector_base_tables(monkeypatch) -> None:
    monkeypatch.setattr(daily_job_module, "IngestionService", _FakeIngestion)
    monkeypatch.setattr(daily_job_module, "trade_calendar_open_status", lambda *args: True)
    monkeypatch.setattr(daily_job_module, "FactorService", _FakeScalarService)
    monkeypatch.setattr(daily_job_module, "MarketService", _FakeScalarService)
    monkeypatch.setattr(daily_job_module, "SectorService", _FakeScalarService)
    monkeypatch.setattr(daily_job_module, "TrendService", _FakeTrendService)
    monkeypatch.setattr(daily_job_module, "record_cross_table_quality", _cross_pass)
    provider = SimpleNamespace(calls=[])
    job = _job()

    DailyJob(_FakeDb(), provider).run(date(2026, 1, 5), job=job)

    assert job.status == "SUCCESS"
    assert "sector_metadata" not in provider.calls
    assert "sector_members" not in provider.calls


def test_daily_job_noops_on_closed_trade_date(monkeypatch) -> None:
    monkeypatch.setattr(daily_job_module, "IngestionService", _FakeIngestion)
    monkeypatch.setattr(daily_job_module, "trade_calendar_open_status", lambda *args: False)
    job = _job()

    DailyJob(_FakeDb(), object()).run(date(2026, 1, 5), job=job)

    assert job.status == "SUCCESS"
    assert job.step == "180 no trading day"
    assert job.job_metadata["noop"] is True


def test_backfill_job_only_syncs_raw_data(monkeypatch) -> None:
    monkeypatch.setattr(backfill_job_module, "upsert_rows", lambda *args, **kwargs: 1)
    monkeypatch.setattr(backfill_job_module, "IngestionService", _FakeIngestion)
    monkeypatch.setattr(backfill_job_module, "ensure_stock_basic_ready", lambda *args: None)
    monkeypatch.setattr(
        backfill_job_module,
        "check_raw_completeness",
        lambda *args, **kwargs: _raw_complete(),
    )
    job = _job("backfill")

    BackfillJob(_FakeDb(), _FakeProvider()).run(date(2026, 1, 5), date(2026, 1, 5), job=job)

    assert job.status == "SUCCESS"
    assert job.step == "180 raw sync complete"
    assert job.error_message is None


def test_backfill_prefetches_index_daily_by_range_when_missing(monkeypatch) -> None:
    states = iter([_raw_complete("ERROR", False), _raw_complete()])
    monkeypatch.setattr(backfill_job_module, "upsert_rows", lambda *args, **kwargs: 1)
    monkeypatch.setattr(backfill_job_module, "IngestionService", _FakeIngestion)
    monkeypatch.setattr(backfill_job_module, "ensure_stock_basic_ready", lambda *args: None)
    monkeypatch.setattr(
        backfill_job_module,
        "check_raw_completeness",
        lambda *args, **kwargs: next(states),
    )
    provider = _FakeProvider()
    provider.calls = []
    job = _job("backfill")

    BackfillJob(_FakeDb(), provider).run(date(2026, 1, 5), date(2026, 1, 5), job=job)

    assert job.status == "SUCCESS"
    assert provider.calls == ["index_daily_range"]


def test_backfill_job_requires_stock_basic(monkeypatch) -> None:
    monkeypatch.setattr(backfill_job_module, "IngestionService", _FakeIngestion)
    monkeypatch.setattr(
        backfill_job_module,
        "ensure_stock_basic_ready",
        lambda *args: (_ for _ in ()).throw(
            RuntimeError("stock_basic is missing or incomplete, run sync-basic first")
        ),
    )
    job = _job("backfill")

    with pytest.raises(RuntimeError, match="run sync-basic first"):
        BackfillJob(_FakeDb(), _FakeProvider()).run(date(2026, 1, 5), date(2026, 1, 5), job=job)

    assert job.status == "FAILED"
