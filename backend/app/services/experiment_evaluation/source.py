import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.experiment_evaluation_config import ExperimentEvaluationConfig
from app.core.performance_config import PERFORMANCE_VERSION
from app.core.performance_period_config import PERIOD_VERSION
from app.core.performance_risk_config import RISK_VERSION
from app.core.performance_trade_config import TRADE_VERSION
from app.domain.experiment_evaluation.contracts import (
    EvaluationMetricSnapshot,
    EvaluationTrialInput,
)
from app.domain.experiment_evaluation.metrics import monthly_robustness
from app.models.experiment import PortfolioExperiment, PortfolioExperimentTrial
from app.models.performance import PortfolioPerformanceDaily, PortfolioPerformanceReport
from app.models.performance_period import (
    PortfolioPerformancePeriod,
    PortfolioPerformancePeriodReport,
)
from app.models.performance_risk import PortfolioPerformanceRiskReport
from app.models.performance_trade import PortfolioPerformanceTradeReport
from app.models.portfolio import PortfolioBacktestRun
from app.services.experiment_evaluation.identity import stable_hash

_TERMINAL = {"SUCCESS", "FAILED", "CANCELLED"}


class ExperimentEvaluationSourceError(RuntimeError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        self.code = code
        self.details = details
        super().__init__(message)


@dataclass(frozen=True)
class ExperimentEvaluationSourceSnapshot:
    experiment_id: uuid.UUID
    definition_hash: str
    parameter_space_hash: str
    trials: tuple[EvaluationTrialInput, ...]
    source_hash: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _BundleIdentity:
    performance_version: str
    performance_config_hash: str
    start_date: object
    end_date: object
    trade_days: int
    trade_date_set: tuple[str, ...]
    risk_version: str
    risk_config_hash: str
    benchmark_code: str
    trade_version: str
    trade_config_hash: str
    period_version: str
    period_config_hash: str
    month_period_key_set: tuple[str, ...]
    year_period_key_set: tuple[str, ...]


class ExperimentEvaluationSourceProvider:
    def __init__(self, db: Session, config: ExperimentEvaluationConfig) -> None:
        self.db = db
        self.config = config

    def readiness(self, experiment_id: uuid.UUID) -> dict[str, Any]:
        experiment, pairs = self._experiment_trials(experiment_id)
        counts = {name: 0 for name in ("success", "failed", "cancelled", "active")}
        missing: list[dict[str, Any]] = []
        for trial, run in pairs:
            state = run.status if run is not None else "PLANNED"
            key = state.lower() if state in _TERMINAL else "active"
            counts[key] += 1
            if state == "SUCCESS":
                stage = self._missing_stage(run.id)
                if stage is not None:
                    missing.append(
                        {
                            "trial_id": str(trial.id),
                            "trial_no": trial.trial_no,
                            "run_id": str(run.id),
                            "missing_stage": stage,
                        }
                    )
        ready = counts["active"] == 0 and counts["success"] > 0 and not missing
        result: dict[str, Any] = {
            "experiment_id": str(experiment.id),
            "ready": ready,
            "trial_count": len(pairs),
            "success_count": counts["success"],
            "failed_count": counts["failed"],
            "cancelled_count": counts["cancelled"],
            "active_count": counts["active"],
            "missing_analytics": missing,
        }
        if counts["active"]:
            result["error_code"] = "EXPERIMENT_EVALUATION_NOT_READY"
        elif not counts["success"]:
            result["error_code"] = "EXPERIMENT_EVALUATION_NO_SUCCESSFUL_TRIAL"
        elif missing:
            result["error_code"] = "EXPERIMENT_EVALUATION_ANALYTICS_INCOMPLETE"
        elif ready:
            try:
                self.load(experiment_id)
            except ExperimentEvaluationSourceError as exc:
                if exc.code == "EXPERIMENT_EVALUATION_ANALYTICS_INCOMPATIBLE":
                    result["ready"] = False
                    result["error_code"] = exc.code
                    result["mismatch_fields"] = exc.details.get("mismatch_fields", [])
        return result

    def load(self, experiment_id: uuid.UUID) -> ExperimentEvaluationSourceSnapshot:
        experiment, pairs = self._experiment_trials(experiment_id)
        active = [
            trial.trial_no
            for trial, run in pairs
            if (run.status if run is not None else "PLANNED") not in _TERMINAL
        ]
        if active:
            raise ExperimentEvaluationSourceError(
                "EXPERIMENT_EVALUATION_NOT_READY",
                "all experiment trials must be terminal before evaluation",
                active_trial_numbers=active,
            )
        success = [(trial, run) for trial, run in pairs if run and run.status == "SUCCESS"]
        if not success:
            raise ExperimentEvaluationSourceError(
                "EXPERIMENT_EVALUATION_NO_SUCCESSFUL_TRIAL",
                "experiment has no successful trial to evaluate",
            )

        source_trials: list[EvaluationTrialInput] = []
        identities: list[tuple[int, _BundleIdentity]] = []
        source_identity_trials: list[dict[str, Any]] = []
        warnings: set[str] = set()
        for trial, run in pairs:
            state = run.status if run is not None else "PLANNED"
            identity: dict[str, Any] = {
                "trial_no": trial.trial_no,
                "trial_id": str(trial.id),
                "parameter_hash": trial.parameter_hash,
                "run_id": str(run.id) if run else None,
                "run_status": state,
            }
            if state != "SUCCESS":
                if state == "FAILED":
                    warnings.add("EXPERIMENT_CONTAINS_FAILED_TRIALS")
                elif state == "CANCELLED":
                    warnings.add("EXPERIMENT_CONTAINS_CANCELLED_TRIALS")
                source_trials.append(
                    EvaluationTrialInput(
                        trial_id=trial.id,
                        trial_no=trial.trial_no,
                        parameter_hash=trial.parameter_hash,
                        parameter_values=dict(trial.parameter_values),
                        run_id=run.id if run else None,
                        run_status=state,
                    )
                )
                source_identity_trials.append(identity)
                continue
            assert run is not None
            bundle = self._bundle(trial, run)
            source_trials.append(bundle[0])
            identities.append((trial.trial_no, bundle[1]))
            identity.update(bundle[2])
            source_identity_trials.append(identity)
            warnings.update(bundle[0].warnings)
            optional = bundle[0].metrics
            assert optional is not None
            if any(
                optional.value(name) is None
                for name in (
                    "strategy_annualized_volatility",
                    "sharpe_ratio",
                    "sortino_ratio",
                    "calmar_ratio",
                    "information_ratio",
                    "alpha_annualized",
                    "win_rate",
                    "profit_factor",
                    "payoff_ratio",
                    "monthly_return_volatility",
                )
            ):
                warnings.add("NULL_OPTIONAL_METRICS_PRESENT")
        self._validate_compatible(identities)
        source_hash = stable_hash(
            {
                "experiment_id": str(experiment.id),
                "definition_hash": experiment.definition_hash,
                "parameter_space_hash": experiment.parameter_space_hash,
                "trials": source_identity_trials,
            }
        )
        return ExperimentEvaluationSourceSnapshot(
            experiment_id=experiment.id,
            definition_hash=experiment.definition_hash,
            parameter_space_hash=experiment.parameter_space_hash,
            trials=tuple(source_trials),
            source_hash=source_hash,
            warnings=tuple(sorted(warnings)),
        )

    def _experiment_trials(
        self, experiment_id: uuid.UUID
    ) -> tuple[
        PortfolioExperiment,
        list[tuple[PortfolioExperimentTrial, PortfolioBacktestRun | None]],
    ]:
        experiment = self.db.scalar(
            select(PortfolioExperiment)
            .where(PortfolioExperiment.id == experiment_id)
            .execution_options(populate_existing=True)
        )
        if experiment is None:
            raise ExperimentEvaluationSourceError(
                "EXPERIMENT_EVALUATION_NOT_FOUND", "portfolio experiment not found"
            )
        pairs = list(
            self.db.execute(
                select(PortfolioExperimentTrial, PortfolioBacktestRun)
                .outerjoin(
                    PortfolioBacktestRun,
                    PortfolioBacktestRun.id == PortfolioExperimentTrial.run_id,
                )
                .where(PortfolioExperimentTrial.experiment_id == experiment_id)
                .order_by(PortfolioExperimentTrial.trial_no)
                .execution_options(populate_existing=True)
            ).all()
        )
        if len(pairs) != experiment.trial_count:
            raise ExperimentEvaluationSourceError(
                "EXPERIMENT_EVALUATION_SOURCE_INVALID",
                "experiment trial count does not match its frozen definition",
            )
        return experiment, pairs

    def _missing_stage(self, run_id: uuid.UUID) -> str | None:
        performance = self._latest_performance(run_id)
        if performance is None:
            return "performance"
        risk = self._latest_risk(performance.id)
        if risk is None:
            return "risk"
        trade = self._latest_trade(performance.id)
        if trade is None:
            return "trade"
        if self._latest_period(performance.id, risk.id, trade.id) is None:
            return "period"
        return None

    def _bundle(
        self, trial: PortfolioExperimentTrial, run: PortfolioBacktestRun
    ) -> tuple[EvaluationTrialInput, _BundleIdentity, dict[str, Any]]:
        performance = self._latest_performance(run.id)
        if performance is None:
            self._incomplete(trial, run, "performance")
        assert performance is not None
        risk = self._latest_risk(performance.id)
        if risk is None:
            self._incomplete(trial, run, "risk")
        trade = self._latest_trade(performance.id)
        if trade is None:
            self._incomplete(trial, run, "trade")
        assert risk is not None and trade is not None
        period = self._latest_period(performance.id, risk.id, trade.id)
        if period is None:
            self._incomplete(trial, run, "period")
        assert period is not None
        daily_dates = tuple(
            str(value)
            for value in self.db.scalars(
                select(PortfolioPerformanceDaily.trade_date)
                .where(PortfolioPerformanceDaily.performance_id == performance.id)
                .order_by(PortfolioPerformanceDaily.trade_date)
                .execution_options(populate_existing=True)
            ).all()
        )
        period_rows = list(
            self.db.scalars(
                select(PortfolioPerformancePeriod)
                .where(PortfolioPerformancePeriod.period_id == period.id)
                .order_by(
                    PortfolioPerformancePeriod.period_type,
                    PortfolioPerformancePeriod.period_key,
                )
                .execution_options(populate_existing=True)
            ).all()
        )
        month_rows = [row for row in period_rows if row.period_type == "MONTH"]
        month_returns = tuple(row.strategy_return for row in month_rows)
        positive, worst, volatility, metric_warnings = monthly_robustness(
            month_returns,
            minimum_observations=self.config.minimum_month_observations,
        )
        metrics = EvaluationMetricSnapshot(
            trade_days=Decimal(performance.trade_days),
            cumulative_return=performance.cumulative_return,
            annualized_return=performance.annualized_return,
            max_drawdown_abs=abs(performance.max_drawdown),
            strategy_annualized_volatility=risk.strategy_annualized_volatility,
            excess_cumulative_return=risk.excess_cumulative_return,
            sharpe_ratio=risk.sharpe_ratio,
            sortino_ratio=risk.sortino_ratio,
            calmar_ratio=risk.calmar_ratio,
            information_ratio=risk.information_ratio,
            alpha_annualized=risk.alpha_annualized,
            annualized_turnover=trade.annualized_turnover,
            total_cost_to_initial_capital=trade.total_cost_to_initial_capital,
            closed_episode_count=Decimal(trade.closed_episode_count),
            win_rate=trade.win_rate,
            profit_factor=trade.profit_factor,
            payoff_ratio=trade.payoff_ratio,
            closed_realized_pnl=trade.closed_realized_pnl,
            positive_month_rate=positive,
            worst_month_return=worst,
            monthly_return_volatility=volatility,
        )
        source = EvaluationTrialInput(
            trial_id=trial.id,
            trial_no=trial.trial_no,
            parameter_hash=trial.parameter_hash,
            parameter_values=dict(trial.parameter_values),
            run_id=run.id,
            run_status=run.status,
            metrics=metrics,
            performance_id=performance.id,
            risk_id=risk.id,
            trade_id=trade.id,
            period_id=period.id,
            warnings=metric_warnings,
        )
        identity = _BundleIdentity(
            performance_version=performance.performance_version,
            performance_config_hash=performance.performance_config_hash,
            start_date=performance.start_date,
            end_date=performance.end_date,
            trade_days=performance.trade_days,
            trade_date_set=daily_dates,
            risk_version=risk.risk_version,
            risk_config_hash=risk.risk_config_hash,
            benchmark_code=risk.benchmark_code,
            trade_version=trade.trade_version,
            trade_config_hash=trade.trade_config_hash,
            period_version=period.period_version,
            period_config_hash=period.period_config_hash,
            month_period_key_set=tuple(row.period_key for row in month_rows),
            year_period_key_set=tuple(
                row.period_key for row in period_rows if row.period_type == "YEAR"
            ),
        )
        hash_identity = {
            "performance_id": str(performance.id),
            "performance_version": performance.performance_version,
            "performance_config_hash": performance.performance_config_hash,
            "performance_source_hash": performance.source_hash,
            "risk_id": str(risk.id),
            "risk_version": risk.risk_version,
            "risk_config_hash": risk.risk_config_hash,
            "risk_source_hash": risk.risk_source_hash,
            "benchmark_source_hash": risk.benchmark_source_hash,
            "trade_id": str(trade.id),
            "trade_version": trade.trade_version,
            "trade_config_hash": trade.trade_config_hash,
            "trade_source_hash": trade.trade_source_hash,
            "period_id": str(period.id),
            "period_version": period.period_version,
            "period_config_hash": period.period_config_hash,
            "period_source_hash": period.period_source_hash,
        }
        return source, identity, hash_identity

    def _validate_compatible(
        self, identities: list[tuple[int, _BundleIdentity]]
    ) -> None:
        baseline = identities[0][1]
        mismatches: set[str] = set()
        for _, current in identities[1:]:
            for field in baseline.__dataclass_fields__:
                if getattr(current, field) != getattr(baseline, field):
                    mismatches.add(field)
        if mismatches:
            raise ExperimentEvaluationSourceError(
                "EXPERIMENT_EVALUATION_ANALYTICS_INCOMPATIBLE",
                "successful trials do not have comparable M14 analytics bundles",
                mismatch_fields=sorted(mismatches),
            )

    def _incomplete(
        self, trial: PortfolioExperimentTrial, run: PortfolioBacktestRun, stage: str
    ) -> None:
        raise ExperimentEvaluationSourceError(
            "EXPERIMENT_EVALUATION_ANALYTICS_INCOMPLETE",
            f"successful trial {trial.trial_no} is missing {stage} analytics",
            missing_analytics=[
                {
                    "trial_id": str(trial.id),
                    "trial_no": trial.trial_no,
                    "run_id": str(run.id),
                    "missing_stage": stage,
                }
            ],
        )

    def _latest_performance(
        self, run_id: uuid.UUID
    ) -> PortfolioPerformanceReport | None:
        return self.db.scalar(
            select(PortfolioPerformanceReport)
            .where(
                PortfolioPerformanceReport.run_id == run_id,
                PortfolioPerformanceReport.status == "SUCCESS",
                PortfolioPerformanceReport.performance_version == PERFORMANCE_VERSION,
            )
            .order_by(
                PortfolioPerformanceReport.calculated_at.desc(),
                PortfolioPerformanceReport.id.desc(),
            )
            .limit(1)
            .execution_options(populate_existing=True)
        )

    def _latest_risk(
        self, performance_id: uuid.UUID
    ) -> PortfolioPerformanceRiskReport | None:
        return self.db.scalar(
            select(PortfolioPerformanceRiskReport)
            .where(
                PortfolioPerformanceRiskReport.performance_id == performance_id,
                PortfolioPerformanceRiskReport.status == "SUCCESS",
                PortfolioPerformanceRiskReport.risk_version == RISK_VERSION,
            )
            .order_by(
                PortfolioPerformanceRiskReport.calculated_at.desc(),
                PortfolioPerformanceRiskReport.id.desc(),
            )
            .limit(1)
            .execution_options(populate_existing=True)
        )

    def _latest_trade(
        self, performance_id: uuid.UUID
    ) -> PortfolioPerformanceTradeReport | None:
        return self.db.scalar(
            select(PortfolioPerformanceTradeReport)
            .where(
                PortfolioPerformanceTradeReport.performance_id == performance_id,
                PortfolioPerformanceTradeReport.status == "SUCCESS",
                PortfolioPerformanceTradeReport.trade_version == TRADE_VERSION,
            )
            .order_by(
                PortfolioPerformanceTradeReport.calculated_at.desc(),
                PortfolioPerformanceTradeReport.id.desc(),
            )
            .limit(1)
            .execution_options(populate_existing=True)
        )

    def _latest_period(
        self, performance_id: uuid.UUID, risk_id: uuid.UUID, trade_id: uuid.UUID
    ) -> PortfolioPerformancePeriodReport | None:
        return self.db.scalar(
            select(PortfolioPerformancePeriodReport)
            .where(
                PortfolioPerformancePeriodReport.performance_id == performance_id,
                PortfolioPerformancePeriodReport.risk_id == risk_id,
                PortfolioPerformancePeriodReport.trade_id == trade_id,
                PortfolioPerformancePeriodReport.status == "SUCCESS",
                PortfolioPerformancePeriodReport.period_version == PERIOD_VERSION,
            )
            .order_by(
                PortfolioPerformancePeriodReport.calculated_at.desc(),
                PortfolioPerformancePeriodReport.id.desc(),
            )
            .limit(1)
            .execution_options(populate_existing=True)
        )
