from datetime import date

import pandas as pd
from app.models.market_data import StockBasic, StockDaily, StockTradeStatusDaily, TradeCalendar
from app.services.realtime_kline import _range_cache, load_realtime_kline
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
    StockBasic.__table__.create(engine)
    StockDaily.__table__.create(engine)
    StockTradeStatusDaily.__table__.create(engine)
    _range_cache.clear()
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
    assert provider.calls == [("000001.SZ", dates[-1], dates[-1])]
    assert db.query(StockDaily).count() == 1


def test_realtime_kline_respects_listing_and_suspension_dates() -> None:
    db = _session()
    dates = [date(2026, 9, day) for day in range(14, 19)]
    db.add_all([TradeCalendar(cal_date=item, is_open=True, exchange="SSE") for item in dates])
    db.add(
        StockBasic(
            ts_code="000001.SZ",
            symbol="000001",
            name="test",
            exchange="SZSE",
            list_status="L",
            list_date=dates[2],
        )
    )
    db.add(
        StockTradeStatusDaily(
            trade_date=dates[3],
            ts_code="000001.SZ",
            is_active=True,
            is_suspended=True,
            is_st=False,
            tradable=False,
            strategy_eligible=False,
            calc_version="trade_status_v1",
            config_hash="hash",
            calculated_at=date(2026, 9, 18),
        )
    )
    db.add(_daily(dates[2], 10))
    db.commit()
    provider = _Provider([])

    result = load_realtime_kline(
        db,
        lambda: provider,
        ts_code="000001.SZ",
        start=dates[0],
        end=dates[-1],
    )

    assert provider.calls == [("000001.SZ", dates[4], dates[4])]
    assert result.rows[0]["trade_date"] == dates[2]


def test_realtime_kline_before_listing_never_initializes_provider() -> None:
    db = _session()
    days = [date(2026, 9, 14), date(2026, 9, 15)]
    db.add_all([TradeCalendar(cal_date=item, is_open=True, exchange="SSE") for item in days])
    db.add(
        StockBasic(
            ts_code="000001.SZ",
            symbol="000001",
            name="test",
            exchange="SZSE",
            list_status="L",
            list_date=date(2026, 9, 16),
        )
    )
    db.commit()

    result = load_realtime_kline(
        db,
        lambda: (_ for _ in ()).throw(AssertionError("provider initialized")),
        ts_code="000001.SZ",
        start=days[0],
        end=days[-1],
    )

    assert result.source == "local"
    assert result.rows == []


def test_realtime_kline_negative_cache_reuses_empty_response() -> None:
    db = _session()
    day = date(2026, 9, 14)
    db.add(TradeCalendar(cal_date=day, is_open=True, exchange="SSE"))
    db.commit()
    provider = _Provider([])
    for _ in range(2):
        result = load_realtime_kline(
            db,
            lambda: provider,
            ts_code="000001.SZ",
            start=day,
            end=day,
            cache_seconds=0,
            negative_cache_seconds=1800,
        )
        assert result.rows == []
    assert provider.calls == [("000001.SZ", day, day)]


def test_realtime_kline_merges_missing_ranges_and_caches_provider_rows() -> None:
    db = _session()
    dates = [date(2026, 9, day) for day in range(14, 20)]
    db.add_all([TradeCalendar(cal_date=item, is_open=True, exchange="SSE") for item in dates])
    db.add_all([_daily(dates[0], 10), _daily(dates[4], 10)])
    db.commit()
    provider = _Provider([])

    for _ in range(2):
        load_realtime_kline(
            db,
            lambda: provider,
            ts_code="000001.SZ",
            start=dates[0],
            end=dates[-1],
            cache_seconds=120,
        )

    assert provider.calls == [
        ("000001.SZ", dates[1], dates[3]),
        ("000001.SZ", dates[5], dates[5]),
    ]
