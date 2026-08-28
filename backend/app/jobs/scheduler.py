from datetime import date
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.jobs.daily_job import DailyJob
from app.providers.logging_provider import LoggingMarketDataProvider
from app.providers.tushare_provider import TushareProvider


def run_scheduler() -> None:
    settings = get_settings()
    scheduler = BlockingScheduler(timezone=ZoneInfo(settings.app_timezone))

    def run_daily() -> None:
        with SessionLocal() as db:
            provider = LoggingMarketDataProvider(db, TushareProvider())
            DailyJob(db, provider).run(date.today())

    cron = settings.app_config.get("app", {}).get("scheduler", {}).get(
        "daily_cron", "10 18 * * 1-5"
    )
    minute, hour, *_ = cron.split()
    scheduler.add_job(run_daily, "cron", hour=int(hour), minute=int(minute), id="daily_job")
    logger.info("scheduler started cron={}", cron)
    scheduler.start()
