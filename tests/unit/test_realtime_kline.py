from datetime import date

import pandas as pd
from app.models.market_data import StockDaily, TradeCalendar
from app.services.realtime_kline import load_realtime_kline
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class _Provider:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, date, date]] = []

    def get_daily_range(self, ts_code: str, start: date, end: date) -> pd.DataFrame:
        self.calls.append((ts_code, start, end))
        return pd.DataFrame(self.rows)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    TradeCalendar.__table__.create(engine)
    StockDaily.__table__.create(engine)
    return Session(engine)


def _daily(trade_date: date, close: float) -> StockDaily:
    return StockDaily(
        trade_date=trade_date,
        ts_code="000001.SZ",
        open=close,
        high=close,
        low=close,
        close=close,
        pre_close=close,
        change=0,
        pct_chg=0,
        vol=1,
        amount=1,
    )


def test_realtime_kline_uses_complete_local_data_without_provider() -> None:
    db = _session()
    dates = [date(2026, 9, 14), date(2026, 9, 15)]
    db.add_all([TradeCalendar(cal_date=item, is_open=True, exchange="SSE") for item in dates])
    db.add_all([_daily(item, float(index)) for index, item in enumerate(dates, 1)])
    db.commit()
    provider = _Provider([])

    result = load_realtime_kline(
        db,
        lambda: provider,
        ts_code="000001.SZ",
        start=dates[0],
        end=dates[-1],
    )

    assert result.source == "local"
    assert [row["trade_date"] for row in result.rows] == dates
    assert provider.calls == []


def test_realtime_kline_fills_local_gap_from_provider_without_writing() -> None:
    db = _session()
    dates = [date(2026, 9, 14), date(2026, 9, 15)]
    db.add_all([TradeCalendar(cal_date=item, is_open=True, exchange="SSE") for item in dates])
    db.add(_daily(dates[0], 10))
    db.commit()
    provider = _Provider(
        [
            {
                "trade_date": "20260915",
                "ts_code": "000001.SZ",
                "open": 11,
                "high": 12,
                "low": 10,
                "close": 12,
            }
        ]
    )

    result = load_realtime_kline(
        db,
        lambda: provider,
        ts_code="000001.SZ",
        start=dates[0],
        end=dates[-1],
    )

    assert result.source == "mixed"
    assert [row["trade_date"] for row in result.rows] == dates
    assert provider.calls == [("000001.SZ", dates[0], dates[-1])]
    assert db.query(StockDaily).count() == 1
