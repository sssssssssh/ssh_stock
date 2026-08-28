from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.v1.common import clamp_limit, envelope, iso, latest_date
from app.core.config import get_settings
from app.core.db import get_db
from app.models.market_data import (
    MarketDaily,
    Sector,
    SectorFactorDaily,
    StockBasic,
    StockStateDaily,
    StrategySignal,
)

router = APIRouter()


@router.get("/summary")
def summary(
    trade_date: date | None = None,
    limit: int = 10,
    algo_version: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    settings = get_settings()
    version = algo_version or settings.algo_version
    target = trade_date or latest_date(db, StockStateDaily.trade_date)
    if not target:
        return envelope(
            {
                "trade_date": None,
                "market": None,
                "state_counts": [],
                "signal_counts": [],
                "sector_heat_top": [],
                "right_side_new": [],
                "trend_leaders": [],
            }
        )

    row_limit = clamp_limit(limit, default=10, maximum=50)
    market = db.get(MarketDaily, target)
    return envelope(
        {
            "trade_date": target.isoformat(),
            "market": _market_payload(market),
            "state_counts": _state_counts(db, target, version),
            "signal_counts": _signal_counts(db, target, version),
            "sector_heat_top": _sector_heat_top(db, target, row_limit),
            "right_side_new": _stock_pool(
                db,
                target,
                version,
                states=["S3"],
                row_limit=row_limit,
                new_only=True,
            ),
            "trend_leaders": _stock_pool(
                db,
                target,
                version,
                states=["S4", "S5"],
                row_limit=row_limit,
                new_only=False,
            ),
        }
    )


def _market_payload(row: MarketDaily | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "trade_date": row.trade_date.isoformat(),
        "market_score": row.market_score,
        "regime": row.regime,
        "breadth20": row.breadth20,
        "breadth60": row.breadth60,
        "up_count": row.up_count,
        "down_count": row.down_count,
        "flat_count": row.flat_count,
        "up_rate": row.up_rate,
        "new_high20_count": row.new_high20_count,
        "new_low20_count": row.new_low20_count,
        "total_amount": row.total_amount,
        "amount_ratio20": row.amount_ratio20,
    }


def _state_counts(db: Session, target: date, algo_version: str) -> list[dict[str, Any]]:
    stmt = (
        select(StockStateDaily.state, func.count().label("count"))
        .where(
            StockStateDaily.trade_date == target,
            StockStateDaily.algo_version == algo_version,
        )
        .group_by(StockStateDaily.state)
        .order_by(StockStateDaily.state)
    )
    return [{"state": row.state, "count": row.count} for row in db.execute(stmt).all()]


def _signal_counts(db: Session, target: date, algo_version: str) -> list[dict[str, Any]]:
    stmt = (
        select(StrategySignal.signal_type, func.count().label("count"))
        .where(
            StrategySignal.trade_date == target,
            StrategySignal.algo_version == algo_version,
        )
        .group_by(StrategySignal.signal_type)
        .order_by(StrategySignal.signal_type)
    )
    return [{"signal_type": row.signal_type, "count": row.count} for row in db.execute(stmt).all()]


def _sector_heat_top(db: Session, target: date, row_limit: int) -> list[dict[str, Any]]:
    stmt = (
        select(
            SectorFactorDaily.trade_date,
            SectorFactorDaily.sector_id,
            Sector.name.label("sector_name"),
            Sector.level,
            SectorFactorDaily.heat_score,
            SectorFactorDaily.heat_rank,
            SectorFactorDaily.rank_change,
            SectorFactorDaily.lifecycle,
            SectorFactorDaily.member_count,
            SectorFactorDaily.eligible_member_count,
        )
        .join(Sector, SectorFactorDaily.sector_id == Sector.sector_id)
        .where(SectorFactorDaily.trade_date == target)
        .order_by(SectorFactorDaily.heat_rank, desc(SectorFactorDaily.heat_score))
        .limit(row_limit)
    )
    return [_mapping_payload(row) for row in db.execute(stmt).mappings().all()]


def _stock_pool(
    db: Session,
    target: date,
    algo_version: str,
    states: list[str],
    row_limit: int,
    new_only: bool,
) -> list[dict[str, Any]]:
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
        .where(
            StockStateDaily.trade_date == target,
            StockStateDaily.algo_version == algo_version,
            StockStateDaily.state.in_(states),
        )
        .order_by(desc(StockStateDaily.opportunity_score), desc(StockStateDaily.trend_score))
        .limit(row_limit)
    )
    if new_only:
        stmt = stmt.where(StockStateDaily.is_new_state.is_(True))
    return [_mapping_payload(row) for row in db.execute(stmt).mappings().all()]


def _mapping_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {key: iso(value) for key, value in dict(row).items()}
