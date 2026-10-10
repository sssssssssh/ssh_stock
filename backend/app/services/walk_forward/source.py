import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.walk_forward_config import (
    WALK_FORWARD_POLICY_IDENTITY_VERSION,
    WalkForwardConfig,
)
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
from app.services.walk_forward.identity import (
    validation_policy_hash,
    validation_policy_snapshot,
    walk_forward_config_hash,
)


class WalkForwardSourceError(RuntimeError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        self.code = code
        self.details = details
        super().__init__(message)


@dataclass(frozen=True)
class ValidationWindowSource:
    window: PortfolioWalkForwardWindow
    metric_input: WindowMetricInput
    identity_snapshot: dict[str, Any]


@dataclass(frozen=True)
class WalkForwardValidationSource:
    study: PortfolioWalkForwardStudy
    windows: tuple[ValidationWindowSource, ...]
    source_hash: str
    walk_forward_config_hash: str
    policy_identity_version: str
    validation_policy_snapshot: dict[str, Any]
    validation_policy_hash: str
    annualization_trade_days: int
    risk_free_rate_annual: Decimal


class WalkForwardValidationSourceProvider:
    def __init__(self, db: Session, config: WalkForwardConfig) -> None:
        self.db = db
        self.config = config

    def readiness(self, study_id: uuid.UUID) -> dict[str, Any]:
        blockers = self.collect_readiness_blockers(study_id)
        if blockers:
            first = blockers[0]
            details = {key: value for key, value in first.items() if key != "code"}
            return {
                "study_id": str(study_id),
                "ready": False,
                "error_code": first["code"],
                **details,
                "details": details,
                "blockers": blockers,
            }
        no_autoflush = getattr(self.db, "no_autoflush", nullcontext())
        with no_autoflush:
            source = self.load(study_id)
        return {
            "study_id": str(study_id),
            "ready": True,
            "window_count": len(source.windows),
            "source_hash": source.source_hash,
            "walk_forward_config_hash": source.walk_forward_config_hash,
            "policy_identity_version": source.policy_identity_version,
            "validation_policy_snapshot": source.validation_policy_snapshot,
            "validation_policy_hash": source.validation_policy_hash,
            "blockers": [],
        }

    def collect_readiness_blockers(
        self, study_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        no_autoflush = getattr(self.db, "no_autoflush", nullcontext())
        with no_autoflush:
            return self._collect_readiness_blockers(study_id)

    def _collect_readiness_blockers(
        self, study_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        study = self.db.scalar(
            select(PortfolioWalkForwardStudy)
            .where(PortfolioWalkForwardStudy.id == study_id)
            .execution_options(populate_existing=True)
        )
        if study is None:
            return [
                {
                    "code": "WALK_FORWARD_NOT_FOUND",
                    "window_no": None,
                    "scope": "STUDY",
                    "missing_stage": "study",
                    "action": "CREATE_WALK_FORWARD",
                }
            ]
        windows = list(
            self.db.scalars(
                select(PortfolioWalkForwardWindow)
                .where(PortfolioWalkForwardWindow.study_id == study_id)
                .order_by(PortfolioWalkForwardWindow.window_no)
                .execution_options(populate_existing=True)
            ).all()
        )
        blockers: list[dict[str, Any]] = []
        if len(windows) != study.window_count:
            blockers.append(
                _source_blocker("stored window count does not match the frozen study")
            )
        elif _stored_definition_hash(study, windows) != study.definition_hash:
            blockers.append(_source_blocker("stored study definition identity changed"))
        if not windows:
            blockers.append(
                {
                    "code": "WALK_FORWARD_VALIDATION_NOT_READY",
                    "window_no": None,
                    "scope": "STUDY",
                    "missing_stage": "train_experiment",
                    "action": "ADVANCE_WALK_FORWARD",
                }
            )
            return _sort_blockers(blockers)

        for window in windows:
            missing = self._missing_window_requirements(window)
            if not missing:
                missing = self._missing_train_analytics(window)
            blockers.extend(missing)
            if missing:
                continue
            try:
                self._window_source(study, window)
            except WalkForwardSourceError as exc:
                blockers.append(_blocker_from_error(exc, window.window_no))

        if not blockers:
            try:
                self.load(study_id)
            except WalkForwardSourceError as exc:
                blockers.append(_blocker_from_error(exc))
        return _sort_blockers(blockers)

    @staticmethod
    def _missing_window_requirements(
        window: PortfolioWalkForwardWindow,
    ) -> list[dict[str, Any]]:
        requirements = (
            (window.train_experiment_id, "TRAIN", "train_experiment", None),
            (window.train_evaluation_id, "TRAIN", "train_evaluation", None),
            (window.selected_trial_id, "TRAIN", "selection", None),
            (window.selected_parameter_hash, "TRAIN", "selection", None),
            (window.selected_parameter_values, "TRAIN", "selection", None),
            (window.selected_portfolio_config_hash, "TRAIN", "selection", None),
            (window.selected_portfolio_config_snapshot, "TRAIN", "selection", None),
            (window.oos_run_id, "OOS", "oos_run", None),
            (window.oos_performance_id, "OOS", "performance", window.oos_run_id),
            (window.oos_risk_id, "OOS", "risk", window.oos_run_id),
            (window.oos_trade_id, "OOS", "trade", window.oos_run_id),
            (window.oos_period_id, "OOS", "period", window.oos_run_id),
            (window.oos_bound_at, "OOS", "period", window.oos_run_id),
        )
        blockers: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for value, scope, stage, run_id in requirements:
            if value is not None or (scope, stage) in seen:
                continue
            seen.add((scope, stage))
            action = (
                "ADVANCE_WALK_FORWARD"
                if stage in {"train_experiment", "train_evaluation", "selection", "oos_run"}
                else f"CALCULATE_M14_{stage.upper()}_EXTERNALLY"
            )
            blocker: dict[str, Any] = {
                "code": "WALK_FORWARD_VALIDATION_NOT_READY",
                "window_no": window.window_no,
                "scope": scope,
                "missing_stage": stage,
                "action": action,
            }
            if run_id is not None:
                blocker["run_id"] = str(run_id)
            blockers.append(blocker)
        return blockers

    def _missing_train_analytics(
        self, window: PortfolioWalkForwardWindow
    ) -> list[dict[str, Any]]:
        trial_evaluation = self.db.scalar(
            select(PortfolioExperimentTrialEvaluation)
            .where(
                PortfolioExperimentTrialEvaluation.evaluation_id
                == window.train_evaluation_id,
                PortfolioExperimentTrialEvaluation.trial_id
                == window.selected_trial_id,
            )
            .execution_options(populate_existing=True)
        )
        if trial_evaluation is None:
            return []
        trial = self.db.get(PortfolioExperimentTrial, window.selected_trial_id)
        run_id = getattr(trial, "run_id", None)
        requirements = (
            (trial_evaluation.performance_id, "performance"),
            (trial_evaluation.risk_id, "risk"),
            (trial_evaluation.trade_id, "trade"),
            (trial_evaluation.period_id, "period"),
        )
        blockers: list[dict[str, Any]] = []
        for value, stage in requirements:
            if value is not None:
                continue
            blocker: dict[str, Any] = {
                "code": "WALK_FORWARD_VALIDATION_NOT_READY",
                "window_no": window.window_no,
                "scope": "TRAIN",
                "missing_stage": stage,
                "action": f"CALCULATE_M14_{stage.upper()}_EXTERNALLY",
            }
            if run_id is not None:
                blocker["run_id"] = str(run_id)
            blockers.append(blocker)
        return blockers

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
                    scope="OOS",
                    missing_stage="source_identity",
                    action="NO_AUTOMATIC_REPAIR",
                )
            sources.append(ValidationWindowSource(window, source, identity))
            identities.append(identity)
        if not sources:
            raise WalkForwardSourceError(
                "WALK_FORWARD_VALIDATION_NOT_READY",
                "study has no windows",
                scope="STUDY",
                missing_stage="train_experiment",
                action="ADVANCE_WALK_FORWARD",
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
        policy_snapshot = validation_policy_snapshot(self.config.validation_policy)
        policy_hash = validation_policy_hash(self.config.validation_policy)
        return WalkForwardValidationSource(
            study=study,
            windows=tuple(sources),
            source_hash=source_hash,
            walk_forward_config_hash=walk_forward_config_hash(self.config),
            policy_identity_version=WALK_FORWARD_POLICY_IDENTITY_VERSION,
            validation_policy_snapshot=policy_snapshot,
            validation_policy_hash=policy_hash,
            annualization_trade_days=annualization_trade_days,
            risk_free_rate_annual=risk_free_rate_annual,
        )

    def _window_source(
        self,
        study: PortfolioWalkForwardStudy,
        window: PortfolioWalkForwardWindow,
    ) -> tuple[WindowMetricInput, dict[str, Any], tuple[Any, ...]]:
        requirements = (
            (window.train_experiment_id, "TRAIN", "train_experiment", None),
            (window.train_evaluation_id, "TRAIN", "train_evaluation", None),
            (window.selected_trial_id, "TRAIN", "selection", None),
            (window.selected_parameter_hash, "TRAIN", "selection", None),
            (window.selected_parameter_values, "TRAIN", "selection", None),
            (window.selected_portfolio_config_hash, "TRAIN", "selection", None),
            (window.selected_portfolio_config_snapshot, "TRAIN", "selection", None),
            (window.oos_run_id, "OOS", "oos_run", None),
            (window.oos_performance_id, "OOS", "performance", window.oos_run_id),
            (window.oos_risk_id, "OOS", "risk", window.oos_run_id),
            (window.oos_trade_id, "OOS", "trade", window.oos_run_id),
            (window.oos_period_id, "OOS", "period", window.oos_run_id),
            (window.oos_bound_at, "OOS", "period", window.oos_run_id),
        )
        for value, scope, stage, run_id in requirements:
            if value is None:
                action = (
                    "ADVANCE_WALK_FORWARD"
                    if stage
                    in {"train_experiment", "train_evaluation", "selection", "oos_run"}
                    else f"CALCULATE_M14_{stage.upper()}_EXTERNALLY"
                )
                details: dict[str, Any] = {
                    "window_no": window.window_no,
                    "scope": scope,
                    "missing_stage": stage,
                    "action": action,
                }
                if run_id is not None:
                    details["run_id"] = str(run_id)
                raise WalkForwardSourceError(
                    "WALK_FORWARD_VALIDATION_NOT_READY",
                    "walk-forward validation source is incomplete",
                    **details,
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
        train_artifact_ids = (
            trial_evaluation.performance_id,
            trial_evaluation.risk_id,
            trial_evaluation.trade_id,
            trial_evaluation.period_id,
        )
        if any(value is None for value in train_artifact_ids):
            raise WalkForwardSourceError(
                "WALK_FORWARD_VALIDATION_NOT_READY",
                "selected train evaluation lacks a complete M14 bundle",
                window_no=window.window_no,
                scope="TRAIN",
                missing_stage=_first_missing_train_stage(trial_evaluation),
                action="CALCULATE_M14_EXTERNALLY",
            )
        train_performance = self.db.get(
            PortfolioPerformanceReport, trial_evaluation.performance_id
        )
        train_risk = self.db.get(
            PortfolioPerformanceRiskReport, trial_evaluation.risk_id
        )
        train_trade = self.db.get(
            PortfolioPerformanceTradeReport, trial_evaluation.trade_id
        )
        train_period = self.db.get(
            PortfolioPerformancePeriodReport, trial_evaluation.period_id
        )
        if any(
            artifact is None
            for artifact in (train_performance, train_risk, train_trade, train_period)
        ):
            self._invalid(
                "a selected train M14 artifact is missing",
                window.window_no,
                scope="TRAIN",
                missing_stage="source_identity",
                action="NO_AUTOMATIC_REPAIR",
            )
        assert train_performance and train_risk and train_trade and train_period
        self._validate_selection(
            study,
            window,
            experiment,
            report,
            trial,
            selected_run,
            trial_evaluation,
        )
        if (
            train_performance.run_id != selected_run.id
            or train_risk.run_id != selected_run.id
            or train_trade.run_id != selected_run.id
            or train_period.run_id != selected_run.id
            or train_risk.performance_id != train_performance.id
            or train_trade.performance_id != train_performance.id
            or train_period.performance_id != train_performance.id
            or train_period.risk_id != train_risk.id
            or train_period.trade_id != train_trade.id
        ):
            raise WalkForwardSourceError(
                "WALK_FORWARD_TRAIN_BUNDLE_MISMATCH",
                "selected train M14 artifacts do not share the exact run owner",
                window_no=window.window_no,
                scope="TRAIN",
                missing_stage="source_identity",
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
                scope="OOS",
                missing_stage="source_identity",
                action="NO_AUTOMATIC_REPAIR",
            )
        train_dates = tuple(
            self.db.scalars(
                select(PortfolioPerformanceDaily.trade_date)
                .where(
                    PortfolioPerformanceDaily.performance_id
                    == train_performance.id
                )
                .order_by(PortfolioPerformanceDaily.trade_date)
                .execution_options(populate_existing=True)
            ).all()
        )
        if train_dates != expected_train_dates:
            raise WalkForwardSourceError(
                "WALK_FORWARD_TRAIN_DATE_SET_MISMATCH",
                "train performance date set does not equal the frozen train date set",
                window_no=window.window_no,
                scope="TRAIN",
                missing_stage="date_set",
                expected_count=len(expected_train_dates),
                actual_count=len(train_dates),
                first_mismatch=_first_date_mismatch(
                    expected_train_dates, train_dates
                ),
                action="NO_AUTOMATIC_REPAIR",
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
            mismatched_dates = (
                strategy_dates
                if strategy_dates != expected_test_dates
                else benchmark_dates
            )
            raise WalkForwardSourceError(
                "WALK_FORWARD_OOS_DATE_SET_MISMATCH",
                "OOS daily date set does not equal the frozen test date set",
                window_no=window.window_no,
                scope="OOS",
                missing_stage="date_set",
                expected_count=len(expected_test_dates),
                actual_count=len(mismatched_dates),
                first_mismatch=_first_date_mismatch(
                    expected_test_dates, mismatched_dates
                ),
                action="NO_AUTOMATIC_REPAIR",
            )
        annualization = performance.result_summary.get("annualization_trade_days")
        if not isinstance(annualization, int) or annualization <= 0:
            raise WalkForwardSourceError(
                "WALK_FORWARD_OOS_BUNDLE_MISMATCH",
                "pinned performance artifact lacks annualization identity",
                window_no=window.window_no,
                scope="OOS",
                missing_stage="source_identity",
                action="NO_AUTOMATIC_REPAIR",
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
            "schema_version": "walk_forward_window_validation_identity_v1",
            "window_no": window.window_no,
            "train": {
                "dates": {
                    "hash": window.train_date_hash,
                    "count": len(expected_train_dates),
                },
                "experiment": {
                    "id": str(experiment.id),
                    "definition_hash": experiment.definition_hash,
                },
                "evaluation": {
                    "id": str(report.id),
                    "policy_hash": report.policy_hash,
                    "source_hash": report.source_hash,
                },
                "selection": {
                    "trial_id": str(trial.id),
                    "run_id": str(selected_run.id),
                    "parameter_hash": trial.parameter_hash,
                    "portfolio_config_hash": trial.portfolio_config_hash,
                },
                "m14": _bundle_identity(
                    train_performance, train_risk, train_trade, train_period
                ),
            },
            "oos": {
                "dates": {
                    "hash": window.test_date_hash,
                    "count": len(expected_test_dates),
                },
                "run": {
                    "id": str(oos_run.id),
                    "start_date": oos_run.start_date.isoformat(),
                    "end_date": oos_run.end_date.isoformat(),
                    "portfolio_config_hash": oos_run.portfolio_config_hash,
                    "source_strategy_config_hash": (
                        oos_run.source_strategy_config_hash
                    ),
                    "opportunity_config_hash": oos_run.opportunity_config_hash,
                    "execution_config_hash": oos_run.execution_config_hash,
                    "accounting_config_hash": oos_run.accounting_config_hash,
                },
                "m14": _bundle_identity(performance, risk, trade, period),
            },
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
            or evaluation.run_id != selected_run.id
            or evaluation.status != "EVALUATED"
            or not evaluation.feasible
            or not evaluation.shortlisted
            or evaluation.selection_rank != 1
        ):
            raise WalkForwardSourceError(
                "WALK_FORWARD_SELECTION_IDENTITY_MISMATCH",
                "selected train candidate does not match the frozen rank-1 evaluation",
                window_no=window.window_no,
                scope="TRAIN",
                missing_stage="source_identity",
                action="NO_AUTOMATIC_REPAIR",
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
                scope="TRAIN",
                missing_stage="source_identity",
                action="NO_AUTOMATIC_REPAIR",
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
                scope="TRAIN",
                missing_stage="source_identity",
                action="NO_AUTOMATIC_REPAIR",
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
                scope="OOS",
                missing_stage="source_identity",
                action="NO_AUTOMATIC_REPAIR",
            )

    def _invalid(
        self,
        message: str,
        window_no: int | None = None,
        **details: Any,
    ) -> None:
        if window_no is not None:
            details["window_no"] = window_no
        details.setdefault("scope", "SOURCE")
        details.setdefault("missing_stage", "source_identity")
        details.setdefault("action", "NO_AUTOMATIC_REPAIR")
        raise WalkForwardSourceError(
            "WALK_FORWARD_SOURCE_CHANGED", message, **details
        )


_SCOPE_ORDER = {"STUDY": 0, "SOURCE": 0, "TRAIN": 1, "OOS": 2}
_STAGE_ORDER = {
    "study": 0,
    "source_identity": 1,
    "train_experiment": 10,
    "train_evaluation": 20,
    "selection": 30,
    "oos_run": 40,
    "performance": 50,
    "risk": 60,
    "trade": 70,
    "period": 80,
    "date_set": 90,
}


def _source_blocker(message: str) -> dict[str, Any]:
    return {
        "code": "WALK_FORWARD_SOURCE_CHANGED",
        "window_no": None,
        "scope": "STUDY",
        "missing_stage": "source_identity",
        "action": "NO_AUTOMATIC_REPAIR",
        "reason": message,
    }


def _blocker_from_error(
    error: WalkForwardSourceError, window_no: int | None = None
) -> dict[str, Any]:
    blocker = {"code": error.code, **error.details}
    blocker.setdefault("window_no", window_no)
    blocker.setdefault("scope", "STUDY" if window_no is None else "SOURCE")
    blocker.setdefault("missing_stage", "source_identity")
    blocker.setdefault("action", "NO_AUTOMATIC_REPAIR")
    return blocker


def _sort_blockers(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(blocker: dict[str, Any]) -> tuple[int, int, int, int, str]:
        window_no = blocker.get("window_no")
        return (
            0 if window_no is None else 1,
            int(window_no or 0),
            _SCOPE_ORDER.get(str(blocker.get("scope")), 99),
            _STAGE_ORDER.get(str(blocker.get("missing_stage")), 99),
            str(blocker.get("code", "")),
        )

    return sorted(blockers, key=key)


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


def _first_missing_train_stage(
    evaluation: PortfolioExperimentTrialEvaluation,
) -> str:
    for name, value in (
        ("train_performance", evaluation.performance_id),
        ("train_risk", evaluation.risk_id),
        ("train_trade", evaluation.trade_id),
        ("train_period", evaluation.period_id),
    ):
        if value is None:
            return name
    return "source_identity"


def _first_date_mismatch(
    expected: tuple[date, ...], actual: tuple[date, ...]
) -> dict[str, str | int | None] | None:
    for index, (expected_date, actual_date) in enumerate(
        zip(expected, actual, strict=False)
    ):
        if expected_date != actual_date:
            return {
                "index": index,
                "expected": expected_date.isoformat(),
                "actual": actual_date.isoformat(),
            }
    if len(expected) == len(actual):
        return None
    index = min(len(expected), len(actual))
    return {
        "index": index,
        "expected": expected[index].isoformat() if index < len(expected) else None,
        "actual": actual[index].isoformat() if index < len(actual) else None,
    }


def _bundle_identity(
    performance: PortfolioPerformanceReport,
    risk: PortfolioPerformanceRiskReport,
    trade: PortfolioPerformanceTradeReport,
    period: PortfolioPerformancePeriodReport,
) -> dict[str, Any]:
    return {
        "performance": {
            "id": str(performance.id),
            "version": performance.performance_version,
            "config_hash": performance.performance_config_hash,
            "source_hash": performance.source_hash,
        },
        "risk": {
            "id": str(risk.id),
            "version": risk.risk_version,
            "config_hash": risk.risk_config_hash,
            "source_hash": risk.risk_source_hash,
            "benchmark_source_hash": risk.benchmark_source_hash,
        },
        "trade": {
            "id": str(trade.id),
            "version": trade.trade_version,
            "config_hash": trade.trade_config_hash,
            "source_hash": trade.trade_source_hash,
        },
        "period": {
            "id": str(period.id),
            "version": period.period_version,
            "config_hash": period.period_config_hash,
            "source_hash": period.period_source_hash,
        },
    }
