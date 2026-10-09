import uuid
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from math import prod
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.experiment_evaluation_config import EvaluationPolicyConfig
from app.core.portfolio_config import PortfolioConfig
from app.core.walk_forward_config import WALK_FORWARD_VERSION
from app.domain.experiment import ExperimentGridError, expand_grid
from app.domain.walk_forward import (
    calculate_parameter_stability,
    calculate_validation_metrics,
)
from app.domain.walk_forward.windows import WindowPlanError
from app.models.experiment import PortfolioExperiment, PortfolioExperimentTrial
from app.models.experiment_evaluation import (
    PortfolioExperimentEvaluationReport,
    PortfolioExperimentTrialEvaluation,
)
from app.models.job import JobRun
from app.models.performance import PortfolioPerformanceDaily
from app.models.portfolio import PortfolioBacktestRun
from app.models.walk_forward import (
    PortfolioWalkForwardParameterStability,
    PortfolioWalkForwardStudy,
    PortfolioWalkForwardValidationReport,
    PortfolioWalkForwardWindow,
    PortfolioWalkForwardWindowValidation,
)
from app.repositories.walk_forward import WalkForwardRepository
from app.services.experiment.application import (
    ExperimentApplicationError,
    ExperimentApplicationService,
)
from app.services.experiment_evaluation.application import (
    ExperimentEvaluationApplicationError,
    ExperimentEvaluationApplicationService,
    ExperimentEvaluationConflictError,
)
from app.services.performance.analytics_bundle import (
    AnalyticsArtifactBundle,
    AnalyticsArtifactBundleResolver,
    AnalyticsBundleError,
)
from app.services.portfolio.backtest_application import (
    BacktestApplicationService,
    BacktestConflictError,
)
from app.services.portfolio.run_factory import BacktestRunFactory
from app.services.walk_forward.identity import (
    definition_hash,
    study_lock_key,
    validation_lock_key,
)
from app.services.walk_forward.orchestration import (
    WindowProjection,
    project_window_state,
)
from app.services.walk_forward.planner import WalkForwardPlanner
from app.services.walk_forward.source import (
    WalkForwardSourceError,
    WalkForwardValidationSource,
    WalkForwardValidationSourceProvider,
)

WALK_FORWARD_VALIDATION_JOB_TYPE = "portfolio_walk_forward_validation"
_ACTIVE_JOB_STATUSES = {"QUEUED", "RUNNING"}
_TERMINAL_RUN_STATUSES = {"SUCCESS", "FAILED", "CANCELLED"}


class WalkForwardApplicationError(RuntimeError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        self.code = code
        self.details = details
        super().__init__(message)


class WalkForwardConflictError(WalkForwardApplicationError):
    def __init__(self, message: str, *, job_id: uuid.UUID | None = None) -> None:
        self.job_id = job_id
        super().__init__("WALK_FORWARD_VALIDATION_CONFLICT", message)


class WalkForwardOwnershipError(RuntimeError):
    code = "WALK_FORWARD_VALIDATION_OWNERSHIP_LOST"


class WalkForwardCancelledError(WalkForwardApplicationError):
    def __init__(self, message: str = "walk-forward validation was cancelled") -> None:
        super().__init__("WALK_FORWARD_CANCELLED", message)


@dataclass(frozen=True)
class _ValidationArtifactDraft:
    report: PortfolioWalkForwardValidationReport
    windows: list[PortfolioWalkForwardWindowValidation]
    stability: list[PortfolioWalkForwardParameterStability]


class WalkForwardApplicationService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        repository: WalkForwardRepository | None = None,
        source_provider: WalkForwardValidationSourceProvider | None = None,
        before_terminal_hook: Callable[[JobRun, PortfolioWalkForwardValidationReport], None]
        | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        if self.settings.walk_forward_config is None:
            raise RuntimeError("walk-forward configuration is not loaded")
        self.config = self.settings.walk_forward_config
        self.repository = repository or WalkForwardRepository(db)
        self.planner = WalkForwardPlanner(db, self.config)
        self.experiments = ExperimentApplicationService(db, settings=self.settings)
        self.evaluations = ExperimentEvaluationApplicationService(
            db, settings=self.settings
        )
        self.bundle_resolver = AnalyticsArtifactBundleResolver(db)
        self.source_provider = source_provider or WalkForwardValidationSourceProvider(
            db, self.config
        )
        self.before_terminal_hook = before_terminal_hook

    def create(
        self,
        *,
        name: str | None,
        start_date: date,
        end_date: date,
        mode: str,
        train_trade_days: int,
        test_trade_days: int,
        step_trade_days: int,
        initial_cash: Decimal | None,
        benchmark_code: str | None,
        grid: Mapping[str, Sequence[Any]],
        train_evaluation_policy: EvaluationPolicyConfig | None,
    ) -> dict[str, Any]:
        try:
            plan, frozen_calendar_hash = self.planner.plan(
                requested_start_date=start_date,
                requested_end_date=end_date,
                mode=mode,
                train_trade_days=train_trade_days,
                test_trade_days=test_trade_days,
                step_trade_days=step_trade_days,
            )
            frozen = self.experiments.freeze_current_base(
                initial_cash=initial_cash,
                benchmark_code=benchmark_code,
            )
            expanded = expand_grid(
                base_portfolio=PortfolioConfig.model_validate(
                    frozen.config_snapshot["portfolio"]
                ),
                grid=grid,
                max_trials=self.experiments.experiment_config.max_trials,
                max_values_per_parameter=(
                    self.experiments.experiment_config.max_values_per_parameter
                ),
            )
            policy_snapshot, policy_hash = self.evaluations.normalize_policy(
                train_evaluation_policy
            )
        except WindowPlanError as exc:
            raise WalkForwardApplicationError(exc.code, str(exc)) from exc
        except ExperimentApplicationError as exc:
            raise WalkForwardApplicationError(
                "WALK_FORWARD_CONFIG_INVALID", str(exc)
            ) from exc
        except (ExperimentGridError, ValidationError, ValueError) as exc:
            code = getattr(exc, "code", "WALK_FORWARD_CONFIG_INVALID")
            if str(code).startswith("EXPERIMENT_"):
                code = "WALK_FORWARD_CONFIG_INVALID"
            raise WalkForwardApplicationError(str(code), str(exc)) from exc

        normalized_mode = mode.upper()
        definition = {
            "walk_forward_version": WALK_FORWARD_VERSION,
            "mode": normalized_mode,
            "requested_start_date": start_date.isoformat(),
            "requested_end_date": end_date.isoformat(),
            "exchange": self.config.exchange,
            "train_trade_days": train_trade_days,
            "test_trade_days": test_trade_days,
            "step_trade_days": step_trade_days,
            "calendar_hash": frozen_calendar_hash,
            "windows": [
                {
                    "window_no": item.window_no,
                    "train_dates": [value.isoformat() for value in item.train_trade_dates],
                    "test_dates": [value.isoformat() for value in item.test_trade_dates],
                    "train_date_hash": item.train_date_hash,
                    "test_date_hash": item.test_date_hash,
                }
                for item in plan.windows
            ],
            "initial_cash": _decimal(frozen.initial_cash),
            "benchmark_code": frozen.benchmark_code,
            "parameter_space": expanded.parameter_space,
            "parameter_space_hash": expanded.parameter_space_hash,
            "train_policy": policy_snapshot,
            "train_policy_hash": policy_hash,
            "base_identities": frozen.identities,
            "base_config_snapshot": frozen.config_snapshot,
        }
        study_id = uuid.uuid4()
        study = PortfolioWalkForwardStudy(
            id=study_id,
            name=name,
            walk_forward_version=WALK_FORWARD_VERSION,
            mode=normalized_mode,
            exchange=self.config.exchange,
            requested_start_date=start_date,
            requested_end_date=end_date,
            train_trade_days=train_trade_days,
            test_trade_days=test_trade_days,
            step_trade_days=step_trade_days,
            window_count=len(plan.windows),
            unused_tail_trade_days=plan.unused_tail_trade_days,
            calendar_hash=frozen_calendar_hash,
            initial_cash=frozen.initial_cash,
            benchmark_code=frozen.benchmark_code,
            parameter_space=expanded.parameter_space,
            parameter_space_hash=expanded.parameter_space_hash,
            train_policy_snapshot=policy_snapshot,
            train_policy_hash=policy_hash,
            base_config_snapshot=frozen.config_snapshot,
            definition_hash=definition_hash(definition),
            **frozen.identities,
        )
        rows = [
            PortfolioWalkForwardWindow(
                study_id=study_id,
                window_no=item.window_no,
                train_start_date=item.train_start_date,
                train_end_date=item.train_end_date,
                test_start_date=item.test_start_date,
                test_end_date=item.test_end_date,
                train_trade_days=len(item.train_trade_dates),
                test_trade_days=len(item.test_trade_dates),
                train_trade_dates=[value.isoformat() for value in item.train_trade_dates],
                test_trade_dates=[value.isoformat() for value in item.test_trade_dates],
                train_date_hash=item.train_date_hash,
                test_date_hash=item.test_date_hash,
            )
            for item in plan.windows
        ]
        try:
            self.repository.create(study, rows)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            raise WalkForwardApplicationError(
                "WALK_FORWARD_CONFIG_INVALID", "walk-forward study could not be persisted"
            ) from exc
        return self.get(study_id)

    def get(self, study_id: uuid.UUID) -> dict[str, Any]:
        study = self._study(study_id)
        windows = self._window_payloads(study)
        progress = _progress(windows)
        return {
            **_study_payload(study),
            "progress": progress,
            "next_required_actions": self._required_actions(study, windows),
        }

    def windows(
        self,
        study_id: uuid.UUID,
        *,
        state: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        study = self._study(study_id)
        rows = self._window_payloads(study)
        if state is not None:
            rows = [row for row in rows if row["state"] == state]
        return rows[offset : offset + limit], len(rows)

    def advance(self, study_id: uuid.UUID) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        for _ in range(self.config.max_actions_per_advance):
            progressed = False
            study = self._study(study_id)
            for window in self.repository.list_windows(study_id):
                action = self._advance_window(study_id, window.window_no)
                if action is not None:
                    actions.append(action)
                    progressed = True
                    break
            if not progressed:
                break
        study = self._study(study_id)
        windows = self._window_payloads(study)
        return {
            "study_id": str(study_id),
            "actions_performed": actions,
            "blocked_windows": [
                {
                    "window_no": row["window_no"],
                    "state": row["state"],
                    "error_code": row.get("error_code"),
                }
                for row in windows
                if row.get("blocked")
            ],
            "required_actions": self._required_actions(study, windows),
            "progress": _progress(windows),
        }

    def cancel(self, study_id: uuid.UUID) -> dict[str, Any]:
        self._study_lock(study_id)
        study = self.repository.get_for_update(study_id)
        if study is None:
            raise WalkForwardApplicationError(
                "WALK_FORWARD_NOT_FOUND", "walk-forward study not found"
            )
        study.cancel_requested = True
        study.updated_at = datetime.now(UTC)
        validation_job_candidates = list(
            self.db.execute(
                select(JobRun.id, JobRun.job_metadata)
                .where(
                    JobRun.job_type == WALK_FORWARD_VALIDATION_JOB_TYPE,
                    JobRun.status.in_(_ACTIVE_JOB_STATUSES),
                    JobRun.job_metadata.contains({"study_id": str(study_id)}),
                )
                .order_by(JobRun.id)
            ).all()
        )
        for source_hash in sorted(
            {
                str(dict(metadata or {}).get("source_hash"))
                for _, metadata in validation_job_candidates
                if dict(metadata or {}).get("source_hash")
            }
        ):
            self._validation_lock(study_id, source_hash)
        candidate_ids = [job_id for job_id, _ in validation_job_candidates]
        validation_jobs = list(
            self.db.scalars(
                select(JobRun)
                .where(
                    JobRun.id.in_(candidate_ids),
                    JobRun.status.in_(_ACTIVE_JOB_STATUSES),
                )
                .order_by(JobRun.id)
                .with_for_update()
            ).all()
        )
        now = datetime.now(UTC)
        for job in validation_jobs:
            metadata = dict(job.job_metadata or {})
            if job.status == "QUEUED":
                job.status = "CANCELLED"
                job.finished_at = now
                job.step = "cancelled by walk-forward study stop gate"
                metadata["stage"] = "CANCELLED"
            else:
                job.cancel_requested = True
                job.step = "walk-forward validation cancellation requested"
                metadata["stage"] = "CANCELLATION_REQUESTED"
            job.job_metadata = metadata
            self.db.add(job)
        self.db.commit()
        cancelled: list[dict[str, str]] = []
        for window in self.repository.list_windows(study_id):
            if window.train_experiment_id:
                experiment = self.db.get(
                    PortfolioExperiment, window.train_experiment_id
                )
                if experiment is not None and self._train_active(experiment.id):
                    try:
                        self.experiments.cancel(experiment.id)
                        cancelled.append(
                            {"scope": "TRAIN", "id": str(experiment.id)}
                        )
                    except ExperimentApplicationError:
                        self.db.rollback()
            if window.oos_run_id:
                run = self.db.get(PortfolioBacktestRun, window.oos_run_id)
                if run is not None and run.status in {"CREATED", "RUNNING"}:
                    try:
                        BacktestApplicationService(
                            self.db, settings=self.settings
                        ).cancel(run.id)
                        cancelled.append({"scope": "OOS", "id": str(run.id)})
                    except (BacktestConflictError, LookupError):
                        self.db.rollback()
        return {
            "study_id": str(study_id),
            "cancel_requested": True,
            "cancelled_children": cancelled,
            "validation_jobs": [
                {"job_id": str(job.id), "status": job.status}
                for job in validation_jobs
            ],
        }

    def validation_readiness(self, study_id: uuid.UUID) -> dict[str, Any]:
        self._study(study_id)
        return self.source_provider.readiness(study_id)

    def queue_validation(self, study_id: uuid.UUID) -> JobRun:
        self._study_lock(study_id)
        study = self.repository.get_for_update(study_id)
        if study is None:
            raise WalkForwardApplicationError(
                "WALK_FORWARD_NOT_FOUND", "walk-forward study not found"
            )
        if study.cancel_requested:
            raise WalkForwardApplicationError(
                "WALK_FORWARD_CANCELLED", "cancelled study cannot queue validation"
            )
        source = self._load_source(study_id)
        self._validation_lock(study_id, source.source_hash)
        active = self.db.scalar(
            select(JobRun)
            .where(
                JobRun.job_type == WALK_FORWARD_VALIDATION_JOB_TYPE,
                JobRun.status.in_(_ACTIVE_JOB_STATUSES),
                JobRun.job_metadata.contains(
                    {
                        "study_id": str(study_id),
                        "source_hash": source.source_hash,
                    }
                ),
            )
            .order_by(JobRun.started_at.desc(), JobRun.id.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
        if active is not None:
            raise WalkForwardConflictError(
                "walk-forward validation already has an active job",
                job_id=active.id,
            )
        job = JobRun(
            job_type=WALK_FORWARD_VALIDATION_JOB_TYPE,
            target_trade_date=None,
            status="QUEUED",
            step="queued for walk-forward validation",
            row_count=0,
            cancel_requested=False,
            job_metadata={
                "study_id": str(study_id),
                "walk_forward_version": WALK_FORWARD_VERSION,
                "walk_forward_config_hash": source.walk_forward_config_hash,
                "validation_policy_hash": source.validation_policy_hash,
                "source_hash": source.source_hash,
                "stage": "QUEUED",
            },
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def run_validation_job(
        self, job_id: uuid.UUID
    ) -> tuple[PortfolioWalkForwardValidationReport, bool]:
        job = self.db.scalar(
            select(JobRun)
            .where(JobRun.id == job_id)
            .execution_options(populate_existing=True)
        )
        if (
            job is None
            or job.job_type != WALK_FORWARD_VALIDATION_JOB_TYPE
            or job.status != "RUNNING"
            or not job.worker_id
        ):
            raise WalkForwardOwnershipError(
                "walk-forward validation job is not owned by a running worker"
            )
        metadata = dict(job.job_metadata or {})
        try:
            study_id = uuid.UUID(str(metadata["study_id"]))
            queued_source_hash = str(metadata["source_hash"])
        except (KeyError, TypeError, ValueError) as exc:
            raise WalkForwardOwnershipError("validation job identity is invalid") from exc
        source = self._load_source(study_id)
        if (
            metadata.get("walk_forward_version") != WALK_FORWARD_VERSION
            or metadata.get("walk_forward_config_hash")
            != source.walk_forward_config_hash
            or queued_source_hash != source.source_hash
        ):
            raise WalkForwardApplicationError(
                "WALK_FORWARD_SOURCE_CHANGED",
                "walk-forward source changed after validation was queued",
            )
        draft = self._build_validation_artifact(source)
        if self.before_terminal_hook:
            self.before_terminal_hook(job, draft.report)
        worker_id = job.worker_id

        # Terminal fence lock order: Study advisory/row -> validation identity
        # advisory -> Job row.  The expensive calculation above holds no locks.
        self._study_lock(study_id)
        study = self.repository.get_for_update(study_id)
        if study is None:
            self.db.rollback()
            raise WalkForwardOwnershipError("walk-forward study disappeared")
        self._validation_lock(study_id, queued_source_hash)
        terminal = self.db.scalar(
            select(JobRun)
            .where(JobRun.id == job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if (
            terminal is None
            or terminal.status != "RUNNING"
            or terminal.worker_id != worker_id
            or dict(terminal.job_metadata or {}).get("source_hash")
            != queued_source_hash
        ):
            self.db.rollback()
            raise WalkForwardOwnershipError(
                "walk-forward validation worker no longer owns terminal update"
            )
        if study.cancel_requested or terminal.cancel_requested:
            terminal.status = "CANCELLED"
            terminal.finished_at = datetime.now(UTC)
            terminal.step = "cancelled before walk-forward validation terminal commit"
            terminal.job_metadata = {
                **dict(terminal.job_metadata or {}),
                "stage": "CANCELLED",
                "error_code": "WALK_FORWARD_CANCELLED",
            }
            self.db.add(terminal)
            self.db.commit()
            raise WalkForwardCancelledError()
        fenced_source = self._load_source(study_id)
        if (
            fenced_source.source_hash != queued_source_hash
            or fenced_source.walk_forward_config_hash
            != source.walk_forward_config_hash
        ):
            self.db.rollback()
            raise WalkForwardApplicationError(
                "WALK_FORWARD_SOURCE_CHANGED",
                "walk-forward source changed before terminal commit",
            )
        existing = self.repository.find_validation(
            study_id=study_id,
            walk_forward_version=WALK_FORWARD_VERSION,
            walk_forward_config_hash=source.walk_forward_config_hash,
            source_hash=queued_source_hash,
        )
        reused = existing is not None
        report = existing or draft.report
        if existing is None:
            self.repository.add_validation(
                draft.report, draft.windows, draft.stability
            )
        terminal.status = "SUCCESS"
        terminal.finished_at = datetime.now(UTC)
        terminal.step = "walk-forward validation complete"
        terminal.row_count = report.window_count
        terminal.job_metadata = {
            **dict(terminal.job_metadata or {}),
            "stage": "SUCCESS",
            "validation_id": str(report.id),
            "reused": reused,
        }
        self.db.add(terminal)
        self.db.commit()
        self.db.refresh(report)
        return report, reused

    def calculate_now(
        self, study_id: uuid.UUID
    ) -> tuple[PortfolioWalkForwardValidationReport, bool]:
        report, reused = self._calculate_uncommitted(self._load_source(study_id))
        self.db.commit()
        self.db.refresh(report)
        return report, reused

    def validation_detail(
        self, study_id: uuid.UUID, validation_id: uuid.UUID
    ) -> dict[str, Any]:
        report = self._validation(study_id, validation_id)
        return _validation_payload(report)

    def validation_history(
        self, study_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        self._study(study_id)
        rows, total = self.repository.validation_history(
            study_id, limit=limit, offset=offset
        )
        return [_validation_payload(row) for row in rows], total

    def validation_windows(
        self,
        study_id: uuid.UUID,
        validation_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        self._validation(study_id, validation_id)
        rows, total = self.repository.window_validation_page(
            validation_id, limit=limit, offset=offset
        )
        payloads = [_model_payload(row, {"created_at"}) for row in rows]
        for payload in payloads:
            payload["identity"] = payload["identity_snapshot"]
        return payloads, total

    def validation_stability(
        self, study_id: uuid.UUID, validation_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        self._validation(study_id, validation_id)
        return [
            _model_payload(row, {"created_at", "study_id", "validation_id"})
            for row in self.repository.stability(validation_id)
        ]

    def _advance_window(
        self, study_id: uuid.UUID, window_no: int
    ) -> dict[str, Any] | None:
        self._study_lock(study_id)
        study = self.repository.get_for_update(study_id)
        window = self.repository.get_window_for_update(study_id, window_no)
        if study is None or window is None:
            raise WalkForwardApplicationError(
                "WALK_FORWARD_NOT_FOUND", "walk-forward study or window not found"
            )
        if study.cancel_requested:
            raise WalkForwardApplicationError(
                "WALK_FORWARD_CANCELLED", "cancelled study cannot advance"
            )
        frozen_experiments = self._frozen_experiment_service(study)
        if window.train_experiment_id is None:
            experiment = frozen_experiments.create_from_frozen_base(
                name=f"{study.name or 'walk-forward'} / train-{window.window_no:03d}",
                start_date=window.train_start_date,
                end_date=window.train_end_date,
                grid=study.parameter_space,
                base_config_snapshot=study.base_config_snapshot,
                base_identities=_study_base_identities(study),
                commit=False,
            )
            if experiment.parameter_space_hash != study.parameter_space_hash:
                self.db.rollback()
                raise WalkForwardApplicationError(
                    "WALK_FORWARD_TRAIN_EXPERIMENT_MISMATCH",
                    "frozen train experiment parameter identity changed",
                )
            window.train_experiment_id = experiment.id
            self.db.add(window)
            self.db.commit()
            return {"window_no": window_no, "action": "CREATE_TRAIN_EXPERIMENT"}

        experiment = self.db.get(PortfolioExperiment, window.train_experiment_id)
        if experiment is None:
            raise WalkForwardApplicationError(
                "WALK_FORWARD_TRAIN_EXPERIMENT_MISMATCH",
                "bound train experiment is missing",
            )
        self._validate_train_experiment(study, window, experiment)
        if experiment.started_at is None:
            try:
                frozen_experiments.start(experiment.id)
            except ExperimentApplicationError as exc:
                raise WalkForwardApplicationError(
                    "WALK_FORWARD_TRAIN_EXPERIMENT_MISMATCH", str(exc)
                ) from exc
            return {"window_no": window_no, "action": "START_TRAIN_EXPERIMENT"}
        if self._train_active(experiment.id):
            return None

        policy = self._study_policy(study)
        readiness = self.evaluations.readiness(experiment.id)
        if not readiness.get("ready"):
            return None
        try:
            report = self.evaluations.resolve_current_artifact(experiment.id, policy)
        except ExperimentEvaluationApplicationError as exc:
            raise WalkForwardApplicationError(
                "WALK_FORWARD_TRAIN_EXPERIMENT_MISMATCH", str(exc)
            ) from exc
        if report is None:
            if self._active_evaluation_job(experiment.id, study.train_policy_hash):
                return None
            try:
                job = self.evaluations.queue_calculation(experiment.id, policy)
            except ExperimentEvaluationConflictError:
                self.db.rollback()
                return None
            return {
                "window_no": window_no,
                "action": "QUEUE_TRAIN_EVALUATION",
                "job_id": str(job.id),
            }
        if window.train_evaluation_id is None:
            if report.selected_trial_id is None or report.selected_run_id is None:
                return None
            self._freeze_selection(window, experiment, report)
            self.db.commit()
            return {"window_no": window_no, "action": "FREEZE_SELECTION"}

        self._validate_frozen_selection(window, experiment)
        if window.oos_run_id is None:
            run = BacktestRunFactory.build(
                name=f"{study.name or 'walk-forward'} / oos-{window.window_no:03d}",
                start_date=window.test_start_date,
                end_date=window.test_end_date,
                strategy_snapshot=experiment.base_config_snapshot["strategy"],
                opportunity_snapshot=experiment.base_config_snapshot["opportunity"],
                portfolio_snapshot=window.selected_portfolio_config_snapshot,
                execution_snapshot=experiment.base_config_snapshot["execution"],
                accounting_snapshot=experiment.base_config_snapshot["accounting"],
                algo_version=study.base_algo_version,
                opportunity_calc_version=study.base_opportunity_calc_version,
                portfolio_version=study.base_portfolio_version,
                execution_version=study.base_execution_version,
                accounting_version=study.base_accounting_version,
                backtest_engine_version=study.base_backtest_engine_version,
            )
            self.repository.add_run(run)
            window.oos_run_id = run.id
            self.db.add(window)
            try:
                _, job = BacktestApplicationService(
                    self.db, settings=self._frozen_settings(study)
                ).execute(run.id)
            except (BacktestConflictError, LookupError, ValueError) as exc:
                self.db.rollback()
                raise WalkForwardApplicationError(
                    "WALK_FORWARD_OOS_IDENTITY_MISMATCH", str(exc)
                ) from exc
            return {
                "window_no": window_no,
                "action": "CREATE_AND_QUEUE_OOS_RUN",
                "run_id": str(run.id),
                "job_id": str(job.id),
            }
        run = self.db.get(PortfolioBacktestRun, window.oos_run_id)
        if run is None:
            raise WalkForwardApplicationError(
                "WALK_FORWARD_OOS_IDENTITY_MISMATCH", "bound OOS run is missing"
            )
        self._validate_oos_run(study, window, experiment, run)
        if run.status in {"CREATED", "RUNNING"}:
            return None
        if run.status == "FAILED":
            return None
        if run.status == "CANCELLED":
            return None
        if window.oos_bound_at is not None:
            return None
        try:
            bundle = self.bundle_resolver.resolve(run.id, require_period=True)
        except AnalyticsBundleError:
            return None
        self._pin_oos_bundle(window, bundle)
        self.db.commit()
        return {"window_no": window_no, "action": "PIN_OOS_ANALYTICS"}

    def _freeze_selection(
        self,
        window: PortfolioWalkForwardWindow,
        experiment: PortfolioExperiment,
        report: PortfolioExperimentEvaluationReport,
    ) -> None:
        evaluation = self.db.scalar(
            select(PortfolioExperimentTrialEvaluation)
            .where(
                PortfolioExperimentTrialEvaluation.evaluation_id == report.id,
                PortfolioExperimentTrialEvaluation.trial_id
                == report.selected_trial_id,
            )
            .execution_options(populate_existing=True)
        )
        trial = self.db.get(PortfolioExperimentTrial, report.selected_trial_id)
        if (
            evaluation is None
            or trial is None
            or report.experiment_id != experiment.id
            or trial.experiment_id != experiment.id
            or evaluation.experiment_id != experiment.id
            or evaluation.status != "EVALUATED"
            or not evaluation.feasible
            or not evaluation.shortlisted
            or evaluation.selection_rank != 1
            or report.selected_run_id != trial.run_id
        ):
            raise WalkForwardApplicationError(
                "WALK_FORWARD_SELECTION_IDENTITY_MISMATCH",
                "evaluation selection is not the frozen rank-1 train candidate",
            )
        window.train_evaluation_id = report.id
        window.selected_trial_id = trial.id
        window.selected_parameter_hash = trial.parameter_hash
        window.selected_parameter_values = dict(trial.parameter_values)
        window.selected_portfolio_config_hash = trial.portfolio_config_hash
        window.selected_portfolio_config_snapshot = dict(
            trial.portfolio_config_snapshot
        )
        window.selected_at = datetime.now(UTC)
        self.db.add(window)

    def _pin_oos_bundle(
        self,
        window: PortfolioWalkForwardWindow,
        bundle: AnalyticsArtifactBundle,
    ) -> None:
        assert bundle.period is not None
        dates = tuple(
            self.db.scalars(
                select(PortfolioPerformanceDaily.trade_date)
                .where(
                    PortfolioPerformanceDaily.performance_id == bundle.performance.id
                )
                .order_by(PortfolioPerformanceDaily.trade_date)
            ).all()
        )
        expected = tuple(date.fromisoformat(value) for value in window.test_trade_dates)
        if dates != expected:
            raise WalkForwardApplicationError(
                "WALK_FORWARD_OOS_DATE_SET_MISMATCH",
                "OOS performance date set does not match the frozen test dates",
            )
        if window.oos_bound_at is not None:
            existing = (
                window.oos_performance_id,
                window.oos_risk_id,
                window.oos_trade_id,
                window.oos_period_id,
            )
            incoming = (
                bundle.performance.id,
                bundle.risk.id,
                bundle.trade.id,
                bundle.period.id,
            )
            if existing != incoming:
                raise WalkForwardApplicationError(
                    "WALK_FORWARD_OOS_BUNDLE_MISMATCH",
                    "a pinned OOS bundle cannot be replaced",
                )
            return
        window.oos_performance_id = bundle.performance.id
        window.oos_risk_id = bundle.risk.id
        window.oos_trade_id = bundle.trade.id
        window.oos_period_id = bundle.period.id
        window.oos_bound_at = datetime.now(UTC)
        self.db.add(window)

    def _calculate_uncommitted(
        self, source: WalkForwardValidationSource
    ) -> tuple[PortfolioWalkForwardValidationReport, bool]:
        if source.study.cancel_requested:
            raise WalkForwardCancelledError(
                "cancelled study cannot calculate a new validation artifact"
            )
        self._validation_lock(source.study.id, source.source_hash)
        existing = self.repository.find_validation(
            study_id=source.study.id,
            walk_forward_version=WALK_FORWARD_VERSION,
            walk_forward_config_hash=source.walk_forward_config_hash,
            source_hash=source.source_hash,
        )
        if existing is not None:
            return existing, True
        draft = self._build_validation_artifact(source)
        self.repository.add_validation(
            draft.report, draft.windows, draft.stability
        )
        return draft.report, False

    def _build_validation_artifact(
        self, source: WalkForwardValidationSource
    ) -> _ValidationArtifactDraft:
        metric_inputs = tuple(item.metric_input for item in source.windows)
        metrics = calculate_validation_metrics(
            metric_inputs,
            annualization_trade_days=source.annualization_trade_days,
            risk_free_rate_annual=source.risk_free_rate_annual,
            minimum_observations=(
                self.config.validation_policy.minimum_stitched_oos_observations
            ),
            short_sample_warning_trade_days=(
                self.config.validation_policy.short_oos_warning_trade_days
            ),
        )
        stability = calculate_parameter_stability(
            tuple(
                (
                    item.metric_input.selected_parameter_hash,
                    item.metric_input.selected_parameter_values,
                )
                for item in source.windows
            ),
            frequent_switch_rate_threshold=(
                self.config.validation_policy.frequent_parameter_switch_rate_threshold
            ),
            low_dominant_parameter_rate_threshold=(
                self.config.validation_policy.low_dominant_parameter_rate_threshold
            ),
        )
        report_id = uuid.uuid4()
        report = PortfolioWalkForwardValidationReport(
            id=report_id,
            study_id=source.study.id,
            walk_forward_version=WALK_FORWARD_VERSION,
            walk_forward_config_hash=source.walk_forward_config_hash,
            validation_policy_snapshot=source.validation_policy_snapshot,
            validation_policy_hash=source.validation_policy_hash,
            source_hash=source.source_hash,
            status="SUCCESS",
            window_count=metrics.window_count,
            total_oos_trade_days=metrics.total_oos_trade_days,
            stitched_oos_final_nav=metrics.stitched_oos_final_nav,
            stitched_oos_cumulative_return=metrics.stitched_oos_cumulative_return,
            stitched_oos_annualized_return=metrics.stitched_oos_annualized_return,
            stitched_oos_max_drawdown=metrics.stitched_oos_max_drawdown,
            stitched_oos_annualized_volatility=(
                metrics.stitched_oos_annualized_volatility
            ),
            stitched_oos_sharpe_ratio=metrics.stitched_oos_sharpe_ratio,
            stitched_benchmark_final_nav=metrics.stitched_benchmark_final_nav,
            stitched_benchmark_cumulative_return=(
                metrics.stitched_benchmark_cumulative_return
            ),
            stitched_excess_cumulative_return=(
                metrics.stitched_excess_cumulative_return
            ),
            positive_oos_window_count=metrics.positive_oos_window_count,
            positive_oos_window_rate=metrics.positive_oos_window_rate,
            mean_oos_annualized_return=metrics.mean_oos_annualized_return,
            median_oos_annualized_return=metrics.median_oos_annualized_return,
            mean_return_degradation=metrics.mean_return_degradation,
            median_return_degradation=metrics.median_return_degradation,
            mean_drawdown_worsening=metrics.mean_drawdown_worsening,
            median_drawdown_worsening=metrics.median_drawdown_worsening,
            unique_selected_parameter_hash_count=(
                stability.unique_selected_parameter_hash_count
            ),
            dominant_parameter_hash=stability.dominant_parameter_hash,
            dominant_parameter_hash_count=stability.dominant_parameter_hash_count,
            dominant_parameter_hash_rate=stability.dominant_parameter_hash_rate,
            transition_count=stability.transition_count,
            switch_count=stability.switch_count,
            switch_rate=stability.switch_rate,
            warnings=list(dict.fromkeys((*metrics.warnings, *stability.warnings))),
            result_summary={
                "semantics": (
                    "time-separated out-of-sample validation evidence for research use"
                ),
                "annualization_trade_days": source.annualization_trade_days,
                "risk_free_rate_annual": _decimal(source.risk_free_rate_annual),
                "stitched_daily": [
                    {
                        "trade_date": row.trade_date.isoformat(),
                        "strategy_daily_return": _decimal(row.strategy_return),
                        "benchmark_daily_return": _decimal(row.benchmark_return),
                        "strategy_nav": _decimal(row.strategy_nav),
                        "benchmark_nav": _decimal(row.benchmark_nav),
                        "relative_nav": _decimal(row.relative_nav),
                    }
                    for row in metrics.stitched_daily
                ],
            },
        )
        source_by_no = {item.window.window_no: item for item in source.windows}
        window_rows = [
            PortfolioWalkForwardWindowValidation(
                validation_id=report_id,
                study_id=source.study.id,
                window_no=row.window_no,
                train_experiment_id=(
                    source_by_no[row.window_no].window.train_experiment_id
                ),
                train_evaluation_id=(
                    source_by_no[row.window_no].window.train_evaluation_id
                ),
                selected_trial_id=(
                    source_by_no[row.window_no].window.selected_trial_id
                ),
                selected_train_run_id=uuid.UUID(
                    source_by_no[row.window_no].identity_snapshot["train"]
                    ["selection"]["run_id"]
                ),
                train_performance_id=uuid.UUID(
                    source_by_no[row.window_no].identity_snapshot["train"]
                    ["m14"]["performance"]["id"]
                ),
                train_risk_id=uuid.UUID(
                    source_by_no[row.window_no].identity_snapshot["train"]
                    ["m14"]["risk"]["id"]
                ),
                train_trade_id=uuid.UUID(
                    source_by_no[row.window_no].identity_snapshot["train"]
                    ["m14"]["trade"]["id"]
                ),
                train_period_id=uuid.UUID(
                    source_by_no[row.window_no].identity_snapshot["train"]
                    ["m14"]["period"]["id"]
                ),
                selected_parameter_hash=(
                    source_by_no[row.window_no].window.selected_parameter_hash
                ),
                selected_parameter_values=(
                    source_by_no[row.window_no].window.selected_parameter_values
                ),
                train_date_hash=(
                    source_by_no[row.window_no].window.train_date_hash
                ),
                test_date_hash=source_by_no[row.window_no].window.test_date_hash,
                identity_snapshot=source_by_no[row.window_no].identity_snapshot,
                oos_run_id=source_by_no[row.window_no].window.oos_run_id,
                oos_performance_id=(
                    source_by_no[row.window_no].window.oos_performance_id
                ),
                oos_risk_id=source_by_no[row.window_no].window.oos_risk_id,
                oos_trade_id=source_by_no[row.window_no].window.oos_trade_id,
                oos_period_id=source_by_no[row.window_no].window.oos_period_id,
                **{
                    name: getattr(row, name)
                    for name in (
                        "train_annualized_return",
                        "train_max_drawdown_abs",
                        "train_sharpe_ratio",
                        "train_annualized_turnover",
                        "oos_cumulative_return",
                        "oos_annualized_return",
                        "oos_max_drawdown_abs",
                        "oos_sharpe_ratio",
                        "oos_annualized_turnover",
                        "oos_total_cost_to_initial_capital",
                        "oos_win_rate",
                        "oos_profit_factor",
                        "return_degradation",
                        "sharpe_degradation",
                        "drawdown_worsening",
                        "turnover_change",
                    )
                },
            )
            for row in metrics.windows
        ]
        stability_rows = [
            PortfolioWalkForwardParameterStability(
                validation_id=report_id,
                study_id=source.study.id,
                parameter_name=row.parameter_name,
                parameter_value=row.parameter_value,
                selected_window_count=row.selected_window_count,
                selected_rate=row.selected_rate,
                transition_count=row.transition_count,
                adjacent_value_switch_count=row.adjacent_value_switch_count,
                adjacent_value_switch_rate=row.adjacent_value_switch_rate,
            )
            for row in stability.rows
        ]
        return _ValidationArtifactDraft(report, window_rows, stability_rows)

    def _window_payloads(
        self, study: PortfolioWalkForwardStudy
    ) -> list[dict[str, Any]]:
        return [
            self._window_payload(study, row)
            for row in self.repository.list_windows(study.id)
        ]

    def _window_payload(
        self,
        study: PortfolioWalkForwardStudy,
        window: PortfolioWalkForwardWindow,
    ) -> dict[str, Any]:
        experiment = (
            self.db.get(PortfolioExperiment, window.train_experiment_id)
            if window.train_experiment_id
            else None
        )
        evaluation_job = (
            self._active_evaluation_job(
                window.train_experiment_id, study.train_policy_hash
            )
            if window.train_experiment_id
            else None
        )
        run = (
            self.db.get(PortfolioBacktestRun, window.oos_run_id)
            if window.oos_run_id
            else None
        )
        projection = project_window_state(
            window,
            experiment=experiment,
            train_active=(
                self._train_active(experiment.id) if experiment is not None else False
            ),
            evaluation_job=evaluation_job,
            oos_run=run,
        )
        projection = self._refine_projection(study, window, projection, experiment, run)
        return {
            "study_id": str(window.study_id),
            "window_no": window.window_no,
            "state": projection.state,
            "blocked": projection.blocked,
            "error_code": projection.error_code,
            "train_start_date": window.train_start_date.isoformat(),
            "train_end_date": window.train_end_date.isoformat(),
            "test_start_date": window.test_start_date.isoformat(),
            "test_end_date": window.test_end_date.isoformat(),
            "train_trade_days": window.train_trade_days,
            "test_trade_days": window.test_trade_days,
            "train_date_hash": window.train_date_hash,
            "test_date_hash": window.test_date_hash,
            "train_experiment_id": _uuid(window.train_experiment_id),
            "train_evaluation_id": _uuid(window.train_evaluation_id),
            "selected_trial_id": _uuid(window.selected_trial_id),
            "selected_parameter_hash": window.selected_parameter_hash,
            "selected_parameter_values": window.selected_parameter_values,
            "selected_portfolio_config_hash": (
                window.selected_portfolio_config_hash
            ),
            "oos_run_id": _uuid(window.oos_run_id),
            "oos_performance_id": _uuid(window.oos_performance_id),
            "oos_risk_id": _uuid(window.oos_risk_id),
            "oos_trade_id": _uuid(window.oos_trade_id),
            "oos_period_id": _uuid(window.oos_period_id),
        }

    def _refine_projection(
        self,
        study: PortfolioWalkForwardStudy,
        window: PortfolioWalkForwardWindow,
        projection: WindowProjection,
        experiment: PortfolioExperiment | None,
        run: PortfolioBacktestRun | None,
    ) -> WindowProjection:
        if projection.state == "TRAIN_TERMINAL" and experiment is not None:
            readiness = self.evaluations.readiness(experiment.id)
            if readiness.get("missing_analytics"):
                return WindowProjection("TRAIN_ANALYTICS_REQUIRED")
            if readiness.get("ready"):
                try:
                    report = self.evaluations.resolve_current_artifact(
                        experiment.id, self._study_policy(study)
                    )
                except ExperimentEvaluationApplicationError:
                    return WindowProjection(
                        "TRAIN_FAILED",
                        True,
                        "WALK_FORWARD_TRAIN_EXPERIMENT_MISMATCH",
                    )
                if report is not None and report.selected_trial_id is None:
                    return WindowProjection(
                        "TRAIN_NO_FEASIBLE_CANDIDATE",
                        True,
                        "WALK_FORWARD_TRAIN_NO_FEASIBLE_CANDIDATE",
                    )
        if projection.state == "OOS_ANALYTICS_REQUIRED" and run is not None:
            if run.status != "SUCCESS":
                return projection
        return projection

    def _required_actions(
        self,
        study: PortfolioWalkForwardStudy,
        windows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        required: list[dict[str, Any]] = []
        for payload in windows:
            if payload["state"] == "TRAIN_ANALYTICS_REQUIRED":
                experiment_id = uuid.UUID(payload["train_experiment_id"])
                readiness = self.evaluations.readiness(experiment_id)
                for item in readiness.get("missing_analytics", []):
                    required.append(
                        {
                            "code": "WALK_FORWARD_VALIDATION_NOT_READY",
                            "window_no": payload["window_no"],
                            "scope": "TRAIN",
                            "run_id": item["run_id"],
                            "missing_stage": item["missing_stage"],
                            "action": (
                                "CALCULATE_M14_"
                                f"{str(item['missing_stage']).upper()}_EXTERNALLY"
                            ),
                        }
                    )
            elif payload["state"] == "OOS_ANALYTICS_REQUIRED":
                run_id = uuid.UUID(payload["oos_run_id"])
                stage = self._missing_oos_stage(run_id)
                if stage:
                    required.append(
                        {
                            "code": "WALK_FORWARD_VALIDATION_NOT_READY",
                            "window_no": payload["window_no"],
                            "scope": "OOS",
                            "run_id": str(run_id),
                            "missing_stage": stage,
                            "action": f"CALCULATE_M14_{stage.upper()}_EXTERNALLY",
                        }
                    )
        return required

    def _missing_oos_stage(self, run_id: uuid.UUID) -> str | None:
        try:
            self.bundle_resolver.resolve(run_id, require_period=True)
        except AnalyticsBundleError as exc:
            for stage in ("performance", "risk", "trade", "period"):
                if stage in str(exc).lower():
                    return stage
            return "performance"
        return None

    def _validate_train_experiment(
        self,
        study: PortfolioWalkForwardStudy,
        window: PortfolioWalkForwardWindow,
        experiment: PortfolioExperiment,
    ) -> None:
        if (
            experiment.start_date != window.train_start_date
            or experiment.end_date != window.train_end_date
            or experiment.initial_cash != study.initial_cash
            or experiment.benchmark_code != study.benchmark_code
            or experiment.parameter_space_hash != study.parameter_space_hash
            or experiment.parameter_space != study.parameter_space
            or experiment.base_config_snapshot != study.base_config_snapshot
            or _study_base_identities(study)
            != {
                name: getattr(experiment, name)
                for name in _study_base_identities(study)
            }
        ):
            raise WalkForwardApplicationError(
                "WALK_FORWARD_TRAIN_EXPERIMENT_MISMATCH",
                "train experiment does not match the frozen study definition",
            )

    def _validate_frozen_selection(
        self,
        window: PortfolioWalkForwardWindow,
        experiment: PortfolioExperiment,
    ) -> None:
        if (
            window.train_evaluation_id is None
            or window.selected_trial_id is None
            or window.selected_portfolio_config_snapshot is None
        ):
            raise WalkForwardApplicationError(
                "WALK_FORWARD_SELECTION_NOT_FROZEN", "selection is not frozen"
            )
        report = self.db.get(
            PortfolioExperimentEvaluationReport, window.train_evaluation_id
        )
        trial = self.db.get(PortfolioExperimentTrial, window.selected_trial_id)
        if (
            report is None
            or trial is None
            or report.experiment_id != experiment.id
            or report.selected_trial_id != trial.id
            or trial.experiment_id != experiment.id
            or trial.parameter_hash != window.selected_parameter_hash
            or trial.portfolio_config_hash != window.selected_portfolio_config_hash
            or trial.portfolio_config_snapshot
            != window.selected_portfolio_config_snapshot
        ):
            raise WalkForwardApplicationError(
                "WALK_FORWARD_SELECTION_IDENTITY_MISMATCH",
                "frozen selection identity changed",
            )

    def _validate_oos_run(
        self,
        study: PortfolioWalkForwardStudy,
        window: PortfolioWalkForwardWindow,
        experiment: PortfolioExperiment,
        run: PortfolioBacktestRun,
    ) -> None:
        if (
            run.start_date != window.test_start_date
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
            or run.portfolio_config_hash != window.selected_portfolio_config_hash
            or run.source_strategy_config_hash
            != experiment.base_source_strategy_config_hash
            or run.opportunity_config_hash != experiment.base_opportunity_config_hash
            or run.execution_config_hash != experiment.base_execution_config_hash
            or run.accounting_config_hash != experiment.base_accounting_config_hash
        ):
            raise WalkForwardApplicationError(
                "WALK_FORWARD_OOS_IDENTITY_MISMATCH",
                "OOS run identity does not match the frozen selection",
            )

    def _train_active(self, experiment_id: uuid.UUID) -> bool:
        statuses = list(
            self.db.scalars(
                select(PortfolioBacktestRun.status)
                .join(
                    PortfolioExperimentTrial,
                    PortfolioExperimentTrial.run_id == PortfolioBacktestRun.id,
                )
                .where(PortfolioExperimentTrial.experiment_id == experiment_id)
                .execution_options(populate_existing=True)
            ).all()
        )
        trial_count = int(
            self.db.scalar(
                select(func.count())
                .select_from(PortfolioExperimentTrial)
                .where(PortfolioExperimentTrial.experiment_id == experiment_id)
            )
            or 0
        )
        return len(statuses) != trial_count or any(
            status not in _TERMINAL_RUN_STATUSES for status in statuses
        )

    def _active_evaluation_job(
        self, experiment_id: uuid.UUID, policy_hash: str
    ) -> JobRun | None:
        return self.db.scalar(
            select(JobRun)
            .where(
                JobRun.job_type == "portfolio_experiment_evaluation",
                JobRun.status.in_(_ACTIVE_JOB_STATUSES),
                JobRun.job_metadata.contains(
                    {
                        "experiment_id": str(experiment_id),
                        "policy_hash": policy_hash,
                    }
                ),
            )
            .order_by(JobRun.started_at.desc(), JobRun.id.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )

    def _study_policy(
        self, study: PortfolioWalkForwardStudy
    ) -> EvaluationPolicyConfig:
        try:
            policy = EvaluationPolicyConfig.model_validate(
                study.train_policy_snapshot
            )
        except ValidationError as exc:
            raise WalkForwardApplicationError(
                "WALK_FORWARD_SELECTION_IDENTITY_MISMATCH",
                "frozen train evaluation policy is invalid",
            ) from exc
        _, policy_hash = self.evaluations.normalize_policy(policy)
        if policy_hash != study.train_policy_hash:
            raise WalkForwardApplicationError(
                "WALK_FORWARD_SELECTION_IDENTITY_MISMATCH",
                "frozen train evaluation policy hash changed",
            )
        return policy

    def _frozen_experiment_service(
        self, study: PortfolioWalkForwardStudy
    ) -> ExperimentApplicationService:
        return ExperimentApplicationService(
            self.db, settings=self._frozen_settings(study)
        )

    def _frozen_settings(self, study: PortfolioWalkForwardStudy) -> Settings:
        snapshot = deepcopy(study.base_config_snapshot)
        frozen = self.settings.model_copy(deep=True)
        frozen.algo_version = study.base_algo_version
        frozen.strategy = snapshot["strategy"]
        frozen.opportunity_config = snapshot["opportunity"]
        frozen.portfolio_config = PortfolioConfig.model_validate(snapshot["portfolio"])
        assert frozen.execution_config is not None
        assert frozen.accounting_config is not None
        frozen.execution_config = type(frozen.execution_config).model_validate(
            snapshot["execution"]
        )
        frozen.accounting_config = type(frozen.accounting_config).model_validate(
            snapshot["accounting"]
        )
        assert frozen.experiment_config is not None
        required_trials = prod(len(values) for values in study.parameter_space.values())
        required_values = max(len(values) for values in study.parameter_space.values())
        frozen.experiment_config = frozen.experiment_config.model_copy(
            update={
                "max_trials": max(
                    frozen.experiment_config.max_trials, required_trials
                ),
                "max_values_per_parameter": max(
                    frozen.experiment_config.max_values_per_parameter,
                    required_values,
                ),
            }
        )
        return frozen

    def _study(self, study_id: uuid.UUID) -> PortfolioWalkForwardStudy:
        study = self.repository.get(study_id)
        if study is None:
            raise WalkForwardApplicationError(
                "WALK_FORWARD_NOT_FOUND", "walk-forward study not found"
            )
        return study

    def _validation(
        self, study_id: uuid.UUID, validation_id: uuid.UUID
    ) -> PortfolioWalkForwardValidationReport:
        report = self.repository.get_validation(study_id, validation_id)
        if report is None:
            raise WalkForwardApplicationError(
                "WALK_FORWARD_NOT_FOUND", "walk-forward validation not found"
            )
        return report

    def _load_source(self, study_id: uuid.UUID) -> WalkForwardValidationSource:
        try:
            return self.source_provider.load(study_id)
        except WalkForwardSourceError as exc:
            raise WalkForwardApplicationError(
                exc.code, str(exc), **exc.details
            ) from exc

    def _study_lock(self, study_id: uuid.UUID) -> None:
        if self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(
                select(func.pg_advisory_xact_lock(study_lock_key(study_id)))
            ).scalar_one()

    def _validation_lock(self, study_id: uuid.UUID, source_hash: str) -> None:
        if self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(
                select(
                    func.pg_advisory_xact_lock(
                        validation_lock_key(study_id, source_hash)
                    )
                )
            ).scalar_one()


def _study_base_identities(study: PortfolioWalkForwardStudy) -> dict[str, str]:
    names = (
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
    return {name: getattr(study, name) for name in names}


def _study_payload(study: PortfolioWalkForwardStudy) -> dict[str, Any]:
    return {
        "id": str(study.id),
        "name": study.name,
        "walk_forward_version": study.walk_forward_version,
        "mode": study.mode,
        "exchange": study.exchange,
        "requested_start_date": study.requested_start_date.isoformat(),
        "requested_end_date": study.requested_end_date.isoformat(),
        "train_trade_days": study.train_trade_days,
        "test_trade_days": study.test_trade_days,
        "step_trade_days": study.step_trade_days,
        "window_count": study.window_count,
        "unused_tail_trade_days": study.unused_tail_trade_days,
        "calendar_hash": study.calendar_hash,
        "initial_cash": str(study.initial_cash),
        "benchmark_code": study.benchmark_code,
        "parameter_space": study.parameter_space,
        "parameter_space_hash": study.parameter_space_hash,
        "train_evaluation_policy": study.train_policy_snapshot,
        "train_policy_hash": study.train_policy_hash,
        "base_identity": _study_base_identities(study),
        "definition_hash": study.definition_hash,
        "cancel_requested": study.cancel_requested,
        "created_at": study.created_at.isoformat(),
        "updated_at": study.updated_at.isoformat(),
    }


def _progress(windows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in windows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    ready = counts.get("OOS_READY", 0)
    return {
        "window_count": len(windows),
        "oos_ready_count": ready,
        "completion_rate": (
            Decimal(ready) / Decimal(len(windows)) if windows else Decimal(0)
        ),
        "state_counts": counts,
    }


def _validation_payload(
    report: PortfolioWalkForwardValidationReport,
) -> dict[str, Any]:
    payload = _model_payload(report, {"created_at", "updated_at"})
    payload["identity"] = {
        "validation_id": str(report.id),
        "study_id": str(report.study_id),
        "walk_forward_version": report.walk_forward_version,
        "walk_forward_config_hash": report.walk_forward_config_hash,
        "validation_policy_hash": report.validation_policy_hash,
        "source_hash": report.source_hash,
    }
    return payload


def _model_payload(model: Any, excluded: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in model.__table__.columns:
        if column.name in excluded:
            continue
        value = getattr(model, column.name)
        if isinstance(value, uuid.UUID):
            value = str(value)
        elif hasattr(value, "isoformat") and not isinstance(value, Decimal):
            value = value.isoformat()
        result[column.name] = value
    return result


def _decimal(value: Decimal) -> str:
    return "0" if value == 0 else format(value.normalize(), "f")


def _uuid(value: uuid.UUID | None) -> str | None:
    return str(value) if value else None
