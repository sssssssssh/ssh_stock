import uuid
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

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


class ExperimentApplicationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ExperimentApplicationService:
    def __init__(self, db: Session, *, settings: Settings | None = None) -> None:
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
        if end_date < start_date:
            raise ExperimentApplicationError(
                "EXPERIMENT_CONFIG_INVALID",
                "end_date must be on or after start_date",
            )
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
        try:
            expanded = expand_grid(
                base_portfolio=effective_portfolio,
                grid=grid,
                max_trials=self.experiment_config.max_trials,
                max_values_per_parameter=(
                    self.experiment_config.max_values_per_parameter
                ),
            )
        except ExperimentGridError as exc:
            raise ExperimentApplicationError(exc.code, str(exc)) from exc

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
        definition_hash = config_hash(
            {
                "experiment_version": self.experiment_config.version,
                "search_method": self.experiment_config.search_method,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "initial_cash": _canonical_decimal(
                    effective_portfolio.initial_cash_cny
                ),
                "benchmark_code": effective_portfolio.benchmark_code,
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
            initial_cash=effective_portfolio.initial_cash_cny,
            benchmark_code=effective_portfolio.benchmark_code,
            definition_hash=definition_hash,
            parameter_space_hash=expanded.parameter_space_hash,
            parameter_space=expanded.parameter_space,
            trial_count=len(expanded.trials),
            base_config_snapshot=base_snapshot,
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
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            raise ExperimentApplicationError(
                "EXPERIMENT_CONFIG_INVALID",
                "experiment definition could not be persisted",
            ) from exc
        return self.get(experiment_id)

    def start(self, experiment_id: uuid.UUID) -> dict[str, Any]:
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
            if experiment.started_at is None:
                experiment.started_at = datetime.now(UTC)
            experiment.updated_at = datetime.now(UTC)
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

        records = self.repository.list_records(experiment_id)
        backtests = BacktestApplicationService(self.db, settings=self.settings)
        for record in records:
            self.db.expire_all()
            current = self.repository.get(experiment_id)
            if current is None or current.cancel_requested:
                break
            if record.run is None or record.run.status in _TERMINAL_TRIAL_STATES:
                continue
            if record.job is not None and record.job.status in _ACTIVE_JOB_STATUSES:
                continue
            try:
                backtests.execute(record.run.id)
            except BacktestConflictError as exc:
                self.db.rollback()
                refreshed = self.repository.get_trial_record(
                    experiment_id, record.trial.id
                )
                if (
                    refreshed is not None
                    and refreshed.run is not None
                    and refreshed.run.job_id == exc.job_id
                    and refreshed.job is not None
                    and refreshed.job.status in _ACTIVE_JOB_STATUSES
                ):
                    continue
                raise ExperimentApplicationError(
                    "EXPERIMENT_DISPATCH_CONFLICT", str(exc)
                ) from exc
            except Exception as exc:
                self.db.rollback()
                raise ExperimentApplicationError(
                    "EXPERIMENT_DISPATCH_CONFLICT",
                    "experiment child run dispatch failed",
                ) from exc
        return self.get(experiment_id)

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
                backtests.cancel(record.run.id)
            except (BacktestConflictError, LookupError):
                self.db.rollback()
                continue
        return self.get(experiment_id)

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
            raise ExperimentApplicationError(
                "EXPERIMENT_SOURCE_IDENTITY_DRIFT", "; ".join(mismatches)
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
            raise ExperimentApplicationError(
                "EXPERIMENT_TRIAL_IDENTITY_MISMATCH",
                "frozen parameter space hash mismatch",
            )
        if config_hash(_stored_definition_payload(experiment)) != experiment.definition_hash:
            raise ExperimentApplicationError(
                "EXPERIMENT_TRIAL_IDENTITY_MISMATCH",
                "frozen experiment definition hash mismatch",
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
            raise ExperimentApplicationError(
                "EXPERIMENT_TRIAL_IDENTITY_MISMATCH",
                f"frozen base snapshot hash mismatch: {mismatches}",
            )

    def _validate_trial(
        self,
        experiment: PortfolioExperiment,
        trial: PortfolioExperimentTrial,
    ) -> dict[str, Any]:
        if set(trial.parameter_values) != set(EXPERIMENT_PARAMETER_ORDER):
            raise ExperimentApplicationError(
                "EXPERIMENT_TRIAL_IDENTITY_MISMATCH",
                f"trial {trial.trial_no} does not contain the complete parameter set",
            )
        if config_hash(trial.parameter_values) != trial.parameter_hash:
            raise ExperimentApplicationError(
                "EXPERIMENT_TRIAL_IDENTITY_MISMATCH",
                f"trial {trial.trial_no} parameter hash mismatch",
            )
        if config_hash(trial.portfolio_config_snapshot) != trial.portfolio_config_hash:
            raise ExperimentApplicationError(
                "EXPERIMENT_TRIAL_IDENTITY_MISMATCH",
                f"trial {trial.trial_no} portfolio hash mismatch",
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
            raise ExperimentApplicationError(
                "EXPERIMENT_TRIAL_IDENTITY_MISMATCH",
                f"trial {trial.trial_no} snapshot does not match its parameters",
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
            raise ExperimentApplicationError(
                "EXPERIMENT_TRIAL_IDENTITY_MISMATCH",
                f"trial {trial.trial_no} references a missing child run",
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
            raise ExperimentApplicationError(
                "EXPERIMENT_TRIAL_IDENTITY_MISMATCH",
                f"trial {trial.trial_no} child run identity mismatch: {mismatches}",
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
    if experiment.cancel_requested and not active:
        state = "CANCELLED"
    elif experiment.started_at is None:
        state = "CREATED"
    elif terminal_count == experiment.trial_count:
        if success_count == experiment.trial_count:
            state = "SUCCESS"
        elif success_count:
            state = "COMPLETED_WITH_ERRORS"
        else:
            state = "FAILED"
    else:
        state = "RUNNING"
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
