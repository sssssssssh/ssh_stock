from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import desc, false, func, select
from sqlalchemy.orm import Session

from app.api.v1.common import clamp_limit, clamp_offset, envelope, iso, latest_date
from app.core.config import get_settings
from app.core.db import get_db
from app.models.market_data import (
    Sector,
    StockBasic,
    StockFactorDaily,
    StockOpportunityDaily,
)
from app.services.analysis_filters import opportunity_identity_filters
from app.services.theme.membership import resolve_theme_memberships

router = APIRouter()


@router.get("/left-reversal")
def left_reversal(
    trade_date: date | None = None,
    min_score: float = 60,
    new_only: bool = False,
    theme_code: str | None = None,
    sector_id: int | None = None,
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    filters = [
        StockOpportunityDaily.opportunity_stage.in_(["LEFT_WATCH", "LEFT_REVERSAL"]),
        StockOpportunityDaily.left_reversal_score >= min_score,
    ]
    if new_only:
        filters.append(StockOpportunityDaily.left_reversal_new.is_(True))
    return _pool(
        db,
        trade_date,
        filters,
        theme_code,
        sector_id,
        limit,
        offset,
        desc(StockOpportunityDaily.left_reversal_score),
    )


@router.get("/right-side")
def right_side(
    trade_date: date | None = None,
    new_only: bool = True,
    theme_code: str | None = None,
    sector_id: int | None = None,
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    stages = ["RIGHT_SIDE_NEW"] if new_only else ["RIGHT_SIDE_NEW", "RIGHT_SIDE"]
    return _pool(
        db,
        trade_date,
        [StockOpportunityDaily.opportunity_stage.in_(stages)],
        theme_code,
        sector_id,
        limit,
        offset,
        desc(StockOpportunityDaily.right_side_score),
    )


@router.get("/trends")
def trends(
    trade_date: date | None = None,
    state: str = "S4,S5",
    extension_risk: str | None = None,
    theme_code: str | None = None,
    sector_id: int | None = None,
    min_trend_rank: float | None = None,
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    states = [value.strip() for value in state.split(",") if value.strip() in {"S4", "S5"}]
    filters = [StockOpportunityDaily.state.in_(states or ["S4", "S5"])]
    if extension_risk:
        filters.append(StockOpportunityDaily.extension_risk == extension_risk)
    if min_trend_rank is not None:
        filters.append(StockOpportunityDaily.trend_rank_score >= min_trend_rank)
    return _pool(
        db,
        trade_date,
        filters,
        theme_code,
        sector_id,
        limit,
        offset,
        desc(StockOpportunityDaily.trend_rank_score),
    )


def _pool(
    db: Session,
    target_date: date | None,
    extra_filters: list[Any],
    theme_code: str | None,
    sector_id: int | None,
    limit: int,
    offset: int,
    order_by: Any,
) -> dict[str, Any]:
    settings = get_settings()
    identity = opportunity_identity_filters(settings)
    target = target_date or latest_date(
        db,
        StockOpportunityDaily.trade_date,
        *identity,
    )
    row_limit, row_offset = clamp_limit(limit, default=30), clamp_offset(offset)
    if not target:
        return envelope(
            [], {"trade_date": None, "limit": row_limit, "offset": row_offset, "total": 0}
        )
    filters = [
        StockOpportunityDaily.trade_date == target,
        *identity,
        *extra_filters,
    ]
    membership_context: dict[str, object] | None = None
    if theme_code:
        resolution = resolve_theme_memberships(db, [target])
        membership_context = resolution.context_by_date.get(target)
        members = resolution.members
        codes = (
            set(
                members.loc[
                    (members["trade_date"] == target)
                    & (members["theme_code"] == theme_code),
                    "ts_code",
                ].astype(str)
            )
            if not members.empty
            else set()
        )
        if not codes:
            filters.append(false())
        else:
            filters.append(StockOpportunityDaily.ts_code.in_(codes))
    if sector_id is not None:
        filters.append(StockOpportunityDaily.industry_sector_id == sector_id)
    query = (
        select(
            StockOpportunityDaily,
            StockBasic.name,
            StockBasic.industry,
            Sector.name.label("industry_name"),
            StockFactorDaily.rps20,
            StockFactorDaily.rps60,
            StockFactorDaily.rps120,
            StockFactorDaily.rps20_delta5,
            StockFactorDaily.ma20_slope5,
            StockFactorDaily.higher_low,
        )
        .outerjoin(StockBasic, StockOpportunityDaily.ts_code == StockBasic.ts_code)
        .outerjoin(Sector, StockOpportunityDaily.industry_sector_id == Sector.sector_id)
        .outerjoin(
            StockFactorDaily,
            (StockOpportunityDaily.trade_date == StockFactorDaily.trade_date)
            & (StockOpportunityDaily.ts_code == StockFactorDaily.ts_code),
        )
        .where(*filters)
        .order_by(order_by, StockOpportunityDaily.ts_code)
        .limit(row_limit)
        .offset(row_offset)
    )
    rows = [_row_payload(row) for row in db.execute(query).all()]
    total = int(
        db.execute(
            select(func.count()).select_from(StockOpportunityDaily).where(*filters)
        ).scalar_one()
    )
    return envelope(
        rows,
        {
            "trade_date": target.isoformat(),
            "limit": row_limit,
            "offset": row_offset,
            "total": total,
            "member_context_available": (
                bool(membership_context.get("available", False))
                if membership_context is not None
                else None
            ),
            "member_context_mode": (
                membership_context.get("mode") if membership_context is not None else None
            ),
        },
    )


def _row_payload(row: Any) -> dict[str, Any]:
    opportunity = row[0]
    payload = {
        column.name: iso(getattr(opportunity, column.name))
        for column in opportunity.__table__.columns
    }
    payload.update(
        {
            "name": row.name,
            "industry": row.industry,
            "industry_name": row.industry_name,
            "rps20": row.rps20,
            "rps60": row.rps60,
            "rps120": row.rps120,
            "rps20_delta5": row.rps20_delta5,
            "ma20_slope5": row.ma20_slope5,
            "higher_low": row.higher_low,
        }
    )
    return payload
