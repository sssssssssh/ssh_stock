import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.performance_period import (
    PortfolioPerformancePeriod,
    PortfolioPerformancePeriodReport,
)
from app.services.performance.period_identity import performance_period_lock_key


class PerformancePeriodRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def lock_bundle(
        self, performance_id: uuid.UUID, risk_id: uuid.UUID, trade_id: uuid.UUID
    ) -> None:
        if self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(
                select(
                    func.pg_advisory_xact_lock(
                        performance_period_lock_key(performance_id, risk_id, trade_id)
                    )
                )
            ).scalar_one()

    def find_by_identity(
        self,
        *,
        performance_id: uuid.UUID,
        risk_id: uuid.UUID,
        trade_id: uuid.UUID,
        period_version: str,
        period_config_hash: str,
        period_source_hash: str,
    ) -> PortfolioPerformancePeriodReport | None:
        return self.db.scalar(
            select(PortfolioPerformancePeriodReport).where(
                PortfolioPerformancePeriodReport.performance_id == performance_id,
                PortfolioPerformancePeriodReport.risk_id == risk_id,
                PortfolioPerformancePeriodReport.trade_id == trade_id,
                PortfolioPerformancePeriodReport.period_version == period_version,
                PortfolioPerformancePeriodReport.period_config_hash == period_config_hash,
                PortfolioPerformancePeriodReport.period_source_hash == period_source_hash,
            )
        )

    def add(
        self,
        report: PortfolioPerformancePeriodReport,
        rows: list[PortfolioPerformancePeriod],
    ) -> None:
        self.db.add(report)
        self.db.flush()
        self.db.add_all(rows)
        self.db.flush()

    def latest_for_bundle(
        self, performance_id: uuid.UUID, risk_id: uuid.UUID, trade_id: uuid.UUID
    ) -> PortfolioPerformancePeriodReport | None:
        return self.db.scalar(
            select(PortfolioPerformancePeriodReport)
            .where(
                PortfolioPerformancePeriodReport.performance_id == performance_id,
                PortfolioPerformancePeriodReport.risk_id == risk_id,
                PortfolioPerformancePeriodReport.trade_id == trade_id,
            )
            .order_by(
                PortfolioPerformancePeriodReport.calculated_at.desc(),
                PortfolioPerformancePeriodReport.id.desc(),
            )
            .limit(1)
        )

    def list_rows(
        self,
        period_id: uuid.UUID,
        *,
        period_type: str | None,
        limit: int,
        offset: int,
        descending: bool = False,
    ) -> list[PortfolioPerformancePeriod]:
        statement = select(PortfolioPerformancePeriod).where(
            PortfolioPerformancePeriod.period_id == period_id
        )
        if period_type:
            statement = statement.where(PortfolioPerformancePeriod.period_type == period_type)
        order = (
            PortfolioPerformancePeriod.period_key.desc()
            if descending
            else PortfolioPerformancePeriod.period_key
        )
        return list(self.db.scalars(statement.order_by(order).limit(limit).offset(offset)).all())

    def count_rows(self, period_id: uuid.UUID, period_type: str | None) -> int:
        statement = (
            select(func.count())
            .select_from(PortfolioPerformancePeriod)
            .where(PortfolioPerformancePeriod.period_id == period_id)
        )
        if period_type:
            statement = statement.where(PortfolioPerformancePeriod.period_type == period_type)
        return int(self.db.scalar(statement) or 0)
