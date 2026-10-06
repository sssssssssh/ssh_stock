import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from loguru import logger
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.experiment_evaluation_config import (
    EXPERIMENT_EVALUATION_VERSION,
    EvaluationPolicyConfig,
)
from app.domain.experiment.contracts import EXPERIMENT_PARAMETER_ORDER
from app.domain.experiment_evaluation import (
    EvaluatedTrial,
    EvaluationPolicy,
    EvaluationResult,
    assign_pareto_fronts,
    calculate_sensitivity,
    evaluate_constraints,
    rank_trials,
)
from app.models.experiment_evaluation import (
    PortfolioExperimentEvaluationReport,
    PortfolioExperimentParameterSensitivity,
    PortfolioExperimentTrialEvaluation,
)
from app.models.job import JobRun
from app.repositories.experiment_evaluation import ExperimentEvaluationRepository
from app.services.experiment_evaluation.identity import (
    effective_policy,
    evaluation_config_hash,
    evaluation_lock_key,
)
from app.services.experiment_evaluation.source import (
    ExperimentEvaluationSourceError,
    ExperimentEvaluationSourceProvider,
    ExperimentEvaluationSourceSnapshot,
)

EXPERIMENT_EVALUATION_JOB_TYPE = "portfolio_experiment_evaluation"
_ACTIVE_JOB_STATUSES = {"QUEUED", "RUNNING"}


class ExperimentEvaluationApplicationError(RuntimeError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        self.code = code
        self.details = details
        super().__init__(message)


class ExperimentEvaluationConflictError(ExperimentEvaluationApplicationError):
    def __init__(self, message: str, *, job_id: uuid.UUID | None = None) -> None:
        self.job_id = job_id
        super().__init__(
            "EXPERIMENT_EVALUATION_CONFLICT", message, job_id=str(job_id) if job_id else None
        )


class ExperimentEvaluationOwnershipError(ExperimentEvaluationApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__("EXPERIMENT_EVALUATION_OWNERSHIP_LOST", message)


@dataclass(frozen=True)
class ExperimentEvaluationExecutionLease:
    job_id: uuid.UUID
    worker_id: str
    experiment_id: uuid.UUID
    policy_hash: str


@dataclass(frozen=True)
class ExperimentEvaluationArtifact:
    report: PortfolioExperimentEvaluationReport
    reused: bool


class ExperimentEvaluationApplicationService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        repository: ExperimentEvaluationRepository | None = None,
        source_provider: ExperimentEvaluationSourceProvider | None = None,
        before_terminal_hook: Callable[
            [ExperimentEvaluationExecutionLease, ExperimentEvaluationArtifact], None
        ]
        | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        if self.settings.experiment_evaluation_config is None:
            raise RuntimeError("experiment evaluation configuration is not loaded")
        self.config = self.settings.experiment_evaluation_config
        self.repository = repository or ExperimentEvaluationRepository(db)
        self.source_provider = source_provider or ExperimentEvaluationSourceProvider(
            db, self.config
        )
        self.before_terminal_hook = before_terminal_hook

    def readiness(self, experiment_id: uuid.UUID) -> dict[str, Any]:
        return self.source_provider.readiness(experiment_id)

    def queue_calculation(
        self,
        experiment_id: uuid.UUID,
        policy_request: EvaluationPolicyConfig | None = None,
    ) -> JobRun:
        _, policy_snapshot, policy_hash = self._policy(policy_request)
        self._advisory_lock(experiment_id, policy_hash)
        self.source_provider.load(experiment_id)
        identity = {
            "experiment_id": str(experiment_id),
            "policy_hash": policy_hash,
        }
        active = self.db.scalar(
            select(JobRun)
            .where(
                JobRun.job_type == EXPERIMENT_EVALUATION_JOB_TYPE,
                JobRun.status.in_(_ACTIVE_JOB_STATUSES),
                JobRun.job_metadata.contains(identity),
            )
            .order_by(JobRun.started_at.desc(), JobRun.id.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
        if active is not None:
            raise ExperimentEvaluationConflictError(
                "experiment evaluation already has an active job for this policy",
                job_id=active.id,
            )
        job = JobRun(
            job_type=EXPERIMENT_EVALUATION_JOB_TYPE,
            target_trade_date=None,
            status="QUEUED",
            step="queued for experiment evaluation",
            row_count=0,
            cancel_requested=False,
            job_metadata={
                **identity,
                "evaluation_version": EXPERIMENT_EVALUATION_VERSION,
                "policy": policy_snapshot,
                "stage": "QUEUED",
            },
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        _log_event(
            "experiment_evaluation_queued",
            experiment_id=experiment_id,
            job_id=job.id,
            policy_hash=policy_hash,
            operation="queue",
            outcome="QUEUED",
        )
        return job

    def run_job(self, job_id: uuid.UUID) -> ExperimentEvaluationArtifact:
        job = self.db.scalar(
            select(JobRun)
            .where(JobRun.id == job_id)
            .execution_options(populate_existing=True)
        )
        if (
            job is None
            or job.job_type != EXPERIMENT_EVALUATION_JOB_TYPE
            or job.status != "RUNNING"
            or not job.worker_id
        ):
            raise ExperimentEvaluationOwnershipError(
                "evaluation job is not owned by a running worker"
            )
        metadata = dict(job.job_metadata or {})
        try:
            policy_request = EvaluationPolicyConfig.model_validate(metadata["policy"])
            lease = ExperimentEvaluationExecutionLease(
                job_id=job.id,
                worker_id=job.worker_id,
                experiment_id=uuid.UUID(str(metadata["experiment_id"])),
                policy_hash=str(metadata["policy_hash"]),
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise ExperimentEvaluationOwnershipError(
                "evaluation job identities are invalid"
            ) from exc
        _, _, current_policy_hash = self._policy(policy_request)
        if (
            metadata.get("evaluation_version") != EXPERIMENT_EVALUATION_VERSION
            or current_policy_hash != lease.policy_hash
        ):
            raise ExperimentEvaluationOwnershipError(
                "evaluation job policy or version identity is invalid"
            )
        artifact = self._calculate_uncommitted(lease.experiment_id, policy_request)
        if self.before_terminal_hook:
            self.before_terminal_hook(lease, artifact)
        terminal = self._owned_job_for_terminal_update(lease)
        terminal.status = "SUCCESS"
        terminal.finished_at = datetime.now(UTC)
        terminal.step = "experiment evaluation complete"
        terminal.row_count = artifact.report.trial_count
        terminal.job_metadata = {
            **dict(terminal.job_metadata or {}),
            "stage": "SUCCESS",
            "evaluation_id": str(artifact.report.id),
            "source_hash": artifact.report.source_hash,
            "reused": artifact.reused,
        }
        self.db.add(terminal)
        self.db.commit()
        self.db.refresh(artifact.report)
        return artifact

    def calculate_now(
        self,
        experiment_id: uuid.UUID,
        policy_request: EvaluationPolicyConfig | None = None,
    ) -> ExperimentEvaluationArtifact:
        artifact = self._calculate_uncommitted(experiment_id, policy_request)
        self.db.commit()
        self.db.refresh(artifact.report)
        return artifact

    def detail(
        self, experiment_id: uuid.UUID, evaluation_id: uuid.UUID
    ) -> dict[str, Any]:
        report = self._report(experiment_id, evaluation_id)
        shortlist = self.repository.shortlist(evaluation_id)
        return {
            **_report_payload(report),
            "policy": report.policy_snapshot,
            "selected_trial": (
                _trial_payload(shortlist[0]) if shortlist else None
            ),
            "shortlist": [_trial_payload(row) for row in shortlist],
        }

    def trials(
        self,
        experiment_id: uuid.UUID,
        evaluation_id: uuid.UUID,
        *,
        status: str | None,
        feasible: bool | None,
        shortlisted: bool | None,
        pareto_front: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        report = self._report(experiment_id, evaluation_id)
        rows, total = self.repository.trial_page(
            evaluation_id,
            status=status,
            feasible=feasible,
            shortlisted=shortlisted,
            pareto_front=pareto_front,
            limit=limit,
            offset=offset,
        )
        return [_trial_payload(row) for row in rows], {
            "evaluation_id": str(evaluation_id),
            "experiment_id": str(experiment_id),
            "policy_hash": report.policy_hash,
            "source_hash": report.source_hash,
            "limit": limit,
            "offset": offset,
            "total": total,
        }

    def sensitivity(
        self,
        experiment_id: uuid.UUID,
        evaluation_id: uuid.UUID,
        parameter_name: str | None,
    ) -> list[dict[str, Any]]:
        self._report(experiment_id, evaluation_id)
        if parameter_name is not None and parameter_name not in EXPERIMENT_PARAMETER_ORDER:
            raise ExperimentEvaluationApplicationError(
                "EXPERIMENT_EVALUATION_POLICY_INVALID",
                f"unsupported experiment parameter: {parameter_name}",
            )
        rows = self.repository.sensitivity(evaluation_id, parameter_name)
        order = {name: index for index, name in enumerate(EXPERIMENT_PARAMETER_ORDER)}
        rows.sort(key=lambda row: (order[row.parameter_name], Decimal(row.parameter_value)))
        return [_sensitivity_payload(row) for row in rows]

    def history(
        self, experiment_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        try:
            self.source_provider._experiment_trials(experiment_id)
        except ExperimentEvaluationSourceError as exc:
            raise _application_error(exc) from exc
        rows, total = self.repository.history(experiment_id, limit=limit, offset=offset)
        return [_report_payload(row) for row in rows], total

    def _calculate_uncommitted(
        self,
        experiment_id: uuid.UUID,
        policy_request: EvaluationPolicyConfig | None,
    ) -> ExperimentEvaluationArtifact:
        policy, policy_snapshot, policy_hash = self._policy(policy_request)
        self._advisory_lock(experiment_id, policy_hash)
        try:
            source = self.source_provider.load(experiment_id)
        except ExperimentEvaluationSourceError as exc:
            raise _application_error(exc) from exc
        config_hash = evaluation_config_hash(self.config)
        existing = self.repository.find_by_identity(
            experiment_id=experiment_id,
            evaluation_version=EXPERIMENT_EVALUATION_VERSION,
            evaluation_config_hash=config_hash,
            policy_hash=policy_hash,
            source_hash=source.source_hash,
        )
        if existing is not None:
            return ExperimentEvaluationArtifact(existing, reused=True)
        result = _evaluate(source, policy)
        report, trial_rows, sensitivity_rows = _models(
            source=source,
            policy=policy,
            policy_snapshot=policy_snapshot,
            policy_hash=policy_hash,
            config_hash=config_hash,
            result=result,
        )
        self.repository.add(report, trial_rows, sensitivity_rows)
        _log_event(
            "experiment_evaluation_calculated",
            experiment_id=experiment_id,
            evaluation_id=report.id,
            policy_hash=policy_hash,
            source_hash=source.source_hash,
            operation="calculate",
            outcome="FLUSHED",
        )
        return ExperimentEvaluationArtifact(report, reused=False)

    def _policy(
        self, request: EvaluationPolicyConfig | None
    ) -> tuple[EvaluationPolicy, dict[str, Any], str]:
        policy = request or self.config.default_policy
        try:
            return effective_policy(policy, self.config)
        except (ValueError, ValidationError) as exc:
            raise ExperimentEvaluationApplicationError(
                "EXPERIMENT_EVALUATION_POLICY_INVALID", str(exc)
            ) from exc

    def _advisory_lock(self, experiment_id: uuid.UUID, policy_hash: str) -> None:
        if self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(
                select(
                    func.pg_advisory_xact_lock(
                        evaluation_lock_key(experiment_id, policy_hash)
                    )
                )
            ).scalar_one()

    def _owned_job_for_terminal_update(
        self, lease: ExperimentEvaluationExecutionLease
    ) -> JobRun:
        job = self.db.scalar(
            select(JobRun)
            .where(JobRun.id == lease.job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        metadata = dict(job.job_metadata or {}) if job is not None else {}
        if (
            job is None
            or job.status != "RUNNING"
            or job.worker_id != lease.worker_id
            or metadata.get("experiment_id") != str(lease.experiment_id)
            or metadata.get("policy_hash") != lease.policy_hash
        ):
            self.db.rollback()
            raise ExperimentEvaluationOwnershipError(
                "evaluation worker no longer owns the terminal update"
            )
        return job

    def _report(
        self, experiment_id: uuid.UUID, evaluation_id: uuid.UUID
    ) -> PortfolioExperimentEvaluationReport:
        report = self.repository.get(experiment_id, evaluation_id)
        if report is None:
            raise ExperimentEvaluationApplicationError(
                "EXPERIMENT_EVALUATION_NOT_FOUND", "experiment evaluation not found"
            )
        return report


def _evaluate(
    source: ExperimentEvaluationSourceSnapshot, policy: EvaluationPolicy
) -> EvaluationResult:
    evaluated: list[EvaluatedTrial] = []
    for trial in source.trials:
        if trial.run_status != "SUCCESS":
            evaluated.append(
                EvaluatedTrial(
                    source=trial,
                    status="EXCLUDED",
                    exclusion_reason=(
                        "RUN_FAILED" if trial.run_status == "FAILED" else "RUN_CANCELLED"
                    ),
                    feasible=False,
                    constraint_violations=(),
                    primary_objective_value=None,
                )
            )
            continue
        assert trial.metrics is not None
        constraint = evaluate_constraints(trial.metrics, policy)
        evaluated.append(
            EvaluatedTrial(
                source=trial,
                status="EVALUATED",
                exclusion_reason=None,
                feasible=constraint.feasible,
                constraint_violations=constraint.violations,
                primary_objective_value=trial.metrics.value(policy.primary_objective),
            )
        )
    fronts = assign_pareto_fronts(tuple(evaluated), policy)
    ranked = rank_trials(fronts, policy)
    sensitivity = calculate_sensitivity(ranked, policy)
    warnings = set(source.warnings)
    if not any(row.feasible for row in ranked):
        warnings.add("NO_FEASIBLE_TRIALS")
    return EvaluationResult(
        trials=ranked,
        sensitivity=sensitivity,
        warnings=tuple(sorted(warnings)),
    )


def _models(
    *,
    source: ExperimentEvaluationSourceSnapshot,
    policy: EvaluationPolicy,
    policy_snapshot: dict[str, Any],
    policy_hash: str,
    config_hash: str,
    result: EvaluationResult,
) -> tuple[
    PortfolioExperimentEvaluationReport,
    list[PortfolioExperimentTrialEvaluation],
    list[PortfolioExperimentParameterSensitivity],
]:
    report_id = uuid.uuid4()
    evaluated = [row for row in result.trials if row.status == "EVALUATED"]
    feasible = [row for row in evaluated if row.feasible]
    shortlist = sorted(
        (row for row in feasible if row.shortlisted),
        key=lambda row: row.selection_rank or 0,
    )
    selected = shortlist[0] if shortlist else None
    report = PortfolioExperimentEvaluationReport(
        id=report_id,
        experiment_id=source.experiment_id,
        evaluation_version=EXPERIMENT_EVALUATION_VERSION,
        evaluation_config_hash=config_hash,
        policy_hash=policy_hash,
        policy_snapshot=policy_snapshot,
        source_hash=source.source_hash,
        trial_count=len(result.trials),
        success_trial_count=len(evaluated),
        excluded_trial_count=len(result.trials) - len(evaluated),
        evaluated_trial_count=len(evaluated),
        feasible_count=len(feasible),
        infeasible_count=len(evaluated) - len(feasible),
        pareto_front1_count=sum(row.pareto_front == 1 for row in feasible),
        shortlist_count=len(shortlist),
        selected_trial_id=selected.source.trial_id if selected else None,
        selected_run_id=selected.source.run_id if selected else None,
        status="SUCCESS",
        warnings=list(result.warnings),
        result_summary={
            "selection_semantics": "in_sample_research_candidate",
            "primary_objective": policy.primary_objective,
            "pareto_metrics": list(policy.pareto_metrics),
        },
    )
    trial_rows = [_trial_model(report_id, source.experiment_id, row) for row in result.trials]
    sensitivity_rows = [
        PortfolioExperimentParameterSensitivity(
            evaluation_id=report_id,
            experiment_id=source.experiment_id,
            **row.__dict__,
        )
        for row in result.sensitivity
    ]
    return report, trial_rows, sensitivity_rows


def _trial_model(
    evaluation_id: uuid.UUID, experiment_id: uuid.UUID, row: EvaluatedTrial
) -> PortfolioExperimentTrialEvaluation:
    metrics = row.source.metrics
    values = {
        name: metrics.value(name) if metrics is not None else None
        for name in (
            "cumulative_return",
            "annualized_return",
            "max_drawdown_abs",
            "strategy_annualized_volatility",
            "excess_cumulative_return",
            "sharpe_ratio",
            "sortino_ratio",
            "calmar_ratio",
            "information_ratio",
            "alpha_annualized",
            "annualized_turnover",
            "total_cost_to_initial_capital",
            "win_rate",
            "profit_factor",
            "payoff_ratio",
            "closed_realized_pnl",
            "positive_month_rate",
            "worst_month_return",
            "monthly_return_volatility",
        )
    }
    return PortfolioExperimentTrialEvaluation(
        evaluation_id=evaluation_id,
        experiment_id=experiment_id,
        trial_id=row.source.trial_id,
        trial_no=row.source.trial_no,
        run_id=row.source.run_id,
        status=row.status,
        exclusion_reason=row.exclusion_reason,
        parameter_hash=row.source.parameter_hash,
        parameter_values=row.source.parameter_values,
        performance_id=row.source.performance_id,
        risk_id=row.source.risk_id,
        trade_id=row.source.trade_id,
        period_id=row.source.period_id,
        closed_episode_count=(
            int(metrics.closed_episode_count)
            if metrics is not None and metrics.closed_episode_count is not None
            else None
        ),
        primary_objective_value=row.primary_objective_value,
        feasible=row.feasible,
        constraint_violations=list(row.constraint_violations),
        pareto_front=row.pareto_front,
        selection_rank=row.selection_rank,
        shortlisted=row.shortlisted,
        warnings=list(row.source.warnings),
        **values,
    )


def _report_payload(report: PortfolioExperimentEvaluationReport) -> dict[str, Any]:
    return {
        "id": str(report.id),
        "experiment_id": str(report.experiment_id),
        "evaluation_version": report.evaluation_version,
        "evaluation_config_hash": report.evaluation_config_hash,
        "policy_hash": report.policy_hash,
        "source_hash": report.source_hash,
        "status": report.status,
        "counts": {
            "trial": report.trial_count,
            "success_trial": report.success_trial_count,
            "excluded_trial": report.excluded_trial_count,
            "evaluated_trial": report.evaluated_trial_count,
            "feasible": report.feasible_count,
            "infeasible": report.infeasible_count,
            "pareto_front1": report.pareto_front1_count,
            "shortlist": report.shortlist_count,
        },
        "selected_trial_id": (
            str(report.selected_trial_id) if report.selected_trial_id else None
        ),
        "selected_run_id": str(report.selected_run_id) if report.selected_run_id else None,
        "warnings": report.warnings,
        "result_summary": report.result_summary,
        "calculated_at": report.calculated_at.isoformat(),
    }


def _trial_payload(row: PortfolioExperimentTrialEvaluation) -> dict[str, Any]:
    fields = (
        "cumulative_return",
        "annualized_return",
        "max_drawdown_abs",
        "strategy_annualized_volatility",
        "excess_cumulative_return",
        "sharpe_ratio",
        "sortino_ratio",
        "calmar_ratio",
        "information_ratio",
        "alpha_annualized",
        "annualized_turnover",
        "total_cost_to_initial_capital",
        "closed_episode_count",
        "win_rate",
        "profit_factor",
        "payoff_ratio",
        "closed_realized_pnl",
        "positive_month_rate",
        "worst_month_return",
        "monthly_return_volatility",
    )
    return {
        "trial_id": str(row.trial_id),
        "trial_no": row.trial_no,
        "run_id": str(row.run_id) if row.run_id else None,
        "status": row.status,
        "exclusion_reason": row.exclusion_reason,
        "parameter_values": row.parameter_values,
        "feasible": row.feasible,
        "constraint_violations": row.constraint_violations,
        "pareto_front": row.pareto_front,
        "selection_rank": row.selection_rank,
        "shortlisted": row.shortlisted,
        "primary_objective_value": row.primary_objective_value,
        "warnings": row.warnings,
        **{field: getattr(row, field) for field in fields},
    }


def _sensitivity_payload(row: PortfolioExperimentParameterSensitivity) -> dict[str, Any]:
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if column.name not in {"evaluation_id", "experiment_id", "created_at"}
    }


def _application_error(
    exc: ExperimentEvaluationSourceError,
) -> ExperimentEvaluationApplicationError:
    return ExperimentEvaluationApplicationError(exc.code, str(exc), **exc.details)


def _log_event(event: str, **fields: Any) -> None:
    allowed = {
        "experiment_id",
        "evaluation_id",
        "job_id",
        "policy_hash",
        "source_hash",
        "trial_id",
        "trial_no",
        "run_id",
        "operation",
        "outcome",
    }
    safe = {key: str(value) for key, value in fields.items() if key in allowed}
    logger.bind(**safe).info(event)
