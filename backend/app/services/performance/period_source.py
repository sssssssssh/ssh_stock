from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.performance.period_contracts import (
    PeriodSourceDaily,
    PeriodSourceEpisode,
    PeriodSourceSnapshot,
)
from app.models.performance import PortfolioPerformanceDaily
from app.models.performance_risk import PortfolioPerformanceRiskDaily
from app.models.performance_trade import (
    PortfolioPerformanceTradeDaily,
    PortfolioPerformanceTradeEpisode,
)
from app.services.performance.analytics_bundle import AnalyticsArtifactBundle
from app.services.performance.period_identity import period_source_hash


class PerformancePeriodSourceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class PerformancePeriodSourceProvider:
    def __init__(self, db: Session) -> None:
        self.db = db

    def load(
        self,
        bundle: AnalyticsArtifactBundle,
        *,
        period_version: str,
        period_config_hash: str,
    ) -> PeriodSourceSnapshot:
        performance_rows = tuple(
            self.db.scalars(
                select(PortfolioPerformanceDaily)
                .where(PortfolioPerformanceDaily.performance_id == bundle.performance.id)
                .order_by(PortfolioPerformanceDaily.trade_date)
                .execution_options(populate_existing=True)
            ).all()
        )
        risk_rows = tuple(
            self.db.scalars(
                select(PortfolioPerformanceRiskDaily)
                .where(PortfolioPerformanceRiskDaily.risk_id == bundle.risk.id)
                .order_by(PortfolioPerformanceRiskDaily.trade_date)
                .execution_options(populate_existing=True)
            ).all()
        )
        trade_rows = tuple(
            self.db.scalars(
                select(PortfolioPerformanceTradeDaily)
                .where(PortfolioPerformanceTradeDaily.trade_id == bundle.trade.id)
                .order_by(PortfolioPerformanceTradeDaily.trade_date)
                .execution_options(populate_existing=True)
            ).all()
        )
        date_sets = (
            tuple(row.trade_date for row in performance_rows),
            tuple(row.trade_date for row in risk_rows),
            tuple(row.trade_date for row in trade_rows),
        )
        expected = bundle.performance.trade_days
        if (
            date_sets[0] != date_sets[1]
            or date_sets[0] != date_sets[2]
            or len(date_sets[0]) != expected
            or bundle.risk.trade_days != expected
            or bundle.trade.trade_days != expected
            or not date_sets[0]
        ):
            raise PerformancePeriodSourceError(
                "PERIOD_SOURCE_DATE_MISMATCH",
                "performance, risk and trade daily dates must match exactly",
            )
        episodes = tuple(
            self.db.scalars(
                select(PortfolioPerformanceTradeEpisode)
                .where(
                    PortfolioPerformanceTradeEpisode.trade_id == bundle.trade.id,
                    PortfolioPerformanceTradeEpisode.status == "CLOSED",
                )
                .order_by(
                    PortfolioPerformanceTradeEpisode.exit_date,
                    PortfolioPerformanceTradeEpisode.ts_code,
                    PortfolioPerformanceTradeEpisode.episode_no,
                )
                .execution_options(populate_existing=True)
            ).all()
        )
        source = PeriodSourceSnapshot(
            run_id=bundle.run.id,
            performance_id=bundle.performance.id,
            risk_id=bundle.risk.id,
            trade_id=bundle.trade.id,
            performance_version=bundle.performance.performance_version,
            performance_config_hash=bundle.performance.performance_config_hash,
            performance_source_hash=bundle.performance.source_hash,
            risk_version=bundle.risk.risk_version,
            risk_config_hash=bundle.risk.risk_config_hash,
            risk_source_hash=bundle.risk.risk_source_hash,
            benchmark_source_hash=bundle.risk.benchmark_source_hash,
            trade_version=bundle.trade.trade_version,
            trade_config_hash=bundle.trade.trade_config_hash,
            trade_source_hash=bundle.trade.trade_source_hash,
            period_version=period_version,
            period_config_hash=period_config_hash,
            period_source_hash="",
            start_date=bundle.performance.start_date,
            end_date=bundle.performance.end_date,
            trade_days=expected,
            daily=tuple(
                PeriodSourceDaily(
                    trade_date=performance.trade_date,
                    strategy_daily_return=performance.daily_return,
                    benchmark_daily_return=risk.benchmark_daily_return,
                    daily_turnover=trade.daily_turnover,
                    traded_gross_amount=trade.traded_gross_amount,
                    commission=trade.commission,
                    stamp_tax=trade.stamp_tax,
                    transfer_fee=trade.transfer_fee,
                    cash_fee_total=trade.cash_fee_total,
                    slippage_cost=trade.slippage_cost,
                    total_execution_cost=trade.total_execution_cost,
                )
                for performance, risk, trade in zip(
                    performance_rows, risk_rows, trade_rows, strict=True
                )
            ),
            closed_episodes=tuple(
                PeriodSourceEpisode(
                    exit_date=row.exit_date,
                    classification=row.classification,
                    realized_pnl=row.realized_pnl,
                )
                for row in episodes
                if row.exit_date is not None and row.classification is not None
            ),
        )
        return replace(source, period_source_hash=period_source_hash(source))
