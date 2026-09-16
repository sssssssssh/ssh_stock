from datetime import date

import app.services.ingestion.service as ingestion_module
import pandas as pd
import pytest
from app.services.ingestion.service import IngestionService
from app.services.quality.raw_checks import QualityIssue


class _FakeDb:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _FakeProvider:
    def get_daily(self, trade_date: date) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "trade_date": "20260831",
                    "ts_code": "000001.SZ",
                    "open": 1,
                    "high": 2,
                    "low": 1,
                    "close": 2,
                    "pre_close": 1,
                    "change": 1,
                    "pct_chg": None,
                    "vol": 100,
                    "amount": 1000,
                },
                {
                    "trade_date": "20260831",
                    "ts_code": "000001.SZ",
                    "open": 1,
                    "high": 2,
                    "low": 1,
                    "close": 2,
                    "pre_close": 1,
                    "change": 1,
                    "pct_chg": None,
                    "vol": 100,
                    "amount": 1000,
                },
            ]
        )


def test_sync_daily_initial_quality_write_records_detail_counts(monkeypatch) -> None:
    persisted = []
    monkeypatch.setattr(ingestion_module, "check_raw_daily", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        ingestion_module,
        "expected_stock_daily_codes",
        lambda *args, **kwargs: {"000001.SZ"},
    )
    monkeypatch.setattr(
        ingestion_module,
        "persist_coverage_result",
        lambda db, result, **kwargs: persisted.append(kwargs),
    )
    monkeypatch.setattr(ingestion_module, "changed_trade_dates", lambda *args, **kwargs: set())
    monkeypatch.setattr(ingestion_module, "record_dirty_range", lambda *args, **kwargs: None)
    monkeypatch.setattr(ingestion_module, "upsert_rows", lambda *args, **kwargs: 2)
    db = _FakeDb()

    rows = IngestionService(db, _FakeProvider()).sync_daily(date(2026, 8, 31))

    assert rows == 2
    assert db.commits == 1
    assert persisted[0]["duplicate_count"] == 1
    assert persisted[0]["null_count"] == 2
    assert "preserve_existing_detail_counts" not in persisted[0]


def test_sync_daily_persists_duplicate_evidence_before_failing(monkeypatch) -> None:
    persisted = []
    monkeypatch.setattr(
        ingestion_module,
        "check_raw_daily",
        lambda *args, **kwargs: [QualityIssue("DAILY_DUPLICATED_PK", "duplicated=1")],
    )
    monkeypatch.setattr(
        ingestion_module,
        "expected_stock_daily_codes",
        lambda *args, **kwargs: {"000001.SZ"},
    )
    monkeypatch.setattr(
        ingestion_module,
        "persist_coverage_result",
        lambda db, result, **kwargs: persisted.append((result, kwargs)),
    )
    db = _FakeDb()

    with pytest.raises(ValueError, match="DAILY_DUPLICATED_PK"):
        IngestionService(db, _FakeProvider()).sync_daily(date(2026, 8, 31))

    assert db.commits == 1
    assert persisted[0][0].status == "ERROR"
    assert persisted[0][1]["duplicate_count"] == 1
    assert persisted[0][1]["extra_issue_codes"] == {
        "raw_issues": ["DAILY_DUPLICATED_PK"]
    }
