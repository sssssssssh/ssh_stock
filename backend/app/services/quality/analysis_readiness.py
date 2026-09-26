from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import (
    MarketDaily,
    StockDaily,
    StockFactorDaily,
    StockStateDaily,
    TradeCalendar,
)
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    MARKET_CALC_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.quality.daily_quality import cross_table_coverage_status
from app.services.quality.opportunity_quality import check_opportunity_quality
from app.services.quality.sector_quality import check_sector_factor_coverage


def analysis_complete_dates(
    db: Session,
    start: date,
    end: date,
    *,
    algo_version: str,
    strategy: dict | None = None,
    opportunity_config: dict | None = None,
) -> set[date]:
    settings = get_settings()
    resolved_strategy = strategy if strategy is not None else settings.strategy
    resolved_opportunity = (
        opportunity_config if opportunity_config is not None else settings.opportunity_config
    )
    open_dates = _open_trade_dates(db, start, end)
    return {
        trade_date
        for trade_date in open_dates
        if is_analysis_complete(
            db,
            trade_date,
            strategy=resolved_strategy,
            opportunity_config=resolved_opportunity,
            algo_version=algo_version,
        )
    }


def _open_trade_dates(db: Session, start: date, end: date) -> list[date]:
    return list(
        db.execute(
            select(TradeCalendar.cal_date)
            .where(
                TradeCalendar.is_open.is_(True),
                TradeCalendar.cal_date.between(start, end),
            )
            .order_by(TradeCalendar.cal_date)
        )
        .scalars()
        .all()
    )


def is_analysis_complete(
    db: Session,
    trade_date: date,
    *,
    strategy: dict,
    opportunity_config: dict | None = None,
    algo_version: str,
) -> bool:
    if not is_core_analysis_complete(
        db,
        trade_date,
        strategy=strategy,
        algo_version=algo_version,
    ):
        return False
    if opportunity_config is None:
        return True
    quality = check_opportunity_quality(
        db,
        trade_date,
        strategy_hash=analysis_strategy_hash(strategy),
        opportunity_hash=config_hash(opportunity_config),
        algo_version=algo_version,
        config=opportunity_config,
    )
    return quality.is_complete


def is_core_analysis_complete(
    db: Session,
    trade_date: date,
    *,
    strategy: dict,
    algo_version: str,
) -> bool:
    strategy_hash = analysis_strategy_hash(strategy)
    stock_daily_count = _count_matching(db, StockDaily, StockDaily.trade_date == trade_date)
    factor_count = _count_matching(
        db,
        StockFactorDaily,
        StockFactorDaily.trade_date == trade_date,
        StockFactorDaily.calc_version == FACTOR_CALC_VERSION,
        StockFactorDaily.config_hash == strategy_hash,
    )
    if (
        cross_table_coverage_status(
            strategy,
            "factor_vs_daily",
            stock_daily_count,
            factor_count,
            error_default=0.90,
        )
        != "PASS"
    ):
        return False
    market_count = _count_matching(
        db,
        MarketDaily,
        MarketDaily.trade_date == trade_date,
        MarketDaily.calc_version == MARKET_CALC_VERSION,
        MarketDaily.config_hash == strategy_hash,
    )
    if market_count < 1:
        return False
    sector_quality = check_sector_factor_coverage(
        db,
        trade_date,
        strategy=strategy,
        strategy_hash=strategy_hash,
    )
    if sector_quality.status != "PASS":
        return False
    state_count = _count_matching(
        db,
        StockStateDaily,
        StockStateDaily.trade_date == trade_date,
        StockStateDaily.algo_version == algo_version,
        StockStateDaily.calc_version == TREND_CALC_VERSION,
        StockStateDaily.config_hash == strategy_hash,
    )
    return (
        cross_table_coverage_status(
            strategy,
            "state_vs_factor",
            factor_count,
            state_count,
            error_default=0.90,
        )
        == "PASS"
    )


def _count_matching(db: Session, model: type, *criteria) -> int:
    return int(db.execute(select(func.count()).select_from(model).where(*criteria)).scalar_one())
