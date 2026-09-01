from datetime import date

from loguru import logger
from sqlalchemy.orm import Session

from app.models.job import JobRun
from app.models.market_data import TradeCalendar
from app.providers.base import MarketDataProvider
from app.repositories.job_run import start_job, update_job
from app.repositories.upsert import upsert_rows
from app.services.factors import FactorService
from app.services.ingestion import IngestionService
from app.services.ingestion.normalizers import normalize_trade_calendar
from app.services.market import MarketService
from app.services.quality.daily_quality import record_cross_table_quality
from app.services.sector import SectorService
from app.services.trend import TrendService


class BackfillJob:
    def __init__(self, db: Session, provider: MarketDataProvider) -> None:
        self.db = db
        self.provider = provider
        self.ingestion = IngestionService(db, provider)

    def run(self, start: date, end: date, job: JobRun | None = None) -> None:
        job = job or start_job(self.db, "backfill", end)
        metadata: dict[str, object] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "stage": "starting",
            "progress_pct": 0,
        }
        update_job(
            self.db,
            job,
            status="RUNNING",
            step="00 start backfill",
            metadata=metadata,
        )
        total_rows = 0
        try:
            update_job(
                self.db,
                job,
                step="10 sync trade_calendar",
                metadata={**metadata, "stage": "calendar", "progress_pct": 5},
            )
            calendar_df = self.provider.get_trade_calendar(start, end)
            calendar_rows = normalize_trade_calendar(calendar_df)
            total_rows += upsert_rows(self.db, TradeCalendar, calendar_rows, ["cal_date"])
            open_dates = [row["cal_date"] for row in calendar_rows if row["is_open"]]
            metadata = {
                **metadata,
                "open_days": len(open_dates),
                "completed_open_days": 0,
                "stage": "metadata",
                "progress_pct": 10,
            }

            update_job(
                self.db,
                job,
                step="20 sync stock_basic",
                row_count=total_rows,
                metadata=metadata,
            )
            total_rows += self.ingestion.sync_stock_basic()

            update_job(
                self.db,
                job,
                step="25 sync sector metadata",
                row_count=total_rows,
                metadata={**metadata, "progress_pct": 13},
            )
            total_rows += self.ingestion.sync_sector_metadata()

            update_job(
                self.db,
                job,
                step="26 sync sector members",
                row_count=total_rows,
                metadata={**metadata, "progress_pct": 16},
            )
            total_rows += self.ingestion.sync_sector_members()

            for index, current in enumerate(open_dates, 1):
                metadata = _daily_progress(metadata, current, index, len(open_dates))
                update_job(
                    self.db,
                    job,
                    step=f"30 sync daily {current}",
                    row_count=total_rows,
                    metadata=metadata,
                )
                total_rows += self.ingestion.sync_daily(current, job_id=job.id)
                total_rows += self.ingestion.sync_adj_factor(current, job_id=job.id)
                total_rows += self.ingestion.sync_daily_basic(current, job_id=job.id)
                total_rows += self.ingestion.sync_index_daily(current, job_id=job.id)
            metadata = {
                **metadata,
                "completed_open_days": len(open_dates),
                "current_open_day_index": len(open_dates),
            }

            update_job(
                self.db,
                job,
                step="90 calculate stock factors",
                row_count=total_rows,
                metadata={**metadata, "stage": "factors", "progress_pct": 75},
            )
            total_rows += FactorService(self.db).recalc(start, end, calc_run_id=job.id)

            update_job(
                self.db,
                job,
                step="100 calculate market score",
                row_count=total_rows,
                metadata={**metadata, "stage": "market", "progress_pct": 83},
            )
            total_rows += MarketService(self.db).recalc(start, end, calc_run_id=job.id)

            update_job(
                self.db,
                job,
                step="110 calculate sector heat",
                row_count=total_rows,
                metadata={**metadata, "stage": "sectors", "progress_pct": 90},
            )
            total_rows += SectorService(self.db).recalc(start, end, calc_run_id=job.id)

            update_job(
                self.db,
                job,
                step="120 calculate trend states",
                row_count=total_rows,
                metadata={**metadata, "stage": "states", "progress_pct": 96},
            )
            trend_rows = TrendService(self.db).recalc(start, end)
            total_rows += trend_rows["states"] + trend_rows["signals"]
            for current in open_dates:
                record_cross_table_quality(self.db, current, job_id=job.id)

            update_job(
                self.db,
                job,
                status="SUCCESS",
                step="180 mark SUCCESS",
                row_count=total_rows,
                metadata={
                    **metadata,
                    "completed_open_days": len(open_dates),
                    "stage": "success",
                    "progress_pct": 100,
                },
            )
            logger.info("backfill job success start={} end={} rows={}", start, end, total_rows)
        except Exception as exc:
            self.db.rollback()
            update_job(self.db, job, status="FAILED", row_count=total_rows, error_message=str(exc))
            logger.exception("backfill job failed start={} end={}", start, end)
            raise


def _daily_progress(
    metadata: dict[str, object],
    current: date,
    completed_open_days: int,
    open_days: int,
) -> dict[str, object]:
    daily_pct = completed_open_days / open_days if open_days else 1
    return {
        **metadata,
        "stage": "daily",
        "current_trade_date": current.isoformat(),
        "current_open_day_index": completed_open_days,
        "completed_open_days": max(0, completed_open_days - 1),
        "open_days": open_days,
        "progress_pct": round(16 + daily_pct * 59, 1),
    }
