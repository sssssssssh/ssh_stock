from datetime import date, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.jobs.research_job import RESEARCH_JOB_TYPE, queue_research_eval
from app.models.job import JobRun
from app.models.market_data import StockDaily, StockOpportunityDaily, StockStateDaily, TradeCalendar
from app.services.analysis_identity import (
    OPPORTUNITY_CALC_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.job_guard import (
    ActiveIngestionJobError,
    ResearchQueueConflictError,
    create_queued_ingestion_job,
    recover_stale_research_jobs,
    research_can_run,
)
from app.services.retention import run_retention


def run_scheduler() -> None:
    settings = get_settings()
    timezone = ZoneInfo(settings.app_timezone)
    scheduler = BlockingScheduler(timezone=timezone)

    def run_daily() -> None:
        with SessionLocal() as db:
            run_scheduled_catchup(db, None, _scheduler_today(timezone))

    def run_basic_info() -> None:
        with SessionLocal() as db:
            run_scheduled_basic_info(db, None)

    cron = (
        settings.app_config.get("app", {}).get("scheduler", {}).get("daily_cron", "10 18 * * 1-5")
    )
    scheduler.add_job(run_daily, "cron", id="daily_job", **cron_trigger_kwargs(cron))
    basic_cron = (
        settings.app_config.get("app", {}).get("scheduler", {}).get("basic_info_cron", "30 9 * * 6")
    )
    scheduler.add_job(
        run_basic_info,
        "cron",
        id="weekly_basic_refresh",
        **cron_trigger_kwargs(basic_cron),
    )

    def cleanup_retention() -> None:
        with SessionLocal() as db:
            logger.info("retention cleanup result={}", run_retention(db))

    scheduler.add_job(
        cleanup_retention,
        "cron",
        id="daily_retention",
        **cron_trigger_kwargs("15 3 * * *"),
    )
    research_runtime = settings.app_config.get("research", {})
    if research_runtime.get("enabled", False):
        research_cron = research_runtime.get("daily_cron", "30 19 * * 1-5")

        def run_research() -> None:
            with SessionLocal() as db:
                run_scheduled_research(db, _scheduler_today(timezone))

        scheduler.add_job(
            run_research,
            "cron",
            id="daily_research_refresh",
            **cron_trigger_kwargs(research_cron),
        )
    logger.info("scheduler started daily_cron={} basic_info_cron={}", cron, basic_cron)
    scheduler.start()


def run_scheduled_catchup(db, provider: object | None, target_date: date) -> bool:
    try:
        create_queued_ingestion_job(
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
    return True


def run_scheduled_basic_info(db, provider: object | None) -> bool:
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


def run_scheduled_research(db, target_date: date) -> bool:
    recover_stale_research_jobs(db)
    if not research_can_run(db):
        return False
    active = db.scalar(
        select(func.count())
        .select_from(JobRun)
        .where(
            JobRun.job_type == RESEARCH_JOB_TYPE,
            JobRun.status.in_(("QUEUED", "RUNNING")),
        )
    )
    if active:
        return False
    expected_latest = db.scalar(
        select(func.max(TradeCalendar.cal_date)).where(
            TradeCalendar.is_open.is_(True), TradeCalendar.cal_date <= target_date
        )
    )
    if expected_latest is None:
        return False
    settings = get_settings()
    latest_raw = db.scalar(
        select(func.max(StockDaily.trade_date)).where(StockDaily.trade_date <= target_date)
    )
    strategy_hash = analysis_strategy_hash(settings.strategy)
    opportunity_hash = config_hash(settings.opportunity_config)
    latest_state = db.scalar(
        select(func.max(StockStateDaily.trade_date)).where(
            StockStateDaily.algo_version == settings.algo_version,
            StockStateDaily.calc_version == TREND_CALC_VERSION,
            StockStateDaily.config_hash == strategy_hash,
        )
    )
    latest_opportunity = db.scalar(
        select(func.max(StockOpportunityDaily.trade_date)).where(
            StockOpportunityDaily.algo_version == settings.algo_version,
            StockOpportunityDaily.calc_version == OPPORTUNITY_CALC_VERSION,
            StockOpportunityDaily.config_hash == opportunity_hash,
        )
    )
    if not _research_sources_current(
        expected_latest, latest_raw, latest_state, latest_opportunity
    ):
        logger.warning(
            "RESEARCH_SOURCE_STALE expected={} raw={} state={} opportunity={}",
            expected_latest,
            latest_raw,
            latest_state,
            latest_opportunity,
        )
        return False
    open_dates = (
        db.execute(
            select(TradeCalendar.cal_date)
            .where(
                TradeCalendar.is_open.is_(True),
                TradeCalendar.cal_date <= latest_raw,
            )
            .order_by(TradeCalendar.cal_date.desc())
            .limit(settings.research_config["refresh_lookback_trade_days"] + 1)
        )
        .scalars()
        .all()
    )
    if not open_dates:
        return False
    try:
        queue_research_eval(db, open_dates[-1], open_dates[0], mode="scheduler")
    except ResearchQueueConflictError:
        return False
    return True


def _research_sources_current(
    expected_latest: date,
    latest_raw: date | None,
    latest_state: date | None,
    latest_opportunity: date | None,
) -> bool:
    return all(
        source_date is not None and source_date >= expected_latest
        for source_date in (latest_raw, latest_state, latest_opportunity)
    )


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
