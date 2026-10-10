from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.domain.agent.contracts import (
    AgentToolResult,
    BacktestSummaryInput,
    PerformanceSummaryInput,
    Readiness,
    WalkForwardSummaryInput,
)
from app.domain.agent.errors import identity_mismatch, invalid_argument, not_found, not_ready
from app.models.performance import PortfolioPerformanceReport
from app.models.performance_period import PortfolioPerformancePeriodReport
from app.models.performance_risk import PortfolioPerformanceRiskReport
from app.models.performance_trade import PortfolioPerformanceTradeReport
from app.models.portfolio import PortfolioBacktestRun, PortfolioNavDaily
from app.models.walk_forward import (
    PortfolioWalkForwardStudy,
    PortfolioWalkForwardValidationReport,
)
from app.services.agent.evidence import evidence_ref


class ResearchAgentAdapter:
    def __init__(self, db: Session) -> None:
        self.db = db

    def backtest_summary(self, request: BacktestSummaryInput) -> AgentToolResult:
        run = self.db.get(PortfolioBacktestRun, request.run_id)
        if run is None:
            raise not_found("backtest run not found")
        if run.account_mode != "BACKTEST" or run.status != "SUCCESS":
            raise not_ready("RUN_NOT_READY: backtest run is not successful")
        nav = self.db.scalar(
            select(PortfolioNavDaily)
            .where(PortfolioNavDaily.run_id == run.id)
            .order_by(desc(PortfolioNavDaily.trade_date))
            .limit(1)
        )
        if nav is None:
            raise not_ready("RUN_NOT_READY: backtest NAV is unavailable")
        warnings: list[str] = []
        record = {
            "run_id": run.id,
            "status": run.status,
            "start_date": run.start_date,
            "end_date": run.end_date,
            "initial_cash": run.initial_cash,
            "latest_nav_date": nav.trade_date,
            "latest_nav": nav.nav,
            "latest_total_assets": nav.total_assets,
            "result_summary": run.result_summary,
            "source_identity": _run_identity(run),
        }
        return AgentToolResult(
            tool_name="backtest.summary",
            status="READY",
            as_of_date=nav.trade_date,
            identity=_run_identity(run),
            records=[record],
            evidence=[
                evidence_ref(
                    layer="STRATEGY_VALIDATION",
                    source_type="derived_record",
                    entity_id=str(run.id),
                    date_value=nav.trade_date,
                    source_record_id=str(run.id),
                    algo_version=run.algo_version,
                    config_hash=run.portfolio_config_hash,
                    observed_at=run.finished_at,
                    quality_status="PASS",
                    limitations=warnings,
                )
            ],
            warnings=warnings,
            readiness=Readiness(ready=True, code="READY"),
        )

    def performance_summary(self, request: PerformanceSummaryInput) -> AgentToolResult:
        performance = self._performance_report(request)
        if performance.status != "SUCCESS":
            raise not_ready("ANALYTICS_NOT_READY: performance report is not successful")
        run = self.db.get(PortfolioBacktestRun, performance.run_id)
        if run is None or run.status != "SUCCESS" or run.account_mode != "BACKTEST":
            raise identity_mismatch("performance report owner is unavailable or not a backtest")
        risk = self._one_bundle_row(
            PortfolioPerformanceRiskReport,
            PortfolioPerformanceRiskReport.performance_id == performance.id,
            "risk",
        )
        trade = self._one_bundle_row(
            PortfolioPerformanceTradeReport,
            PortfolioPerformanceTradeReport.performance_id == performance.id,
            "trade",
        )
        if risk.run_id != run.id or trade.run_id != run.id:
            raise identity_mismatch("analytics reports do not share the same run identity")
        periods = list(
            self.db.scalars(
                select(PortfolioPerformancePeriodReport)
                .where(
                    PortfolioPerformancePeriodReport.performance_id == performance.id,
                    PortfolioPerformancePeriodReport.risk_id == risk.id,
                    PortfolioPerformancePeriodReport.trade_id == trade.id,
                )
                .limit(2)
            ).all()
        )
        if len(periods) > 1:
            raise identity_mismatch("multiple period reports match the analytics bundle")
        period = periods[0] if periods else None
        warnings = list(performance.warnings or [])
        warnings.extend(risk.warnings or [])
        warnings.extend(trade.warnings or [])
        if period is None:
            warnings.append("DATA_UNAVAILABLE:period_report")
        else:
            warnings.extend(period.warnings or [])
        identity = {
            "run_id": run.id,
            "performance_id": performance.id,
            "risk_id": risk.id,
            "trade_id": trade.id,
            "period_id": period.id if period else None,
            "performance_version": performance.performance_version,
            "performance_config_hash": performance.performance_config_hash,
            "performance_source_hash": performance.source_hash,
            "risk_version": risk.risk_version,
            "risk_config_hash": risk.risk_config_hash,
            "risk_source_hash": risk.risk_source_hash,
            "trade_version": trade.trade_version,
            "trade_config_hash": trade.trade_config_hash,
            "trade_source_hash": trade.trade_source_hash,
            "period_version": period.period_version if period else None,
            "period_source_hash": period.period_source_hash if period else None,
        }
        record = {
            "report_ids": {
                "performance_id": performance.id,
                "risk_id": risk.id,
                "trade_id": trade.id,
                "period_id": period.id if period else None,
            },
            "performance": {
                "start_date": performance.start_date,
                "end_date": performance.end_date,
                "trade_days": performance.trade_days,
                "final_nav": performance.final_nav,
                "cumulative_return": performance.cumulative_return,
                "annualized_return": performance.annualized_return,
                "max_drawdown": performance.max_drawdown,
            },
            "risk": {
                "benchmark_code": risk.benchmark_code,
                "benchmark_cumulative_return": risk.benchmark_cumulative_return,
                "excess_cumulative_return": risk.excess_cumulative_return,
                "sharpe_ratio": risk.sharpe_ratio,
                "sortino_ratio": risk.sortino_ratio,
                "calmar_ratio": risk.calmar_ratio,
            },
            "trade": {
                "total_turnover": trade.total_turnover,
                "total_execution_cost": trade.total_execution_cost,
                "closed_episode_count": trade.closed_episode_count,
                "open_episode_count": trade.open_episode_count,
                "win_rate": trade.win_rate,
                "profit_factor": trade.profit_factor,
            },
            "period": {
                "month_count": period.month_count,
                "year_count": period.year_count,
            }
            if period
            else None,
        }
        warnings.extend(_null_warnings(record, "performance_summary"))
        reports: list[tuple[Any, str, str]] = [
            (performance, performance.source_hash, performance.performance_config_hash),
            (risk, risk.risk_source_hash, risk.risk_config_hash),
            (trade, trade.trade_source_hash, trade.trade_config_hash),
        ]
        if period:
            reports.append((period, period.period_source_hash, period.period_config_hash))
        return AgentToolResult(
            tool_name="performance.summary",
            status="READY",
            as_of_date=performance.end_date,
            identity=identity,
            records=[record],
            evidence=[
                evidence_ref(
                    layer="STRATEGY_VALIDATION",
                    source_type="report",
                    entity_id=str(run.id),
                    date_value=performance.end_date,
                    source_record_id=str(report.id),
                    config_hash=config_hash,
                    source_hash=source_hash,
                    report_id=str(report.id),
                    observed_at=report.calculated_at,
                    quality_status="WARNING" if warnings else "PASS",
                    limitations=sorted(set(warnings)),
                )
                for report, source_hash, config_hash in reports
            ],
            warnings=sorted(set(warnings)),
            readiness=Readiness(ready=True, code="READY"),
        )

    def walk_forward_summary(self, request: WalkForwardSummaryInput) -> AgentToolResult:
        study = self.db.get(PortfolioWalkForwardStudy, request.study_id)
        if study is None:
            raise not_found("walk-forward study not found")
        report = self.db.scalar(
            select(PortfolioWalkForwardValidationReport).where(
                PortfolioWalkForwardValidationReport.id == request.validation_id,
                PortfolioWalkForwardValidationReport.study_id == request.study_id,
            )
        )
        if report is None or report.status != "SUCCESS":
            raise not_ready("VALIDATION_NOT_READY: walk-forward validation is unavailable")
        identity = {
            "study_id": study.id,
            "validation_id": report.id,
            "walk_forward_version": report.walk_forward_version,
            "walk_forward_config_hash": report.walk_forward_config_hash,
            "policy_identity_version": report.policy_identity_version,
            "validation_policy_hash": report.validation_policy_hash,
            "source_hash": report.source_hash,
            "definition_hash": study.definition_hash,
        }
        record = {
            "result_stage": "OOS",
            "oos_sample": {
                "window_count": report.window_count,
                "total_oos_trade_days": report.total_oos_trade_days,
                "positive_oos_window_count": report.positive_oos_window_count,
                "positive_oos_window_rate": report.positive_oos_window_rate,
            },
            "returns": {
                "stitched_oos_final_nav": report.stitched_oos_final_nav,
                "stitched_oos_cumulative_return": report.stitched_oos_cumulative_return,
                "stitched_oos_annualized_return": report.stitched_oos_annualized_return,
                "stitched_oos_max_drawdown": report.stitched_oos_max_drawdown,
                "stitched_excess_cumulative_return": (report.stitched_excess_cumulative_return),
            },
            "parameter_switching": {
                "unique_selected_parameter_hash_count": (
                    report.unique_selected_parameter_hash_count
                ),
                "dominant_parameter_hash": report.dominant_parameter_hash,
                "dominant_parameter_hash_rate": report.dominant_parameter_hash_rate,
                "transition_count": report.transition_count,
                "switch_count": report.switch_count,
                "switch_rate": report.switch_rate,
            },
            "train_to_oos_degradation": {
                "mean_return_degradation": report.mean_return_degradation,
                "median_return_degradation": report.median_return_degradation,
                "mean_drawdown_worsening": report.mean_drawdown_worsening,
                "median_drawdown_worsening": report.median_drawdown_worsening,
            },
            "policy_identity": {
                "policy_identity_version": report.policy_identity_version,
                "validation_policy_hash": report.validation_policy_hash,
            },
        }
        warnings = list(report.warnings or [])
        warnings.extend(_null_warnings(record, "walk_forward_summary"))
        return AgentToolResult(
            tool_name="walk_forward.summary",
            status="READY",
            as_of_date=study.requested_end_date,
            identity=identity,
            records=[record],
            evidence=[
                evidence_ref(
                    layer="STRATEGY_VALIDATION",
                    source_type="report",
                    entity_id=str(study.id),
                    date_value=study.requested_end_date,
                    source_record_id=str(report.id),
                    calc_version=report.walk_forward_version,
                    config_hash=report.validation_policy_hash,
                    source_hash=report.source_hash,
                    report_id=str(report.id),
                    observed_at=report.calculated_at,
                    quality_status="WARNING" if warnings else "PASS",
                    limitations=[
                        "OOS validation summary; not a live trading signal",
                        *sorted(set(warnings)),
                    ],
                )
            ],
            warnings=sorted(set(warnings)),
            readiness=Readiness(ready=True, code="READY"),
        )

    def _performance_report(self, request: PerformanceSummaryInput) -> PortfolioPerformanceReport:
        if request.report_id:
            report = self.db.get(PortfolioPerformanceReport, request.report_id)
            if report is None:
                raise not_found("performance report not found")
            return report
        reports = list(
            self.db.scalars(
                select(PortfolioPerformanceReport)
                .where(PortfolioPerformanceReport.run_id == request.run_id)
                .limit(2)
            ).all()
        )
        if not reports:
            raise not_ready("ANALYTICS_NOT_READY: performance report is unavailable")
        if len(reports) > 1:
            raise invalid_argument(
                "run has multiple performance reports; provide report_id explicitly"
            )
        return reports[0]

    def _one_bundle_row(self, model: Any, criterion: Any, name: str) -> Any:
        rows = list(self.db.scalars(select(model).where(criterion).limit(2)).all())
        if not rows:
            raise not_ready(f"ANALYTICS_NOT_READY: {name} report is unavailable")
        if len(rows) > 1:
            raise identity_mismatch(f"multiple {name} reports match the selected report")
        if rows[0].status != "SUCCESS":
            raise not_ready(f"ANALYTICS_NOT_READY: {name} report is not successful")
        return rows[0]


def _run_identity(run: PortfolioBacktestRun) -> dict[str, Any]:
    return {
        "algo_version": run.algo_version,
        "source_strategy_config_hash": run.source_strategy_config_hash,
        "opportunity_calc_version": run.opportunity_calc_version,
        "opportunity_config_hash": run.opportunity_config_hash,
        "portfolio_version": run.portfolio_version,
        "portfolio_config_hash": run.portfolio_config_hash,
        "execution_version": run.execution_version,
        "execution_config_hash": run.execution_config_hash,
        "accounting_version": run.accounting_version,
        "accounting_config_hash": run.accounting_config_hash,
        "backtest_engine_version": run.backtest_engine_version,
    }


def _null_warnings(value: Any, prefix: str) -> list[str]:
    if value is None:
        return [f"DATA_UNAVAILABLE:{prefix}"]
    warnings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            warnings.extend(_null_warnings(item, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            warnings.extend(_null_warnings(item, f"{prefix}[{index}]"))
    return sorted(set(warnings))
