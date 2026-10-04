import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.performance_period_config import ANALYTICS_READ_SCHEMA_VERSION
from app.models.performance import PortfolioPerformanceReport
from app.models.performance_period import (
    PortfolioPerformancePeriod,
    PortfolioPerformancePeriodReport,
)
from app.models.performance_risk import PortfolioPerformanceRiskReport
from app.models.performance_trade import PortfolioPerformanceTradeReport
from app.models.portfolio import PortfolioBacktestRun
from app.services.performance.analytics_bundle import (
    AnalyticsArtifactBundle,
    AnalyticsArtifactBundleResolver,
    AnalyticsBundleError,
)


class AnalyticsDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalyticsIdentityDTO(AnalyticsDTO):
    run_id: uuid.UUID
    performance_id: uuid.UUID
    risk_id: uuid.UUID
    trade_id: uuid.UUID
    period_id: uuid.UUID | None


class AnalyticsBacktestDTO(AnalyticsDTO):
    name: str | None
    status: str
    start_date: date
    end_date: date
    initial_cash: Decimal
    benchmark_code: str


class AnalyticsPerformanceDTO(AnalyticsDTO):
    cumulative_return: Decimal
    annualized_return: Decimal
    max_drawdown: Decimal
    max_drawdown_peak_date: date | None
    max_drawdown_trough_date: date | None
    max_drawdown_recovery_date: date | None
    trade_days: int


class AnalyticsRiskDTO(AnalyticsDTO):
    benchmark_code: str
    benchmark_cumulative_return: Decimal
    benchmark_annualized_return: Decimal
    excess_cumulative_return: Decimal
    strategy_annualized_volatility: Decimal | None
    sharpe_ratio: Decimal | None
    sortino_ratio: Decimal | None
    calmar_ratio: Decimal | None
    tracking_error: Decimal | None
    information_ratio: Decimal | None
    alpha_annualized: Decimal | None
    beta: Decimal | None
    correlation: Decimal | None


class AnalyticsTradeDTO(AnalyticsDTO):
    total_turnover: Decimal
    annualized_turnover: Decimal
    traded_gross_amount: Decimal
    cash_fee_total: Decimal
    slippage_cost_total: Decimal
    total_execution_cost: Decimal
    total_cost_to_initial_capital: Decimal
    closed_episode_count: int
    open_episode_count: int
    win_rate: Decimal | None
    profit_factor: Decimal | None
    payoff_ratio: Decimal | None
    average_holding_trade_days: Decimal | None
    median_holding_trade_days: Decimal | None
    closed_realized_pnl: Decimal


class AnalyticsPeriodDTO(AnalyticsDTO):
    period_type: str
    period_key: str
    period_start_date: date
    period_end_date: date
    trade_days: int
    strategy_return: Decimal
    benchmark_return: Decimal
    relative_return: Decimal
    return_spread: Decimal
    period_turnover: Decimal
    total_execution_cost: Decimal
    closed_episode_count: int
    win_rate: Decimal | None
    closed_realized_pnl: Decimal


class AnalyticsSummaryDTO(AnalyticsDTO):
    schema_version: str
    identity: AnalyticsIdentityDTO
    backtest: AnalyticsBacktestDTO
    performance: AnalyticsPerformanceDTO
    risk: AnalyticsRiskDTO
    trade: AnalyticsTradeDTO
    warnings: list[str]
    source_versions: dict[str, str]


class AnalyticsContextDTO(AnalyticsSummaryDTO):
    month_periods: list[AnalyticsPeriodDTO]
    year_periods: list[AnalyticsPeriodDTO]


class AnalyticsReadApplicationService:
    def __init__(
        self, db: Session, *, resolver: AnalyticsArtifactBundleResolver | None = None
    ) -> None:
        self.db = db
        self.resolver = resolver or AnalyticsArtifactBundleResolver(db)

    def summary(
        self,
        run_id: uuid.UUID,
        *,
        performance_id: uuid.UUID | None = None,
        risk_id: uuid.UUID | None = None,
        trade_id: uuid.UUID | None = None,
        period_id: uuid.UUID | None = None,
    ) -> AnalyticsSummaryDTO:
        bundle = self.resolver.resolve(
            run_id,
            performance_id=performance_id,
            risk_id=risk_id,
            trade_id=trade_id,
            period_id=period_id,
        )
        return self._summary(bundle)

    def context(
        self,
        run_id: uuid.UUID,
        *,
        performance_id: uuid.UUID | None = None,
        risk_id: uuid.UUID | None = None,
        trade_id: uuid.UUID | None = None,
        period_id: uuid.UUID | None = None,
    ) -> AnalyticsContextDTO:
        bundle = self.resolver.resolve(
            run_id,
            performance_id=performance_id,
            risk_id=risk_id,
            trade_id=trade_id,
            period_id=period_id,
        )
        summary = self._summary(bundle)
        months: list[PortfolioPerformancePeriod] = []
        years: list[PortfolioPerformancePeriod] = []
        if bundle.period:
            months = list(
                reversed(
                    self.db.scalars(
                        select(PortfolioPerformancePeriod)
                        .where(
                            PortfolioPerformancePeriod.period_id == bundle.period.id,
                            PortfolioPerformancePeriod.period_type == "MONTH",
                        )
                        .order_by(PortfolioPerformancePeriod.period_key.desc())
                        .limit(12)
                        .execution_options(populate_existing=True)
                    ).all()
                )
            )
            years = list(
                self.db.scalars(
                    select(PortfolioPerformancePeriod)
                    .where(
                        PortfolioPerformancePeriod.period_id == bundle.period.id,
                        PortfolioPerformancePeriod.period_type == "YEAR",
                    )
                    .order_by(PortfolioPerformancePeriod.period_key)
                    .execution_options(populate_existing=True)
                ).all()
            )
        return AnalyticsContextDTO(
            **summary.model_dump(),
            month_periods=[self._period(row) for row in months],
            year_periods=[self._period(row) for row in years],
        )

    def history(self, run_id: uuid.UUID) -> dict[str, Any]:
        run = self.db.scalar(
            select(PortfolioBacktestRun)
            .where(PortfolioBacktestRun.id == run_id)
            .execution_options(populate_existing=True)
        )
        if run is None or run.status != "SUCCESS" or run.account_mode != "BACKTEST":
            raise AnalyticsBundleError(
                "ANALYTICS_BASE_NOT_FOUND", "successful backtest run not found"
            )
        performances = list(
            self.db.scalars(
                select(PortfolioPerformanceReport)
                .where(PortfolioPerformanceReport.run_id == run_id)
                .order_by(
                    PortfolioPerformanceReport.calculated_at.desc(),
                    PortfolioPerformanceReport.id.desc(),
                )
                .execution_options(populate_existing=True)
            ).all()
        )
        performance_ids = [row.id for row in performances]
        risks = list(
            self.db.scalars(
                select(PortfolioPerformanceRiskReport)
                .where(PortfolioPerformanceRiskReport.performance_id.in_(performance_ids))
                .order_by(
                    PortfolioPerformanceRiskReport.calculated_at.desc(),
                    PortfolioPerformanceRiskReport.id.desc(),
                )
                .execution_options(populate_existing=True)
            ).all()
        )
        trades = list(
            self.db.scalars(
                select(PortfolioPerformanceTradeReport)
                .where(PortfolioPerformanceTradeReport.performance_id.in_(performance_ids))
                .order_by(
                    PortfolioPerformanceTradeReport.calculated_at.desc(),
                    PortfolioPerformanceTradeReport.id.desc(),
                )
                .execution_options(populate_existing=True)
            ).all()
        )
        periods = list(
            self.db.scalars(
                select(PortfolioPerformancePeriodReport)
                .where(PortfolioPerformancePeriodReport.run_id == run_id)
                .order_by(
                    PortfolioPerformancePeriodReport.calculated_at.desc(),
                    PortfolioPerformancePeriodReport.id.desc(),
                )
                .execution_options(populate_existing=True)
            ).all()
        )
        return {
            "schema_version": ANALYTICS_READ_SCHEMA_VERSION,
            "run_id": str(run_id),
            "performance": [
                self._history_item(
                    row.id,
                    row.performance_version,
                    row.performance_config_hash,
                    row.source_hash,
                    row.calculated_at,
                    {},
                )
                for row in performances
            ],
            "risk": [
                self._history_item(
                    row.id,
                    row.risk_version,
                    row.risk_config_hash,
                    row.risk_source_hash,
                    row.calculated_at,
                    {"performance_id": str(row.performance_id)},
                )
                for row in risks
            ],
            "trade": [
                self._history_item(
                    row.id,
                    row.trade_version,
                    row.trade_config_hash,
                    row.trade_source_hash,
                    row.calculated_at,
                    {"performance_id": str(row.performance_id)},
                )
                for row in trades
            ],
            "period": [
                self._history_item(
                    row.id,
                    row.period_version,
                    row.period_config_hash,
                    row.period_source_hash,
                    row.calculated_at,
                    {
                        "performance_id": str(row.performance_id),
                        "risk_id": str(row.risk_id),
                        "trade_id": str(row.trade_id),
                    },
                )
                for row in periods
            ],
        }

    @staticmethod
    def _summary(bundle: AnalyticsArtifactBundle) -> AnalyticsSummaryDTO:
        performance, risk, trade = bundle.performance, bundle.risk, bundle.trade
        return AnalyticsSummaryDTO(
            schema_version=ANALYTICS_READ_SCHEMA_VERSION,
            identity=AnalyticsIdentityDTO(
                run_id=bundle.run.id,
                performance_id=performance.id,
                risk_id=risk.id,
                trade_id=trade.id,
                period_id=bundle.period.id if bundle.period else None,
            ),
            backtest=AnalyticsBacktestDTO(
                name=bundle.run.name,
                status=bundle.run.status,
                start_date=bundle.run.start_date,
                end_date=bundle.run.end_date,
                initial_cash=bundle.run.initial_cash,
                benchmark_code=bundle.run.benchmark_code,
            ),
            performance=AnalyticsPerformanceDTO(
                cumulative_return=performance.cumulative_return,
                annualized_return=performance.annualized_return,
                max_drawdown=performance.max_drawdown,
                max_drawdown_peak_date=performance.max_drawdown_peak_date,
                max_drawdown_trough_date=performance.max_drawdown_trough_date,
                max_drawdown_recovery_date=performance.max_drawdown_recovery_date,
                trade_days=performance.trade_days,
            ),
            risk=AnalyticsRiskDTO(
                benchmark_code=risk.benchmark_code,
                benchmark_cumulative_return=risk.benchmark_cumulative_return,
                benchmark_annualized_return=risk.benchmark_annualized_return,
                excess_cumulative_return=risk.excess_cumulative_return,
                strategy_annualized_volatility=risk.strategy_annualized_volatility,
                sharpe_ratio=risk.sharpe_ratio,
                sortino_ratio=risk.sortino_ratio,
                calmar_ratio=risk.calmar_ratio,
                tracking_error=risk.tracking_error,
                information_ratio=risk.information_ratio,
                alpha_annualized=risk.alpha_annualized,
                beta=risk.beta,
                correlation=risk.correlation,
            ),
            trade=AnalyticsTradeDTO(
                total_turnover=trade.total_turnover,
                annualized_turnover=trade.annualized_turnover,
                traded_gross_amount=trade.traded_gross_amount,
                cash_fee_total=trade.cash_fee_total,
                slippage_cost_total=trade.slippage_cost_total,
                total_execution_cost=trade.total_execution_cost,
                total_cost_to_initial_capital=trade.total_cost_to_initial_capital,
                closed_episode_count=trade.closed_episode_count,
                open_episode_count=trade.open_episode_count,
                win_rate=trade.win_rate,
                profit_factor=trade.profit_factor,
                payoff_ratio=trade.payoff_ratio,
                average_holding_trade_days=trade.average_holding_trade_days,
                median_holding_trade_days=trade.median_holding_trade_days,
                closed_realized_pnl=trade.closed_realized_pnl,
            ),
            warnings=sorted(
                set(performance.warnings) | set(risk.warnings) | set(trade.warnings)
            ),
            source_versions={
                "performance": performance.performance_version,
                "risk": risk.risk_version,
                "trade": trade.trade_version,
                "period": bundle.period.period_version if bundle.period else "NOT_CALCULATED",
            },
        )

    @staticmethod
    def _period(row: PortfolioPerformancePeriod) -> AnalyticsPeriodDTO:
        return AnalyticsPeriodDTO(
            **{
                field: getattr(row, field)
                for field in AnalyticsPeriodDTO.model_fields
            }
        )

    @staticmethod
    def _history_item(
        identity: uuid.UUID,
        version: str,
        config_hash: str,
        source_hash: str,
        calculated_at: datetime,
        upstream: dict[str, str],
    ) -> dict[str, Any]:
        return {
            "id": str(identity),
            "version": version,
            "config_hash": config_hash,
            "source_hash": source_hash,
            "calculated_at": calculated_at.isoformat(),
            **upstream,
        }
