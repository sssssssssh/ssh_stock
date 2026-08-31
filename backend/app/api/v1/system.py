from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import Select, desc, func, select
from sqlalchemy.orm import Session

from app.api.v1.common import clamp_limit, envelope
from app.core.db import get_db
from app.models.market_data import (
    IndexDaily,
    MarketDaily,
    SectorFactorDaily,
    SignalForwardEval,
    StockAdjFactor,
    StockDaily,
    StockDailyBasic,
    StockFactorDaily,
    StockStateDaily,
    StrategySignal,
    TradeCalendar,
)

router = APIRouter()


def _latest_date(db: Session, stmt: Select[tuple[Any]]) -> str | None:
    value = db.execute(stmt).scalar_one_or_none()
    return value.isoformat() if value else None


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "latest_trade_date": _latest_date(
                db, select(func.max(TradeCalendar.cal_date)).where(TradeCalendar.is_open.is_(True))
            ),
            "latest_raw_date": _latest_date(db, select(func.max(StockDaily.trade_date))),
            "latest_adj_factor_date": _latest_date(db, select(func.max(StockAdjFactor.trade_date))),
            "latest_daily_basic_date": _latest_date(
                db, select(func.max(StockDailyBasic.trade_date))
            ),
            "latest_index_date": _latest_date(db, select(func.max(IndexDaily.trade_date))),
            "latest_factor_date": _latest_date(db, select(func.max(StockFactorDaily.trade_date))),
            "latest_market_date": _latest_date(db, select(func.max(MarketDaily.trade_date))),
            "latest_sector_factor_date": _latest_date(
                db, select(func.max(SectorFactorDaily.trade_date))
            ),
            "latest_state_date": _latest_date(db, select(func.max(StockStateDaily.trade_date))),
            "latest_signal_date": _latest_date(db, select(func.max(StrategySignal.trade_date))),
            "latest_signal_eval_date": _latest_date(
                db, select(func.max(SignalForwardEval.trade_date))
            ),
        },
        "meta": {},
    }


@router.get("/data-coverage")
def data_coverage(
    start: date | None = None,
    end: date | None = None,
    limit: int = 90,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row_limit = clamp_limit(limit, default=90, maximum=1000)
    date_stmt = select(StockDaily.trade_date).distinct().order_by(desc(StockDaily.trade_date))
    if start:
        date_stmt = date_stmt.where(StockDaily.trade_date >= start)
    if end:
        date_stmt = date_stmt.where(StockDaily.trade_date <= end)
    trade_dates = db.execute(date_stmt.limit(row_limit)).scalars().all()

    rows = []
    for trade_date in trade_dates:
        rows.append(
            {
                "trade_date": trade_date.isoformat(),
                "stock_daily_rows": _count_by_date(db, StockDaily.trade_date, trade_date),
                "daily_basic_rows": _count_by_date(db, StockDailyBasic.trade_date, trade_date),
                "adj_factor_rows": _count_by_date(db, StockAdjFactor.trade_date, trade_date),
                "index_daily_rows": _count_by_date(db, IndexDaily.trade_date, trade_date),
                "factor_rows": _count_by_date(db, StockFactorDaily.trade_date, trade_date),
                "market_rows": _count_by_date(db, MarketDaily.trade_date, trade_date),
                "sector_factor_rows": _count_by_date(db, SectorFactorDaily.trade_date, trade_date),
                "state_rows": _count_by_date(db, StockStateDaily.trade_date, trade_date),
                "signal_rows": _count_by_date(db, StrategySignal.trade_date, trade_date),
                "signal_eval_rows": _count_by_date(db, SignalForwardEval.trade_date, trade_date),
            }
        )

    return envelope(
        rows,
        {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "limit": row_limit,
        },
    )


@router.get("/data-calendar")
def data_calendar(
    start: date,
    end: date,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if end < start:
        return envelope([], {"start": start.isoformat(), "end": end.isoformat()})

    calendar_rows = (
        db.execute(
            select(TradeCalendar.cal_date, TradeCalendar.is_open)
            .where(TradeCalendar.cal_date >= start, TradeCalendar.cal_date <= end)
            .order_by(TradeCalendar.cal_date)
        )
        .mappings()
        .all()
    )
    calendar_map = {row.cal_date: bool(row.is_open) for row in calendar_rows}
    stock_daily_counts = _counts_by_date(db, StockDaily.trade_date, start, end)
    daily_basic_counts = _counts_by_date(db, StockDailyBasic.trade_date, start, end)
    adj_factor_counts = _counts_by_date(db, StockAdjFactor.trade_date, start, end)
    index_daily_counts = _counts_by_date(db, IndexDaily.trade_date, start, end)
    factor_counts = _counts_by_date(db, StockFactorDaily.trade_date, start, end)
    market_counts = _counts_by_date(db, MarketDaily.trade_date, start, end)
    sector_counts = _counts_by_date(db, SectorFactorDaily.trade_date, start, end)
    state_counts = _counts_by_date(db, StockStateDaily.trade_date, start, end)
    signal_counts = _counts_by_date(db, StrategySignal.trade_date, start, end)
    signal_eval_counts = _counts_by_date(db, SignalForwardEval.trade_date, start, end)

    rows = []
    current = start
    while current <= end:
        is_open = calendar_map.get(current)
        if is_open is None and current.weekday() >= 5:
            is_open = False
        stock_rows = stock_daily_counts.get(current, 0)
        factor_rows = factor_counts.get(current, 0)
        market_rows = market_counts.get(current, 0)
        state_rows = state_counts.get(current, 0)
        sector_rows = sector_counts.get(current, 0)
        if is_open is False:
            coverage_status = "CLOSED"
        elif stock_rows <= 0:
            coverage_status = "MISSING"
        elif factor_rows > 0 and market_rows > 0 and state_rows > 0 and sector_rows > 0:
            coverage_status = "COMPLETE"
        elif factor_rows > 0 and market_rows > 0 and state_rows > 0:
            coverage_status = "ANALYZED"
        else:
            coverage_status = "RAW_ONLY"

        rows.append(
            {
                "date": current.isoformat(),
                "is_open": is_open,
                "coverage_status": coverage_status,
                "stock_daily_rows": stock_rows,
                "daily_basic_rows": daily_basic_counts.get(current, 0),
                "adj_factor_rows": adj_factor_counts.get(current, 0),
                "index_daily_rows": index_daily_counts.get(current, 0),
                "factor_rows": factor_rows,
                "market_rows": market_rows,
                "sector_factor_rows": sector_rows,
                "state_rows": state_rows,
                "signal_rows": signal_counts.get(current, 0),
                "signal_eval_rows": signal_eval_counts.get(current, 0),
            }
        )
        current += timedelta(days=1)

    return envelope(rows, {"start": start.isoformat(), "end": end.isoformat()})


def _count_by_date(db: Session, column: Any, trade_date: date) -> int:
    table = column.class_
    stmt = select(func.count()).select_from(table).where(column == trade_date)
    return int(db.execute(stmt).scalar_one())


def _counts_by_date(db: Session, column: Any, start: date, end: date) -> dict[date, int]:
    table = column.class_
    rows = (
        db.execute(
            select(column.label("trade_date"), func.count().label("rows"))
            .select_from(table)
            .where(column >= start, column <= end)
            .group_by(column)
        )
        .mappings()
        .all()
    )
    return {row.trade_date: int(row.rows) for row in rows}
