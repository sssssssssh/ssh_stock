from dataclasses import dataclass
from datetime import date, timedelta

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import (
    MarketDaily,
    SectorFactorDaily,
    StockDaily,
    StockFactorDaily,
    StockStateDaily,
    TradeCalendar,
)
from app.providers.base import MarketDataProvider
from app.repositories.job_run import start_job
from app.services.analysis_identity import TREND_CALC_VERSION
from app.services.calc_metadata import config_hash
from app.services.dirty import (
    latest_raw_trade_date,
    repairable_dirty_ranges,
    unresolved_dirty_ranges,
)
from app.services.ingestion import IngestionService
from app.services.job_guard import scheduler_setting
from app.services.quality.daily_quality import DataQualityError, cross_table_coverage_status
from app.services.quality.opportunity_quality import check_opportunity_quality
from app.services.quality.raw_completeness import check_raw_completeness
from app.services.recalculation import run_recalculation
from app.services.trade_status import TradeStatusService


@dataclass(frozen=True)
class CatchUpPlan:
    raw_required_dates: list[date]
    analysis_required_dates: list[date]
    refresh_dates: list[date]
    skipped: bool
    reason: str | None = None

    @property
    def required_dates(self) -> list[date]:
        return sorted(set(self.raw_required_dates + self.analysis_required_dates))


class CatchUpJob:
    def __init__(self, db: Session, provider: MarketDataProvider) -> None:
        self.db = db
        self.provider = provider
        self.settings = get_settings()
        self.ingestion = IngestionService(db, provider)

    def run(self, target_date: date) -> CatchUpPlan:
        max_trade_days = int(scheduler_setting("max_catchup_trade_days", 20))
        refresh_recent_days = int(scheduler_setting("refresh_recent_trade_days", 5))
        calendar_start = target_date - timedelta(days=max(90, max_trade_days * 4))
        self.ingestion.sync_trade_calendar(calendar_start, target_date)
        self.ingestion.sync_stock_basic()
        sync_theme_catalog = getattr(self.ingestion, "sync_ths_themes", None)
        if callable(sync_theme_catalog):
            try:
                sync_theme_catalog(target_date)
            except Exception as exc:
                rollback = getattr(self.db, "rollback", None)
                if callable(rollback):
                    rollback()
                logger.warning("catch-up theme catalog sync failed error={}", exc)
        open_dates = _open_trade_dates(self.db, calendar_start, target_date)
        candidate_dates = _candidate_catchup_dates(
            open_dates,
            max_trade_days=max_trade_days,
        )
        raw_required_dates, analysis_required_dates = classify_catchup_dates(
            self.db,
            candidate_dates,
            strategy=self.settings.strategy,
            opportunity_config=getattr(self.settings, "opportunity_config", None),
            algo_version=self.settings.algo_version,
        )
        plan = build_catchup_plan(
            open_dates=open_dates,
            raw_required_dates=raw_required_dates,
            analysis_required_dates=analysis_required_dates,
            max_catchup_trade_days=max_trade_days,
            refresh_recent_trade_days=refresh_recent_days,
        )
        if plan.skipped:
            logger.warning(
                "catch-up skipped target_date={} reason={} required_dates={}",
                target_date,
                plan.reason,
                len(plan.required_dates),
            )
            return plan

        for current in plan.raw_required_dates:
            logger.info("catch-up raw-only repair trade_date={}", current)
            self._sync_and_validate_raw_date(current)

        recalc_dates = plan.required_dates
        if recalc_dates:
            latest = latest_raw_trade_date(self.db)
            if latest is None:
                raise RuntimeError(
                    "catch-up recalculation requested but no stock_daily data available"
                )
            self._run_analysis_repair(
                min(recalc_dates),
                latest,
                mode="catchup_analysis",
            )

        for current in plan.refresh_dates:
            logger.info("catch-up raw-only refresh trade_date={}", current)
            self._refresh_raw_only(current)

        self._run_dirty_repair_if_needed()
        logger.info(
            "catch-up complete target_date={} raw_required={} "
            "analysis_required={} refresh_dates={}",
            target_date,
            len(plan.raw_required_dates),
            len(plan.analysis_required_dates),
            len(plan.refresh_dates),
        )
        return plan

    def _run_analysis_repair(self, start: date, end: date, *, mode: str) -> None:
        job = start_job(
            self.db,
            "recalculate",
            end,
            status="RUNNING",
            step="started by catchup",
            metadata={
                "source": mode,
                "execution_owner": "catchup",
                "mode": mode,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "evaluate_signals": True,
                "progress_pct": 0,
            },
        )
        run_recalculation(
            self.db,
            job,
            start,
            end,
            evaluate_signals=True,
            mode=mode,
        )

    def _sync_and_validate_raw_date(self, trade_date: date) -> None:
        self.ingestion.sync_stock_st(trade_date)
        self.ingestion.sync_suspend_daily(trade_date)
        self.ingestion.sync_daily(trade_date)
        self.ingestion.sync_adj_factor(trade_date)
        self.ingestion.sync_daily_basic(trade_date)
        self.ingestion.sync_index_daily(trade_date)
        self.ingestion.sync_stock_limit(trade_date)
        raw_quality = check_raw_completeness(
            self.db,
            trade_date,
            strategy=self.settings.strategy,
            persist=True,
        )
        self.db.commit()
        if raw_quality.overall_status == "ERROR":
            statuses = raw_quality.as_metadata()["current_day_datasets"]
            raise DataQualityError(
                f"raw completeness failed: trade_date={trade_date} statuses={statuses}"
            )
        TradeStatusService(self.db).recalc(trade_date, trade_date)

    def _refresh_raw_only(self, trade_date: date) -> None:
        self._sync_and_validate_raw_date(trade_date)
        try:
            self.ingestion.sync_theme_daily(trade_date)
            self.ingestion.sync_theme_optional_sources(trade_date)
        except Exception as exc:
            self.db.rollback()
            logger.exception(
                "catch-up theme refresh failed trade_date={} error={}", trade_date, exc
            )

    def _run_dirty_repair_if_needed(self) -> None:
        dirty_ranges = repairable_dirty_ranges(
            self.db,
            max_retry_count=int(scheduler_setting("dirty_max_retry_count", 3)),
        )
        if not dirty_ranges:
            unresolved = unresolved_dirty_ranges(self.db)
            if unresolved:
                logger.warning(
                    "dirty repair skipped because retry limit was reached; "
                    "manual intervention required count={}",
                    len(unresolved),
                )
            return
        latest = latest_raw_trade_date(self.db)
        if latest is None:
            raise RuntimeError("dirty repair requested but no stock_daily data available")
        start = min(row.dirty_start_date for row in dirty_ranges)
        job = start_job(
            self.db,
            "recalculate",
            latest,
            status="RUNNING",
            step="started by catchup dirty repair",
            metadata={
                "source": "dirty_repair",
                "execution_owner": "catchup",
                "mode": "dirty_repair",
                "start": start.isoformat(),
                "end": latest.isoformat(),
                "evaluate_signals": True,
                "dirty_range_ids": [row.id for row in dirty_ranges],
                "progress_pct": 0,
            },
        )
        run_recalculation(
            self.db,
            job,
            start,
            latest,
            evaluate_signals=True,
            mode="dirty_repair",
            dirty_ranges=dirty_ranges,
        )


def build_catchup_plan(
    *,
    open_dates: list[date],
    raw_required_dates: list[date],
    analysis_required_dates: list[date],
    max_catchup_trade_days: int,
    refresh_recent_trade_days: int,
) -> CatchUpPlan:
    ordered_open_dates = sorted(set(open_dates))
    raw_required = sorted(set(raw_required_dates))
    analysis_required = sorted(set(analysis_required_dates) - set(raw_required))
    required_dates = sorted(set(raw_required + analysis_required))
    if len(required_dates) > max_catchup_trade_days:
        return CatchUpPlan(
            raw_required_dates=raw_required,
            analysis_required_dates=analysis_required,
            refresh_dates=[],
            skipped=True,
            reason=(
                "required catch-up trade days exceeds "
                f"max_catchup_trade_days={max_catchup_trade_days}; run manual backfill"
            ),
        )

    refresh_dates = (
        ordered_open_dates[-refresh_recent_trade_days:] if refresh_recent_trade_days > 0 else []
    )
    refresh_dates = [trade_date for trade_date in refresh_dates if trade_date not in raw_required]
    return CatchUpPlan(
        raw_required_dates=raw_required,
        analysis_required_dates=analysis_required,
        refresh_dates=refresh_dates,
        skipped=False,
    )


def _open_trade_dates(db: Session, start: date, end: date) -> list[date]:
    return list(
        db.execute(
            select(TradeCalendar.cal_date)
            .where(
                TradeCalendar.cal_date >= start,
                TradeCalendar.cal_date <= end,
                TradeCalendar.is_open.is_(True),
            )
            .order_by(TradeCalendar.cal_date)
        )
        .scalars()
        .all()
    )


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
        opportunity_config
        if opportunity_config is not None
        else settings.opportunity_config
    )
    return {
        trade_date
        for trade_date in _open_trade_dates(db, start, end)
        if is_analysis_complete(
            db,
            trade_date,
            strategy=resolved_strategy,
            opportunity_config=resolved_opportunity,
            algo_version=algo_version,
        )
    }


def classify_catchup_dates(
    db: Session,
    candidate_dates: list[date],
    *,
    strategy: dict,
    opportunity_config: dict | None = None,
    algo_version: str,
) -> tuple[list[date], list[date]]:
    raw_required_dates: list[date] = []
    analysis_required_dates: list[date] = []
    for trade_date in candidate_dates:
        raw = check_raw_completeness(
            db,
            trade_date,
            strategy=strategy,
            persist=False,
        )
        if not raw.is_complete:
            raw_required_dates.append(trade_date)
            continue
        if not is_analysis_complete(
            db,
            trade_date,
            strategy=strategy,
            opportunity_config=opportunity_config,
            algo_version=algo_version,
        ):
            analysis_required_dates.append(trade_date)
    return raw_required_dates, analysis_required_dates


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
    resolved_opportunity = opportunity_config
    quality = check_opportunity_quality(
        db,
        trade_date,
        strategy_hash=config_hash(strategy),
        opportunity_hash=config_hash(resolved_opportunity),
        algo_version=algo_version,
        config=resolved_opportunity,
    )
    return quality.is_complete


def is_core_analysis_complete(
    db: Session,
    trade_date: date,
    *,
    strategy: dict,
    algo_version: str,
) -> bool:
    current_config_hash = config_hash(strategy)
    stock_daily_count = _count_matching(db, StockDaily, StockDaily.trade_date == trade_date)
    factor_count = _count_matching(
        db,
        StockFactorDaily,
        StockFactorDaily.trade_date == trade_date,
        StockFactorDaily.calc_version == "factor_v1",
        StockFactorDaily.config_hash == current_config_hash,
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
        MarketDaily.calc_version == "market_v1",
        MarketDaily.config_hash == current_config_hash,
    )
    if market_count < 1:
        return False

    sector_count = _count_matching(
        db,
        SectorFactorDaily,
        SectorFactorDaily.trade_date == trade_date,
        SectorFactorDaily.calc_version == "sector_v1",
        SectorFactorDaily.config_hash == current_config_hash,
    )
    if sector_count < 1:
        return False

    state_count = _count_matching(
        db,
        StockStateDaily,
        StockStateDaily.trade_date == trade_date,
        StockStateDaily.algo_version == algo_version,
        StockStateDaily.calc_version == TREND_CALC_VERSION,
        StockStateDaily.config_hash == current_config_hash,
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


def _candidate_catchup_dates(
    open_dates: list[date],
    *,
    max_trade_days: int,
) -> list[date]:
    return open_dates[-max_trade_days:] if max_trade_days > 0 else []


def _count_matching(db: Session, model: type, *criteria) -> int:
    return int(db.execute(select(func.count()).select_from(model).where(*criteria)).scalar_one())
