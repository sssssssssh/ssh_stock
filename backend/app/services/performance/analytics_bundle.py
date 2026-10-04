import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.performance import PortfolioPerformanceReport
from app.models.performance_period import PortfolioPerformancePeriodReport
from app.models.performance_risk import PortfolioPerformanceRiskReport
from app.models.performance_trade import PortfolioPerformanceTradeReport
from app.models.portfolio import PortfolioBacktestRun


class AnalyticsBundleError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class AnalyticsArtifactBundle:
    run: PortfolioBacktestRun
    performance: PortfolioPerformanceReport
    risk: PortfolioPerformanceRiskReport
    trade: PortfolioPerformanceTradeReport
    period: PortfolioPerformancePeriodReport | None


class AnalyticsArtifactBundleResolver:
    def __init__(self, db: Session) -> None:
        self.db = db

    def resolve(
        self,
        run_id: uuid.UUID,
        *,
        performance_id: uuid.UUID | None = None,
        risk_id: uuid.UUID | None = None,
        trade_id: uuid.UUID | None = None,
        period_id: uuid.UUID | None = None,
        require_period: bool = False,
    ) -> AnalyticsArtifactBundle:
        run = self._fresh_one(PortfolioBacktestRun, run_id)
        if run is None or run.status != "SUCCESS" or run.account_mode != "BACKTEST":
            raise AnalyticsBundleError(
                "ANALYTICS_BASE_NOT_FOUND", "successful backtest run not found"
            )
        performance = (
            self._fresh_one(PortfolioPerformanceReport, performance_id)
            if performance_id
            else self.db.scalar(
                select(PortfolioPerformanceReport)
                .where(PortfolioPerformanceReport.run_id == run_id)
                .order_by(
                    PortfolioPerformanceReport.calculated_at.desc(),
                    PortfolioPerformanceReport.id.desc(),
                )
                .limit(1)
                .execution_options(populate_existing=True)
            )
        )
        if performance is None:
            raise AnalyticsBundleError(
                "ANALYTICS_ARTIFACT_BUNDLE_INCOMPLETE", "performance artifact is missing"
            )
        risk = (
            self._fresh_one(PortfolioPerformanceRiskReport, risk_id)
            if risk_id
            else self.db.scalar(
                select(PortfolioPerformanceRiskReport)
                .where(PortfolioPerformanceRiskReport.performance_id == performance.id)
                .order_by(
                    PortfolioPerformanceRiskReport.calculated_at.desc(),
                    PortfolioPerformanceRiskReport.id.desc(),
                )
                .limit(1)
                .execution_options(populate_existing=True)
            )
        )
        trade = (
            self._fresh_one(PortfolioPerformanceTradeReport, trade_id)
            if trade_id
            else self.db.scalar(
                select(PortfolioPerformanceTradeReport)
                .where(PortfolioPerformanceTradeReport.performance_id == performance.id)
                .order_by(
                    PortfolioPerformanceTradeReport.calculated_at.desc(),
                    PortfolioPerformanceTradeReport.id.desc(),
                )
                .limit(1)
                .execution_options(populate_existing=True)
            )
        )
        if risk is None or trade is None:
            missing = "risk" if risk is None else "trade"
            raise AnalyticsBundleError(
                "ANALYTICS_ARTIFACT_BUNDLE_INCOMPLETE", f"{missing} artifact is missing"
            )
        self._validate_owner(run_id, performance, risk, trade)
        period = (
            self._fresh_one(PortfolioPerformancePeriodReport, period_id)
            if period_id
            else self.db.scalar(
                select(PortfolioPerformancePeriodReport)
                .where(
                    PortfolioPerformancePeriodReport.performance_id == performance.id,
                    PortfolioPerformancePeriodReport.risk_id == risk.id,
                    PortfolioPerformancePeriodReport.trade_id == trade.id,
                )
                .order_by(
                    PortfolioPerformancePeriodReport.calculated_at.desc(),
                    PortfolioPerformancePeriodReport.id.desc(),
                )
                .limit(1)
                .execution_options(populate_existing=True)
            )
        )
        if period is not None and (
            period.run_id != run_id
            or period.performance_id != performance.id
            or period.risk_id != risk.id
            or period.trade_id != trade.id
        ):
            raise AnalyticsBundleError(
                "ANALYTICS_ARTIFACT_BUNDLE_MISMATCH",
                "period artifact does not belong to the selected bundle",
            )
        if require_period and period is None:
            raise AnalyticsBundleError(
                "ANALYTICS_ARTIFACT_BUNDLE_INCOMPLETE", "period artifact is missing"
            )
        return AnalyticsArtifactBundle(run, performance, risk, trade, period)

    def resolve_many(
        self,
        selections: list[
            tuple[
                uuid.UUID,
                uuid.UUID | None,
                uuid.UUID | None,
                uuid.UUID | None,
            ]
        ],
    ) -> list[AnalyticsArtifactBundle]:
        """Resolve Compare bundles in four fixed query groups while preserving input order."""
        run_ids = [item[0] for item in selections]
        runs = {
            row.id: row
            for row in self.db.scalars(
                select(PortfolioBacktestRun)
                .where(PortfolioBacktestRun.id.in_(run_ids))
                .execution_options(populate_existing=True)
            ).all()
        }
        if any(
            (run := runs.get(run_id)) is None
            or run.status != "SUCCESS"
            or run.account_mode != "BACKTEST"
            for run_id in run_ids
        ):
            raise AnalyticsBundleError(
                "ANALYTICS_BASE_NOT_FOUND", "successful backtest run not found"
            )

        explicit_performance_ids = [item[1] for item in selections if item[1] is not None]
        performance_rows = list(
            self.db.scalars(
                select(PortfolioPerformanceReport)
                .where(
                    or_(
                        PortfolioPerformanceReport.run_id.in_(run_ids),
                        PortfolioPerformanceReport.id.in_(explicit_performance_ids),
                    )
                )
                .order_by(
                    PortfolioPerformanceReport.calculated_at.desc(),
                    PortfolioPerformanceReport.id.desc(),
                )
                .execution_options(populate_existing=True)
            ).all()
        )
        performances_by_id = {row.id: row for row in performance_rows}
        latest_performance: dict[uuid.UUID, PortfolioPerformanceReport] = {}
        for row in performance_rows:
            latest_performance.setdefault(row.run_id, row)
        selected_performances: list[PortfolioPerformanceReport] = []
        for run_id, performance_id, _, _ in selections:
            performance = (
                performances_by_id.get(performance_id)
                if performance_id
                else latest_performance.get(run_id)
            )
            if performance is None:
                raise AnalyticsBundleError(
                    "ANALYTICS_ARTIFACT_BUNDLE_INCOMPLETE",
                    "performance artifact is missing",
                )
            if performance.run_id != run_id:
                raise AnalyticsBundleError(
                    "ANALYTICS_ARTIFACT_BUNDLE_MISMATCH",
                    "performance artifact belongs to another run",
                )
            selected_performances.append(performance)

        performance_ids = [row.id for row in selected_performances]
        explicit_risk_ids = [item[2] for item in selections if item[2] is not None]
        explicit_trade_ids = [item[3] for item in selections if item[3] is not None]
        risk_rows = list(
            self.db.scalars(
                select(PortfolioPerformanceRiskReport)
                .where(
                    or_(
                        PortfolioPerformanceRiskReport.performance_id.in_(performance_ids),
                        PortfolioPerformanceRiskReport.id.in_(explicit_risk_ids),
                    )
                )
                .order_by(
                    PortfolioPerformanceRiskReport.calculated_at.desc(),
                    PortfolioPerformanceRiskReport.id.desc(),
                )
                .execution_options(populate_existing=True)
            ).all()
        )
        trade_rows = list(
            self.db.scalars(
                select(PortfolioPerformanceTradeReport)
                .where(
                    or_(
                        PortfolioPerformanceTradeReport.performance_id.in_(performance_ids),
                        PortfolioPerformanceTradeReport.id.in_(explicit_trade_ids),
                    )
                )
                .order_by(
                    PortfolioPerformanceTradeReport.calculated_at.desc(),
                    PortfolioPerformanceTradeReport.id.desc(),
                )
                .execution_options(populate_existing=True)
            ).all()
        )
        risks_by_id = {row.id: row for row in risk_rows}
        trades_by_id = {row.id: row for row in trade_rows}
        latest_risk: dict[uuid.UUID, PortfolioPerformanceRiskReport] = {}
        latest_trade: dict[uuid.UUID, PortfolioPerformanceTradeReport] = {}
        for row in risk_rows:
            latest_risk.setdefault(row.performance_id, row)
        for row in trade_rows:
            latest_trade.setdefault(row.performance_id, row)

        bundles: list[AnalyticsArtifactBundle] = []
        for selection, performance in zip(selections, selected_performances, strict=True):
            run_id, _, risk_id, trade_id = selection
            risk = risks_by_id.get(risk_id) if risk_id else latest_risk.get(performance.id)
            trade = trades_by_id.get(trade_id) if trade_id else latest_trade.get(performance.id)
            if risk is None or trade is None:
                missing = "risk" if risk is None else "trade"
                raise AnalyticsBundleError(
                    "ANALYTICS_ARTIFACT_BUNDLE_INCOMPLETE", f"{missing} artifact is missing"
                )
            self._validate_owner(run_id, performance, risk, trade)
            bundles.append(
                AnalyticsArtifactBundle(runs[run_id], performance, risk, trade, None)
            )
        return bundles

    def _fresh_one(self, model, identity):
        if identity is None:
            return None
        return self.db.scalar(
            select(model)
            .where(model.id == identity)
            .execution_options(populate_existing=True)
        )

    @staticmethod
    def _validate_owner(run_id, performance, risk, trade) -> None:
        if (
            performance.run_id != run_id
            or risk.run_id != run_id
            or trade.run_id != run_id
            or risk.performance_id != performance.id
            or trade.performance_id != performance.id
        ):
            raise AnalyticsBundleError(
                "ANALYTICS_ARTIFACT_BUNDLE_MISMATCH",
                "performance, risk and trade artifacts do not share one owner",
            )
