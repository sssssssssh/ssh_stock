from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.market_data import StockDaily, TradeCalendar


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
    expected_dates = set(
        db.execute(
            select(TradeCalendar.cal_date).where(
                TradeCalendar.cal_date.between(start, end),
                TradeCalendar.is_open.is_(True),
            )
        )
        .scalars()
        .all()
    )
    if expected_dates and expected_dates <= local_dates:
        return RealtimeKlineResult(source="local", rows=local_rows)

    provider_frame = provider_factory().get_daily_range(ts_code=ts_code, start=start, end=end)
    provider_rows = _provider_rows(provider_frame, ts_code)
    merged = {row["trade_date"]: row for row in local_rows}
    merged.update({row["trade_date"]: row for row in provider_rows})
    source = "mixed" if local_rows and provider_rows else "tushare" if provider_rows else "local"
    return RealtimeKlineResult(
        source=source,
        rows=[merged[key] for key in sorted(merged)],
    )


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
