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
    def execute(self, statement):
        return SimpleNamespace(scalar_one=lambda: 1)

    def add(self, row):
        return None

    def commit(self):
        return None

    def refresh(self, row):
        return None

    def rollback(self):
        return None


class _QualityEvidenceDb(_FakeDb):
    def __init__(self) -> None:
        self.pending: list[tuple[str, str]] = []
        self.committed: list[tuple[str, str]] = []
        self.rollbacks = 0

    def commit(self):
        self.committed.extend(self.pending)
        self.pending.clear()

    def rollback(self):
        self.rollbacks += 1
        self.pending.clear()


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

    def sync_stock_st(self, trade_date, job_id=None):
        self._record("stock_st")
        return 1

    def sync_suspend_daily(self, trade_date, job_id=None):
        self._record("suspend_d")
        return 1

    def sync_stock_limit(self, trade_date, job_id=None):
        self._record("stk_limit")
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

    def sync_theme_daily(self, trade_date):
        self._record("theme_daily")
        return 1

    def sync_theme_optional_sources(self, trade_date):
        self._record("theme_optional")
        return {"moneyflow": "PASS", "limit": "PASS"}


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


@pytest.fixture(autouse=True)
def _patch_trade_status_service(monkeypatch):
    monkeypatch.setattr(daily_job_module, "TradeStatusService", _FakeScalarService)
    monkeypatch.setattr(daily_job_module, "ThemeFactorService", _FakeScalarService)
    monkeypatch.setattr(daily_job_module, "OpportunityService", _FakeScalarService)


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


def _raw_complete(
    index_status: str = "PASS",
    is_complete: bool = True,
    overall_status: str = "PASS",
    adj_factor_status: str = "PASS",
    daily_basic_status: str = "PASS",
):
    stock_daily = SimpleNamespace(
        status="PASS",
        is_acceptable=True,
        missing_codes=[],
        invalid_count=0,
    )
    adj_factor = SimpleNamespace(
        status=adj_factor_status,
        is_acceptable=adj_factor_status in {"PASS", "WARNING"},
        missing_codes=["000001.SZ"] if adj_factor_status == "ERROR" else [],
        invalid_count=0,
    )
    daily_basic = SimpleNamespace(
        status=daily_basic_status,
        is_acceptable=daily_basic_status in {"PASS", "WARNING"},
        missing_codes=[],
        invalid_count=0,
    )
    index = SimpleNamespace(
        status=index_status,
        is_acceptable=index_status == "PASS",
        missing_codes=[],
        invalid_count=0,
    )
    stock_st = SimpleNamespace(status="PASS", is_acceptable=True, invalid_count=0)
    suspend_d = SimpleNamespace(status="PASS", is_acceptable=True, invalid_count=0)
    stk_limit = SimpleNamespace(status="PASS", is_acceptable=True, invalid_count=0)
    return SimpleNamespace(
        is_complete=is_complete,
        overall_status=overall_status,
        trade_date=date(2026, 1, 5),
        stock_daily=stock_daily,
        adj_factor=adj_factor,
        daily_basic=daily_basic,
        index_daily=index,
        stock_st=stock_st,
        suspend_d=suspend_d,
        stk_limit=stk_limit,
        dataset=lambda name: {
            "stock_daily": stock_daily,
            "adj_factor": adj_factor,
            "daily_basic": daily_basic,
            "index_daily": index,
            "stock_st": stock_st,
            "suspend_d": suspend_d,
            "stk_limit": stk_limit,
        }[name],
        as_metadata=lambda: {
            "current_day_datasets": {
                "stock_daily": "PASS",
                "adj_factor": adj_factor_status,
                "daily_basic": daily_basic_status,
                "index_daily": index_status,
            },
            "current_day_status": overall_status,
            "current_day_invalid_counts": {
                "stock_daily": 0,
                "adj_factor": 0,
                "daily_basic": 0,
                "index_daily": 0,
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
    monkeypatch.setattr(
        daily_job_module,
        "check_raw_completeness",
        lambda *args, **kwargs: _raw_complete(),
    )
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
    monkeypatch.setattr(
        daily_job_module,
        "check_raw_completeness",
        lambda *args, **kwargs: _raw_complete(),
    )
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


def test_daily_raw_gate_error_blocks_calculation(monkeypatch) -> None:
    monkeypatch.setattr(daily_job_module, "IngestionService", _FakeIngestion)
    monkeypatch.setattr(daily_job_module, "trade_calendar_open_status", lambda *args: True)
    monkeypatch.setattr(
        daily_job_module,
        "check_raw_completeness",
        lambda *args, **kwargs: _raw_complete(
            is_complete=False,
            overall_status="ERROR",
            adj_factor_status="ERROR",
        ),
    )
    calls = []

    class FailingFactorService:
        def __init__(self, db):
            self.db = db

        def recalc(self, *args, **kwargs):
            calls.append("factor")
            return 1

    monkeypatch.setattr(daily_job_module, "FactorService", FailingFactorService)
    job = _job()

    with pytest.raises(DataQualityError, match="raw completeness gate failed"):
        DailyJob(_FakeDb(), object()).run(date(2026, 1, 5), job=job)

    assert calls == []
    assert job.status == "FAILED"


def test_daily_raw_error_quality_evidence_survives_failed_job(monkeypatch) -> None:
    db = _QualityEvidenceDb()

    def raw_error(db, *args, **kwargs):
        db.pending.append(("stock_adj_factor", "ERROR"))
        return _raw_complete(
            is_complete=False,
            overall_status="ERROR",
            adj_factor_status="ERROR",
        )

    monkeypatch.setattr(daily_job_module, "IngestionService", _FakeIngestion)
    monkeypatch.setattr(daily_job_module, "trade_calendar_open_status", lambda *args: True)
    monkeypatch.setattr(daily_job_module, "check_raw_completeness", raw_error)
    job = _job()

    with pytest.raises(DataQualityError, match="raw completeness gate failed"):
        DailyJob(db, object()).run(date(2026, 1, 5), job=job)

    assert ("stock_adj_factor", "ERROR") in db.committed
    assert job.status == "FAILED"
    assert db.rollbacks >= 1


def test_daily_raw_gate_warning_allows_calculation(monkeypatch) -> None:
    monkeypatch.setattr(daily_job_module, "IngestionService", _FakeIngestion)
    monkeypatch.setattr(daily_job_module, "trade_calendar_open_status", lambda *args: True)
    monkeypatch.setattr(
        daily_job_module,
        "check_raw_completeness",
        lambda *args, **kwargs: _raw_complete(
            is_complete=True,
            overall_status="WARNING",
            daily_basic_status="WARNING",
        ),
    )
    monkeypatch.setattr(daily_job_module, "FactorService", _FakeScalarService)
    monkeypatch.setattr(daily_job_module, "MarketService", _FakeScalarService)
    monkeypatch.setattr(daily_job_module, "SectorService", _FakeScalarService)
    monkeypatch.setattr(daily_job_module, "TrendService", _FakeTrendService)
    monkeypatch.setattr(daily_job_module, "record_cross_table_quality", _cross_pass)
    job = _job()

    DailyJob(_FakeDb(), object()).run(date(2026, 1, 5), job=job)

    assert job.status == "SUCCESS"
    assert job.job_metadata["current_day_status"] == "WARNING"


def test_daily_cross_table_error_quality_evidence_survives_failed_job(monkeypatch) -> None:
    db = _QualityEvidenceDb()

    def cross_error(db, *args, **kwargs):
        db.pending.append(("factor_vs_daily", "ERROR"))
        return _cross_error()

    monkeypatch.setattr(daily_job_module, "IngestionService", _FakeIngestion)
    monkeypatch.setattr(daily_job_module, "trade_calendar_open_status", lambda *args: True)
    monkeypatch.setattr(
        daily_job_module,
        "check_raw_completeness",
        lambda *args, **kwargs: _raw_complete(),
    )
    monkeypatch.setattr(daily_job_module, "FactorService", _FakeScalarService)
    monkeypatch.setattr(daily_job_module, "MarketService", _FakeScalarService)
    monkeypatch.setattr(daily_job_module, "SectorService", _FakeScalarService)
    monkeypatch.setattr(daily_job_module, "TrendService", _FakeTrendService)
    monkeypatch.setattr(daily_job_module, "record_cross_table_quality", cross_error)
    job = _job()

    with pytest.raises(DataQualityError, match="cross table quality failed"):
        DailyJob(db, object()).run(date(2026, 1, 5), job=job)

    assert ("factor_vs_daily", "ERROR") in db.committed
    assert job.status == "FAILED"
    assert db.rollbacks >= 1


def test_backfill_job_only_syncs_raw_data(monkeypatch) -> None:
    monkeypatch.setattr(backfill_job_module, "upsert_rows", lambda *args, **kwargs: 1)
    monkeypatch.setattr(backfill_job_module, "IngestionService", _FakeIngestion)
    monkeypatch.setattr(backfill_job_module, "ensure_stock_basic_ready", lambda *args: None)
    monkeypatch.setattr(backfill_job_module, "_any_index_daily_incomplete", lambda *args: False)
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
    states = iter([_raw_complete()])
    monkeypatch.setattr(backfill_job_module, "upsert_rows", lambda *args, **kwargs: 1)
    monkeypatch.setattr(backfill_job_module, "IngestionService", _FakeIngestion)
    monkeypatch.setattr(backfill_job_module, "ensure_stock_basic_ready", lambda *args: None)
    monkeypatch.setattr(backfill_job_module, "_any_index_daily_incomplete", lambda *args: True)
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
    assert provider.calls == ["index_daily_range", "theme_daily", "theme_optional"]


def test_backfill_falls_back_to_daily_index_when_range_fails(monkeypatch) -> None:
    states = iter(
        [
            _raw_complete("ERROR", False),
            _raw_complete(),
        ]
    )

    class FallbackIngestion(_FakeIngestion):
        def sync_index_daily_range(self, start, end, job_id=None):
            self._record("index_daily_range")
            raise RuntimeError("range unavailable")

    monkeypatch.setattr(backfill_job_module, "upsert_rows", lambda *args, **kwargs: 1)
    monkeypatch.setattr(backfill_job_module, "IngestionService", FallbackIngestion)
    monkeypatch.setattr(backfill_job_module, "ensure_stock_basic_ready", lambda *args: None)
    monkeypatch.setattr(backfill_job_module, "_any_index_daily_incomplete", lambda *args: True)
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
    assert provider.calls == [
        "index_daily_range",
        "theme_daily",
        "theme_optional",
        "index_daily",
    ]
    assert job.job_metadata["index_daily_range_status"] == "WARNING"


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
