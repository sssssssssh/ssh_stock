from loguru import logger
from sqlalchemy.orm import Session

from app.core.clock import business_today
from app.models.job import JobRun
from app.providers.base import MarketDataProvider
from app.repositories.job_run import start_job, update_job
from app.services.ingestion import IngestionService


class BasicInfoJob:
    def __init__(self, db: Session, provider: MarketDataProvider) -> None:
        self.db = db
        self.ingestion = IngestionService(db, provider)

    def run(self, job: JobRun | None = None, *, source: str = "manual") -> None:
        job = job or start_job(self.db, "sync_basic", None)
        metadata: dict[str, object] = {
            "source": source,
            "stage": "starting",
            "progress_pct": 0,
        }
        total_rows = 0
        update_job(
            self.db,
            job,
            status="RUNNING",
            step="00 start sync basic info",
            metadata=metadata,
        )
        try:
            update_job(
                self.db,
                job,
                step="20 sync stock_basic",
                row_count=total_rows,
                metadata={**metadata, "stage": "stock_basic", "progress_pct": 35},
            )
            total_rows += self.ingestion.sync_stock_basic()

            update_job(
                self.db,
                job,
                step="25 sync sector metadata",
                row_count=total_rows,
                metadata={**metadata, "stage": "sector_metadata", "progress_pct": 65},
            )
            total_rows += self.ingestion.sync_sector_metadata()

            update_job(
                self.db,
                job,
                step="26 sync sector members",
                row_count=total_rows,
                metadata={**metadata, "stage": "sector_members", "progress_pct": 85},
            )
            total_rows += self.ingestion.sync_sector_members()

            snapshot_date = business_today()
            update_job(
                self.db,
                job,
                step="27 sync THS theme catalog",
                row_count=total_rows,
                metadata={**metadata, "stage": "theme_catalog", "progress_pct": 90},
            )
            try:
                total_rows += self.ingestion.sync_ths_themes(snapshot_date)
                total_rows += self.ingestion.sync_ths_theme_member_snapshot(snapshot_date)
                metadata = {**metadata, "theme_sync_status": "PASS"}
            except Exception as exc:
                self.db.rollback()
                metadata = {
                    **metadata,
                    "theme_sync_status": "ERROR",
                    "theme_sync_error": str(exc)[:1000],
                }
                logger.exception(
                    "THS theme snapshot sync failed without rolling back core basic data"
                )

            update_job(
                self.db,
                job,
                status="SUCCESS",
                step="180 sync basic info complete",
                row_count=total_rows,
                metadata={**metadata, "stage": "success", "progress_pct": 100},
            )
            logger.info("sync basic info job success rows={}", total_rows)
        except Exception as exc:
            self.db.rollback()
            update_job(self.db, job, status="FAILED", row_count=total_rows, error_message=str(exc))
            logger.exception("sync basic info job failed")
            raise
