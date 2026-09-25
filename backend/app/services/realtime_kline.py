import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from time import monotonic
from typing import Protocol

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.market_data import (
    StockBasic,
    StockDaily,
    StockTradeStatusDaily,
    TradeCalendar,
)

_cache_lock = threading.Lock()
_range_cache: dict[tuple[str, date, date], tuple[float, list[dict[str, object]]]] = {}


class DailyRangeProvider(Protocol):
    def get_daily_range(self, ts_code: str, start: date, end: date) -> pd.DataFrame: ...


@dataclass(frozen=True)
class RealtimeKlineResult:
    source: str
    rows: list[dict[str, object]]


def load_realtime_kline(
    db: Session,
    provider_factory: Callable[[], DailyRangeProvider],
    *,
    ts_code: str,
    start: date,
    end: date,
    cache_seconds: int = 120,
) -> RealtimeKlineResult:
    local_models = (
        db.execute(
            select(StockDaily)
            .where(
                StockDaily.ts_code == ts_code,
                StockDaily.trade_date.between(start, end),
            )
            .order_by(StockDaily.trade_date)
        )
        .scalars()
        .all()
    )
    local_rows = [_stock_daily_row(row) for row in local_models]
    local_dates = {row["trade_date"] for row in local_rows}
    open_dates = set(
        db.execute(
            select(TradeCalendar.cal_date).where(
                TradeCalendar.cal_date.between(start, end),
                TradeCalendar.is_open.is_(True),
            )
        )
        .scalars()
        .all()
    )
    stock = db.get(StockBasic, ts_code)
    expected_dates = {
        item
        for item in open_dates
        if stock is None
        or (
            (stock.list_date is None or item >= stock.list_date)
            and (stock.delist_date is None or item <= stock.delist_date)
        )
    }
    if expected_dates:
        non_trading_dates = set(
            db.execute(
                select(StockTradeStatusDaily.trade_date).where(
                    StockTradeStatusDaily.ts_code == ts_code,
                    StockTradeStatusDaily.trade_date.in_(expected_dates),
                    (
                        StockTradeStatusDaily.is_suspended.is_(True)
                        | StockTradeStatusDaily.tradable.is_(False)
                    ),
                )
            )
            .scalars()
            .all()
        )
        expected_dates -= non_trading_dates
    if expected_dates and expected_dates <= local_dates:
        return RealtimeKlineResult(source="local", rows=local_rows)

    missing_dates = expected_dates - local_dates
    provider = provider_factory()
    provider_rows: list[dict[str, object]] = []
    for range_start, range_end in _merge_missing_ranges(missing_dates, sorted(open_dates)):
        provider_rows.extend(
            _cached_provider_rows(
                provider,
                ts_code,
                range_start,
                range_end,
                cache_seconds=cache_seconds,
            )
        )
    merged = {row["trade_date"]: row for row in local_rows}
    merged.update({row["trade_date"]: row for row in provider_rows})
    source = "mixed" if local_rows and provider_rows else "tushare" if provider_rows else "local"
    return RealtimeKlineResult(
        source=source,
        rows=[merged[key] for key in sorted(merged)],
    )


def _merge_missing_ranges(
    missing_dates: set[date], ordered_market_dates: list[date]
) -> list[tuple[date, date]]:
    missing = [item for item in ordered_market_dates if item in missing_dates]
    if not missing:
        return []
    positions = {item: index for index, item in enumerate(ordered_market_dates)}
    ranges: list[tuple[date, date]] = []
    range_start = previous = missing[0]
    for current in missing[1:]:
        if positions[current] == positions[previous] + 1:
            previous = current
            continue
        ranges.append((range_start, previous))
        range_start = previous = current
    ranges.append((range_start, previous))
    return ranges


def _cached_provider_rows(
    provider: DailyRangeProvider,
    ts_code: str,
    start: date,
    end: date,
    *,
    cache_seconds: int,
) -> list[dict[str, object]]:
    key = (ts_code, start, end)
    now = monotonic()
    if cache_seconds > 0:
        with _cache_lock:
            cached = _range_cache.get(key)
            if cached is not None and cached[0] > now:
                return [dict(row) for row in cached[1]]
    rows = _provider_rows(provider.get_daily_range(ts_code=ts_code, start=start, end=end), ts_code)
    if cache_seconds > 0:
        with _cache_lock:
            _range_cache[key] = (now + cache_seconds, [dict(row) for row in rows])
    return rows


def _stock_daily_row(row: StockDaily) -> dict[str, object]:
    return {
        "ts_code": row.ts_code,
        "trade_date": row.trade_date,
        "open": row.open,
        "high": row.high,
        "low": row.low,
        "close": row.close,
        "pre_close": row.pre_close,
        "change": row.change,
        "pct_chg": row.pct_chg,
        "vol": row.vol,
        "amount": row.amount,
    }


def _provider_rows(frame: pd.DataFrame | None, ts_code: str) -> list[dict[str, object]]:
    if frame is None or frame.empty:
        return []
    rows: list[dict[str, object]] = []
    for item in frame.to_dict("records"):
        trade_date = _parse_provider_date(item.get("trade_date"))
        if trade_date is None:
            continue
        rows.append(
            {
                "ts_code": item.get("ts_code") or ts_code,
                "trade_date": trade_date,
                **{
                    field: _float_or_none(item.get(field))
                    for field in [
                        "open",
                        "high",
                        "low",
                        "close",
                        "pre_close",
                        "change",
                        "pct_chg",
                        "vol",
                        "amount",
                    ]
                },
            }
        )
    return rows


def _parse_provider_date(value: object) -> date | None:
    text = str(value or "").replace("-", "")[:8]
    if len(text) != 8 or not text.isdigit():
        return None
    return date(int(text[:4]), int(text[4:6]), int(text[6:8]))


def _float_or_none(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number
