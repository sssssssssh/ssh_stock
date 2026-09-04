from dataclasses import dataclass
from datetime import date, timedelta

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import (
    MarketDaily,
    SectorFactorDaily,
    StockFactorDaily,
    StockStateDaily,
    TradeCalendar,
)
from app.providers.base import MarketDataProvider
from app.repositories.job_run import start_job
from app.services.dirty import latest_raw_trade_date, open_dirty_ranges
from app.services.ingestion import IngestionService
from app.services.job_guard import scheduler_setting
from app.services.quality.daily_quality import DataQualityError
from app.services.quality.raw_completeness import check_raw_completeness
from app.services.recalculation import run_recalculation


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
        open_dates = _open_trade_dates(self.db, calendar_start, target_date)
        raw_required_dates = _recent_raw_incomplete_dates(
            self.db,
            open_dates,
            max_trade_days=max_trade_days,
        )
        analysis_complete = analysis_complete_dates(
            self.db,
            calendar_start,
            target_date,
            algo_version=self.settings.algo_version,
        )
        raw_required_set = set(raw_required_dates)
        analysis_required_dates = [
            current
            for current in open_dates
            if current not in raw_required_set and current not in analysis_complete
        ]
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

        from app.jobs.daily_job import DailyJob

        for current in plan.raw_required_dates:
            logger.info("catch-up running daily for raw gap trade_date={}", current)
            DailyJob(self.db, self.provider).run(current)

        if plan.analysis_required_dates:
            self._run_analysis_repair(
                min(plan.analysis_required_dates),
                max(open_dates),
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
            status="QUEUED",
            step="queued from catchup",
            metadata={
                "source": mode,
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

    def _refresh_raw_only(self, trade_date: date) -> None:
        self.ingestion.sync_daily(trade_date)
        self.ingestion.sync_adj_factor(trade_date)
        self.ingestion.sync_daily_basic(trade_date)
        self.ingestion.sync_index_daily(trade_date)
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
                "raw refresh completeness failed: "
                f"trade_date={trade_date} statuses={statuses}"
            )

    def _run_dirty_repair_if_needed(self) -> None:
        dirty_ranges = open_dirty_ranges(self.db)
        if not dirty_ranges:
            return
        latest = latest_raw_trade_date(self.db)
        if latest is None:
            raise RuntimeError("dirty repair requested but no stock_daily data available")
        start = min(row.dirty_start_date for row in dirty_ranges)
        job = start_job(
            self.db,
            "recalculate",
            latest,
            status="QUEUED",
            step="queued from scheduler dirty repair",
            metadata={
                "source": "dirty_repair",
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
) -> set[date]:
    factor_dates = _dates_with_rows(db, StockFactorDaily, StockFactorDaily.trade_date, start, end)
    market_dates = _dates_with_rows(db, MarketDaily, MarketDaily.trade_date, start, end)
    sector_dates = _dates_with_rows(db, SectorFactorDaily, SectorFactorDaily.trade_date, start, end)
    state_dates = set(
        db.execute(
            select(StockStateDaily.trade_date)
            .where(
                StockStateDaily.trade_date >= start,
                StockStateDaily.trade_date <= end,
                StockStateDaily.algo_version == algo_version,
            )
            .distinct()
        )
        .scalars()
        .all()
    )
    return factor_dates & market_dates & sector_dates & state_dates


def _dates_with_rows(
    db: Session,
    model: type,
    column,
    start: date,
    end: date,
) -> set[date]:
    return set(
        db.execute(
            select(column)
            .select_from(model)
            .where(column >= start, column <= end)
            .distinct()
        )
        .scalars()
        .all()
    )


def _recent_raw_incomplete_dates(
    db: Session,
    open_dates: list[date],
    *,
    max_trade_days: int,
) -> list[date]:
    strategy = get_settings().strategy
    recent = open_dates[-max_trade_days:] if max_trade_days > 0 else []
    incomplete: list[date] = []
    for current in recent:
        result = check_raw_completeness(
            db,
            current,
            strategy=strategy,
            persist=False,
        )
        if not result.is_complete:
            incomplete.append(current)
    return incomplete
