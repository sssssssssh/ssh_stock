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
    StockOpportunityDaily,
    StockStateDaily,
    StrategySignal,
    Theme,
    ThemeFactorDaily,
)
from app.services.analysis_filters import (
    opportunity_identity_filters,
    theme_factor_identity_filters,
)
from app.services.analysis_identity import (
    MARKET_CALC_VERSION,
    SECTOR_CALC_VERSION,
    SIGNAL_CALC_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash

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
    hash_value = analysis_strategy_hash(settings.strategy)
    target = trade_date or latest_date(
        db,
        StockStateDaily.trade_date,
        StockStateDaily.algo_version == version,
        StockStateDaily.calc_version == TREND_CALC_VERSION,
        StockStateDaily.config_hash == hash_value,
    )
    if not target:
        return envelope(
            {
                "trade_date": None,
                "market": None,
                "state_counts": [],
                "signal_counts": [],
                "sector_heat_top": [],
                "industry_heat_top": [],
                "theme_heat_top": [],
                "left_reversal_top": [],
                "right_side_new": [],
                "trend_leaders": [],
            }
        )

    row_limit = clamp_limit(limit, default=10, maximum=50)
    market = db.execute(
        select(MarketDaily).where(
            MarketDaily.trade_date == target,
            MarketDaily.calc_version == MARKET_CALC_VERSION,
            MarketDaily.config_hash == hash_value,
        )
    ).scalar_one_or_none()
    industry_top = _sector_heat_top(db, target, row_limit, hash_value)
    opportunity_hash = config_hash(settings.opportunity_config)
    return envelope(
        {
            "trade_date": target.isoformat(),
            "market": _market_payload(market),
            "state_counts": _state_counts(db, target, version, hash_value),
            "signal_counts": _signal_counts(db, target, version, hash_value),
            "sector_heat_top": industry_top,
            "industry_heat_top": industry_top,
            "theme_heat_top": _theme_heat_top(
                db, target, row_limit, opportunity_hash, hash_value
            ),
            "left_reversal_top": _opportunity_pool(
                db,
                target,
                version,
                ["LEFT_WATCH", "LEFT_REVERSAL"],
                row_limit,
                opportunity_hash,
                hash_value,
            ),
            "right_side_new": _opportunity_pool(
                db,
                target,
                version,
                ["RIGHT_SIDE_NEW"],
                row_limit,
                opportunity_hash,
                hash_value,
                desc(StockOpportunityDaily.right_side_score),
            ),
            "trend_leaders": _opportunity_pool(
                db,
                target,
                version,
                ["TREND", "STRONG_TREND"],
                row_limit,
                opportunity_hash,
                hash_value,
                desc(StockOpportunityDaily.trend_rank_score),
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


def _state_counts(
    db: Session, target: date, algo_version: str, hash_value: str
) -> list[dict[str, Any]]:
    stmt = (
        select(StockStateDaily.state, func.count().label("count"))
        .where(
            StockStateDaily.trade_date == target,
            StockStateDaily.algo_version == algo_version,
            StockStateDaily.calc_version == TREND_CALC_VERSION,
            StockStateDaily.config_hash == hash_value,
        )
        .group_by(StockStateDaily.state)
        .order_by(StockStateDaily.state)
    )
    return [{"state": row.state, "count": row.count} for row in db.execute(stmt).all()]


def _signal_counts(
    db: Session, target: date, algo_version: str, hash_value: str
) -> list[dict[str, Any]]:
    stmt = (
        select(StrategySignal.signal_type, func.count().label("count"))
        .where(
            StrategySignal.trade_date == target,
            StrategySignal.algo_version == algo_version,
            StrategySignal.calc_version == SIGNAL_CALC_VERSION,
            StrategySignal.config_hash == hash_value,
        )
        .group_by(StrategySignal.signal_type)
        .order_by(StrategySignal.signal_type)
    )
    return [{"signal_type": row.signal_type, "count": row.count} for row in db.execute(stmt).all()]


def _sector_heat_top(
    db: Session, target: date, row_limit: int, hash_value: str
) -> list[dict[str, Any]]:
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
        .where(
            SectorFactorDaily.trade_date == target,
            SectorFactorDaily.calc_version == SECTOR_CALC_VERSION,
            SectorFactorDaily.config_hash == hash_value,
            Sector.level == "L1",
        )
        .order_by(SectorFactorDaily.heat_rank, desc(SectorFactorDaily.heat_score))
        .limit(row_limit)
    )
    return [_mapping_payload(row) for row in db.execute(stmt).mappings().all()]


def _theme_heat_top(
    db: Session,
    target: date,
    row_limit: int,
    opportunity_hash: str,
    strategy_hash: str,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            ThemeFactorDaily.trade_date,
            ThemeFactorDaily.theme_code,
            Theme.name,
            ThemeFactorDaily.heat_score,
            ThemeFactorDaily.heat_rank,
            ThemeFactorDaily.heat_momentum3,
            ThemeFactorDaily.rank_change,
            ThemeFactorDaily.lifecycle,
            ThemeFactorDaily.return1,
            ThemeFactorDaily.return5,
            ThemeFactorDaily.moneyflow_score,
            ThemeFactorDaily.net_amount,
            ThemeFactorDaily.limit_up_count,
            ThemeFactorDaily.continuous_limit_count,
            ThemeFactorDaily.breadth20,
            ThemeFactorDaily.rps60_median,
            ThemeFactorDaily.data_coverage,
        )
        .join(Theme, ThemeFactorDaily.theme_code == Theme.theme_code)
        .where(
            ThemeFactorDaily.trade_date == target,
            *theme_factor_identity_filters(
                strategy_hash=strategy_hash, opportunity_hash=opportunity_hash
            ),
        )
        .order_by(ThemeFactorDaily.heat_rank)
        .limit(row_limit)
    )
    return [_mapping_payload(row) for row in db.execute(stmt).mappings().all()]


def _opportunity_pool(
    db: Session,
    target: date,
    algo_version: str,
    stages: list[str],
    row_limit: int,
    hash_value: str,
    strategy_hash: str,
    order_by: Any = desc(StockOpportunityDaily.left_reversal_score),
) -> list[dict[str, Any]]:
    stmt = (
        select(
            StockOpportunityDaily,
            StockBasic.name,
            StockBasic.industry,
        )
        .outerjoin(StockBasic, StockOpportunityDaily.ts_code == StockBasic.ts_code)
        .where(
            StockOpportunityDaily.trade_date == target,
            StockOpportunityDaily.opportunity_stage.in_(stages),
            *opportunity_identity_filters(
                algo_version=algo_version,
                strategy_hash=strategy_hash,
                opportunity_hash=hash_value,
            ),
        )
        .order_by(order_by, StockOpportunityDaily.ts_code)
        .limit(row_limit)
    )
    result = []
    for opportunity, name, industry in db.execute(stmt).all():
        payload = {
            column.name: iso(getattr(opportunity, column.name))
            for column in opportunity.__table__.columns
        }
        payload.update({"name": name, "industry": industry})
        result.append(payload)
    return result


def _mapping_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {key: iso(value) for key, value in dict(row).items()}
