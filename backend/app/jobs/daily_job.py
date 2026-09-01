from datetime import date, timedelta

from loguru import logger
from sqlalchemy.orm import Session

from app.models.job import JobRun
from app.providers.base import MarketDataProvider
from app.repositories.job_run import start_job, update_job
from app.services.factors import FactorService
from app.services.ingestion import IngestionService
from app.services.market import MarketService
from app.services.quality.daily_quality import record_cross_table_quality
from app.services.sector import SectorService
from app.services.trend import TrendService


class DailyJob:
    def __init__(self, db: Session, provider: MarketDataProvider) -> None:
        self.db = db
        self.ingestion = IngestionService(db, provider)

    def run(self, trade_date: date, job: JobRun | None = None) -> None:
        job = job or start_job(self.db, "daily", trade_date)
        metadata = {"trade_date": trade_date.isoformat(), "stage_total": 12}
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
                step="30 sync daily",
                row_count=total_rows,
                metadata=_progress(metadata, 3),
            )
            total_rows += self.ingestion.sync_daily(trade_date, job_id=job.id)

            update_job(
                self.db,
                job,
                step="40 sync adj_factor",
                row_count=total_rows,
                metadata=_progress(metadata, 4),
            )
            total_rows += self.ingestion.sync_adj_factor(trade_date, job_id=job.id)

            update_job(
                self.db,
                job,
                step="50 sync daily_basic",
                row_count=total_rows,
                metadata=_progress(metadata, 5),
            )
            total_rows += self.ingestion.sync_daily_basic(trade_date, job_id=job.id)

            update_job(
                self.db,
                job,
                step="60 sync index_daily",
                row_count=total_rows,
                metadata=_progress(metadata, 6),
            )
            total_rows += self.ingestion.sync_index_daily(trade_date, job_id=job.id)

            update_job(
                self.db,
                job,
                step="70 sync sector metadata",
                row_count=total_rows,
                metadata=_progress(metadata, 7),
            )
            total_rows += self.ingestion.sync_sector_metadata()

            update_job(
                self.db,
                job,
                step="80 sync sector members",
                row_count=total_rows,
                metadata=_progress(metadata, 8),
            )
            total_rows += self.ingestion.sync_sector_members()

            update_job(
                self.db,
                job,
                step="90 calculate stock factors",
                row_count=total_rows,
                metadata=_progress(metadata, 9),
            )
            total_rows += FactorService(self.db).recalc(trade_date, trade_date, calc_run_id=job.id)

            update_job(
                self.db,
                job,
                step="100 calculate market score",
                row_count=total_rows,
                metadata=_progress(metadata, 10),
            )
            total_rows += MarketService(self.db).recalc(trade_date, trade_date, calc_run_id=job.id)

            update_job(
                self.db,
                job,
                step="110 calculate sector heat",
                row_count=total_rows,
                metadata=_progress(metadata, 11),
            )
            total_rows += SectorService(self.db).recalc(trade_date, trade_date, calc_run_id=job.id)

            update_job(
                self.db,
                job,
                step="120 calculate trend states",
                row_count=total_rows,
                metadata=_progress(metadata, 12),
            )
            trend_rows = TrendService(self.db).recalc(trade_date, trade_date)
            total_rows += trend_rows["states"] + trend_rows["signals"]
            record_cross_table_quality(self.db, trade_date, job_id=job.id)

            update_job(
                self.db,
                job,
                status="SUCCESS",
                step="180 mark SUCCESS",
                row_count=total_rows,
                metadata={**metadata, "stage_index": 12, "progress_pct": 100},
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
