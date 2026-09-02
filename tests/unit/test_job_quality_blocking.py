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

    def sync_trade_calendar(self, start, end):
        return 1

    def sync_stock_basic(self):
        return 1

    def sync_daily(self, trade_date, job_id=None):
        return 1

    def sync_adj_factor(self, trade_date, job_id=None):
        return 1

    def sync_daily_basic(self, trade_date, job_id=None):
        return 1

    def sync_index_daily(self, trade_date, job_id=None):
        return 1

    def sync_sector_metadata(self):
        return 1

    def sync_sector_members(self):
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


def test_daily_job_fails_on_cross_table_error(monkeypatch) -> None:
    monkeypatch.setattr(daily_job_module, "IngestionService", _FakeIngestion)
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


def test_backfill_job_only_syncs_raw_data(monkeypatch) -> None:
    monkeypatch.setattr(backfill_job_module, "upsert_rows", lambda *args, **kwargs: 1)
    monkeypatch.setattr(backfill_job_module, "IngestionService", _FakeIngestion)
    monkeypatch.setattr(backfill_job_module, "_raw_data_complete", lambda *args, **kwargs: False)
    job = _job("backfill")

    BackfillJob(_FakeDb(), _FakeProvider()).run(date(2026, 1, 5), date(2026, 1, 5), job=job)

    assert job.status == "SUCCESS"
    assert job.step == "180 raw sync complete"
    assert job.error_message is None
