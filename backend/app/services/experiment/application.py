import uuid
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from loguru import logger
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.portfolio_config import PortfolioConfig
from app.domain.experiment import (
    EXPERIMENT_PARAMETER_ORDER,
    ExperimentGridError,
    expand_grid,
)
from app.models.experiment import PortfolioExperiment, PortfolioExperimentTrial
from app.repositories.experiment import ExperimentRepository, ExperimentTrialRecord
from app.services.analysis_identity import (
    ACCOUNTING_VERSION,
    BACKTEST_ENGINE_VERSION,
    EXECUTION_VERSION,
    OPPORTUNITY_CALC_VERSION,
    PORTFOLIO_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.portfolio.backtest_application import (
    BacktestApplicationService,
    BacktestConflictError,
)
from app.services.portfolio.run_factory import BacktestRunFactory

_ACTIVE_JOB_STATUSES = {"QUEUED", "RUNNING"}
_TERMINAL_TRIAL_STATES = {"SUCCESS", "FAILED", "CANCELLED"}
_TRIAL_STATES = {"PLANNED", "CREATED", "RUNNING", *_TERMINAL_TRIAL_STATES}
_EXPERIMENT_LOG_FIELDS = {
    "experiment_id",
    "trial_id",
    "trial_no",
    "run_id",
    "job_id",
    "trial_count",
    "definition_hash",
    "parameter_hash",
    "operation",
    "outcome",
    "reason",
    "mismatch_fields",
}


class ExperimentApplicationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class FrozenExperimentBase:
    config_snapshot: dict[str, Any]
    identities: dict[str, str]
    initial_cash: Decimal
    benchmark_code: str


class ExperimentApplicationService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        fault_hook: Callable[[str, PortfolioExperimentTrial | None], None]
        | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        required = (
            self.settings.experiment_config,
            self.settings.portfolio_config,
            self.settings.execution_config,
            self.settings.accounting_config,
        )
        if any(item is None for item in required):
            raise RuntimeError("experiment and backtest configuration must be loaded")
        self.experiment_config = self.settings.experiment_config
        self.portfolio_config = self.settings.portfolio_config
        self.execution_config = self.settings.execution_config
        self.accounting_config = self.settings.accounting_config
        self.repository = ExperimentRepository(db)
        self.fault_hook = fault_hook

    def create(
        self,
        *,
        name: str | None,
        start_date: date,
        end_date: date,
        initial_cash: Decimal | None,
        benchmark_code: str | None,
        grid: Mapping[str, Sequence[Any]],
    ) -> dict[str, Any]:
        frozen = self.freeze_current_base(
            initial_cash=initial_cash,
            benchmark_code=benchmark_code,
        )
        experiment = self.create_from_frozen_base(
            name=name,
            start_date=start_date,
            end_date=end_date,
            grid=grid,
            base_config_snapshot=frozen.config_snapshot,
            base_identities=frozen.identities,
            commit=True,
        )
        return self.get(experiment.id)

    def freeze_current_base(
        self,
        *,
        initial_cash: Decimal | None,
        benchmark_code: str | None,
    ) -> FrozenExperimentBase:
        try:
            effective_portfolio = PortfolioConfig.model_validate(
                self.portfolio_config.model_copy(
                    update={
                        "initial_cash_cny": (
                            initial_cash
                            if initial_cash is not None
                            else self.portfolio_config.initial_cash_cny
                        ),
                        "benchmark_code": (
                            benchmark_code
                            if benchmark_code is not None
                            else self.portfolio_config.benchmark_code
                        ),
                    }
                ).model_dump(mode="python")
            )
        except ValidationError as exc:
            raise ExperimentApplicationError(
                "EXPERIMENT_CONFIG_INVALID", f"invalid experiment base config: {exc}"
            ) from exc
        if not effective_portfolio.benchmark_code.strip():
            raise ExperimentApplicationError(
                "EXPERIMENT_CONFIG_INVALID", "benchmark_code must be nonempty"
            )
        portfolio_snapshot = effective_portfolio.model_dump(mode="json")
        execution_snapshot = self.execution_config.model_dump(mode="json")
        accounting_snapshot = self.accounting_config.model_dump(mode="json")
        base_snapshot = {
            "strategy": self.settings.strategy,
            "opportunity": self.settings.opportunity_config,
            "portfolio": portfolio_snapshot,
            "execution": execution_snapshot,
            "accounting": accounting_snapshot,
        }
        identities = {
            "base_algo_version": self.settings.algo_version,
            "base_source_strategy_config_hash": analysis_strategy_hash(
                self.settings.strategy
            ),
            "base_opportunity_calc_version": OPPORTUNITY_CALC_VERSION,
            "base_opportunity_config_hash": config_hash(
                self.settings.opportunity_config
            ),
            "base_portfolio_version": PORTFOLIO_VERSION,
            "base_portfolio_config_hash": config_hash(portfolio_snapshot),
            "base_execution_version": EXECUTION_VERSION,
            "base_execution_config_hash": config_hash(execution_snapshot),
            "base_accounting_version": ACCOUNTING_VERSION,
            "base_accounting_config_hash": config_hash(accounting_snapshot),
            "base_backtest_engine_version": BACKTEST_ENGINE_VERSION,
        }
        return FrozenExperimentBase(
            config_snapshot=deepcopy(base_snapshot),
            identities=identities,
            initial_cash=effective_portfolio.initial_cash_cny,
            benchmark_code=effective_portfolio.benchmark_code,
        )

    def create_from_frozen_base(
        self,
        *,
        name: str | None,
        start_date: date,
        end_date: date,
        grid: Mapping[str, Sequence[Any]],
        base_config_snapshot: Mapping[str, Any],
        base_identities: Mapping[str, str],
        commit: bool = True,
    ) -> PortfolioExperiment:
        if end_date < start_date:
            raise ExperimentApplicationError(
                "EXPERIMENT_CONFIG_INVALID",
                "end_date must be on or after start_date",
            )
        required_snapshot = {
            "strategy",
            "opportunity",
            "portfolio",
            "execution",
            "accounting",
        }
        required_identities = {
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
        }
        snapshot = deepcopy(dict(base_config_snapshot))
        identities = dict(base_identities)
        if set(snapshot) != required_snapshot or set(identities) != required_identities:
            raise ExperimentApplicationError(
                "EXPERIMENT_CONFIG_INVALID", "frozen experiment base is incomplete"
            )
        try:
            portfolio = PortfolioConfig.model_validate(snapshot["portfolio"])
            expanded = expand_grid(
                base_portfolio=portfolio,
                grid=grid,
                max_trials=self.experiment_config.max_trials,
                max_values_per_parameter=(
                    self.experiment_config.max_values_per_parameter
                ),
            )
        except (ExperimentGridError, ValidationError) as exc:
            code = getattr(exc, "code", "EXPERIMENT_CONFIG_INVALID")
            raise ExperimentApplicationError(code, str(exc)) from exc
        actual_hashes = {
            "base_source_strategy_config_hash": analysis_strategy_hash(
                snapshot["strategy"]
            ),
            "base_opportunity_config_hash": config_hash(snapshot["opportunity"]),
            "base_portfolio_config_hash": config_hash(
                portfolio.model_dump(mode="json")
            ),
            "base_execution_config_hash": config_hash(snapshot["execution"]),
            "base_accounting_config_hash": config_hash(snapshot["accounting"]),
        }
        mismatches = [
            field
            for field, actual in actual_hashes.items()
            if identities.get(field) != actual
        ]
        if mismatches:
            raise ExperimentApplicationError(
                "EXPERIMENT_CONFIG_INVALID",
                f"frozen experiment base identity mismatch: {mismatches}",
            )
        definition_hash = config_hash(
            {
                "experiment_version": self.experiment_config.version,
                "search_method": self.experiment_config.search_method,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "initial_cash": _canonical_decimal(portfolio.initial_cash_cny),
                "benchmark_code": portfolio.benchmark_code,
                "algo_version": identities["base_algo_version"],
                "source_strategy_config_hash": identities[
                    "base_source_strategy_config_hash"
                ],
                "opportunity_calc_version": identities[
                    "base_opportunity_calc_version"
                ],
                "opportunity_config_hash": identities[
                    "base_opportunity_config_hash"
                ],
                "base_portfolio_version": identities["base_portfolio_version"],
                "base_portfolio_config_hash": identities[
                    "base_portfolio_config_hash"
                ],
                "execution_version": identities["base_execution_version"],
                "execution_config_hash": identities[
                    "base_execution_config_hash"
                ],
                "accounting_version": identities["base_accounting_version"],
                "accounting_config_hash": identities[
                    "base_accounting_config_hash"
                ],
                "backtest_engine_version": identities[
                    "base_backtest_engine_version"
                ],
                "parameter_space_hash": expanded.parameter_space_hash,
            }
        )
        experiment_id = uuid.uuid4()
        experiment = PortfolioExperiment(
            id=experiment_id,
            name=name,
            experiment_version=self.experiment_config.version,
            search_method=self.experiment_config.search_method,
            start_date=start_date,
            end_date=end_date,
            initial_cash=portfolio.initial_cash_cny,
            benchmark_code=portfolio.benchmark_code,
            definition_hash=definition_hash,
            parameter_space_hash=expanded.parameter_space_hash,
            parameter_space=expanded.parameter_space,
            trial_count=len(expanded.trials),
            base_config_snapshot=snapshot,
            **identities,
        )
        trials = [
            PortfolioExperimentTrial(
                experiment_id=experiment_id,
                trial_no=item.trial_no,
                parameter_values=item.parameter_values,
                parameter_hash=item.parameter_hash,
                portfolio_config_snapshot=item.portfolio_config_snapshot,
                portfolio_config_hash=item.portfolio_config_hash,
            )
            for item in expanded.trials
        ]
        try:
            self.repository.create(experiment, trials)
            if commit:
                self.db.commit()
        except Exception as exc:
            self.db.rollback()
            raise ExperimentApplicationError(
                "EXPERIMENT_CONFIG_INVALID",
                "experiment definition could not be persisted",
            ) from exc
        _log_experiment_event(
            "experiment_created",
            experiment_id=experiment.id,
            trial_count=experiment.trial_count,
            definition_hash=experiment.definition_hash,
            operation="create",
            outcome="CREATED",
        )
        return experiment

    def start(self, experiment_id: uuid.UUID) -> dict[str, Any]:
        materialized: list[dict[str, Any]] = []
        try:
            self._advisory_lock(experiment_id)
            experiment = self.repository.get_for_update(experiment_id)
            if experiment is None:
                raise ExperimentApplicationError(
                    "EXPERIMENT_NOT_FOUND", "portfolio experiment not found"
                )
            if experiment.cancel_requested:
                raise ExperimentApplicationError(
                    "EXPERIMENT_CANCELLED", "cancelled experiment cannot be started"
                )
            self._validate_source_identity(experiment)
            trials = self.repository.list_trials_for_update(experiment_id)
            if len(trials) != experiment.trial_count:
                raise ExperimentApplicationError(
                    "EXPERIMENT_TRIAL_IDENTITY_MISMATCH",
                    "stored trial count does not match the frozen experiment",
                )
            self._validate_base_snapshot(experiment)
            for trial in trials:
                portfolio_snapshot = self._validate_trial(experiment, trial)
                if trial.run_id is not None:
                    self._validate_bound_run(
                        experiment, trial, portfolio_snapshot
                    )
                    continue
                self._invoke_fault_hook("before_materialize_trial", trial)
                run = BacktestRunFactory.build(
                    name=_trial_run_name(experiment, trial),
                    start_date=experiment.start_date,
                    end_date=experiment.end_date,
                    strategy_snapshot=experiment.base_config_snapshot["strategy"],
                    opportunity_snapshot=experiment.base_config_snapshot[
                        "opportunity"
                    ],
                    portfolio_snapshot=portfolio_snapshot,
                    execution_snapshot=experiment.base_config_snapshot["execution"],
                    accounting_snapshot=experiment.base_config_snapshot["accounting"],
                    algo_version=experiment.base_algo_version,
                    opportunity_calc_version=(
                        experiment.base_opportunity_calc_version
                    ),
                    portfolio_version=experiment.base_portfolio_version,
                    execution_version=experiment.base_execution_version,
                    accounting_version=experiment.base_accounting_version,
                    backtest_engine_version=(
                        experiment.base_backtest_engine_version
                    ),
                )
                self.repository.add_run(run)
                trial.run_id = run.id
                materialized.append(
                    {
                        "experiment_id": experiment_id,
                        "trial_id": trial.id,
                        "trial_no": trial.trial_no,
                        "run_id": run.id,
                        "parameter_hash": trial.parameter_hash,
                    }
                )
            if experiment.started_at is None:
                experiment.started_at = datetime.now(UTC)
            experiment.updated_at = datetime.now(UTC)
            trial_ids = [trial.id for trial in trials]
            self.db.commit()
        except ExperimentApplicationError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            raise ExperimentApplicationError(
                "EXPERIMENT_MATERIALIZATION_FAILED",
                "experiment child run materialization failed",
            ) from exc

        for log_fields in materialized:
            _log_experiment_event(
                "experiment_materialize_trial",
                **log_fields,
                operation="materialize",
                outcome="CREATED",
            )
        self._invoke_fault_hook("after_materialization_commit", None)
        for trial_id in trial_ids:
            outcome = self._dispatch_trial_if_allowed(experiment_id, trial_id)
            if outcome == "CANCELLED_GATE":
                break
        return self.get(experiment_id)

    def _dispatch_trial_if_allowed(
        self, experiment_id: uuid.UUID, trial_id: uuid.UUID
    ) -> str:
        """Serialize the parent stop gate and M13 job creation in one transaction."""
        try:
            self._invoke_fault_hook("before_dispatch_lock", None)
            self._advisory_lock(experiment_id)
            experiment = self.repository.get_for_update(experiment_id)
            if experiment is None:
                raise ExperimentApplicationError(
                    "EXPERIMENT_NOT_FOUND", "portfolio experiment not found"
                )
            record = self.repository.get_trial_record(experiment_id, trial_id)
            if record is None:
                self._raise_identity_mismatch(
                    experiment,
                    "experiment trial disappeared before dispatch",
                )
            trial = record.trial
            if experiment.cancel_requested:
                log_fields = {
                    "experiment_id": experiment_id,
                    "trial_id": trial.id,
                    "trial_no": trial.trial_no,
                    "run_id": trial.run_id,
                    "parameter_hash": trial.parameter_hash,
                }
                self.db.commit()
                _log_experiment_event(
                    "experiment_dispatch_skipped",
                    **log_fields,
                    operation="dispatch",
                    outcome="CANCELLED_GATE",
                    reason="parent_cancel_requested",
                )
                return "CANCELLED_GATE"
            if record.run is None:
                self._raise_identity_mismatch(
                    experiment,
                    f"trial {trial.trial_no} has no materialized child run",
                    trial=trial,
                )
            if record.run.status in _TERMINAL_TRIAL_STATES:
                return self._skip_dispatch(record, "TERMINAL", record.run.status)
            if record.job is not None and record.job.status in _ACTIVE_JOB_STATUSES:
                return self._skip_dispatch(record, "ACTIVE", record.job.status)
            if record.run.status != "CREATED":
                return self._skip_dispatch(
                    record, "ACTIVE", f"run_status_{record.run.status.lower()}"
                )

            self._invoke_fault_hook("after_dispatch_gate", trial)
            run, job = BacktestApplicationService(
                self.db, settings=self.settings
            ).execute(record.run.id)
            _log_experiment_event(
                "experiment_dispatch_trial",
                experiment_id=experiment_id,
                trial_id=trial.id,
                trial_no=trial.trial_no,
                run_id=run.id,
                job_id=job.id,
                parameter_hash=trial.parameter_hash,
                operation="dispatch",
                outcome="DISPATCHED",
            )
            return "DISPATCHED"
        except ExperimentApplicationError:
            self.db.rollback()
            raise
        except BacktestConflictError as exc:
            self.db.rollback()
            refreshed = self.repository.get_trial_record(experiment_id, trial_id)
            if refreshed is not None and refreshed.run is not None:
                if (
                    refreshed.run.job_id == exc.job_id
                    and refreshed.job is not None
                    and refreshed.job.status in _ACTIVE_JOB_STATUSES
                ):
                    return self._skip_dispatch(
                        refreshed, "ACTIVE", "same_active_job_conflict"
                    )
                if refreshed.run.status in _TERMINAL_TRIAL_STATES:
                    return self._skip_dispatch(
                        refreshed, "TERMINAL", refreshed.run.status
                    )
            self.db.rollback()
            raise ExperimentApplicationError(
                "EXPERIMENT_DISPATCH_CONFLICT",
                "experiment child run dispatch conflicted with another lifecycle operation",
            ) from exc
        except Exception as exc:
            self.db.rollback()
            raise ExperimentApplicationError(
                "EXPERIMENT_DISPATCH_CONFLICT",
                "experiment child run dispatch failed",
            ) from exc

    def _skip_dispatch(
        self, record: ExperimentTrialRecord, outcome: str, reason: str
    ) -> str:
        log_fields = {
            "experiment_id": record.trial.experiment_id,
            "trial_id": record.trial.id,
            "trial_no": record.trial.trial_no,
            "run_id": record.trial.run_id,
            "job_id": record.run.job_id if record.run is not None else None,
            "parameter_hash": record.trial.parameter_hash,
        }
        self.db.commit()
        _log_experiment_event(
            "experiment_dispatch_skipped",
            **log_fields,
            operation="dispatch",
            outcome=outcome,
            reason=reason,
        )
        return outcome

    def get(self, experiment_id: uuid.UUID) -> dict[str, Any]:
        experiment = self.repository.get(experiment_id)
        if experiment is None:
            raise ExperimentApplicationError(
                "EXPERIMENT_NOT_FOUND", "portfolio experiment not found"
            )
        return _experiment_payload(experiment, self.repository.list_records(experiment_id))

    def trials(
        self,
        experiment_id: uuid.UUID,
        *,
        state: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        if state is not None and state not in _TRIAL_STATES:
            raise ExperimentApplicationError(
                "EXPERIMENT_CONFIG_INVALID", f"unsupported trial state: {state}"
            )
        if self.repository.get(experiment_id) is None:
            raise ExperimentApplicationError(
                "EXPERIMENT_NOT_FOUND", "portfolio experiment not found"
            )
        records, total = self.repository.trial_page(
            experiment_id, state=state, limit=limit, offset=offset
        )
        return [_trial_payload(item) for item in records], total

    def trial(
        self, experiment_id: uuid.UUID, trial_id: uuid.UUID
    ) -> dict[str, Any]:
        if self.repository.get(experiment_id) is None:
            raise ExperimentApplicationError(
                "EXPERIMENT_NOT_FOUND", "portfolio experiment not found"
            )
        record = self.repository.get_trial_record(experiment_id, trial_id)
        if record is None:
            raise ExperimentApplicationError(
                "EXPERIMENT_NOT_FOUND", "portfolio experiment trial not found"
            )
        payload = _trial_payload(record)
        if record.run is not None:
            progress = BacktestApplicationService(
                self.db, settings=self.settings
            ).progress(record.run.id)
            payload["progress"] = {
                "current_trade_date": (
                    progress.current_trade_date.isoformat()
                    if progress.current_trade_date
                    else None
                ),
                "current_phase": progress.current_phase,
                "total_trade_days": progress.total_trade_days,
                "completed_trade_days": progress.completed_trade_days,
                "progress_pct": progress.progress_pct,
                "error_code": progress.error_code,
                "error_message": progress.error_message,
            }
        else:
            payload["progress"] = None
        return payload

    def cancel(self, experiment_id: uuid.UUID) -> dict[str, Any]:
        self._advisory_lock(experiment_id)
        experiment = self.repository.get_for_update(experiment_id)
        if experiment is None:
            self.db.rollback()
            raise ExperimentApplicationError(
                "EXPERIMENT_NOT_FOUND", "portfolio experiment not found"
            )
        experiment.cancel_requested = True
        experiment.updated_at = datetime.now(UTC)
        self.db.commit()
        _log_experiment_event(
            "experiment_cancel_requested",
            experiment_id=experiment_id,
            operation="cancel",
            outcome="GATE_COMMITTED",
        )

        self.db.expire_all()
        records = self.repository.list_records(experiment_id)
        backtests = BacktestApplicationService(self.db, settings=self.settings)
        for record in records:
            if record.run is None or record.run.status in _TERMINAL_TRIAL_STATES:
                continue
            if not (
                record.run.status == "RUNNING"
                or (
                    record.job is not None
                    and record.job.status in _ACTIVE_JOB_STATUSES
                )
            ):
                continue
            try:
                run, job = backtests.cancel(record.run.id)
                _log_experiment_event(
                    "experiment_cancel_child",
                    experiment_id=experiment_id,
                    trial_id=record.trial.id,
                    trial_no=record.trial.trial_no,
                    run_id=run.id,
                    job_id=job.id if job is not None else None,
                    parameter_hash=record.trial.parameter_hash,
                    operation="cancel",
                    outcome="CANCEL_REQUESTED",
                )
            except (BacktestConflictError, LookupError) as exc:
                self.db.rollback()
                _log_experiment_event(
                    "experiment_cancel_child",
                    level="WARNING",
                    experiment_id=experiment_id,
                    trial_id=record.trial.id,
                    trial_no=record.trial.trial_no,
                    run_id=record.trial.run_id,
                    parameter_hash=record.trial.parameter_hash,
                    operation="cancel",
                    outcome="CONFLICT",
                    reason=type(exc).__name__,
                )
                continue
        return self.get(experiment_id)

    def _invoke_fault_hook(
        self, stage: str, trial: PortfolioExperimentTrial | None
    ) -> None:
        if self.fault_hook is not None:
            self.fault_hook(stage, trial)

    def _advisory_lock(self, experiment_id: uuid.UUID) -> None:
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            lock_key = int.from_bytes(
                experiment_id.bytes[:8], byteorder="big", signed=True
            )
            self.db.execute(select(func.pg_advisory_xact_lock(lock_key)))

    def _validate_source_identity(self, experiment: PortfolioExperiment) -> None:
        current = {
            "algo_version": self.settings.algo_version,
            "source_strategy_config_hash": analysis_strategy_hash(
                self.settings.strategy
            ),
            "opportunity_calc_version": OPPORTUNITY_CALC_VERSION,
            "opportunity_config_hash": config_hash(
                self.settings.opportunity_config
            ),
        }
        frozen = {
            "algo_version": experiment.base_algo_version,
            "source_strategy_config_hash": (
                experiment.base_source_strategy_config_hash
            ),
            "opportunity_calc_version": experiment.base_opportunity_calc_version,
            "opportunity_config_hash": experiment.base_opportunity_config_hash,
        }
        mismatches = [
            f"{key}: runtime={current[key]}, frozen={frozen[key]}"
            for key in current
            if current[key] != frozen[key]
        ]
        if mismatches:
            _log_experiment_event(
                "experiment_source_identity_drift",
                level="WARNING",
                experiment_id=experiment.id,
                operation="start",
                outcome="REJECTED",
                mismatch_fields=tuple(
                    key for key in current if current[key] != frozen[key]
                ),
            )
            raise ExperimentApplicationError(
                "EXPERIMENT_SOURCE_IDENTITY_DRIFT", "; ".join(mismatches)
            )

    def _raise_identity_mismatch(
        self,
        experiment: PortfolioExperiment,
        reason: str,
        *,
        trial: PortfolioExperimentTrial | None = None,
        mismatch_fields: Sequence[str] = (),
    ) -> None:
        _log_experiment_event(
            "experiment_identity_mismatch",
            level="ERROR",
            experiment_id=experiment.id,
            trial_id=trial.id if trial is not None else None,
            trial_no=trial.trial_no if trial is not None else None,
            run_id=trial.run_id if trial is not None else None,
            parameter_hash=trial.parameter_hash if trial is not None else None,
            operation="validate",
            outcome="REJECTED",
            reason=reason,
            mismatch_fields=tuple(mismatch_fields),
        )
        raise ExperimentApplicationError(
            "EXPERIMENT_TRIAL_IDENTITY_MISMATCH", reason
        )

    def _validate_base_snapshot(self, experiment: PortfolioExperiment) -> None:
        snapshot = experiment.base_config_snapshot
        required = {"strategy", "opportunity", "portfolio", "execution", "accounting"}
        if (
            not isinstance(snapshot, dict)
            or set(snapshot) != required
            or any(
            not isinstance(snapshot.get(key), dict) for key in required
            )
        ):
            raise ExperimentApplicationError(
                "EXPERIMENT_TRIAL_CONFIG_INVALID",
                "frozen base_config_snapshot is incomplete",
            )
        if config_hash(experiment.parameter_space) != experiment.parameter_space_hash:
            self._raise_identity_mismatch(
                experiment, "frozen parameter space hash mismatch"
            )
        if config_hash(_stored_definition_payload(experiment)) != experiment.definition_hash:
            self._raise_identity_mismatch(
                experiment, "frozen experiment definition hash mismatch"
            )
        hashes = {
            "base_source_strategy_config_hash": analysis_strategy_hash(
                snapshot["strategy"]
            ),
            "base_opportunity_config_hash": config_hash(snapshot["opportunity"]),
            "base_portfolio_config_hash": config_hash(snapshot["portfolio"]),
            "base_execution_config_hash": config_hash(snapshot["execution"]),
            "base_accounting_config_hash": config_hash(snapshot["accounting"]),
        }
        mismatches = [
            field
            for field, actual in hashes.items()
            if actual != getattr(experiment, field)
        ]
        if mismatches:
            self._raise_identity_mismatch(
                experiment,
                f"frozen base snapshot hash mismatch: {mismatches}",
                mismatch_fields=mismatches,
            )

    def _validate_trial(
        self,
        experiment: PortfolioExperiment,
        trial: PortfolioExperimentTrial,
    ) -> dict[str, Any]:
        if set(trial.parameter_values) != set(EXPERIMENT_PARAMETER_ORDER):
            self._raise_identity_mismatch(
                experiment,
                f"trial {trial.trial_no} does not contain the complete parameter set",
                trial=trial,
            )
        if config_hash(trial.parameter_values) != trial.parameter_hash:
            self._raise_identity_mismatch(
                experiment,
                f"trial {trial.trial_no} parameter hash mismatch",
                trial=trial,
                mismatch_fields=("parameter_hash",),
            )
        if config_hash(trial.portfolio_config_snapshot) != trial.portfolio_config_hash:
            self._raise_identity_mismatch(
                experiment,
                f"trial {trial.trial_no} portfolio hash mismatch",
                trial=trial,
                mismatch_fields=("portfolio_config_hash",),
            )
        expected = deepcopy(experiment.base_config_snapshot["portfolio"])
        try:
            for path, value in trial.parameter_values.items():
                section, field = path.split(".", maxsplit=1)
                expected[section][field] = value
        except (KeyError, TypeError, ValueError) as exc:
            raise ExperimentApplicationError(
                "EXPERIMENT_TRIAL_CONFIG_INVALID",
                f"trial {trial.trial_no} parameter mapping is invalid",
            ) from exc
        try:
            portfolio = PortfolioConfig.model_validate(expected)
        except ValidationError as exc:
            raise ExperimentApplicationError(
                "EXPERIMENT_TRIAL_CONFIG_INVALID",
                f"trial {trial.trial_no} portfolio configuration is invalid: {exc}",
            ) from exc
        canonical = portfolio.model_dump(mode="json")
        if canonical != trial.portfolio_config_snapshot:
            self._raise_identity_mismatch(
                experiment,
                f"trial {trial.trial_no} snapshot does not match its parameters",
                trial=trial,
                mismatch_fields=("portfolio_config_snapshot",),
            )
        if portfolio.candidate.top_n < portfolio.construction.max_positions or (
            portfolio.construction.max_new_positions_per_day
            > portfolio.construction.max_positions
        ):
            raise ExperimentApplicationError(
                "EXPERIMENT_TRIAL_CONFIG_INVALID",
                f"trial {trial.trial_no} violates Portfolio cross-field constraints",
            )
        return canonical

    def _validate_bound_run(
        self,
        experiment: PortfolioExperiment,
        trial: PortfolioExperimentTrial,
        portfolio_snapshot: dict[str, Any],
    ) -> None:
        assert trial.run_id is not None
        run = self.repository.get_run(trial.run_id)
        if run is None:
            self._raise_identity_mismatch(
                experiment,
                f"trial {trial.trial_no} references a missing child run",
                trial=trial,
                mismatch_fields=("run_id",),
            )
        expected_snapshot = {
            "strategy": experiment.base_config_snapshot["strategy"],
            "opportunity": experiment.base_config_snapshot["opportunity"],
            "portfolio": portfolio_snapshot,
            "execution": experiment.base_config_snapshot["execution"],
            "accounting": experiment.base_config_snapshot["accounting"],
        }
        mismatches = [
            field
            for field, expected in (
                ("account_mode", "BACKTEST"),
                ("start_date", experiment.start_date),
                ("end_date", experiment.end_date),
                ("initial_cash", experiment.initial_cash),
                ("benchmark_code", experiment.benchmark_code),
                ("algo_version", experiment.base_algo_version),
                (
                    "source_strategy_config_hash",
                    experiment.base_source_strategy_config_hash,
                ),
                (
                    "opportunity_calc_version",
                    experiment.base_opportunity_calc_version,
                ),
                (
                    "opportunity_config_hash",
                    experiment.base_opportunity_config_hash,
                ),
                ("portfolio_version", experiment.base_portfolio_version),
                ("portfolio_config_hash", trial.portfolio_config_hash),
                ("execution_version", experiment.base_execution_version),
                (
                    "execution_config_hash",
                    experiment.base_execution_config_hash,
                ),
                ("accounting_version", experiment.base_accounting_version),
                (
                    "accounting_config_hash",
                    experiment.base_accounting_config_hash,
                ),
                (
                    "backtest_engine_version",
                    experiment.base_backtest_engine_version,
                ),
                ("config_snapshot", expected_snapshot),
            )
            if getattr(run, field) != expected
        ]
        if mismatches:
            self._raise_identity_mismatch(
                experiment,
                f"trial {trial.trial_no} child run identity mismatch: {mismatches}",
                trial=trial,
                mismatch_fields=mismatches,
            )


def _experiment_payload(
    experiment: PortfolioExperiment, records: list[ExperimentTrialRecord]
) -> dict[str, Any]:
    counts = {state.lower(): 0 for state in _TRIAL_STATES}
    active = False
    for record in records:
        state = _trial_state(record)
        counts[state.lower()] += 1
        if record.run is not None and record.run.status == "RUNNING":
            active = True
        if record.job is not None and record.job.status in _ACTIVE_JOB_STATUSES:
            active = True
    terminal_count = sum(counts[state.lower()] for state in _TERMINAL_TRIAL_STATES)
    success_count = counts["success"]
    failed_count = counts["failed"]
    cancelled_count = counts["cancelled"]
    if experiment.cancel_requested and not active:
        state = "CANCELLED"
    elif experiment.started_at is None:
        state = "CREATED"
    elif terminal_count < experiment.trial_count:
        state = "RUNNING"
    elif success_count == experiment.trial_count:
        state = "SUCCESS"
    elif failed_count > 0 and success_count == 0:
        state = "FAILED"
    elif cancelled_count == experiment.trial_count:
        state = "CANCELLED"
    else:
        state = "COMPLETED_WITH_ERRORS"
    return {
        "id": str(experiment.id),
        "name": experiment.name,
        "experiment_version": experiment.experiment_version,
        "search_method": experiment.search_method,
        "state": state,
        "start_date": experiment.start_date.isoformat(),
        "end_date": experiment.end_date.isoformat(),
        "initial_cash": str(experiment.initial_cash),
        "benchmark_code": experiment.benchmark_code,
        "definition_hash": experiment.definition_hash,
        "parameter_space_hash": experiment.parameter_space_hash,
        "parameter_space": experiment.parameter_space,
        "trial_count": experiment.trial_count,
        "counts": {**counts, "terminal": terminal_count},
        **{f"{name}_count": value for name, value in counts.items()},
        "terminal_count": terminal_count,
        "progress_pct": round(terminal_count / experiment.trial_count * 100, 2),
        "cancel_requested": experiment.cancel_requested,
        "started_at": experiment.started_at.isoformat() if experiment.started_at else None,
        "created_at": experiment.created_at.isoformat(),
        "updated_at": experiment.updated_at.isoformat(),
        "base_identity": {
            "algo_version": experiment.base_algo_version,
            "source_strategy_config_hash": (
                experiment.base_source_strategy_config_hash
            ),
            "opportunity_calc_version": experiment.base_opportunity_calc_version,
            "opportunity_config_hash": experiment.base_opportunity_config_hash,
            "portfolio_version": experiment.base_portfolio_version,
            "portfolio_config_hash": experiment.base_portfolio_config_hash,
            "execution_version": experiment.base_execution_version,
            "execution_config_hash": experiment.base_execution_config_hash,
            "accounting_version": experiment.base_accounting_version,
            "accounting_config_hash": experiment.base_accounting_config_hash,
            "backtest_engine_version": experiment.base_backtest_engine_version,
        },
    }


def _trial_payload(record: ExperimentTrialRecord) -> dict[str, Any]:
    trial, run, job = record.trial, record.run, record.job
    summary = dict(run.result_summary or {}) if run is not None else {}
    return {
        "id": str(trial.id),
        "experiment_id": str(trial.experiment_id),
        "trial_no": trial.trial_no,
        "state": _trial_state(record),
        "parameter_values": trial.parameter_values,
        "parameter_hash": trial.parameter_hash,
        "portfolio_config_hash": trial.portfolio_config_hash,
        "run_id": str(run.id) if run is not None else None,
        "run_status": run.status if run is not None else None,
        "job_id": str(job.id) if job is not None else None,
        "job_status": job.status if job is not None else None,
        "error_code": summary.get("error_code"),
        "error_message": (
            job.error_message
            if job is not None and job.error_message
            else run.error_message if run is not None else None
        ),
        "created_at": trial.created_at.isoformat(),
        "updated_at": trial.updated_at.isoformat(),
    }


def _trial_state(record: ExperimentTrialRecord) -> str:
    return record.run.status if record.run is not None else "PLANNED"


def _trial_run_name(
    experiment: PortfolioExperiment, trial: PortfolioExperimentTrial
) -> str:
    prefix = experiment.name or "experiment"
    return f"{prefix} / trial-{trial.trial_no:04d}"[:128]


def _canonical_decimal(value: Decimal) -> str:
    return "0" if value == 0 else format(value.normalize(), "f")


def _stored_definition_payload(experiment: PortfolioExperiment) -> dict[str, Any]:
    return {
        "experiment_version": experiment.experiment_version,
        "search_method": experiment.search_method,
        "start_date": experiment.start_date.isoformat(),
        "end_date": experiment.end_date.isoformat(),
        "initial_cash": _canonical_decimal(experiment.initial_cash),
        "benchmark_code": experiment.benchmark_code,
        "algo_version": experiment.base_algo_version,
        "source_strategy_config_hash": experiment.base_source_strategy_config_hash,
        "opportunity_calc_version": experiment.base_opportunity_calc_version,
        "opportunity_config_hash": experiment.base_opportunity_config_hash,
        "base_portfolio_version": experiment.base_portfolio_version,
        "base_portfolio_config_hash": experiment.base_portfolio_config_hash,
        "execution_version": experiment.base_execution_version,
        "execution_config_hash": experiment.base_execution_config_hash,
        "accounting_version": experiment.base_accounting_version,
        "accounting_config_hash": experiment.base_accounting_config_hash,
        "backtest_engine_version": experiment.base_backtest_engine_version,
        "parameter_space_hash": experiment.parameter_space_hash,
    }


def _safe_log_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in fields.items():
        if key not in _EXPERIMENT_LOG_FIELDS or value is None:
            continue
        if isinstance(value, uuid.UUID):
            safe[key] = str(value)
        elif key == "mismatch_fields":
            safe[key] = tuple(str(item) for item in value)
        elif isinstance(value, (str, int, float, bool)):
            safe[key] = value
    return safe


def _log_experiment_event(
    event: str, *, level: str = "INFO", **fields: Any
) -> None:
    logger.bind(event=event, **_safe_log_fields(fields)).log(level, event)
