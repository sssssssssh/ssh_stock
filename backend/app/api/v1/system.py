from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import Select, desc, func, select
from sqlalchemy.orm import Session

from app.api.v1.common import envelope
from app.core.config import get_settings
from app.core.db import get_db
from app.models.job import JobRun
from app.models.market_data import (
    DataQualityDaily,
    IndexDaily,
    MarketDaily,
    SectorFactorDaily,
    SignalForwardEval,
    StockAdjFactor,
    StockDaily,
    StockDailyBasic,
    StockFactorDaily,
    StockOpportunityDaily,
    StockStateDaily,
    StrategySignal,
    ThemeDaily,
    ThemeFactorDaily,
    ThemeMemberSnapshot,
    TradeCalendar,
)
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    MARKET_CALC_VERSION,
    OPPORTUNITY_CALC_VERSION,
    SECTOR_CALC_VERSION,
    SIGNAL_CALC_VERSION,
    THEME_CALC_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash

router = APIRouter()


def _latest_date(db: Session, stmt: Select[tuple[Any]]) -> str | None:
    value = db.execute(stmt).scalar_one_or_none()
    return value.isoformat() if value else None


@router.get("/runtime")
def runtime(db: Session = Depends(get_db)) -> dict[str, Any]:
    settings = get_settings()
    active = db.scalar(
        select(JobRun)
        .where(JobRun.status == "RUNNING")
        .order_by(JobRun.started_at)
        .limit(1)
    )
    counts = dict(
        db.execute(
            select(JobRun.status, func.count())
            .where(JobRun.status.in_(("QUEUED", "RUNNING")))
            .group_by(JobRun.status)
        ).all()
    )
    latest_worker_heartbeat = db.scalar(select(func.max(JobRun.heartbeat_at)))
    scheduler = settings.app_config.get("app", {}).get("scheduler", {})
    research = settings.app_config.get("research", {})
    return envelope(
        {
            "worker_heartbeat": latest_worker_heartbeat.isoformat()
            if latest_worker_heartbeat
            else None,
            "active_job": {
                "id": str(active.id),
                "job_type": active.job_type,
                "step": active.step,
                "started_at": active.started_at.isoformat() if active.started_at else None,
            }
            if active
            else None,
            "queued_count": int(counts.get("QUEUED", 0)),
            "running_count": int(counts.get("RUNNING", 0)),
            "scheduler_cron": {
                "daily": scheduler.get("daily_cron", "10 18 * * 1-5"),
                "basic_info": scheduler.get("basic_info_cron", "30 9 * * 6"),
                "research": research.get("daily_cron", "30 19 * * 1-5"),
            },
            "latest_raw_date": _latest_date(db, select(func.max(StockDaily.trade_date))),
            "latest_analysis_date": _latest_date(
                db, select(func.max(StockStateDaily.trade_date))
            ),
            "latest_opportunity_date": _latest_date(
                db, select(func.max(StockOpportunityDaily.trade_date))
            ),
        }
    )


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict[str, Any]:
    settings = get_settings()
    version = settings.algo_version
    hash_value = analysis_strategy_hash(settings.strategy)
    opportunity_hash = config_hash(settings.opportunity_config)
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
            "latest_factor_date": _latest_date(
                db,
                select(func.max(StockFactorDaily.trade_date)).where(
                    StockFactorDaily.calc_version == FACTOR_CALC_VERSION,
                    StockFactorDaily.config_hash == hash_value,
                ),
            ),
            "latest_market_date": _latest_date(
                db,
                select(func.max(MarketDaily.trade_date)).where(
                    MarketDaily.calc_version == MARKET_CALC_VERSION,
                    MarketDaily.config_hash == hash_value,
                ),
            ),
            "latest_sector_factor_date": _latest_date(
                db,
                select(func.max(SectorFactorDaily.trade_date)).where(
                    SectorFactorDaily.calc_version == SECTOR_CALC_VERSION,
                    SectorFactorDaily.config_hash == hash_value,
                ),
            ),
            "latest_state_date": _latest_date(
                db,
                select(func.max(StockStateDaily.trade_date)).where(
                    StockStateDaily.algo_version == version,
                    StockStateDaily.calc_version == TREND_CALC_VERSION,
                    StockStateDaily.config_hash == hash_value,
                ),
            ),
            "latest_signal_date": _latest_date(
                db,
                select(func.max(StrategySignal.trade_date)).where(
                    StrategySignal.algo_version == version,
                    StrategySignal.calc_version == SIGNAL_CALC_VERSION,
                    StrategySignal.config_hash == hash_value,
                ),
            ),
            "latest_signal_eval_date": _latest_date(
                db,
                select(func.max(SignalForwardEval.trade_date)).where(
                    SignalForwardEval.algo_version == version
                ),
            ),
            "latest_theme_daily_date": _latest_date(db, select(func.max(ThemeDaily.trade_date))),
            "latest_theme_factor_date": _latest_date(
                db,
                select(func.max(ThemeFactorDaily.trade_date)).where(
                    ThemeFactorDaily.calc_version == THEME_CALC_VERSION,
                    ThemeFactorDaily.config_hash == opportunity_hash,
                ),
            ),
            "latest_opportunity_date": _latest_date(
                db,
                select(func.max(StockOpportunityDaily.trade_date)).where(
                    StockOpportunityDaily.algo_version == version,
                    StockOpportunityDaily.calc_version == OPPORTUNITY_CALC_VERSION,
                    StockOpportunityDaily.config_hash == opportunity_hash,
                ),
            ),
            "latest_theme_member_snapshot": _latest_date(
                db, select(func.max(ThemeMemberSnapshot.snapshot_date))
            ),
        },
        "meta": {
            "algo_version": version,
            "config_hash": hash_value,
            "strategy_config_hash": hash_value,
            "opportunity_config_hash": opportunity_hash,
        },
    }


@router.get("/data-coverage")
def data_coverage(
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    settings = get_settings()
    version = settings.algo_version
    hash_value = analysis_strategy_hash(settings.strategy)
    opportunity_hash = config_hash(settings.opportunity_config)
    date_stmt = select(StockDaily.trade_date).distinct().order_by(desc(StockDaily.trade_date))
    if start:
        date_stmt = date_stmt.where(StockDaily.trade_date >= start)
    if end:
        date_stmt = date_stmt.where(StockDaily.trade_date <= end)
    if limit is not None:
        date_stmt = date_stmt.limit(max(1, limit))
    trade_dates = db.execute(date_stmt).scalars().all()
    if not trade_dates:
        return envelope(
            [],
            {
                "start": start.isoformat() if start else None,
                "end": end.isoformat() if end else None,
                "limit": limit,
                "total": 0,
                "algo_version": version,
                "config_hash": hash_value,
            },
        )

    coverage_start = min(trade_dates)
    coverage_end = max(trade_dates)
    stock_daily_counts = _counts_by_date(db, StockDaily.trade_date, coverage_start, coverage_end)
    daily_basic_counts = _counts_by_date(
        db, StockDailyBasic.trade_date, coverage_start, coverage_end
    )
    adj_factor_counts = _counts_by_date(db, StockAdjFactor.trade_date, coverage_start, coverage_end)
    index_daily_counts = _counts_by_date(db, IndexDaily.trade_date, coverage_start, coverage_end)
    factor_counts = _counts_by_date(
        db,
        StockFactorDaily.trade_date,
        coverage_start,
        coverage_end,
        StockFactorDaily.calc_version == FACTOR_CALC_VERSION,
        StockFactorDaily.config_hash == hash_value,
    )
    market_counts = _counts_by_date(
        db,
        MarketDaily.trade_date,
        coverage_start,
        coverage_end,
        MarketDaily.calc_version == MARKET_CALC_VERSION,
        MarketDaily.config_hash == hash_value,
    )
    sector_counts = _counts_by_date(
        db,
        SectorFactorDaily.trade_date,
        coverage_start,
        coverage_end,
        SectorFactorDaily.calc_version == SECTOR_CALC_VERSION,
        SectorFactorDaily.config_hash == hash_value,
    )
    state_counts = _counts_by_date(
        db,
        StockStateDaily.trade_date,
        coverage_start,
        coverage_end,
        StockStateDaily.algo_version == version,
        StockStateDaily.calc_version == TREND_CALC_VERSION,
        StockStateDaily.config_hash == hash_value,
    )
    signal_counts = _counts_by_date(
        db,
        StrategySignal.trade_date,
        coverage_start,
        coverage_end,
        StrategySignal.algo_version == version,
        StrategySignal.calc_version == SIGNAL_CALC_VERSION,
        StrategySignal.config_hash == hash_value,
    )
    signal_eval_counts = _counts_by_date(
        db,
        SignalForwardEval.trade_date,
        coverage_start,
        coverage_end,
        SignalForwardEval.algo_version == version,
    )
    theme_daily_counts = _counts_by_date(db, ThemeDaily.trade_date, coverage_start, coverage_end)
    theme_factor_counts = _counts_by_date(
        db,
        ThemeFactorDaily.trade_date,
        coverage_start,
        coverage_end,
        ThemeFactorDaily.calc_version == THEME_CALC_VERSION,
        ThemeFactorDaily.config_hash == opportunity_hash,
    )
    opportunity_counts = _counts_by_date(
        db,
        StockOpportunityDaily.trade_date,
        coverage_start,
        coverage_end,
        StockOpportunityDaily.algo_version == version,
        StockOpportunityDaily.calc_version == OPPORTUNITY_CALC_VERSION,
        StockOpportunityDaily.config_hash == opportunity_hash,
    )
    quality_status = _quality_status_by_date(db, coverage_start, coverage_end)

    rows = []
    for trade_date in trade_dates:
        rows.append(
            {
                "trade_date": trade_date.isoformat(),
                "stock_daily_rows": stock_daily_counts.get(trade_date, 0),
                "daily_basic_rows": daily_basic_counts.get(trade_date, 0),
                "adj_factor_rows": adj_factor_counts.get(trade_date, 0),
                "index_daily_rows": index_daily_counts.get(trade_date, 0),
                "factor_rows": factor_counts.get(trade_date, 0),
                "market_rows": market_counts.get(trade_date, 0),
                "sector_factor_rows": sector_counts.get(trade_date, 0),
                "state_rows": state_counts.get(trade_date, 0),
                "signal_rows": signal_counts.get(trade_date, 0),
                "signal_eval_rows": signal_eval_counts.get(trade_date, 0),
                "theme_daily_rows": theme_daily_counts.get(trade_date, 0),
                "theme_factor_rows": theme_factor_counts.get(trade_date, 0),
                "opportunity_rows": opportunity_counts.get(trade_date, 0),
                "current_version_rows": {
                    "factor": factor_counts.get(trade_date, 0),
                    "market": market_counts.get(trade_date, 0),
                    "sector_factor": sector_counts.get(trade_date, 0),
                    "state": state_counts.get(trade_date, 0),
                    "signal": signal_counts.get(trade_date, 0),
                    "theme_factor": theme_factor_counts.get(trade_date, 0),
                    "opportunity": opportunity_counts.get(trade_date, 0),
                },
                "quality_status": quality_status.get(trade_date),
            }
        )

    return envelope(
        rows,
        {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "limit": limit,
            "total": len(rows),
            "algo_version": version,
            "config_hash": hash_value,
            "opportunity_config_hash": opportunity_hash,
        },
    )


@router.get("/data-calendar")
def data_calendar(
    start: date,
    end: date,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    settings = get_settings()
    version = settings.algo_version
    hash_value = analysis_strategy_hash(settings.strategy)
    opportunity_hash = config_hash(settings.opportunity_config)
    if end < start:
        return envelope(
            [],
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "algo_version": version,
                "config_hash": hash_value,
                "opportunity_config_hash": opportunity_hash,
            },
        )

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
    factor_counts = _counts_by_date(
        db,
        StockFactorDaily.trade_date,
        start,
        end,
        StockFactorDaily.calc_version == FACTOR_CALC_VERSION,
        StockFactorDaily.config_hash == hash_value,
    )
    market_counts = _counts_by_date(
        db,
        MarketDaily.trade_date,
        start,
        end,
        MarketDaily.calc_version == MARKET_CALC_VERSION,
        MarketDaily.config_hash == hash_value,
    )
    sector_counts = _counts_by_date(
        db,
        SectorFactorDaily.trade_date,
        start,
        end,
        SectorFactorDaily.calc_version == SECTOR_CALC_VERSION,
        SectorFactorDaily.config_hash == hash_value,
    )
    state_counts = _counts_by_date(
        db,
        StockStateDaily.trade_date,
        start,
        end,
        StockStateDaily.algo_version == version,
        StockStateDaily.calc_version == TREND_CALC_VERSION,
        StockStateDaily.config_hash == hash_value,
    )
    signal_counts = _counts_by_date(
        db,
        StrategySignal.trade_date,
        start,
        end,
        StrategySignal.algo_version == version,
        StrategySignal.calc_version == SIGNAL_CALC_VERSION,
        StrategySignal.config_hash == hash_value,
    )
    signal_eval_counts = _counts_by_date(
        db,
        SignalForwardEval.trade_date,
        start,
        end,
        SignalForwardEval.algo_version == version,
    )
    theme_daily_counts = _counts_by_date(db, ThemeDaily.trade_date, start, end)
    theme_factor_counts = _counts_by_date(
        db,
        ThemeFactorDaily.trade_date,
        start,
        end,
        ThemeFactorDaily.calc_version == THEME_CALC_VERSION,
        ThemeFactorDaily.config_hash == opportunity_hash,
    )
    opportunity_counts = _counts_by_date(
        db,
        StockOpportunityDaily.trade_date,
        start,
        end,
        StockOpportunityDaily.algo_version == version,
        StockOpportunityDaily.calc_version == OPPORTUNITY_CALC_VERSION,
        StockOpportunityDaily.config_hash == opportunity_hash,
    )
    theme_source_status = _theme_source_status_by_date(db, start, end)
    quality_status = _quality_status_by_date(db, start, end)

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
        theme_daily_rows = theme_daily_counts.get(current, 0)
        theme_factor_rows = theme_factor_counts.get(current, 0)
        opportunity_rows = opportunity_counts.get(current, 0)
        day_quality_status = quality_status.get(current)
        if is_open is False:
            coverage_status = "CLOSED"
        elif day_quality_status == "ERROR" and stock_rows > 0:
            coverage_status = "DEGRADED"
        elif stock_rows <= 0:
            coverage_status = "MISSING"
        elif factor_rows > 0 and market_rows > 0 and state_rows > 0 and sector_rows > 0:
            opportunity_complete = _configured_coverage_not_error(
                state_rows,
                opportunity_rows,
                settings.opportunity_config,
                "opportunity_vs_state",
            )
            source_usable = theme_source_status.get(current) in {"PASS", "WARNING"}
            theme_complete = not source_usable or _configured_coverage_not_error(
                theme_daily_rows,
                theme_factor_rows,
                settings.opportunity_config,
                "theme_factor_vs_theme_daily",
            )
            coverage_status = (
                "OPPORTUNITY_COMPLETE"
                if opportunity_complete and theme_complete
                else "CORE_COMPLETE"
            )
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
                "theme_daily_rows": theme_daily_rows,
                "theme_factor_rows": theme_factor_rows,
                "opportunity_rows": opportunity_rows,
                "current_version_rows": {
                    "factor": factor_rows,
                    "market": market_rows,
                    "sector_factor": sector_rows,
                    "state": state_rows,
                    "signal": signal_counts.get(current, 0),
                    "theme_factor": theme_factor_rows,
                    "opportunity": opportunity_rows,
                },
                "quality_status": day_quality_status,
            }
        )
        current += timedelta(days=1)

    return envelope(
        rows,
        {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "algo_version": version,
            "config_hash": hash_value,
            "opportunity_config_hash": opportunity_hash,
        },
    )


def _counts_by_date(
    db: Session,
    column: Any,
    start: date,
    end: date,
    *criteria: Any,
) -> dict[date, int]:
    table = column.class_
    rows = (
        db.execute(
            select(column.label("trade_date"), func.count().label("rows"))
            .select_from(table)
            .where(column >= start, column <= end, *criteria)
            .group_by(column)
        )
        .mappings()
        .all()
    )
    return {row.trade_date: int(row.rows) for row in rows}


def _quality_status_by_date(db: Session, start: date, end: date) -> dict[date, str]:
    rows = db.execute(
        select(DataQualityDaily.trade_date, DataQualityDaily.status)
        .where(DataQualityDaily.trade_date >= start, DataQualityDaily.trade_date <= end)
        .where(DataQualityDaily.status.in_(["ERROR", "WARNING"]))
        .where(~DataQualityDaily.dataset.like("ths_theme%"))
        .order_by(DataQualityDaily.trade_date)
    ).all()
    priority = {"ERROR": 2, "WARNING": 1}
    result: dict[date, str] = {}
    for trade_date, status in rows:
        if priority[status] > priority.get(result.get(trade_date, ""), 0):
            result[trade_date] = status
    return result


def _theme_source_status_by_date(db: Session, start: date, end: date) -> dict[date, str]:
    rows = db.execute(
        select(DataQualityDaily.trade_date, DataQualityDaily.status).where(
            DataQualityDaily.trade_date >= start,
            DataQualityDaily.trade_date <= end,
            DataQualityDaily.dataset == "ths_theme_daily",
        )
    ).all()
    return {trade_date: status for trade_date, status in rows}


def _configured_coverage_not_error(
    expected: int,
    actual: int,
    config: dict[str, Any],
    dataset: str,
) -> bool:
    if expected <= 0:
        return True
    thresholds = config.get("opportunity_quality", {}).get(dataset, {})
    error_rate = float(thresholds.get("error_coverage_rate", 0.90))
    return min(actual / expected, 1.0) >= error_rate
