from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from app.api.v1.common import clamp_limit, clamp_offset, envelope, iso, latest_date
from app.core.config import get_settings
from app.core.db import get_db
from app.models.market_data import (
    StockBasic,
    StockOpportunityDaily,
    Theme,
    ThemeFactorDaily,
)
from app.services.analysis_filters import (
    opportunity_identity_filters,
    theme_factor_identity_filters,
)
from app.services.theme.membership import resolve_theme_memberships

router = APIRouter()


@router.get("")
def theme_list(
    trade_date: date | None = None,
    lifecycle: str | None = None,
    min_heat: float | None = None,
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    settings = get_settings()
    identity = theme_factor_identity_filters(settings)
    target = trade_date or latest_date(
        db,
        ThemeFactorDaily.trade_date,
        *identity,
    )
    row_limit, row_offset = clamp_limit(limit, default=30), clamp_offset(offset)
    if not target:
        return envelope([], _meta(None, row_limit, row_offset, 0))
    filters = [
        ThemeFactorDaily.trade_date == target,
        *identity,
    ]
    if lifecycle:
        filters.append(ThemeFactorDaily.lifecycle == lifecycle)
    if min_heat is not None:
        filters.append(ThemeFactorDaily.heat_score >= min_heat)
    stmt = (
        select(
            ThemeFactorDaily,
            Theme.name,
            Theme.source,
            Theme.theme_type,
        )
        .join(Theme, ThemeFactorDaily.theme_code == Theme.theme_code)
        .where(*filters)
        .order_by(asc(ThemeFactorDaily.heat_rank), desc(ThemeFactorDaily.heat_score))
        .limit(row_limit)
        .offset(row_offset)
    )
    total = int(
        db.execute(
            select(func.count())
            .select_from(ThemeFactorDaily)
            .join(Theme, ThemeFactorDaily.theme_code == Theme.theme_code)
            .where(*filters)
        ).scalar_one()
    )
    rows = []
    for factor, name, source, theme_type in db.execute(stmt).all():
        payload = _model_payload(factor)
        payload.update({"name": name, "source": source, "theme_type": theme_type})
        rows.append(payload)
    return envelope(rows, _meta(target, row_limit, row_offset, total))


@router.get("/{theme_code}/overview")
def overview(
    theme_code: str,
    trade_date: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    theme = db.get(Theme, theme_code)
    if not theme:
        raise HTTPException(status_code=404, detail="theme not found")
    settings = get_settings()
    theme_identity = theme_factor_identity_filters(settings)
    target = trade_date or latest_date(
        db,
        ThemeFactorDaily.trade_date,
        ThemeFactorDaily.theme_code == theme_code,
        *theme_identity,
    )
    history = []
    factor = None
    if target:
        factors = list(
            db.execute(
                select(ThemeFactorDaily)
                .where(
                    ThemeFactorDaily.theme_code == theme_code,
                    ThemeFactorDaily.trade_date <= target,
                    *theme_identity,
                )
                .order_by(desc(ThemeFactorDaily.trade_date))
                .limit(60)
            )
            .scalars()
            .all()
        )
        factor = factors[0] if factors and factors[0].trade_date == target else None
        history = [_model_payload(item) for item in reversed(factors)]
    member_distribution: list[dict[str, Any]] = []
    top_members: dict[str, list[dict[str, Any]]] = {"trend": [], "right": [], "left": []}
    context_meta = _member_context_meta(None)
    if target:
        resolution = resolve_theme_memberships(db, [target])
        member_codes = _theme_member_codes(resolution.members, theme_code, target)
        context_meta = _member_context_meta(resolution.context_by_date.get(target))
        member_rows = _member_opportunities(db, member_codes, target, None, 200, 0)
        counts: dict[str, int] = {}
        for row in member_rows:
            stage = str(row["opportunity_stage"])
            counts[stage] = counts.get(stage, 0) + 1
        member_distribution = [
            {"stage": stage, "count": count} for stage, count in sorted(counts.items())
        ]
        top_members["trend"] = _member_opportunities(
            db, member_codes, target, None, 10, 0, pool="trend"
        )
        top_members["right"] = _member_opportunities(
            db, member_codes, target, None, 10, 0, pool="right"
        )
        top_members["left"] = _member_opportunities(
            db, member_codes, target, None, 10, 0, pool="left"
        )
    return envelope(
        {
            "theme": _model_payload(theme),
            "factor": _model_payload(factor) if factor else None,
            "history": history,
            "member_distribution": member_distribution,
            "top_members": top_members,
            "member_context": context_meta,
            "member_snapshot": _legacy_snapshot_meta(context_meta),
        },
        {
            "trade_date": target.isoformat() if target else None,
            **context_meta,
        },
    )


@router.get("/{theme_code}/members")
def members(
    theme_code: str,
    trade_date: date | None = None,
    stage: str | None = None,
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not db.get(Theme, theme_code):
        raise HTTPException(status_code=404, detail="theme not found")
    settings = get_settings()
    opportunity_identity = opportunity_identity_filters(settings)
    target = trade_date or latest_date(
        db,
        StockOpportunityDaily.trade_date,
        *opportunity_identity,
    )
    row_limit, row_offset = clamp_limit(limit, default=30), clamp_offset(offset)
    if not target:
        return envelope([], _meta(None, row_limit, row_offset, 0))
    resolution = resolve_theme_memberships(db, [target])
    member_codes = _theme_member_codes(resolution.members, theme_code, target)
    rows = _member_opportunities(
        db, member_codes, target, stage, row_limit, row_offset
    )
    total = _member_count(db, member_codes, target, stage)
    return envelope(
        rows,
        {
            **_meta(target, row_limit, row_offset, total),
            **_member_context_meta(resolution.context_by_date.get(target)),
        },
    )


def _member_opportunities(
    db: Session,
    member_codes: set[str],
    target: date,
    stage: str | None,
    limit: int,
    offset: int,
    *,
    pool: str | None = None,
) -> list[dict[str, Any]]:
    settings = get_settings()
    if not member_codes:
        return []
    filters = [
        StockOpportunityDaily.ts_code.in_(member_codes),
        StockOpportunityDaily.trade_date == target,
        *opportunity_identity_filters(settings),
    ]
    if stage:
        filters.append(StockOpportunityDaily.opportunity_stage == stage)
    order = desc(StockOpportunityDaily.opportunity_score)
    if pool == "trend":
        filters.append(StockOpportunityDaily.state.in_(("S4", "S5")))
        order = desc(StockOpportunityDaily.trend_rank_score)
    elif pool == "right":
        filters.append(StockOpportunityDaily.state == "S3")
        order = desc(StockOpportunityDaily.right_side_score)
    elif pool == "left":
        filters.append(StockOpportunityDaily.opportunity_stage.like("LEFT%"))
        order = desc(StockOpportunityDaily.left_reversal_score)
    stmt = (
        select(StockOpportunityDaily, StockBasic.name)
        .outerjoin(StockBasic, StockOpportunityDaily.ts_code == StockBasic.ts_code)
        .where(*filters)
        .order_by(order)
        .limit(limit)
        .offset(offset)
    )
    rows = []
    for opportunity, name in db.execute(stmt).all():
        rows.append(
            {
                "ts_code": opportunity.ts_code,
                "name": name,
                "state": opportunity.state,
                "left_reversal_score": opportunity.left_reversal_score,
                "right_side_score": opportunity.right_side_score,
                "trend_score": opportunity.trend_score,
                "trend_rank_score": opportunity.trend_rank_score,
                "position_score": opportunity.position_score,
                "opportunity_stage": opportunity.opportunity_stage,
                "opportunity_score": opportunity.opportunity_score,
            }
        )
    return rows


def _member_count(
    db: Session,
    member_codes: set[str],
    target: date,
    stage: str | None,
) -> int:
    settings = get_settings()
    if not member_codes:
        return 0
    filters = [
        StockOpportunityDaily.ts_code.in_(member_codes),
        StockOpportunityDaily.trade_date == target,
        *opportunity_identity_filters(settings),
    ]
    if stage:
        filters.append(StockOpportunityDaily.opportunity_stage == stage)
    return int(
        db.execute(
            select(func.count()).select_from(StockOpportunityDaily).where(*filters)
        ).scalar_one()
    )


def _theme_member_codes(members: Any, theme_code: str, target: date) -> set[str]:
    if members.empty:
        return set()
    rows = members[
        (members["trade_date"] == target) & (members["theme_code"] == theme_code)
    ]
    return set(rows["ts_code"].astype(str))


def _member_context_meta(context: dict[str, object] | None) -> dict[str, Any]:
    context = context or {}
    snapshot_date = context.get("source_snapshot_date")
    return {
        "member_context_available": bool(context.get("available", False)),
        "member_context_mode": context.get("mode", "UNAVAILABLE"),
        "member_context_coverage": context.get("coverage"),
        "source_snapshot_date": snapshot_date.isoformat()
        if isinstance(snapshot_date, date)
        else snapshot_date,
    }


def _legacy_snapshot_meta(context: dict[str, Any]) -> dict[str, Any]:
    mode = context["member_context_mode"]
    return {
        "member_snapshot_date": context["source_snapshot_date"],
        "member_snapshot_status": None,
        "member_snapshot_coverage": context["member_context_coverage"],
        "member_snapshot_mode": (
            "PARTIAL" if mode == "INTERVAL_SNAPSHOT" else "FULL" if mode != "UNAVAILABLE" else None
        ),
    }


def _meta(target: date | None, limit: int, offset: int, total: int) -> dict[str, Any]:
    return {
        "trade_date": target.isoformat() if target else None,
        "limit": limit,
        "offset": offset,
        "total": total,
    }


def _model_payload(row: Any) -> dict[str, Any]:
    return {column.name: iso(getattr(row, column.name)) for column in row.__table__.columns}
