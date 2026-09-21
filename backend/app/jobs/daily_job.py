from datetime import date, timedelta

from loguru import logger
from sqlalchemy.orm import Session

from app.core.clock import business_today
from app.core.config import get_settings
from app.models.job import JobRun
from app.providers.base import MarketDataProvider
from app.repositories.job_run import start_job, update_job
from app.services.factors import FactorService
from app.services.ingestion import IngestionService
from app.services.market import MarketService
from app.services.opportunity import OpportunityService
from app.services.quality.daily_quality import DataQualityError, record_cross_table_quality
from app.services.quality.raw_completeness import (
    RawCompletenessResult,
    check_raw_completeness,
    trade_calendar_open_status,
)
from app.services.sector import SectorService
from app.services.theme import ThemeFactorService
from app.services.trade_status import TradeStatusService
from app.services.trend import TrendService


class DailyJob:
    def __init__(self, db: Session, provider: MarketDataProvider) -> None:
        self.db = db
        self.ingestion = IngestionService(db, provider)

    def run(self, trade_date: date, job: JobRun | None = None) -> None:
        job = job or start_job(self.db, "daily", trade_date)
        metadata = {"trade_date": trade_date.isoformat(), "stage_total": 19}
        update_job(
            self.db,
            job,
            status="RUNNING",
            step="00 start daily",
            metadata={**metadata, "stage_index": 0, "progress_pct": 0},
        )
        total_rows = 0
        try:
            update_job(self.db, job, step="10 sync trade_calendar", metadata=_progress(metadata, 1))
            total_rows += self.ingestion.sync_trade_calendar(
                trade_date - timedelta(days=10), trade_date
            )
            is_open = trade_calendar_open_status(self.db, trade_date)
            if is_open is False:
                update_job(
                    self.db,
                    job,
                    status="SUCCESS",
                    step="180 no trading day",
                    row_count=total_rows,
                    metadata={**metadata, "stage_index": 1, "progress_pct": 100, "noop": True},
                )
                logger.info("daily job noop closed trade_date={} rows={}", trade_date, total_rows)
                return
            if is_open is None:
                raise ValueError(f"trade_calendar missing target date: {trade_date}")

            update_job(
                self.db,
                job,
                step="20 sync stock_basic",
                row_count=total_rows,
                metadata=_progress(metadata, 2),
            )
            total_rows += self.ingestion.sync_stock_basic()

            update_job(
                self.db,
                job,
                step="30 sync stock_st",
                row_count=total_rows,
                metadata=_progress(metadata, 3),
            )
            total_rows += self.ingestion.sync_stock_st(trade_date, job_id=job.id)

            update_job(
                self.db,
                job,
                step="35 sync suspend_d",
                row_count=total_rows,
                metadata=_progress(metadata, 4),
            )
            total_rows += self.ingestion.sync_suspend_daily(trade_date, job_id=job.id)

            update_job(
                self.db,
                job,
                step="40 sync daily",
                row_count=total_rows,
                metadata=_progress(metadata, 5),
            )
            total_rows += self.ingestion.sync_daily(trade_date, job_id=job.id)

            update_job(
                self.db,
                job,
                step="50 sync adj_factor",
                row_count=total_rows,
                metadata=_progress(metadata, 6),
            )
            total_rows += self.ingestion.sync_adj_factor(trade_date, job_id=job.id)

            update_job(
                self.db,
                job,
                step="55 sync daily_basic",
                row_count=total_rows,
                metadata=_progress(metadata, 7),
            )
            total_rows += self.ingestion.sync_daily_basic(trade_date, job_id=job.id)

            update_job(
                self.db,
                job,
                step="60 sync index_daily",
                row_count=total_rows,
                metadata=_progress(metadata, 8),
            )
            total_rows += self.ingestion.sync_index_daily(trade_date, job_id=job.id)

            update_job(
                self.db,
                job,
                step="66 sync stk_limit",
                row_count=total_rows,
                metadata=_progress(metadata, 9),
            )
            total_rows += self.ingestion.sync_stock_limit(trade_date, job_id=job.id)

            update_job(
                self.db,
                job,
                step="70 raw completeness gate",
                row_count=total_rows,
                metadata=_progress(metadata, 10),
            )
            raw_quality = check_raw_completeness(
                self.db,
                trade_date,
                strategy=get_settings().strategy,
                job_id=job.id,
                persist=True,
            )
            self.db.commit()
            metadata = {**metadata, **raw_quality.as_metadata()}
            if raw_quality.overall_status == "ERROR":
                raise DataQualityError(_raw_quality_error(raw_quality))

            update_job(
                self.db,
                job,
                step="72 sync theme raw",
                row_count=total_rows,
                metadata=_progress(metadata, 11),
            )
            try:
                total_rows += self.ingestion.sync_ths_themes(business_today())
                total_rows += self.ingestion.sync_theme_daily(trade_date)
                optional_status = self.ingestion.sync_theme_optional_sources(trade_date)
                metadata = {
                    **metadata,
                    "theme_sync_status": "PASS",
                    "theme_optional_status": optional_status,
                }
            except Exception as exc:
                self.db.rollback()
                metadata = {
                    **metadata,
                    "theme_sync_status": "ERROR",
                    "theme_sync_error": str(exc)[:1000],
                }
                logger.exception("theme raw sync failed; continuing core daily analysis")

            update_job(
                self.db,
                job,
                step="75 calculate trade status",
                row_count=total_rows,
                metadata=_progress(metadata, 12),
            )
            total_rows += TradeStatusService(self.db).recalc(
                trade_date,
                trade_date,
                calc_run_id=job.id,
            )

            update_job(
                self.db,
                job,
                step="80 calculate stock factors",
                row_count=total_rows,
                metadata=_progress(metadata, 13),
            )
            total_rows += FactorService(self.db).recalc(trade_date, trade_date, calc_run_id=job.id)

            update_job(
                self.db,
                job,
                step="90 calculate market score",
                row_count=total_rows,
                metadata=_progress(metadata, 14),
            )
            total_rows += MarketService(self.db).recalc(trade_date, trade_date, calc_run_id=job.id)

            update_job(
                self.db,
                job,
                step="100 calculate sector heat",
                row_count=total_rows,
                metadata=_progress(metadata, 15),
            )
            total_rows += SectorService(self.db).recalc(trade_date, trade_date, calc_run_id=job.id)

            update_job(
                self.db,
                job,
                step="105 calculate theme heat",
                row_count=total_rows,
                metadata=_progress(metadata, 16),
            )
            total_rows += ThemeFactorService(self.db).recalc(
                trade_date, trade_date, calc_run_id=job.id
            )

            update_job(
                self.db,
                job,
                step="110 calculate trend states",
                row_count=total_rows,
                metadata=_progress(metadata, 17),
            )
            trend_rows = TrendService(self.db).recalc(
                trade_date,
                trade_date,
                calc_run_id=job.id,
            )
            total_rows += trend_rows["states"] + trend_rows["signals"]
            update_job(
                self.db,
                job,
                step="120 calculate opportunities",
                row_count=total_rows,
                metadata=_progress(metadata, 18),
            )
            total_rows += OpportunityService(self.db).recalc(
                trade_date, trade_date, calc_run_id=job.id
            )
            quality = record_cross_table_quality(
                self.db,
                trade_date,
                job_id=job.id,
                strategy=get_settings().strategy,
            )
            self.db.commit()
            if quality.has_error:
                raise DataQualityError(
                    "cross table quality failed: "
                    f"trade_date={trade_date} datasets={quality.error_datasets}"
                )

            update_job(
                self.db,
                job,
                status="SUCCESS",
                step="180 mark SUCCESS",
                row_count=total_rows,
                metadata={**metadata, "stage_index": 19, "progress_pct": 100},
            )
            logger.info("daily job success trade_date={} rows={}", trade_date, total_rows)
        except Exception as exc:
            self.db.rollback()
            update_job(
                self.db,
                job,
                status="FAILED",
                row_count=total_rows,
                error_message=str(exc),
            )
            logger.exception("daily job failed trade_date={}", trade_date)
            raise


def _progress(metadata: dict[str, object], stage_index: int) -> dict[str, object]:
    stage_total = int(metadata["stage_total"])
    return {
        **metadata,
        "stage_index": stage_index,
        "progress_pct": round(stage_index / stage_total * 100, 1),
    }


def _raw_quality_error(raw_quality: RawCompletenessResult) -> str:
    dataset_summary = {
        name: {
            "status": dataset.status,
            "missing_count": len(getattr(dataset, "missing_codes", [])),
            "invalid_count": getattr(dataset, "invalid_count", 0),
        }
        for name, dataset in {
            "stock_daily": raw_quality.stock_daily,
            "adj_factor": raw_quality.adj_factor,
            "daily_basic": raw_quality.daily_basic,
            "index_daily": raw_quality.index_daily,
            "stock_st": raw_quality.stock_st,
            "suspend_d": raw_quality.suspend_d,
            "stk_limit": raw_quality.stk_limit,
        }.items()
        if dataset is not None
    }
    return (
        "raw completeness gate failed: "
        f"trade_date={raw_quality.trade_date} "
        f"overall_status={raw_quality.overall_status} "
        f"datasets={dataset_summary}"
    )
