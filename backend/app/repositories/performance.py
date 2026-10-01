import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.performance import PortfolioPerformanceDaily, PortfolioPerformanceReport


class PerformanceRepository:
    """Persistence-only repository; calculations belong to the domain engine."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def lock_run_calculation(self, run_id: uuid.UUID) -> None:
        """Serialize same-run calculations without locking or updating M13 rows."""
        self.db.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(str(run_id), 0)
                )
            )
        )

    def find_by_identity(
        self,
        *,
        run_id: uuid.UUID,
        performance_version: str,
        performance_config_hash: str,
        source_hash: str,
    ) -> PortfolioPerformanceReport | None:
        return self.db.scalar(
            select(PortfolioPerformanceReport).where(
                PortfolioPerformanceReport.run_id == run_id,
                PortfolioPerformanceReport.performance_version == performance_version,
                PortfolioPerformanceReport.performance_config_hash
                == performance_config_hash,
                PortfolioPerformanceReport.source_hash == source_hash,
            )
        )

    def add_report(
        self, report: PortfolioPerformanceReport
    ) -> PortfolioPerformanceReport:
        self.db.add(report)
        self.db.flush()

        return report

    def add_daily(self, daily: list[PortfolioPerformanceDaily]) -> None:
        self.db.add_all(daily)
        self.db.flush()

    def latest_report(self, run_id: uuid.UUID) -> PortfolioPerformanceReport | None:
        return self.db.scalar(
            select(PortfolioPerformanceReport)
            .where(PortfolioPerformanceReport.run_id == run_id)
            .order_by(
                PortfolioPerformanceReport.calculated_at.desc(),
                PortfolioPerformanceReport.id.desc(),
            )
            .limit(1)
        )

    def list_daily(
        self, performance_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[PortfolioPerformanceDaily]:
        return list(
            self.db.scalars(
                select(PortfolioPerformanceDaily)
                .where(PortfolioPerformanceDaily.performance_id == performance_id)
                .order_by(PortfolioPerformanceDaily.trade_date)
                .limit(limit)
                .offset(offset)
            ).all()
        )

    def count_daily(self, performance_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(PortfolioPerformanceDaily).where(
                    PortfolioPerformanceDaily.performance_id == performance_id
                )
            )
            or 0
        )
