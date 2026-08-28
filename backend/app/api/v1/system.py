from datetime import date
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


def _count_by_date(db: Session, column: Any, trade_date: date) -> int:
    table = column.class_
    stmt = select(func.count()).select_from(table).where(column == trade_date)
    return int(db.execute(stmt).scalar_one())
