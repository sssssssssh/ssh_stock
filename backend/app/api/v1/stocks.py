from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.v1.common import clamp_limit, clamp_offset, envelope, iso, latest_date, scalar_count
from app.core.clock import business_today
from app.core.config import get_settings
from app.core.db import get_db
from app.models.market_data import (
    Sector,
    StockBasic,
    StockDaily,
    StockFactorDaily,
    StockStateDaily,
    StrategySignal,
)
from app.providers.tushare_provider import TushareProvider
from app.services.realtime_kline import load_realtime_kline

router = APIRouter()


@router.get("/right-side")
def right_side(
    trade_date: date | None = None,
    new_only: bool = True,
    limit: int = 50,
    offset: int = 0,
    algo_version: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _state_pool(
        db=db,
        trade_date=trade_date,
        states=["S3"],
        new_only=new_only,
        limit=limit,
        offset=offset,
        algo_version=algo_version,
    )


@router.get("/trends")
def trends(
    trade_date: date | None = None,
    states: str = "S4,S5",
    limit: int = 50,
    offset: int = 0,
    algo_version: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    parsed_states = [state.strip() for state in states.split(",") if state.strip()]
    return _state_pool(
        db=db,
        trade_date=trade_date,
        states=parsed_states or ["S4", "S5"],
        new_only=False,
        limit=limit,
        offset=offset,
        algo_version=algo_version,
    )


@router.get("/decay")
def decay(
    trade_date: date | None = None,
    limit: int = 50,
    offset: int = 0,
    algo_version: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _state_pool(
        db=db,
        trade_date=trade_date,
        states=["S6"],
        new_only=False,
        limit=limit,
        offset=offset,
        algo_version=algo_version,
    )


@router.get("/{ts_code}/realtime-kline")
def realtime_kline(
    ts_code: str,
    days: int = 180,
    end: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    stock = db.get(StockBasic, ts_code)
    target_end = end or business_today()
    natural_days = max(30, min(days, 730))
    start = target_end - timedelta(days=natural_days)

    try:
        result = load_realtime_kline(
            db,
            TushareProvider,
            ts_code=ts_code,
            start=start,
            end=target_end,
        )
    except Exception as exc:
        detail = f"tushare realtime kline failed: {exc}"
        raise HTTPException(status_code=502, detail=detail) from exc

    rows = [{**row, "trade_date": row["trade_date"].isoformat()} for row in result.rows]

    return envelope(
        {
            "stock": _stock_payload(stock) if stock else {"ts_code": ts_code, "name": None},
            "source": result.source,
            "stored": False,
            "days": natural_days,
            "start": start.isoformat(),
            "end": target_end.isoformat(),
            "rows": rows,
        },
        {"source": result.source, "stored": False, "rows": len(rows)},
    )


@router.get("/{ts_code}/overview")
def overview(
    ts_code: str,
    trade_date: date | None = None,
    algo_version: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    settings = get_settings()
    version = algo_version or settings.algo_version
    target = trade_date or latest_date(
        db,
        StockStateDaily.trade_date,
        StockStateDaily.algo_version == version,
    )
    stock = db.get(StockBasic, ts_code)
    if not stock:
        raise HTTPException(status_code=404, detail="stock not found")

    state = None
    factor = None
    daily = None
    signals: list[StrategySignal] = []
    if target:
        state = db.get(
            StockStateDaily,
            {"trade_date": target, "ts_code": ts_code, "algo_version": version},
        )
        factor = db.get(StockFactorDaily, {"trade_date": target, "ts_code": ts_code})
        daily = db.get(StockDaily, {"trade_date": target, "ts_code": ts_code})
        signals = (
            db.execute(
                select(StrategySignal)
                .where(
                    StrategySignal.trade_date == target,
                    StrategySignal.ts_code == ts_code,
                    StrategySignal.algo_version == version,
                )
                .order_by(StrategySignal.signal_type)
            )
            .scalars()
            .all()
        )

    sector = db.get(Sector, state.primary_sector_id) if state and state.primary_sector_id else None
    return envelope(
        {
            "stock": _stock_payload(stock),
            "trade_date": target.isoformat() if target else None,
            "daily": _model_payload(daily) if daily else None,
            "factor": _model_payload(factor) if factor else None,
            "state": _model_payload(state) if state else None,
            "sector": _sector_payload(sector) if sector else None,
            "signals": [_model_payload(signal) for signal in signals],
        }
    )


@router.get("/{ts_code}/history")
def history(
    ts_code: str,
    start: date | None = None,
    end: date | None = None,
    algo_version: str | None = None,
    limit: int = 240,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    settings = get_settings()
    version = algo_version or settings.algo_version
    if not db.get(StockBasic, ts_code):
        raise HTTPException(status_code=404, detail="stock not found")

    row_limit = clamp_limit(limit, default=240, maximum=1000)
    stmt = (
        select(StockStateDaily)
        .where(
            StockStateDaily.ts_code == ts_code,
            StockStateDaily.algo_version == version,
        )
        .order_by(desc(StockStateDaily.trade_date))
        .limit(row_limit)
    )
    if start:
        stmt = stmt.where(StockStateDaily.trade_date >= start)
    if end:
        stmt = stmt.where(StockStateDaily.trade_date <= end)
    rows = db.execute(stmt).scalars().all()
    rows = sorted(rows, key=lambda row: row.trade_date)
    return envelope([_model_payload(row) for row in rows], {"limit": row_limit})


@router.get("/{ts_code}/factors")
def factors(
    ts_code: str,
    start: date | None = None,
    end: date | None = None,
    limit: int = 240,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not db.get(StockBasic, ts_code):
        raise HTTPException(status_code=404, detail="stock not found")

    row_limit = clamp_limit(limit, default=240, maximum=1000)
    stmt = (
        select(StockFactorDaily)
        .where(StockFactorDaily.ts_code == ts_code)
        .order_by(desc(StockFactorDaily.trade_date))
        .limit(row_limit)
    )
    if start:
        stmt = stmt.where(StockFactorDaily.trade_date >= start)
    if end:
        stmt = stmt.where(StockFactorDaily.trade_date <= end)
    rows = db.execute(stmt).scalars().all()
    rows = sorted(rows, key=lambda row: row.trade_date)
    return envelope([_model_payload(row) for row in rows], {"limit": row_limit})


def _state_pool(
    db: Session,
    trade_date: date | None,
    states: list[str],
    new_only: bool,
    limit: int,
    offset: int,
    algo_version: str | None,
) -> dict[str, Any]:
    settings = get_settings()
    version = algo_version or settings.algo_version
    target = trade_date or latest_date(
        db,
        StockStateDaily.trade_date,
        StockStateDaily.algo_version == version,
    )
    if not target:
        return envelope([], {"trade_date": None, "limit": limit, "offset": offset, "total": 0})

    row_limit = clamp_limit(limit)
    row_offset = clamp_offset(offset)
    filters = [
        StockStateDaily.trade_date == target,
        StockStateDaily.algo_version == version,
        StockStateDaily.state.in_(states),
    ]
    if new_only:
        filters.append(StockStateDaily.is_new_state.is_(True))

    stmt = (
        select(
            StockStateDaily.trade_date,
            StockStateDaily.ts_code,
            StockBasic.name,
            StockBasic.industry,
            StockStateDaily.state,
            StockStateDaily.previous_state,
            StockStateDaily.state_day_count,
            StockStateDaily.is_new_state,
            StockStateDaily.right_side_score,
            StockStateDaily.trend_score,
            StockStateDaily.opportunity_score,
            StockStateDaily.primary_sector_id,
            Sector.name.label("sector_name"),
            StockStateDaily.sector_heat,
            StockStateDaily.market_score,
            StockStateDaily.fast_transition,
            StockStateDaily.reason_codes,
        )
        .select_from(StockStateDaily)
        .outerjoin(StockBasic, StockStateDaily.ts_code == StockBasic.ts_code)
        .outerjoin(Sector, StockStateDaily.primary_sector_id == Sector.sector_id)
        .where(*filters)
        .order_by(desc(StockStateDaily.opportunity_score), desc(StockStateDaily.trend_score))
        .limit(row_limit)
        .offset(row_offset)
    )
    total_stmt = select(func.count()).select_from(StockStateDaily).where(*filters)
    return envelope(
        [_mapping_payload(row) for row in db.execute(stmt).mappings().all()],
        {
            "trade_date": target.isoformat(),
            "states": states,
            "new_only": new_only,
            "algo_version": version,
            "limit": row_limit,
            "offset": row_offset,
            "total": scalar_count(db, total_stmt),
        },
    )


def _mapping_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {key: iso(value) for key, value in dict(row).items()}


def _model_payload(row: Any) -> dict[str, Any]:
    return {column.name: iso(getattr(row, column.name)) for column in row.__table__.columns}


def _stock_payload(row: StockBasic) -> dict[str, Any]:
    return _model_payload(row)


def _sector_payload(row: Sector) -> dict[str, Any]:
    return _model_payload(row)
