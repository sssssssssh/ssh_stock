from dataclasses import dataclass
from datetime import date, timedelta

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import StockStateDaily, TradeCalendar
from app.providers.base import MarketDataProvider
from app.services.ingestion import IngestionService
from app.services.job_guard import scheduler_setting
from app.services.quality.raw_completeness import check_raw_completeness


@dataclass(frozen=True)
class CatchUpPlan:
    run_dates: list[date]
    required_dates: list[date]
    refresh_dates: list[date]
    skipped: bool
    reason: str | None = None


class CatchUpJob:
    def __init__(self, db: Session, provider: MarketDataProvider) -> None:
        self.db = db
        self.provider = provider
        self.ingestion = IngestionService(db, provider)

    def run(self, target_date: date) -> CatchUpPlan:
        max_trade_days = int(scheduler_setting("max_catchup_trade_days", 20))
        refresh_recent_days = int(scheduler_setting("refresh_recent_trade_days", 5))
        calendar_start = target_date - timedelta(days=max(90, max_trade_days * 4))
        self.ingestion.sync_trade_calendar(calendar_start, target_date)
        open_dates = _open_trade_dates(self.db, calendar_start, target_date)
        latest_completed = _latest_completed_state_date(self.db)
        raw_incomplete_dates = _recent_raw_incomplete_dates(
            self.db,
            open_dates,
            max_trade_days=max_trade_days,
        )
        plan = build_catchup_plan(
            open_dates=open_dates,
            latest_completed_date=latest_completed,
            raw_incomplete_dates=raw_incomplete_dates,
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

        for current in plan.run_dates:
            logger.info("catch-up running daily trade_date={}", current)
            DailyJob(self.db, self.provider).run(current)
        logger.info(
            "catch-up complete target_date={} run_dates={} required_dates={} refresh_dates={}",
            target_date,
            len(plan.run_dates),
            len(plan.required_dates),
            len(plan.refresh_dates),
        )
        return plan


def build_catchup_plan(
    *,
    open_dates: list[date],
    latest_completed_date: date | None,
    raw_incomplete_dates: list[date],
    max_catchup_trade_days: int,
    refresh_recent_trade_days: int,
) -> CatchUpPlan:
    ordered_open_dates = sorted(set(open_dates))
    missing_after_latest = [
        current
        for current in ordered_open_dates
        if latest_completed_date is None or current > latest_completed_date
    ]
    required_dates = sorted(set(missing_after_latest + raw_incomplete_dates))
    if len(required_dates) > max_catchup_trade_days:
        return CatchUpPlan(
            run_dates=[],
            required_dates=required_dates,
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
    run_dates = sorted(set(required_dates + refresh_dates))
    return CatchUpPlan(
        run_dates=run_dates,
        required_dates=required_dates,
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


def _latest_completed_state_date(db: Session) -> date | None:
    return db.execute(select(func.max(StockStateDaily.trade_date))).scalar_one_or_none()


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
