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
    ThemeMemberSnapshot,
)
from app.services.analysis_identity import OPPORTUNITY_CALC_VERSION, THEME_CALC_VERSION
from app.services.calc_metadata import config_hash
from app.services.quality.theme_quality import latest_valid_theme_member_snapshot

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
    hash_value = config_hash(get_settings().opportunity_config)
    target = trade_date or latest_date(
        db,
        ThemeFactorDaily.trade_date,
        ThemeFactorDaily.calc_version == THEME_CALC_VERSION,
        ThemeFactorDaily.config_hash == hash_value,
    )
    row_limit, row_offset = clamp_limit(limit, default=30), clamp_offset(offset)
    if not target:
        return envelope([], _meta(None, row_limit, row_offset, 0))
    filters = [
        ThemeFactorDaily.trade_date == target,
        ThemeFactorDaily.calc_version == THEME_CALC_VERSION,
        ThemeFactorDaily.config_hash == hash_value,
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
    theme_hash = config_hash(settings.opportunity_config)
    target = trade_date or latest_date(
        db,
        ThemeFactorDaily.trade_date,
        ThemeFactorDaily.theme_code == theme_code,
        ThemeFactorDaily.calc_version == THEME_CALC_VERSION,
        ThemeFactorDaily.config_hash == theme_hash,
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
                    ThemeFactorDaily.calc_version == THEME_CALC_VERSION,
                    ThemeFactorDaily.config_hash == theme_hash,
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
    if target:
        member_rows = _member_opportunities(db, theme_code, target, None, 200, 0)
        counts: dict[str, int] = {}
        for row in member_rows:
            stage = str(row["opportunity_stage"])
            counts[stage] = counts.get(stage, 0) + 1
        member_distribution = [
            {"stage": stage, "count": count} for stage, count in sorted(counts.items())
        ]
        top_members["trend"] = _member_opportunities(
            db, theme_code, target, None, 10, 0, pool="trend"
        )
        top_members["right"] = _member_opportunities(
            db, theme_code, target, None, 10, 0, pool="right"
        )
        top_members["left"] = _member_opportunities(
            db, theme_code, target, None, 10, 0, pool="left"
        )
    return envelope(
        {
            "theme": _model_payload(theme),
            "factor": _model_payload(factor) if factor else None,
            "history": history,
            "member_distribution": member_distribution,
            "top_members": top_members,
        },
        {"trade_date": target.isoformat() if target else None},
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
    hash_value = config_hash(settings.opportunity_config)
    target = trade_date or latest_date(
        db,
        StockOpportunityDaily.trade_date,
        StockOpportunityDaily.algo_version == settings.algo_version,
        StockOpportunityDaily.calc_version == OPPORTUNITY_CALC_VERSION,
        StockOpportunityDaily.config_hash == hash_value,
    )
    row_limit, row_offset = clamp_limit(limit, default=30), clamp_offset(offset)
    if not target:
        return envelope([], _meta(None, row_limit, row_offset, 0))
    rows = _member_opportunities(db, theme_code, target, stage, row_limit, row_offset)
    snapshot = latest_valid_theme_member_snapshot(db, target)
    total = _member_count(db, theme_code, target, stage)
    return envelope(
        rows,
        {
            **_meta(target, row_limit, row_offset, total),
            "member_snapshot_date": snapshot.isoformat() if snapshot else None,
        },
    )


def _member_opportunities(
    db: Session,
    theme_code: str,
    target: date,
    stage: str | None,
    limit: int,
    offset: int,
    *,
    pool: str | None = None,
) -> list[dict[str, Any]]:
    snapshot = latest_valid_theme_member_snapshot(db, target)
    if snapshot is None:
        return []
    settings = get_settings()
    filters = [
        ThemeMemberSnapshot.snapshot_date == snapshot,
        ThemeMemberSnapshot.theme_code == theme_code,
        StockOpportunityDaily.trade_date == target,
        StockOpportunityDaily.algo_version == settings.algo_version,
        StockOpportunityDaily.calc_version == OPPORTUNITY_CALC_VERSION,
        StockOpportunityDaily.config_hash == config_hash(settings.opportunity_config),
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
        .select_from(ThemeMemberSnapshot)
        .join(
            StockOpportunityDaily,
            ThemeMemberSnapshot.ts_code == StockOpportunityDaily.ts_code,
        )
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


def _member_count(db: Session, theme_code: str, target: date, stage: str | None) -> int:
    snapshot = latest_valid_theme_member_snapshot(db, target)
    if snapshot is None:
        return 0
    settings = get_settings()
    filters = [
        ThemeMemberSnapshot.snapshot_date == snapshot,
        ThemeMemberSnapshot.theme_code == theme_code,
        StockOpportunityDaily.trade_date == target,
        StockOpportunityDaily.algo_version == settings.algo_version,
        StockOpportunityDaily.calc_version == OPPORTUNITY_CALC_VERSION,
        StockOpportunityDaily.config_hash == config_hash(settings.opportunity_config),
    ]
    if stage:
        filters.append(StockOpportunityDaily.opportunity_stage == stage)
    return int(
        db.execute(
            select(func.count())
            .select_from(ThemeMemberSnapshot)
            .join(
                StockOpportunityDaily,
                ThemeMemberSnapshot.ts_code == StockOpportunityDaily.ts_code,
            )
            .where(*filters)
        ).scalar_one()
    )


def _meta(target: date | None, limit: int, offset: int, total: int) -> dict[str, Any]:
    return {
        "trade_date": target.isoformat() if target else None,
        "limit": limit,
        "offset": offset,
        "total": total,
    }


def _model_payload(row: Any) -> dict[str, Any]:
    return {column.name: iso(getattr(row, column.name)) for column in row.__table__.columns}
