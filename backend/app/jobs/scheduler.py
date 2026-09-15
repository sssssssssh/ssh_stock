from datetime import date, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.jobs.catchup_job import CatchUpJob
from app.providers.base import MarketDataProvider
from app.providers.logging_provider import LoggingMarketDataProvider
from app.providers.tushare_provider import TushareProvider
from app.repositories.job_run import update_job
from app.services.job_guard import (
    ActiveIngestionJobError,
    create_queued_ingestion_job,
)


def run_scheduler() -> None:
    settings = get_settings()
    timezone = ZoneInfo(settings.app_timezone)
    scheduler = BlockingScheduler(timezone=timezone)

    def run_daily() -> None:
        with SessionLocal() as db:
            provider = LoggingMarketDataProvider(db, TushareProvider())
            run_scheduled_catchup(db, provider, _scheduler_today(timezone))

    def run_basic_info() -> None:
        with SessionLocal() as db:
            provider = LoggingMarketDataProvider(db, TushareProvider())
            run_scheduled_basic_info(db, provider)

    cron = settings.app_config.get("app", {}).get("scheduler", {}).get(
        "daily_cron", "10 18 * * 1-5"
    )
    scheduler.add_job(run_daily, "cron", id="daily_job", **cron_trigger_kwargs(cron))
    basic_cron = settings.app_config.get("app", {}).get("scheduler", {}).get(
        "basic_info_cron", "30 9 * * 6"
    )
    scheduler.add_job(
        run_basic_info,
        "cron",
        id="weekly_basic_refresh",
        **cron_trigger_kwargs(basic_cron),
    )
    logger.info("scheduler started daily_cron={} basic_info_cron={}", cron, basic_cron)
    scheduler.start()


def run_scheduled_catchup(db, provider: MarketDataProvider, target_date: date) -> bool:
    try:
        job = create_queued_ingestion_job(
            db,
            "catchup",
            target_date,
            step="queued from scheduler",
            metadata={"source": "scheduler", "trade_date": target_date.isoformat()},
        )
    except ActiveIngestionJobError as active:
        logger.warning(
            "scheduler daily skipped because active job exists id={} type={} status={}",
            active.job_id,
            active.job_type,
            active.status,
        )
        return False
    update_job(db, job, status="RUNNING", step="catchup running")
    try:
        plan = CatchUpJob(db, provider).run(target_date)
        update_job(
            db,
            job,
            status="SUCCESS",
            step="catchup complete",
            metadata={
                **(job.job_metadata or {}),
                "raw_required_days": len(plan.raw_required_dates),
                "analysis_required_days": len(plan.analysis_required_dates),
                "refresh_days": len(plan.refresh_dates),
                "skipped": plan.skipped,
            },
        )
    except Exception as exc:
        update_job(db, job, status="FAILED", error_message=str(exc))
        raise
    return True


def run_scheduled_basic_info(db, provider: MarketDataProvider) -> bool:
    try:
        create_queued_ingestion_job(
            db,
            "sync_basic",
            None,
            step="queued from weekly scheduler",
            metadata={"source": "scheduler", "stage": "queued", "progress_pct": 0},
        )
    except ActiveIngestionJobError as active:
        logger.warning(
            "scheduler basic info skipped because active job exists id={} type={} status={}",
            active.job_id,
            active.job_type,
            active.status,
        )
        return False
    return True


def _scheduler_today(timezone: ZoneInfo) -> date:
    return datetime.now(timezone).date()


def cron_trigger_kwargs(cron: str) -> dict[str, object]:
    parts = cron.split()
    if len(parts) != 5:
        raise ValueError(f"scheduler daily_cron must have 5 fields: {cron}")
    minute, hour, day, month, day_of_week = parts
    return {
        "minute": minute,
        "hour": hour,
        "day": day,
        "month": month,
        "day_of_week": _cron_day_of_week_to_apscheduler(day_of_week),
    }


def _cron_day_of_week_to_apscheduler(value: str) -> str:
    if value == "*":
        return value
    names = {
        "0": "sun",
        "7": "sun",
        "1": "mon",
        "2": "tue",
        "3": "wed",
        "4": "thu",
        "5": "fri",
        "6": "sat",
    }
    if "-" in value:
        left, right = value.split("-", maxsplit=1)
        if left in names and right in names:
            return f"{names[left]}-{names[right]}"
    if "," in value:
        converted = [names.get(part, part) for part in value.split(",")]
        return ",".join(converted)
    return names.get(value, value)
