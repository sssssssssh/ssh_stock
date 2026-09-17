from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from app.api.v1.common import clamp_limit, clamp_offset, envelope, iso, latest_date, scalar_count
from app.core.config import get_settings
from app.core.db import get_db
from app.models.market_data import Sector, SectorFactorDaily
from app.services.analysis_identity import SECTOR_CALC_VERSION
from app.services.calc_metadata import config_hash

router = APIRouter()


@router.get("/heat")
def heat(
    trade_date: date | None = None,
    level: str | None = "L1",
    sort: str = "heat_score",
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    hash_value = config_hash(get_settings().strategy)
    target = trade_date or latest_date(
        db,
        SectorFactorDaily.trade_date,
        SectorFactorDaily.calc_version == SECTOR_CALC_VERSION,
        SectorFactorDaily.config_hash == hash_value,
    )
    if not target:
        return envelope([], {"trade_date": None, "limit": limit, "offset": offset, "total": 0})

    row_limit = clamp_limit(limit, default=30)
    row_offset = clamp_offset(offset)
    filters = [
        SectorFactorDaily.trade_date == target,
        SectorFactorDaily.calc_version == SECTOR_CALC_VERSION,
        SectorFactorDaily.config_hash == hash_value,
    ]
    if level:
        filters.append(Sector.level == level)

    stmt = (
        select(
            SectorFactorDaily.trade_date,
            SectorFactorDaily.sector_id,
            Sector.source,
            Sector.source_code,
            Sector.name,
            Sector.level,
            SectorFactorDaily.member_count,
            SectorFactorDaily.eligible_member_count,
            SectorFactorDaily.return1,
            SectorFactorDaily.return3,
            SectorFactorDaily.return5,
            SectorFactorDaily.return20,
            SectorFactorDaily.breadth20,
            SectorFactorDaily.breadth60,
            SectorFactorDaily.up_rate,
            SectorFactorDaily.new_high20_rate,
            SectorFactorDaily.rps60_median,
            SectorFactorDaily.rps60_top20_rate,
            SectorFactorDaily.amount,
            SectorFactorDaily.amount_ratio20,
            SectorFactorDaily.heat_score,
            SectorFactorDaily.heat_momentum1,
            SectorFactorDaily.heat_momentum3,
            SectorFactorDaily.heat_rank,
            SectorFactorDaily.rank_change,
            SectorFactorDaily.lifecycle,
        )
        .join(Sector, SectorFactorDaily.sector_id == Sector.sector_id)
        .where(*filters)
        .limit(row_limit)
        .offset(row_offset)
    )
    if sort == "heat_rank":
        stmt = stmt.order_by(asc(SectorFactorDaily.heat_rank), desc(SectorFactorDaily.heat_score))
    else:
        stmt = stmt.order_by(desc(SectorFactorDaily.heat_score), asc(SectorFactorDaily.heat_rank))

    total_stmt = (
        select(func.count())
        .select_from(SectorFactorDaily)
        .join(Sector, SectorFactorDaily.sector_id == Sector.sector_id)
        .where(*filters)
    )
    return envelope(
        [_payload(row) for row in db.execute(stmt).mappings().all()],
        {
            "trade_date": target.isoformat(),
            "limit": row_limit,
            "offset": row_offset,
            "total": scalar_count(db, total_stmt),
        },
    )


@router.get("/{sector_id}")
def overview(
    sector_id: int,
    trade_date: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    hash_value = config_hash(get_settings().strategy)
    target = trade_date or latest_date(
        db,
        SectorFactorDaily.trade_date,
        SectorFactorDaily.calc_version == SECTOR_CALC_VERSION,
        SectorFactorDaily.config_hash == hash_value,
    )
    sector = db.get(Sector, sector_id)
    if not sector:
        raise HTTPException(status_code=404, detail="sector not found")
    factor = None
    if target:
        factor = db.execute(
            select(SectorFactorDaily).where(
                SectorFactorDaily.trade_date == target,
                SectorFactorDaily.sector_id == sector_id,
                SectorFactorDaily.calc_version == SECTOR_CALC_VERSION,
                SectorFactorDaily.config_hash == hash_value,
            )
        ).scalar_one_or_none()
    return envelope(
        {
            "sector": {
                "sector_id": sector.sector_id,
                "source": sector.source,
                "source_code": sector.source_code,
                "name": sector.name,
                "level": sector.level,
                "parent_code": sector.parent_code,
                "is_active": sector.is_active,
            },
            "factor": _model_payload(factor) if factor else None,
        },
        {"trade_date": target.isoformat() if target else None},
    )


@router.get("/{sector_id}/history")
def history(
    sector_id: int,
    start: date | None = None,
    end: date | None = None,
    limit: int = 240,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not db.get(Sector, sector_id):
        raise HTTPException(status_code=404, detail="sector not found")

    hash_value = config_hash(get_settings().strategy)
    row_limit = clamp_limit(limit, default=240, maximum=1000)
    stmt = (
        select(SectorFactorDaily)
        .where(
            SectorFactorDaily.sector_id == sector_id,
            SectorFactorDaily.calc_version == SECTOR_CALC_VERSION,
            SectorFactorDaily.config_hash == hash_value,
        )
        .order_by(desc(SectorFactorDaily.trade_date))
        .limit(row_limit)
    )
    if start:
        stmt = stmt.where(SectorFactorDaily.trade_date >= start)
    if end:
        stmt = stmt.where(SectorFactorDaily.trade_date <= end)
    rows = db.execute(stmt).scalars().all()
    rows = sorted(rows, key=lambda row: row.trade_date)
    return envelope([_model_payload(row) for row in rows], {"limit": row_limit})


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    return {key: iso(value) for key, value in dict(row).items()}


def _model_payload(row: SectorFactorDaily) -> dict[str, Any]:
    return {column.name: iso(getattr(row, column.name)) for column in row.__table__.columns}
