import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.performance import PortfolioPerformanceDaily
from app.models.performance_risk import PortfolioPerformanceRiskDaily
from app.services.performance.analytics_bundle import (
    AnalyticsArtifactBundleResolver,
)


class AnalyticsSeriesError(RuntimeError):
    code = "ANALYTICS_SERIES_DATE_MISMATCH"


class AnalyticsSeriesDTO(BaseModel):
    """Persisted performance/risk facts; no metric is recalculated here."""

    model_config = ConfigDict(extra="forbid")

    trade_date: date
    strategy_nav: Decimal
    strategy_daily_return: Decimal
    strategy_cumulative_return: Decimal
    drawdown: Decimal
    benchmark_nav: Decimal
    benchmark_daily_return: Decimal
    active_return: Decimal


class AnalyticsSeriesMetaDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: uuid.UUID
    performance_id: uuid.UUID
    risk_id: uuid.UUID
    trade_id: uuid.UUID
    period_id: uuid.UUID | None
    limit: int
    offset: int
    total: int


@dataclass(frozen=True)
class AnalyticsSeriesPage:
    rows: list[AnalyticsSeriesDTO]
    meta: AnalyticsSeriesMetaDTO


class AnalyticsSeriesReadApplicationService:
    def __init__(
        self,
        db: Session,
        *,
        resolver: AnalyticsArtifactBundleResolver | None = None,
    ) -> None:
        self.db = db
        self.resolver = resolver or AnalyticsArtifactBundleResolver(db)

    def page(
        self,
        run_id: uuid.UUID,
        *,
        performance_id: uuid.UUID,
        risk_id: uuid.UUID,
        trade_id: uuid.UUID | None,
        period_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> AnalyticsSeriesPage:
        bundle = self.resolver.resolve(
            run_id,
            performance_id=performance_id,
            risk_id=risk_id,
            trade_id=trade_id,
            period_id=period_id,
        )
        performance_total = self._count_performance(performance_id)
        risk_total = self._count_risk(risk_id)
        expected_total = bundle.performance.trade_days
        if (
            performance_total != expected_total
            or risk_total != expected_total
            or bundle.risk.trade_days != expected_total
        ):
            raise AnalyticsSeriesError(
                "performance and risk daily facts must exactly match artifact trade_days"
            )

        joined = list(
            self.db.execute(
                select(PortfolioPerformanceDaily, PortfolioPerformanceRiskDaily)
                .join(
                    PortfolioPerformanceRiskDaily,
                    and_(
                        PortfolioPerformanceRiskDaily.risk_id == risk_id,
                        PortfolioPerformanceRiskDaily.performance_id
                        == PortfolioPerformanceDaily.performance_id,
                        PortfolioPerformanceRiskDaily.trade_date
                        == PortfolioPerformanceDaily.trade_date,
                    ),
                )
                .where(PortfolioPerformanceDaily.performance_id == performance_id)
                .order_by(PortfolioPerformanceDaily.trade_date)
                .limit(limit)
                .offset(offset)
                .execution_options(populate_existing=True)
            ).all()
        )
        expected_page_size = max(0, min(limit, expected_total - offset))
        if len(joined) != expected_page_size:
            raise AnalyticsSeriesError(
                "performance and risk daily dates must match exactly"
            )
        rows = [
            AnalyticsSeriesDTO(
                trade_date=performance.trade_date,
                strategy_nav=performance.nav,
                strategy_daily_return=performance.daily_return,
                strategy_cumulative_return=performance.cumulative_return,
                drawdown=performance.drawdown,
                benchmark_nav=risk.benchmark_nav,
                benchmark_daily_return=risk.benchmark_daily_return,
                active_return=risk.active_return,
            )
            for performance, risk in joined
        ]
        return AnalyticsSeriesPage(
            rows=rows,
            meta=AnalyticsSeriesMetaDTO(
                run_id=run_id,
                performance_id=bundle.performance.id,
                risk_id=bundle.risk.id,
                trade_id=bundle.trade.id,
                period_id=bundle.period.id if bundle.period else None,
                limit=limit,
                offset=offset,
                total=expected_total,
            ),
        )

    def _count_performance(self, performance_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(PortfolioPerformanceDaily)
                .where(PortfolioPerformanceDaily.performance_id == performance_id)
            )
            or 0
        )

    def _count_risk(self, risk_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(PortfolioPerformanceRiskDaily)
                .where(PortfolioPerformanceRiskDaily.risk_id == risk_id)
            )
            or 0
        )
