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
from app.services.job_guard import find_active_ingestion_job, recover_stale_ingestion_jobs


def run_scheduler() -> None:
    settings = get_settings()
    timezone = ZoneInfo(settings.app_timezone)
    scheduler = BlockingScheduler(timezone=timezone)

    def run_daily() -> None:
        with SessionLocal() as db:
            provider = LoggingMarketDataProvider(db, TushareProvider())
            run_scheduled_catchup(db, provider, _scheduler_today(timezone))

    cron = settings.app_config.get("app", {}).get("scheduler", {}).get(
        "daily_cron", "10 18 * * 1-5"
    )
    scheduler.add_job(run_daily, "cron", id="daily_job", **cron_trigger_kwargs(cron))
    logger.info("scheduler started cron={}", cron)
    scheduler.start()


def run_scheduled_catchup(db, provider: MarketDataProvider, target_date: date) -> bool:
    recovered = recover_stale_ingestion_jobs(db)
    if recovered:
        logger.warning("scheduler recovered stale ingestion jobs count={}", recovered)
    active = find_active_ingestion_job(db, recover_stale=False)
    if active:
        logger.warning(
            "scheduler daily skipped because active job exists id={} type={} status={}",
            active.id,
            active.job_type,
            active.status,
        )
        return False
    CatchUpJob(db, provider).run(target_date)
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
