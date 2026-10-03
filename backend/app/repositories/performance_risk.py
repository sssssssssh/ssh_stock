import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.performance_risk import (
    PortfolioPerformanceRiskDaily,
    PortfolioPerformanceRiskReport,
)
from app.services.performance.risk_identity import performance_risk_lock_key


class PerformanceRiskRepository:
    """Persistence-only repository for immutable risk artifacts."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def lock_performance(self, performance_id: uuid.UUID) -> None:
        if self.db.get_bind().dialect.name != "postgresql":
            return
        self.db.execute(
            select(
                func.pg_advisory_xact_lock(
                    performance_risk_lock_key(performance_id)
                )
            )
        ).scalar_one()

    def find_by_identity(
        self,
        *,
        performance_id: uuid.UUID,
        risk_version: str,
        risk_config_hash: str,
        benchmark_source_hash: str,
    ) -> PortfolioPerformanceRiskReport | None:
        return self.db.scalar(
            select(PortfolioPerformanceRiskReport).where(
                PortfolioPerformanceRiskReport.performance_id == performance_id,
                PortfolioPerformanceRiskReport.risk_version == risk_version,
                PortfolioPerformanceRiskReport.risk_config_hash == risk_config_hash,
                PortfolioPerformanceRiskReport.benchmark_source_hash
                == benchmark_source_hash,
            )
        )

    def add_report(
        self, report: PortfolioPerformanceRiskReport
    ) -> PortfolioPerformanceRiskReport:
        self.db.add(report)
        self.db.flush()
        return report

    def add_daily(self, rows: list[PortfolioPerformanceRiskDaily]) -> None:
        self.db.add_all(rows)
        self.db.flush()

    def latest_report(
        self, performance_id: uuid.UUID
    ) -> PortfolioPerformanceRiskReport | None:
        return self.db.scalar(
            select(PortfolioPerformanceRiskReport)
            .where(PortfolioPerformanceRiskReport.performance_id == performance_id)
            .order_by(
                PortfolioPerformanceRiskReport.calculated_at.desc(),
                PortfolioPerformanceRiskReport.id.desc(),
            )
            .limit(1)
        )

    def list_daily(
        self, risk_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[PortfolioPerformanceRiskDaily]:
        return list(
            self.db.scalars(
                select(PortfolioPerformanceRiskDaily)
                .where(PortfolioPerformanceRiskDaily.risk_id == risk_id)
                .order_by(PortfolioPerformanceRiskDaily.trade_date)
                .limit(limit)
                .offset(offset)
            ).all()
        )

    def count_daily(self, risk_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(PortfolioPerformanceRiskDaily)
                .where(PortfolioPerformanceRiskDaily.risk_id == risk_id)
            )
            or 0
        )
