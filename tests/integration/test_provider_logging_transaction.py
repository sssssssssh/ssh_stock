from datetime import date

import app.providers.logging_provider as logging_provider_module
import app.services.ingestion.service as ingestion_module
import pandas as pd
import pytest
from app.providers.logging_provider import LoggingMarketDataProvider
from app.services.ingestion.service import IngestionService


class _BusinessDb:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _LogDb:
    def __init__(self, sink):
        self.sink = sink
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def commit(self):
        self.commits += 1


class _LogSessionFactory:
    def __init__(self):
        self.sessions = []
        self.records = []

    def __call__(self):
        session = _LogDb(self.records)
        self.sessions.append(session)
        return session


class _Provider:
    def get_daily(self, trade_date):
        return pd.DataFrame(
            [
                {
                    "trade_date": trade_date.strftime("%Y%m%d"),
                    "ts_code": "000001.SZ",
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "pre_close": 1,
                    "change": 0,
                    "pct_chg": 0,
                    "vol": 1,
                    "amount": 1,
                }
            ]
        )

    def get_adj_factor(self, trade_date):
        raise RuntimeError("adj failed")


def test_provider_logging_uses_independent_transaction(monkeypatch) -> None:
    def fake_log_provider_call(db, **kwargs):
        db.sink.append(kwargs)

    monkeypatch.setattr(logging_provider_module, "log_provider_call", fake_log_provider_call)
    monkeypatch.setattr(ingestion_module, "upsert_rows", lambda *args, **kwargs: 1)
    monkeypatch.setattr(ingestion_module, "changed_trade_dates", lambda *args, **kwargs: set())
    monkeypatch.setattr(ingestion_module, "record_dirty_range", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        ingestion_module,
        "expected_stock_daily_codes",
        lambda *args, **kwargs: {"000001.SZ"},
    )
    monkeypatch.setattr(
        ingestion_module,
        "persist_coverage_result",
        lambda *args, **kwargs: None,
    )

    log_factory = _LogSessionFactory()
    business_db = _BusinessDb()
    provider = LoggingMarketDataProvider(
        business_db,
        _Provider(),
        log_session_factory=log_factory,
    )
    service = IngestionService(business_db, provider)

    assert service.sync_daily(date(2026, 8, 31)) == 1
    with pytest.raises(RuntimeError, match="adj failed"):
        service.sync_adj_factor(date(2026, 8, 31))

    assert business_db.commits == 1
    assert business_db.rollbacks == 1
    assert [record["status"] for record in log_factory.records] == ["SUCCESS", "FAILED"]
    assert sum(session.commits for session in log_factory.sessions) == 2
