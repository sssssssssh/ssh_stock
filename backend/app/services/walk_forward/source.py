import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.walk_forward_config import WalkForwardConfig
from app.domain.walk_forward.contracts import DailyReturnPoint, WindowMetricInput
from app.domain.walk_forward.windows import date_set_hash
from app.models.experiment import PortfolioExperiment, PortfolioExperimentTrial
from app.models.experiment_evaluation import (
    PortfolioExperimentEvaluationReport,
    PortfolioExperimentTrialEvaluation,
)
from app.models.performance import PortfolioPerformanceDaily, PortfolioPerformanceReport
from app.models.performance_period import PortfolioPerformancePeriodReport
from app.models.performance_risk import (
    PortfolioPerformanceRiskDaily,
    PortfolioPerformanceRiskReport,
)
from app.models.performance_trade import PortfolioPerformanceTradeReport
from app.models.portfolio import PortfolioBacktestRun
from app.models.walk_forward import (
    PortfolioWalkForwardStudy,
    PortfolioWalkForwardWindow,
)
from app.services.calc_metadata import config_hash
from app.services.experiment_evaluation.identity import (
    experiment_parameter_hash,
    stable_hash,
)
from app.services.walk_forward.identity import walk_forward_config_hash


class WalkForwardSourceError(RuntimeError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        self.code = code
        self.details = details
        super().__init__(message)


@dataclass(frozen=True)
class ValidationWindowSource:
    window: PortfolioWalkForwardWindow
    metric_input: WindowMetricInput


@dataclass(frozen=True)
class WalkForwardValidationSource:
    study: PortfolioWalkForwardStudy
    windows: tuple[ValidationWindowSource, ...]
    source_hash: str
    walk_forward_config_hash: str
    annualization_trade_days: int
    risk_free_rate_annual: Decimal


class WalkForwardValidationSourceProvider:
    def __init__(self, db: Session, config: WalkForwardConfig) -> None:
        self.db = db
        self.config = config

    def readiness(self, study_id: uuid.UUID) -> dict[str, Any]:
        try:
            source = self.load(study_id)
        except WalkForwardSourceError as exc:
            return {
                "study_id": str(study_id),
                "ready": False,
                "error_code": exc.code,
                **exc.details,
            }
        return {
            "study_id": str(study_id),
            "ready": True,
            "window_count": len(source.windows),
            "source_hash": source.source_hash,
            "walk_forward_config_hash": source.walk_forward_config_hash,
        }

    def load(self, study_id: uuid.UUID) -> WalkForwardValidationSource:
        study = self.db.scalar(
            select(PortfolioWalkForwardStudy)
            .where(PortfolioWalkForwardStudy.id == study_id)
            .execution_options(populate_existing=True)
        )
        if study is None:
            raise WalkForwardSourceError(
                "WALK_FORWARD_NOT_FOUND", "walk-forward study not found"
            )
        windows = list(
            self.db.scalars(
                select(PortfolioWalkForwardWindow)
                .where(PortfolioWalkForwardWindow.study_id == study_id)
                .order_by(PortfolioWalkForwardWindow.window_no)
                .execution_options(populate_existing=True)
            ).all()
        )
        if len(windows) != study.window_count:
            self._invalid("stored window count does not match the frozen study")
        if _stored_definition_hash(study, windows) != study.definition_hash:
            self._invalid("stored study definition identity changed")
        sources: list[ValidationWindowSource] = []
        identities: list[dict[str, Any]] = []
        compatibility: tuple[Any, ...] | None = None
        annualization_trade_days = 0
        risk_free_rate_annual = Decimal(0)
        previous_test_end: date | None = None
        for window in windows:
            source, identity, current = self._window_source(study, window)
            expected_dates = tuple(date.fromisoformat(value) for value in window.test_trade_dates)
            if previous_test_end is not None:
                first = expected_dates[0]
                if first <= previous_test_end:
                    self._invalid("OOS windows overlap or are not ordered")
            previous_test_end = expected_dates[-1]
            if compatibility is None:
                compatibility = current
                annualization_trade_days = int(current[-2])
                risk_free_rate_annual = Decimal(current[-1])
            elif compatibility != current:
                raise WalkForwardSourceError(
                    "WALK_FORWARD_OOS_BUNDLE_MISMATCH",
                    "OOS M14 config identity differs across windows",
                    window_no=window.window_no,
                )
            sources.append(ValidationWindowSource(window, source))
            identities.append(identity)
        if not sources:
            raise WalkForwardSourceError(
                "WALK_FORWARD_VALIDATION_NOT_READY", "study has no windows"
            )
        source_hash = stable_hash(
            {
                "study": {
                    "study_id": str(study.id),
                    "definition_hash": study.definition_hash,
                    "calendar_hash": study.calendar_hash,
                    "parameter_space_hash": study.parameter_space_hash,
                    "train_policy_hash": study.train_policy_hash,
                },
                "windows": identities,
            }
        )
        return WalkForwardValidationSource(
            study=study,
            windows=tuple(sources),
            source_hash=source_hash,
            walk_forward_config_hash=walk_forward_config_hash(self.config),
            annualization_trade_days=annualization_trade_days,
            risk_free_rate_annual=risk_free_rate_annual,
        )

    def _window_source(
        self,
        study: PortfolioWalkForwardStudy,
        window: PortfolioWalkForwardWindow,
    ) -> tuple[WindowMetricInput, dict[str, Any], tuple[Any, ...]]:
        required = (
            window.train_experiment_id,
            window.train_evaluation_id,
            window.selected_trial_id,
            window.selected_parameter_hash,
            window.selected_parameter_values,
            window.selected_portfolio_config_hash,
            window.selected_portfolio_config_snapshot,
            window.oos_run_id,
            window.oos_performance_id,
            window.oos_risk_id,
            window.oos_trade_id,
            window.oos_period_id,
            window.oos_bound_at,
        )
        if any(value is None for value in required):
            raise WalkForwardSourceError(
                "WALK_FORWARD_VALIDATION_NOT_READY",
                "all windows must have frozen selection and pinned OOS analytics",
                window_no=window.window_no,
            )
        expected_train_dates = tuple(
            date.fromisoformat(value) for value in window.train_trade_dates
        )
        expected_test_dates = tuple(date.fromisoformat(value) for value in window.test_trade_dates)
        if (
            date_set_hash(expected_train_dates) != window.train_date_hash
            or date_set_hash(expected_test_dates) != window.test_date_hash
            or len(expected_train_dates) != window.train_trade_days
            or len(expected_test_dates) != window.test_trade_days
        ):
            self._invalid("frozen window date identity is invalid", window.window_no)

        experiment = self.db.get(PortfolioExperiment, window.train_experiment_id)
        report = self.db.get(
            PortfolioExperimentEvaluationReport, window.train_evaluation_id
        )
        trial = self.db.get(PortfolioExperimentTrial, window.selected_trial_id)
        selected_run = (
            self.db.get(PortfolioBacktestRun, trial.run_id)
            if trial is not None and trial.run_id is not None
            else None
        )
        trial_evaluation = self.db.scalar(
            select(PortfolioExperimentTrialEvaluation)
            .where(
                PortfolioExperimentTrialEvaluation.evaluation_id
                == window.train_evaluation_id,
                PortfolioExperimentTrialEvaluation.trial_id == window.selected_trial_id,
            )
            .execution_options(populate_existing=True)
        )
        oos_run = self.db.get(PortfolioBacktestRun, window.oos_run_id)
        performance = self.db.get(PortfolioPerformanceReport, window.oos_performance_id)
        risk = self.db.get(PortfolioPerformanceRiskReport, window.oos_risk_id)
        trade = self.db.get(PortfolioPerformanceTradeReport, window.oos_trade_id)
        period = self.db.get(PortfolioPerformancePeriodReport, window.oos_period_id)
        if any(
            item is None
            for item in (
                experiment,
                report,
                trial,
                selected_run,
                trial_evaluation,
                oos_run,
                performance,
                risk,
                trade,
                period,
            )
        ):
            self._invalid("a pinned walk-forward source row is missing", window.window_no)
        assert experiment and report and trial and selected_run and trial_evaluation
        assert oos_run and performance and risk and trade and period
        self._validate_selection(
            study,
            window,
            experiment,
            report,
            trial,
            selected_run,
            trial_evaluation,
        )
        self._validate_oos(study, window, experiment, trial, oos_run)
        if (
            performance.run_id != oos_run.id
            or risk.run_id != oos_run.id
            or trade.run_id != oos_run.id
            or period.run_id != oos_run.id
            or risk.performance_id != performance.id
            or trade.performance_id != performance.id
            or period.performance_id != performance.id
            or period.risk_id != risk.id
            or period.trade_id != trade.id
        ):
            raise WalkForwardSourceError(
                "WALK_FORWARD_OOS_BUNDLE_MISMATCH",
                "pinned OOS artifacts do not share the exact run owner",
                window_no=window.window_no,
            )
        strategy_rows = list(
            self.db.execute(
                select(
                    PortfolioPerformanceDaily.trade_date,
                    PortfolioPerformanceDaily.daily_return,
                )
                .where(PortfolioPerformanceDaily.performance_id == performance.id)
                .order_by(PortfolioPerformanceDaily.trade_date)
                .execution_options(populate_existing=True)
            ).all()
        )
        benchmark_rows = list(
            self.db.execute(
                select(
                    PortfolioPerformanceRiskDaily.trade_date,
                    PortfolioPerformanceRiskDaily.benchmark_daily_return,
                )
                .where(PortfolioPerformanceRiskDaily.risk_id == risk.id)
                .order_by(PortfolioPerformanceRiskDaily.trade_date)
                .execution_options(populate_existing=True)
            ).all()
        )
        strategy_dates = tuple(row[0] for row in strategy_rows)
        benchmark_dates = tuple(row[0] for row in benchmark_rows)
        if strategy_dates != expected_test_dates or benchmark_dates != expected_test_dates:
            raise WalkForwardSourceError(
                "WALK_FORWARD_OOS_DATE_SET_MISMATCH",
                "OOS daily date set does not equal the frozen test date set",
                window_no=window.window_no,
            )
        annualization = performance.result_summary.get("annualization_trade_days")
        if not isinstance(annualization, int) or annualization <= 0:
            raise WalkForwardSourceError(
                "WALK_FORWARD_OOS_BUNDLE_MISMATCH",
                "pinned performance artifact lacks annualization identity",
                window_no=window.window_no,
            )
        if any(
            value is None
            for value in (
                trial_evaluation.annualized_return,
                trial_evaluation.max_drawdown_abs,
                trial_evaluation.annualized_turnover,
            )
        ):
            self._invalid("selected train metrics are incomplete", window.window_no)
        points = tuple(
            DailyReturnPoint(day, strategy_return, benchmark_return)
            for (day, strategy_return), (_, benchmark_return) in zip(
                strategy_rows, benchmark_rows, strict=True
            )
        )
        metric = WindowMetricInput(
            window_no=window.window_no,
            selected_parameter_hash=window.selected_parameter_hash,
            selected_parameter_values=dict(window.selected_parameter_values),
            daily_returns=points,
            train_annualized_return=trial_evaluation.annualized_return,
            train_max_drawdown_abs=trial_evaluation.max_drawdown_abs,
            train_sharpe_ratio=trial_evaluation.sharpe_ratio,
            train_annualized_turnover=trial_evaluation.annualized_turnover,
            oos_cumulative_return=performance.cumulative_return,
            oos_annualized_return=performance.annualized_return,
            oos_max_drawdown_abs=abs(performance.max_drawdown),
            oos_sharpe_ratio=risk.sharpe_ratio,
            oos_annualized_turnover=trade.annualized_turnover,
            oos_total_cost_to_initial_capital=trade.total_cost_to_initial_capital,
            oos_win_rate=trade.win_rate,
            oos_profit_factor=trade.profit_factor,
        )
        compatibility = (
            performance.performance_version,
            performance.performance_config_hash,
            risk.risk_version,
            risk.risk_config_hash,
            trade.trade_version,
            trade.trade_config_hash,
            period.period_version,
            period.period_config_hash,
            risk.benchmark_code,
            annualization,
            risk.risk_free_rate_annual,
        )
        identity = {
            "window_no": window.window_no,
            "train_dates": list(window.train_trade_dates),
            "train_date_hash": window.train_date_hash,
            "test_dates": list(window.test_trade_dates),
            "test_date_hash": window.test_date_hash,
            "train_experiment_id": str(experiment.id),
            "train_experiment_definition_hash": experiment.definition_hash,
            "train_evaluation_id": str(report.id),
            "train_evaluation_policy_hash": report.policy_hash,
            "train_evaluation_source_hash": report.source_hash,
            "selected_trial_id": str(trial.id),
            "selected_parameter_hash": trial.parameter_hash,
            "selected_portfolio_config_hash": trial.portfolio_config_hash,
            "oos_run": {
                "id": str(oos_run.id),
                "start_date": oos_run.start_date.isoformat(),
                "end_date": oos_run.end_date.isoformat(),
                "portfolio_config_hash": oos_run.portfolio_config_hash,
                "source_strategy_config_hash": oos_run.source_strategy_config_hash,
                "opportunity_config_hash": oos_run.opportunity_config_hash,
                "execution_config_hash": oos_run.execution_config_hash,
                "accounting_config_hash": oos_run.accounting_config_hash,
            },
            "oos_performance": [str(performance.id), performance.source_hash],
            "oos_risk": [str(risk.id), risk.risk_source_hash, risk.benchmark_source_hash],
            "oos_trade": [str(trade.id), trade.trade_source_hash],
            "oos_period": [str(period.id), period.period_source_hash],
        }
        return metric, identity, compatibility

    def _validate_selection(
        self,
        study: PortfolioWalkForwardStudy,
        window: PortfolioWalkForwardWindow,
        experiment: PortfolioExperiment,
        report: PortfolioExperimentEvaluationReport,
        trial: PortfolioExperimentTrial,
        selected_run: PortfolioBacktestRun,
        evaluation: PortfolioExperimentTrialEvaluation,
    ) -> None:
        if (
            experiment.id != window.train_experiment_id
            or experiment.start_date != window.train_start_date
            or experiment.end_date != window.train_end_date
            or experiment.initial_cash != study.initial_cash
            or experiment.benchmark_code != study.benchmark_code
            or experiment.parameter_space_hash != study.parameter_space_hash
            or experiment.parameter_space != study.parameter_space
            or experiment.base_config_snapshot != study.base_config_snapshot
            or any(
                getattr(experiment, name) != getattr(study, name)
                for name in (
                    "base_algo_version",
                    "base_source_strategy_config_hash",
                    "base_opportunity_calc_version",
                    "base_opportunity_config_hash",
                    "base_portfolio_version",
                    "base_portfolio_config_hash",
                    "base_execution_version",
                    "base_execution_config_hash",
                    "base_accounting_version",
                    "base_accounting_config_hash",
                    "base_backtest_engine_version",
                )
            )
            or report.experiment_id != experiment.id
            or report.policy_hash != study.train_policy_hash
            or report.status != "SUCCESS"
            or report.selected_trial_id != trial.id
            or report.selected_run_id != trial.run_id
            or trial.experiment_id != experiment.id
            or evaluation.experiment_id != experiment.id
            or evaluation.trial_id != trial.id
            or evaluation.status != "EVALUATED"
            or not evaluation.feasible
            or not evaluation.shortlisted
            or evaluation.selection_rank != 1
        ):
            raise WalkForwardSourceError(
                "WALK_FORWARD_SELECTION_IDENTITY_MISMATCH",
                "selected train candidate does not match the frozen rank-1 evaluation",
                window_no=window.window_no,
            )
        if (
            experiment_parameter_hash(trial.parameter_values) != trial.parameter_hash
            or trial.parameter_hash != window.selected_parameter_hash
            or trial.parameter_values != window.selected_parameter_values
            or config_hash(trial.portfolio_config_snapshot) != trial.portfolio_config_hash
            or trial.portfolio_config_hash != window.selected_portfolio_config_hash
            or trial.portfolio_config_snapshot
            != window.selected_portfolio_config_snapshot
        ):
            raise WalkForwardSourceError(
                "WALK_FORWARD_SELECTION_IDENTITY_MISMATCH",
                "selected candidate snapshot or hash is invalid",
                window_no=window.window_no,
            )
        expected_snapshot = {
            "strategy": experiment.base_config_snapshot["strategy"],
            "opportunity": experiment.base_config_snapshot["opportunity"],
            "portfolio": trial.portfolio_config_snapshot,
            "execution": experiment.base_config_snapshot["execution"],
            "accounting": experiment.base_config_snapshot["accounting"],
        }
        if (
            selected_run.status != "SUCCESS"
            or selected_run.start_date != window.train_start_date
            or selected_run.end_date != window.train_end_date
            or selected_run.initial_cash != study.initial_cash
            or selected_run.benchmark_code != study.benchmark_code
            or selected_run.algo_version != study.base_algo_version
            or selected_run.source_strategy_config_hash
            != study.base_source_strategy_config_hash
            or selected_run.opportunity_calc_version
            != study.base_opportunity_calc_version
            or selected_run.opportunity_config_hash
            != study.base_opportunity_config_hash
            or selected_run.portfolio_version != study.base_portfolio_version
            or selected_run.portfolio_config_hash != trial.portfolio_config_hash
            or selected_run.execution_version != study.base_execution_version
            or selected_run.execution_config_hash
            != study.base_execution_config_hash
            or selected_run.accounting_version != study.base_accounting_version
            or selected_run.accounting_config_hash
            != study.base_accounting_config_hash
            or selected_run.backtest_engine_version
            != study.base_backtest_engine_version
            or selected_run.config_snapshot != expected_snapshot
        ):
            raise WalkForwardSourceError(
                "WALK_FORWARD_SELECTION_IDENTITY_MISMATCH",
                "selected train run does not match the frozen candidate identity",
                window_no=window.window_no,
            )

    def _validate_oos(
        self,
        study: PortfolioWalkForwardStudy,
        window: PortfolioWalkForwardWindow,
        experiment: PortfolioExperiment,
        trial: PortfolioExperimentTrial,
        run: PortfolioBacktestRun,
    ) -> None:
        expected_snapshot = {
            "strategy": experiment.base_config_snapshot["strategy"],
            "opportunity": experiment.base_config_snapshot["opportunity"],
            "portfolio": trial.portfolio_config_snapshot,
            "execution": experiment.base_config_snapshot["execution"],
            "accounting": experiment.base_config_snapshot["accounting"],
        }
        if (
            run.status != "SUCCESS"
            or run.start_date != window.test_start_date
            or run.end_date != window.test_end_date
            or run.initial_cash != study.initial_cash
            or run.benchmark_code != study.benchmark_code
            or run.algo_version != study.base_algo_version
            or run.opportunity_calc_version
            != study.base_opportunity_calc_version
            or run.portfolio_version != study.base_portfolio_version
            or run.execution_version != study.base_execution_version
            or run.accounting_version != study.base_accounting_version
            or run.backtest_engine_version != study.base_backtest_engine_version
            or run.portfolio_config_hash != trial.portfolio_config_hash
            or run.source_strategy_config_hash
            != study.base_source_strategy_config_hash
            or run.opportunity_config_hash != study.base_opportunity_config_hash
            or run.execution_config_hash != study.base_execution_config_hash
            or run.accounting_config_hash != study.base_accounting_config_hash
            or run.config_snapshot != expected_snapshot
        ):
            raise WalkForwardSourceError(
                "WALK_FORWARD_OOS_IDENTITY_MISMATCH",
                "OOS run does not match the frozen train selection and study base",
                window_no=window.window_no,
            )

    def _invalid(self, message: str, window_no: int | None = None) -> None:
        details = {"window_no": window_no} if window_no is not None else {}
        raise WalkForwardSourceError(
            "WALK_FORWARD_SOURCE_CHANGED", message, **details
        )


def _stored_definition_hash(
    study: PortfolioWalkForwardStudy,
    windows: list[PortfolioWalkForwardWindow],
) -> str:
    identities = (
        "base_algo_version",
        "base_source_strategy_config_hash",
        "base_opportunity_calc_version",
        "base_opportunity_config_hash",
        "base_portfolio_version",
        "base_portfolio_config_hash",
        "base_execution_version",
        "base_execution_config_hash",
        "base_accounting_version",
        "base_accounting_config_hash",
        "base_backtest_engine_version",
    )
    return stable_hash(
        {
            "walk_forward_version": study.walk_forward_version,
            "mode": study.mode,
            "requested_start_date": study.requested_start_date.isoformat(),
            "requested_end_date": study.requested_end_date.isoformat(),
            "exchange": study.exchange,
            "train_trade_days": study.train_trade_days,
            "test_trade_days": study.test_trade_days,
            "step_trade_days": study.step_trade_days,
            "calendar_hash": study.calendar_hash,
            "windows": [
                {
                    "window_no": row.window_no,
                    "train_dates": list(row.train_trade_dates),
                    "test_dates": list(row.test_trade_dates),
                    "train_date_hash": row.train_date_hash,
                    "test_date_hash": row.test_date_hash,
                }
                for row in windows
            ],
            "initial_cash": _canonical_decimal(study.initial_cash),
            "benchmark_code": study.benchmark_code,
            "parameter_space": study.parameter_space,
            "parameter_space_hash": study.parameter_space_hash,
            "train_policy": study.train_policy_snapshot,
            "train_policy_hash": study.train_policy_hash,
            "base_identities": {
                name: getattr(study, name) for name in identities
            },
            "base_config_snapshot": study.base_config_snapshot,
        }
    )


def _canonical_decimal(value: Decimal) -> str:
    return "0" if value == 0 else format(value.normalize(), "f")
