import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.performance_trade import (
    PortfolioPerformanceTradeDaily,
    PortfolioPerformanceTradeEpisode,
    PortfolioPerformanceTradeReport,
)
from app.services.performance.trade_identity import performance_trade_lock_key


class PerformanceTradeRepository:
    """Persistence-only repository for immutable trade analytics artifacts."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def lock_performance(self, performance_id: uuid.UUID) -> None:
        if self.db.get_bind().dialect.name != "postgresql":
            return
        self.db.execute(
            select(func.pg_advisory_xact_lock(performance_trade_lock_key(performance_id)))
        ).scalar_one()

    def find_by_identity(
        self,
        *,
        performance_id: uuid.UUID,
        trade_version: str,
        trade_config_hash: str,
        trade_source_hash: str,
    ) -> PortfolioPerformanceTradeReport | None:
        return self.db.scalar(
            select(PortfolioPerformanceTradeReport).where(
                PortfolioPerformanceTradeReport.performance_id == performance_id,
                PortfolioPerformanceTradeReport.trade_version == trade_version,
                PortfolioPerformanceTradeReport.trade_config_hash == trade_config_hash,
                PortfolioPerformanceTradeReport.trade_source_hash == trade_source_hash,
            )
        )

    def add_report(
        self, report: PortfolioPerformanceTradeReport
    ) -> PortfolioPerformanceTradeReport:
        self.db.add(report)
        self.db.flush()
        return report

    def add_daily(self, rows: list[PortfolioPerformanceTradeDaily]) -> None:
        self.db.add_all(rows)
        self.db.flush()

    def add_episodes(self, rows: list[PortfolioPerformanceTradeEpisode]) -> None:
        self.db.add_all(rows)
        self.db.flush()

    def latest_report(self, performance_id: uuid.UUID) -> PortfolioPerformanceTradeReport | None:
        return self.db.scalar(
            select(PortfolioPerformanceTradeReport)
            .where(PortfolioPerformanceTradeReport.performance_id == performance_id)
            .order_by(
                PortfolioPerformanceTradeReport.calculated_at.desc(),
                PortfolioPerformanceTradeReport.id.desc(),
            )
            .limit(1)
        )

    def list_daily(
        self, trade_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[PortfolioPerformanceTradeDaily]:
        return list(
            self.db.scalars(
                select(PortfolioPerformanceTradeDaily)
                .where(PortfolioPerformanceTradeDaily.trade_id == trade_id)
                .order_by(PortfolioPerformanceTradeDaily.trade_date)
                .limit(limit)
                .offset(offset)
            ).all()
        )

    def count_daily(self, trade_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(PortfolioPerformanceTradeDaily)
                .where(PortfolioPerformanceTradeDaily.trade_id == trade_id)
            )
            or 0
        )

    def list_episodes(
        self,
        trade_id: uuid.UUID,
        *,
        status: str | None,
        ts_code: str | None,
        limit: int,
        offset: int,
        classification: str | None = None,
    ) -> list[PortfolioPerformanceTradeEpisode]:
        statement = select(PortfolioPerformanceTradeEpisode).where(
            PortfolioPerformanceTradeEpisode.trade_id == trade_id
        )
        if status is not None:
            statement = statement.where(PortfolioPerformanceTradeEpisode.status == status)
        if ts_code is not None:
            statement = statement.where(PortfolioPerformanceTradeEpisode.ts_code == ts_code)
        if classification is not None:
            statement = statement.where(
                PortfolioPerformanceTradeEpisode.classification == classification
            )
        return list(
            self.db.scalars(
                statement.order_by(
                    PortfolioPerformanceTradeEpisode.entry_date,
                    PortfolioPerformanceTradeEpisode.ts_code,
                    PortfolioPerformanceTradeEpisode.episode_no,
                )
                .limit(limit)
                .offset(offset)
            ).all()
        )

    def count_episodes(
        self,
        trade_id: uuid.UUID,
        *,
        status: str | None,
        ts_code: str | None,
        classification: str | None = None,
    ) -> int:
        statement = (
            select(func.count())
            .select_from(PortfolioPerformanceTradeEpisode)
            .where(PortfolioPerformanceTradeEpisode.trade_id == trade_id)
        )
        if status is not None:
            statement = statement.where(PortfolioPerformanceTradeEpisode.status == status)
        if ts_code is not None:
            statement = statement.where(PortfolioPerformanceTradeEpisode.ts_code == ts_code)
        if classification is not None:
            statement = statement.where(
                PortfolioPerformanceTradeEpisode.classification == classification
            )
        return int(self.db.scalar(statement) or 0)
