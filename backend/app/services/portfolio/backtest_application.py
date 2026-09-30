import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.execution import OrderIntent
from app.domain.portfolio import (
    AccountState,
    DailyPortfolioSnapshot,
    PendingOrderState,
    PortfolioTarget,
)
from app.models.job import JobRun
from app.models.market_data import TradeCalendar
from app.models.portfolio import (
    PortfolioBacktestCheckpoint,
    PortfolioBacktestRun,
    PortfolioFill,
    PortfolioNavDaily,
    PortfolioOrder,
    PortfolioOrderAttempt,
    PortfolioPositionDaily,
)
from app.repositories.portfolio import PortfolioRepository
from app.services.calc_metadata import config_hash
from app.services.execution.application import ExecutionApplicationService
from app.services.execution.market_data import ExecutionMarketDataProvider
from app.services.portfolio.account_gateway import (
    PortfolioAccountingAccountGateway,
    canonical_account_snapshot,
    load_persisted_close_snapshot,
)
from app.services.portfolio.accounting import AccountingFill
from app.services.portfolio.accounting_application import AccountingApplicationService
from app.services.portfolio.candidates import OpportunityCandidateProvider
from app.services.portfolio.contracts import PortfolioSourceNotReadyError
from app.services.portfolio.policy import TopNEqualWeightPolicy
from app.services.portfolio.rebalance_application import RebalanceApplicationService
from app.services.portfolio.rebalance_market_data import RebalanceMarketDataProvider
from app.services.portfolio.run_guard import (
    FrozenRunConfig,
    validate_resumable_backtest_contract,
)

BACKTEST_JOB_TYPE = "portfolio_backtest"
PHASES = (
    "START_OF_DAY",
    "OPEN",
    "CLOSE",
    "AFTER_CLOSE",
    "DAY_COMPLETED",
)
_ACTIVE_JOB_STATUSES = {"QUEUED", "RUNNING"}
_TERMINAL_RUN_STATUSES = {"SUCCESS", "FAILED", "CANCELLED"}
_AFTER_CLOSE_RESULT_IDENTITY_VERSION = "after_close_result_v2"


class BacktestConflictError(RuntimeError):
    def __init__(self, message: str, *, job_id: uuid.UUID | None = None) -> None:
        self.job_id = job_id
        super().__init__(message)


class BacktestOwnershipError(RuntimeError):
    pass


class _BacktestCancellationRequested(RuntimeError):
    pass


class BacktestRecoveryRejectedError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class BacktestProgress:
    run: PortfolioBacktestRun
    job: JobRun | None
    current_trade_date: date | None
    current_phase: str | None
    total_trade_days: int
    completed_trade_days: int
    progress_pct: float
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True)
class BacktestExecutionLease:
    run_id: uuid.UUID
    job_id: uuid.UUID
    worker_id: str
    ownership_version: int


class BacktestApplicationService:
    """Queue lifecycle and read APIs; the worker remains the only execution entry."""

    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        repository: PortfolioRepository | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repository = repository or PortfolioRepository(db)

    def execute(self, run_id: uuid.UUID) -> tuple[PortfolioBacktestRun, JobRun]:
        run = self._locked_run(run_id)
        active = self._active_job(run)
        if active is not None:
            raise BacktestConflictError(
                "backtest already has an active execution job", job_id=active.id
            )
        if run.status != "CREATED":
            raise BacktestConflictError(
                f"only a CREATED backtest can be executed, got {run.status}",
                job_id=run.job_id,
            )
        validate_resumable_backtest_contract(run, settings=self.settings)
        return self._queue(run, resume=False)

    def resume(self, run_id: uuid.UUID) -> tuple[PortfolioBacktestRun, JobRun]:
        run = self._locked_run(run_id)
        active = self._active_job(run)
        if active is not None:
            raise BacktestConflictError(
                "backtest already has an active execution job", job_id=active.id
            )
        if run.status not in {"FAILED", "CANCELLED"}:
            raise BacktestConflictError(
                f"only a FAILED or CANCELLED backtest can be resumed, got {run.status}",
                job_id=run.job_id,
            )
        validate_resumable_backtest_contract(run, settings=self.settings)
        BacktestRunner(
            self.db, settings=self.settings, repository=self.repository
        ).audit_checkpoint_sequence(run.id, validate_sources=False)
        return self._queue(run, resume=True)

    def cancel(self, run_id: uuid.UUID) -> tuple[PortfolioBacktestRun, JobRun | None]:
        # Lock order is JobRun -> PortfolioBacktestRun everywhere that needs both.
        # The initial scalar read only discovers the current job pointer; both rows
        # are revalidated after the locks have been acquired.
        job_id = self.db.scalar(
            select(PortfolioBacktestRun.job_id).where(
                PortfolioBacktestRun.id == run_id
            )
        )
        if job_id is None:
            run = self._locked_run(run_id)
            job = None
        else:
            job = self.db.execute(
                select(JobRun)
                .where(JobRun.id == job_id)
                .execution_options(populate_existing=True)
                .with_for_update()
            ).scalar_one_or_none()
            run = self._locked_run(run_id)
            if run.job_id != job_id:
                self.db.rollback()
                raise BacktestConflictError(
                    "backtest execution changed while cancellation was requested",
                    job_id=run.job_id,
                )
        now = datetime.now(UTC)
        if run.status == "CANCELLED":
            self.db.commit()
            return run, job
        if job is None or job.status not in _ACTIVE_JOB_STATUSES:
            raise BacktestConflictError(
                f"backtest has no cancellable job in status {run.status}",
                job_id=run.job_id,
            )
        job.cancel_requested = True
        if job.status == "QUEUED":
            job.status = "CANCELLED"
            job.finished_at = now
            job.step = "cancelled before execution"
            run.status = "CANCELLED"
            run.finished_at = now
            run.owner_worker_id = None
            run.error_message = None
        else:
            job.step = "cancellation requested; waiting for phase boundary"
        self.db.add_all([run, job])
        self.db.commit()
        self.db.refresh(run)
        self.db.refresh(job)
        return run, job

    def progress(self, run_id: uuid.UUID) -> BacktestProgress:
        run = self.repository.get_run(run_id)
        if run is None:
            raise LookupError("portfolio backtest run not found")
        checkpoints = self.repository.list_checkpoints(run_id)
        dates = _trade_dates(self.db, run)
        completed_days = sum(
            item.phase == "DAY_COMPLETED" and item.phase_status == "COMPLETED"
            for item in checkpoints
        )
        current = checkpoints[-1] if checkpoints else None
        failed = next(
            (item for item in reversed(checkpoints) if item.phase_status == "FAILED"),
            None,
        )
        total = len(dates)
        pct = round(completed_days / total * 100, 2) if total else 0.0
        job = self.db.get(JobRun, run.job_id) if run.job_id else None
        return BacktestProgress(
            run=run,
            job=job,
            current_trade_date=current.trade_date if current else None,
            current_phase=current.phase if current else None,
            total_trade_days=total,
            completed_trade_days=completed_days,
            progress_pct=pct,
            error_code=failed.error_code if failed else None,
            error_message=(failed.error_message if failed else run.error_message),
        )

    def nav_page(
        self, run_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[PortfolioNavDaily], int]:
        self._require_run(run_id)
        return (
            self.repository.list_nav_page(run_id, limit=limit, offset=offset),
            self.repository.count_nav(run_id),
        )

    def positions_page(
        self, run_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[PortfolioPositionDaily], int]:
        self._require_run(run_id)
        return (
            self.repository.list_positions_page(run_id, limit=limit, offset=offset),
            self.repository.count_positions(run_id),
        )

    def orders_page(
        self, run_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[PortfolioOrder], int]:
        self._require_run(run_id)
        return (
            self.repository.list_orders_page(run_id, limit=limit, offset=offset),
            self.repository.count_orders(run_id),
        )

    def _queue(
        self, run: PortfolioBacktestRun, *, resume: bool
    ) -> tuple[PortfolioBacktestRun, JobRun]:
        job = JobRun(
            job_type=BACKTEST_JOB_TYPE,
            target_trade_date=run.end_date,
            status="QUEUED",
            step="queued for explicit resume" if resume else "queued for execution",
            row_count=0,
            cancel_requested=False,
            job_metadata={
                "portfolio_run_id": str(run.id),
                "resume": resume,
                "stage": "queued",
                "progress_pct": 0,
            },
        )
        self.db.add(job)
        self.db.flush()
        run.job_id = job.id
        run.owner_worker_id = None
        run.error_message = None
        run.result_summary = {
            **dict(run.result_summary or {}),
            "stage": "queued",
            "resume": resume,
        }
        self.db.add(run)
        self.db.commit()
        self.db.refresh(job)
        self.db.refresh(run)
        return run, job

    def _locked_run(self, run_id: uuid.UUID) -> PortfolioBacktestRun:
        run = self.repository.get_run_for_update(run_id)
        if run is None:
            raise LookupError("portfolio backtest run not found")
        return run

    def _require_run(self, run_id: uuid.UUID) -> PortfolioBacktestRun:
        run = self.repository.get_run(run_id)
        if run is None:
            raise LookupError("portfolio backtest run not found")
        return run

    def _active_job(self, run: PortfolioBacktestRun) -> JobRun | None:
        if run.job_id is None:
            return None
        job = self.db.get(JobRun, run.job_id)
        return job if job is not None and job.status in _ACTIVE_JOB_STATUSES else None


class BacktestRunner:
    """The single production path for persistent portfolio backtest execution."""

    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        repository: PortfolioRepository | None = None,
        fault_hook: Callable[[str, str], None] | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repository = repository or PortfolioRepository(db)
        self.fault_hook = fault_hook
        self._dates: tuple[date, ...] = ()

    def run_job(self, job_id: uuid.UUID) -> None:
        try:
            run, job, lease = self._claim_run(job_id)
        except Exception as exc:
            self._mark_claim_failed(job_id, exc)
            raise
        run_id = run.id
        try:
            self._dates = tuple(_trade_dates(self.db, run))
            _validate_trade_calendar(self.db, run, self._dates)
            self.audit_checkpoint_sequence(run_id, validate_sources=True)
            for trade_date in self._dates:
                for phase in PHASES:
                    if self._cancel_requested(job_id):
                        self._finish_cancelled(lease)
                        return
                    try:
                        self._run_phase(lease, trade_date, phase)
                    except _BacktestCancellationRequested:
                        self._finish_cancelled(lease)
                        return
            self._finish_success(lease)
        except Exception as exc:
            self._mark_run_failed(lease, exc)
            raise

    def _mark_claim_failed(self, job_id: uuid.UUID, exc: Exception) -> None:
        self.db.rollback()
        job = self.db.execute(
            select(JobRun)
            .where(JobRun.id == job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        ).scalar_one_or_none()
        if job is None:
            return
        if (
            job.job_type != BACKTEST_JOB_TYPE
            or job.status != "RUNNING"
            or not job.worker_id
        ):
            return
        raw_run_id = dict(job.job_metadata or {}).get("portfolio_run_id")
        try:
            run_id = uuid.UUID(str(raw_run_id))
        except (TypeError, ValueError):
            run_id = None
        run = (
            self.repository.get_run_for_update(run_id)
            if run_id is not None
            else None
        )
        # A competing runner may already own the current generation. A failed
        # duplicate claim must never fail or detach that execution.
        if run is not None and run.status == "RUNNING":
            self.db.rollback()
            return
        now = datetime.now(UTC)
        job.status = "FAILED"
        job.finished_at = now
        job.error_message = str(exc)[:2048]
        job.step = "backtest ownership or compatibility check failed"
        if run is not None and run.job_id == job.id:
            run.status = "FAILED"
            run.finished_at = now
            run.owner_worker_id = None
            run.error_message = str(exc)[:2048]
            run.result_summary = {
                **dict(run.result_summary or {}),
                "stage": "failed",
                "error_code": _error_code(exc),
            }
        self.db.commit()

    def audit_checkpoint_sequence(
        self, run_id: uuid.UUID, *, validate_sources: bool
    ) -> None:
        run = self.repository.get_run(run_id)
        if run is None:
            raise LookupError("portfolio backtest run not found")
        validate_resumable_backtest_contract(run, settings=self.settings)
        dates = tuple(_trade_dates(self.db, run))
        if not dates:
            raise BacktestRecoveryRejectedError(
                "TRADE_CALENDAR_EMPTY", "run interval has no open trade date"
            )
        self._dates = dates
        checkpoints = {
            (item.trade_date, item.phase): item
            for item in self.repository.list_checkpoints(run_id)
        }
        gap_seen = False
        for trade_date in dates:
            for phase in PHASES:
                checkpoint = checkpoints.get((trade_date, phase))
                if checkpoint is None or checkpoint.phase_status != "COMPLETED":
                    if self._phase_has_business_evidence(
                        run_id, trade_date, phase
                    ):
                        raise BacktestRecoveryRejectedError(
                            "UNSEALED_PHASE_EVIDENCE",
                            f"{phase} has business evidence without a completed "
                            "checkpoint",
                        )
                    gap_seen = True
                    continue
                if gap_seen:
                    raise BacktestRecoveryRejectedError(
                        "CHECKPOINT_SEQUENCE_INVALID",
                        "completed checkpoint exists after an incomplete phase",
                    )
                if validate_sources:
                    self._validate_completed_checkpoint(checkpoint)
                elif phase != "START_OF_DAY":
                    self._validate_checkpoint_result(checkpoint)

    def _claim_run(
        self, job_id: uuid.UUID
    ) -> tuple[PortfolioBacktestRun, JobRun, BacktestExecutionLease]:
        job = self.db.execute(
            select(JobRun)
            .where(JobRun.id == job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        ).scalar_one_or_none()
        if job is None or job.job_type != BACKTEST_JOB_TYPE:
            raise BacktestOwnershipError("portfolio backtest job not found")
        if job.status != "RUNNING" or not job.worker_id:
            raise BacktestOwnershipError("backtest job is not owned by a running worker")
        raw_run_id = dict(job.job_metadata or {}).get("portfolio_run_id")
        try:
            run_id = uuid.UUID(str(raw_run_id))
        except (TypeError, ValueError) as exc:
            raise BacktestOwnershipError("backtest job metadata has invalid run id") from exc
        run = self.repository.get_run_for_update(run_id)
        if run is None or run.job_id != job.id:
            raise BacktestOwnershipError("job is not the current execution for this run")
        if run.status in {"CREATED", "FAILED", "CANCELLED"}:
            run.status = "RUNNING"
            run.owner_worker_id = job.worker_id
            run.ownership_version += 1
            run.started_at = run.started_at or datetime.now(UTC)
            run.finished_at = None
            run.error_message = None
        else:
            raise BacktestOwnershipError(f"run cannot start from {run.status}")
        validate_resumable_backtest_contract(run, settings=self.settings)
        job.step = "backtest ownership acquired"
        job.job_metadata = {
            **dict(job.job_metadata or {}),
            "ownership_version": run.ownership_version,
        }
        self.db.add_all([run, job])
        self.db.commit()
        lease = BacktestExecutionLease(
            run_id=run.id,
            job_id=job.id,
            worker_id=job.worker_id,
            ownership_version=run.ownership_version,
        )
        return run, job, lease

    def _run_phase(
        self,
        lease: BacktestExecutionLease,
        trade_date: date,
        phase: str,
    ) -> None:
        run_id = lease.run_id
        job_id = lease.job_id
        worker_id = lease.worker_id
        self._assert_ownership(lease, allow_cancel=False)
        existing = self.repository.get_checkpoint(run_id, trade_date, phase)
        if existing is not None and existing.phase_status == "COMPLETED":
            self._validate_completed_checkpoint(existing)
            self.db.commit()
            return
        if self._phase_has_business_evidence(run_id, trade_date, phase):
            raise BacktestRecoveryRejectedError(
                "UNSEALED_PHASE_EVIDENCE",
                f"{phase} has business evidence without a completed checkpoint",
            )
        input_identity = self._input_identity(run_id, trade_date, phase, completed=False)
        checkpoint = self.repository.get_checkpoint_for_update(
            run_id, trade_date, phase
        )
        now = datetime.now(UTC)
        if checkpoint is None:
            checkpoint = PortfolioBacktestCheckpoint(
                run_id=run_id,
                trade_date=trade_date,
                phase=phase,
                phase_status="STARTED",
                input_identity=input_identity,
                result_identity={},
                started_at=now,
                attempt=1,
                version=1,
                worker_owner=worker_id,
            )
            self.repository.insert_checkpoint(checkpoint)
        else:
            checkpoint.phase_status = "STARTED"
            checkpoint.input_identity = input_identity
            checkpoint.result_identity = {}
            checkpoint.started_at = now
            checkpoint.completed_at = None
            checkpoint.error_code = None
            checkpoint.error_message = None
            checkpoint.attempt += 1
            checkpoint.version += 1
            checkpoint.worker_owner = worker_id
        job = self.db.get(JobRun, job_id)
        assert job is not None
        self._update_job_progress(job, trade_date, phase)
        self.db.commit()

        try:
            # Begin the business transaction with the canonical Job -> Run locks.
            # Nested services may re-lock Run, but they never invert the order.
            self._assert_ownership(lease, allow_cancel=True)
            self._fault(phase, "before_business")
            self._execute_phase(run_id, trade_date, phase)
            self._fault(phase, "after_business_before_checkpoint")
            self._assert_ownership(lease, allow_cancel=True)
            checkpoint = self.repository.get_checkpoint_for_update(
                run_id, trade_date, phase
            )
            if checkpoint is None:
                raise BacktestRecoveryRejectedError(
                    "CHECKPOINT_MISSING", "phase checkpoint disappeared"
                )
            checkpoint.result_identity = self._result_identity(
                run_id, trade_date, phase
            )
            checkpoint.phase_status = "COMPLETED"
            checkpoint.completed_at = datetime.now(UTC)
            checkpoint.error_code = None
            checkpoint.error_message = None
            job = self.db.get(JobRun, job_id)
            assert job is not None
            self._update_job_progress(job, trade_date, phase)
            self.db.commit()
            self._fault(phase, "after_phase_commit")
        except Exception as exc:
            self.db.rollback()
            self._mark_checkpoint_failed(
                lease, trade_date, phase, exc
            )
            raise

    def _execute_phase(self, run_id: uuid.UUID, trade_date: date, phase: str) -> None:
        if phase == "START_OF_DAY":
            PortfolioAccountingAccountGateway(
                self.db, repository=self.repository, settings=self.settings
            ).account_state(run_id, trade_date)
            return
        if phase == "OPEN":
            ExecutionApplicationService(
                self.db, repository=self.repository, settings=self.settings
            ).execute_open_batch(run_id, trade_date, commit=False)
            return
        if phase == "CLOSE":
            AccountingApplicationService(
                self.db, repository=self.repository, settings=self.settings
            ).rebuild_close_snapshot(run_id, trade_date, commit=False)
            return
        if phase == "AFTER_CLOSE":
            next_date = self._next_in_range(trade_date)
            if next_date is None:
                return
            contract, target, account = self._target_for_day(run_id, trade_date)
            RebalanceApplicationService(
                self.db, repository=self.repository, settings=self.settings
            ).plan_and_persist(
                run_id,
                target=target,
                account=account,
                scheduled_trade_date=next_date,
                commit=False,
            )
            if contract.run.id != run_id:
                raise AssertionError("frozen contract run mismatch")
            return
        if phase == "DAY_COMPLETED":
            for required in PHASES[:-1]:
                checkpoint = self.repository.get_checkpoint(
                    run_id, trade_date, required
                )
                if checkpoint is None or checkpoint.phase_status != "COMPLETED":
                    raise BacktestRecoveryRejectedError(
                        "DAY_PHASE_INCOMPLETE",
                        f"{trade_date} {required} is not completed",
                    )
            return
        raise ValueError(f"unsupported backtest phase: {phase}")

    def _input_identity(
        self, run_id: uuid.UUID, trade_date: date, phase: str, *, completed: bool
    ) -> dict[str, Any]:
        run = self.repository.get_run(run_id)
        if run is None:
            raise LookupError("portfolio backtest run not found")
        validate_resumable_backtest_contract(run, settings=self.settings)
        payload: dict[str, Any] = {
            "identity_version": "backtest_phase_input_v1",
            "run_id": str(run_id),
            "trade_date": trade_date.isoformat(),
            "phase": phase,
            "algorithm": {
                "algo_version": run.algo_version,
                "strategy_hash": run.source_strategy_config_hash,
                "opportunity_version": run.opportunity_calc_version,
                "opportunity_hash": run.opportunity_config_hash,
                "portfolio_version": run.portfolio_version,
                "portfolio_hash": run.portfolio_config_hash,
                "execution_version": run.execution_version,
                "execution_hash": run.execution_config_hash,
                "accounting_version": run.accounting_version,
                "accounting_hash": run.accounting_config_hash,
                "backtest_version": run.backtest_engine_version,
            },
        }
        if phase == "START_OF_DAY":
            calendar = self.db.get(TradeCalendar, trade_date)
            account = PortfolioAccountingAccountGateway(
                self.db, repository=self.repository, settings=self.settings
            ).account_state(run_id, trade_date)
            payload["source"] = {
                "pretrade_date": (
                    calendar.pretrade_date.isoformat()
                    if calendar is not None and calendar.pretrade_date
                    else None
                ),
                "account": _json_value(asdict(account)),
            }
        elif phase == "OPEN":
            intents = self._open_intents(run_id, trade_date, completed=completed)
            account = PortfolioAccountingAccountGateway(
                self.db, repository=self.repository, settings=self.settings
            ).account_state(run_id, trade_date)
            market = ExecutionMarketDataProvider(self.db, self.settings).load(
                trade_date, intents
            )
            payload["source"] = {
                "intents": _json_value([asdict(item) for item in intents]),
                "account": _json_value(asdict(account)),
                "market": _json_value(asdict(market)),
            }
        elif phase == "CLOSE":
            service = AccountingApplicationService(
                self.db, repository=self.repository, settings=self.settings
            )
            account = service.account_gateway.account_state(run_id, trade_date)
            fill_rows = self.repository.list_fills_for_date(run_id, trade_date)
            fills = tuple(
                AccountingFill(
                    fill_id=fill.id,
                    order_id=fill.order_id,
                    scheduled_trade_date=order.scheduled_trade_date,
                    ts_code=fill.ts_code,
                    side=fill.side,
                    quantity=fill.quantity,
                    price=fill.price,
                    gross_amount=fill.gross_amount,
                    cash_fee_total=fill.cash_fee_total,
                    total_cost=fill.total_cost,
                )
                for fill, order in fill_rows
            )
            post_fill, _ = service.engine.apply_fills(account, fills)
            market = service.provider.load_close(
                trade_date=trade_date,
                held_codes=tuple(item.ts_code for item in post_fill.positions),
            )
            payload["source"] = {
                "account": _json_value(asdict(account)),
                "fills": _json_value([asdict(item) for item in fills]),
                "market": _json_value(market),
            }
        elif phase == "AFTER_CLOSE":
            next_date = self._next_in_range(trade_date)
            if next_date is None:
                payload["source"] = {"terminal_policy": "NO_PLAN_OUTSIDE_RANGE"}
            else:
                _, target, account = self._target_for_day(run_id, trade_date)
                pending, closes, profiles = self._rebalance_inputs(
                    run_id,
                    trade_date,
                    target,
                    account,
                    completed=completed,
                )
                payload["source"] = {
                    "scheduled_trade_date": next_date.isoformat(),
                    "target": _json_value(asdict(target)),
                    "account": canonical_account_snapshot(account),
                    "pre_plan_pending": _json_value(
                        [asdict(item) for item in pending]
                    ),
                    "close_prices": _json_value(closes),
                    "instrument_profiles": _json_value(profiles),
                }
        elif phase == "DAY_COMPLETED":
            payload["source"] = {
                item: self._completed_result_hash(run_id, trade_date, item)
                for item in PHASES[:-1]
            }
        else:
            raise ValueError(f"unsupported backtest phase: {phase}")
        evidence = _json_value(payload)
        return {"hash": config_hash(evidence), "evidence": evidence}

    def _result_identity(
        self,
        run_id: uuid.UUID,
        trade_date: date,
        phase: str,
        *,
        legacy_after_close: bool = False,
    ) -> dict[str, Any]:
        if phase == "START_OF_DAY":
            payload = self._input_identity(
                run_id, trade_date, phase, completed=True
            )["evidence"]["source"]
        elif phase == "OPEN":
            attempts = self._attempts_for_date(run_id, trade_date)
            fills = [
                row
                for row in self.repository.list_fills(run_id)
                if row.trade_date == trade_date
            ]
            payload = {
                "attempts": [_attempt_payload(item) for item in attempts],
                "fills": [_fill_payload(item) for item in fills],
            }
        elif phase == "CLOSE":
            nav = self.repository.get_nav(run_id, trade_date)
            if nav is None:
                raise BacktestRecoveryRejectedError(
                    "CLOSE_EVIDENCE_MISSING", "completed CLOSE requires NAV"
                )
            payload = {
                "nav": _model_payload(nav),
                "positions": [
                    _model_payload(item)
                    for item in self.repository.list_position_snapshot(
                        run_id, trade_date
                    )
                ],
            }
        elif phase == "AFTER_CLOSE":
            next_date = self._next_in_range(trade_date)
            plan = self.repository.get_rebalance_plan(run_id, trade_date)
            if next_date is None:
                if plan is not None:
                    raise BacktestRecoveryRejectedError(
                        "OUT_OF_RANGE_PLAN",
                        "final in-range date must not create a rebalance plan",
                    )
                payload = {"terminal_policy": "NO_PLAN_OUTSIDE_RANGE"}
            else:
                if plan is None:
                    raise BacktestRecoveryRejectedError(
                        "REBALANCE_EVIDENCE_MISSING",
                        "completed AFTER_CLOSE requires a rebalance plan",
                    )
                orders = [
                    item
                    for item in self.repository.list_orders(run_id)
                    if item.rebalance_plan_id == plan.id
                ]
                payload = {
                    "plan": _model_payload(plan),
                    "orders": [_order_payload(item) for item in orders],
                }
                if not legacy_after_close:
                    payload = {
                        "identity_version": _AFTER_CLOSE_RESULT_IDENTITY_VERSION,
                        **payload,
                        "cancelled_prior_orders": self._after_close_cancel_evidence(
                            run_id, plan
                        ),
                    }
        elif phase == "DAY_COMPLETED":
            payload = {
                item: self._completed_result_hash(run_id, trade_date, item)
                for item in PHASES[:-1]
            }
        else:
            raise ValueError(f"unsupported backtest phase: {phase}")
        evidence = _json_value(payload)
        return {"hash": config_hash(evidence), "evidence": evidence}

    def _validate_completed_checkpoint(
        self, checkpoint: PortfolioBacktestCheckpoint
    ) -> None:
        current_input = self._input_identity(
            checkpoint.run_id,
            checkpoint.trade_date,
            checkpoint.phase,
            completed=True,
        )
        if current_input.get("hash") != checkpoint.input_identity.get("hash"):
            raise BacktestRecoveryRejectedError(
                "HISTORICAL_INPUT_DRIFT",
                f"input identity changed for {checkpoint.trade_date} {checkpoint.phase}",
            )
        self._validate_checkpoint_result(checkpoint)

    def _validate_checkpoint_result(
        self, checkpoint: PortfolioBacktestCheckpoint
    ) -> None:
        saved_evidence = checkpoint.result_identity.get("evidence")
        legacy_after_close = (
            checkpoint.phase == "AFTER_CLOSE"
            and isinstance(saved_evidence, dict)
            and "plan" in saved_evidence
            and saved_evidence.get("identity_version") is None
        )
        if legacy_after_close:
            plan = self.repository.get_rebalance_plan(
                checkpoint.run_id, checkpoint.trade_date
            )
            if plan is not None and self._cancel_actions(plan):
                raise BacktestRecoveryRejectedError(
                    "LEGACY_AFTER_CLOSE_CANCEL_EVIDENCE_UNVERIFIABLE",
                    "legacy AFTER_CLOSE checkpoint omitted prior-order cancellation evidence",
                )
            current_result = self._result_identity(
                checkpoint.run_id,
                checkpoint.trade_date,
                checkpoint.phase,
                legacy_after_close=True,
            )
        else:
            current_result = self._result_identity(
                checkpoint.run_id, checkpoint.trade_date, checkpoint.phase
            )
        if current_result.get("hash") != checkpoint.result_identity.get("hash"):
            raise BacktestRecoveryRejectedError(
                "CHECKPOINT_EVIDENCE_MISMATCH",
                f"business evidence changed for {checkpoint.trade_date} "
                f"{checkpoint.phase}",
            )

    def _cancel_actions(self, plan: Any) -> list[dict[str, Any]]:
        result = dict(plan.plan_snapshot or {}).get("result", {})
        actions = result.get("pending_actions", []) if isinstance(result, dict) else []
        return sorted(
            [
                item
                for item in actions
                if isinstance(item, dict) and item.get("action") == "CANCEL"
            ],
            key=lambda item: str(item.get("order_id", "")),
        )

    def _after_close_cancel_evidence(
        self, run_id: uuid.UUID, plan: Any
    ) -> list[dict[str, Any]]:
        pre_pending = dict(plan.plan_snapshot or {}).get("pre_plan_pending", [])
        pre_ids = {
            str(item.get("order_id"))
            for item in pre_pending
            if isinstance(item, dict) and item.get("order_id") is not None
        }
        actions = self._cancel_actions(plan)
        action_by_id: dict[uuid.UUID, dict[str, Any]] = {}
        for action in actions:
            raw_order_id = str(action.get("order_id", ""))
            try:
                order_id = uuid.UUID(raw_order_id)
            except ValueError as exc:
                raise BacktestRecoveryRejectedError(
                    "AFTER_CLOSE_CANCEL_EVIDENCE_INVALID",
                    f"invalid cancelled prior order id: {raw_order_id}",
                ) from exc
            if raw_order_id not in pre_ids or order_id in action_by_id:
                raise BacktestRecoveryRejectedError(
                    "AFTER_CLOSE_CANCEL_EVIDENCE_INVALID",
                    "cancel action must identify one unique pre-plan pending order",
                )
            action_by_id[order_id] = action
        if not action_by_id:
            return []
        orders = {
            row.id: row
            for row in self.db.execute(
                select(PortfolioOrder)
                .where(PortfolioOrder.id.in_(action_by_id))
                .execution_options(populate_existing=True)
            ).scalars()
        }
        evidence: list[dict[str, Any]] = []
        for order_id, action in sorted(
            action_by_id.items(), key=lambda item: str(item[0])
        ):
            order = orders.get(order_id)
            expected_reason = str(
                action.get("reason_code") or "SUPERSEDED_BY_REBALANCE"
            )
            if (
                order is None
                or order.run_id != run_id
                or order.status != "CANCELLED"
                or order.reason_code != expected_reason
            ):
                raise BacktestRecoveryRejectedError(
                    "AFTER_CLOSE_CANCEL_EVIDENCE_MISMATCH",
                    f"cancelled prior order evidence changed: {order_id}",
                )
            evidence.append(
                {
                    "order_id": str(order.id),
                    "run_id": str(order.run_id),
                    "decision": "CANCEL",
                    "status": order.status,
                    "reason_code": order.reason_code,
                }
            )
        return evidence

    def _target_for_day(
        self, run_id: uuid.UUID, trade_date: date
    ) -> tuple[FrozenRunConfig, PortfolioTarget, DailyPortfolioSnapshot]:
        run = self.repository.get_run(run_id)
        contract = validate_resumable_backtest_contract(run, settings=self.settings)
        batch = OpportunityCandidateProvider(self.db, self.settings).list_candidates(
            trade_date, contract.portfolio
        )
        if not batch.source_ready:
            raise PortfolioSourceNotReadyError(batch)
        account = load_persisted_close_snapshot(
            self.repository, contract.run, trade_date
        )
        account_state = AccountState(
            trade_date=trade_date,
            cash=account.cash,
            positions=account.positions,
        )
        target = TopNEqualWeightPolicy().build_target(
            batch.candidates,
            account_state,
            contract.portfolio,
            source_available=True,
        )
        return contract, target, account

    def _open_intents(
        self, run_id: uuid.UUID, trade_date: date, *, completed: bool
    ) -> tuple[OrderIntent, ...]:
        if completed:
            attempts = self._attempts_for_date(run_id, trade_date)
            order_ids = [item.order_id for item in attempts]
            orders = {
                item.id: item
                for item in self.db.execute(
                    select(PortfolioOrder).where(PortfolioOrder.id.in_(order_ids))
                ).scalars()
            }
            pairs = [(orders[item.order_id], item.attempt_no - 1) for item in attempts]
        else:
            pairs = [
                (item, item.attempt_count)
                for item in self.repository.list_pending_orders(run_id, trade_date)
            ]
        pairs.sort(
            key=lambda item: (
                item[0].scheduled_trade_date,
                str(item[0].id),
                item[0].ts_code,
            )
        )
        return tuple(
            OrderIntent(
                order_id=order.id,
                signal_trade_date=order.signal_trade_date,
                scheduled_trade_date=order.scheduled_trade_date,
                ts_code=order.ts_code,
                side=order.side,
                order_type=order.order_type,
                target_weight=order.target_weight,
                target_quantity=order.target_quantity,
                attempt_count=attempt_count,
            )
            for order, attempt_count in pairs
        )

    def _rebalance_inputs(
        self,
        run_id: uuid.UUID,
        trade_date: date,
        target: PortfolioTarget,
        account: DailyPortfolioSnapshot,
        *,
        completed: bool,
    ) -> tuple[
        tuple[PendingOrderState, ...],
        dict[str, Decimal],
        dict[str, Any],
    ]:
        plan = self.repository.get_rebalance_plan(run_id, trade_date)
        if completed and plan is not None:
            raw_pending = plan.plan_snapshot.get("pre_plan_pending", [])
            pending = tuple(
                PendingOrderState(
                    order_id=item["order_id"],
                    ts_code=str(item["ts_code"]),
                    side=str(item["side"]),
                    quantity=int(item["quantity"]),
                    attempt_count=int(item.get("attempt_count", 0)),
                )
                for item in raw_pending
                if isinstance(item, dict)
            )
        else:
            pending = tuple(
                PendingOrderState(
                    order_id=row.id,
                    ts_code=row.ts_code,
                    side=row.side,
                    quantity=row.target_quantity or 0,
                    attempt_count=row.attempt_count,
                )
                for row in self.repository.list_active_pending_orders(run_id)
            )
        codes = {item.ts_code for item in target.targets}
        codes.update(item.ts_code for item in account.positions)
        codes.update(item.ts_code for item in pending)
        closes, profiles = RebalanceMarketDataProvider(self.db).load(
            trade_date, tuple(codes)
        )
        return pending, closes, profiles

    def _attempts_for_date(
        self, run_id: uuid.UUID, trade_date: date
    ) -> list[PortfolioOrderAttempt]:
        return list(
            self.db.execute(
                select(PortfolioOrderAttempt)
                .where(
                    PortfolioOrderAttempt.run_id == run_id,
                    PortfolioOrderAttempt.attempt_trade_date == trade_date,
                )
                .order_by(
                    PortfolioOrderAttempt.order_id,
                    PortfolioOrderAttempt.attempt_no,
                )
            )
            .scalars()
            .all()
        )

    def _phase_has_business_evidence(
        self, run_id: uuid.UUID, trade_date: date, phase: str
    ) -> bool:
        if phase == "OPEN":
            return bool(self._attempts_for_date(run_id, trade_date))
        if phase == "CLOSE":
            return self.repository.get_nav(run_id, trade_date) is not None
        if phase == "AFTER_CLOSE":
            return self.repository.get_rebalance_plan(run_id, trade_date) is not None
        return False

    def _completed_result_hash(
        self, run_id: uuid.UUID, trade_date: date, phase: str
    ) -> str:
        checkpoint = self.repository.get_checkpoint(run_id, trade_date, phase)
        if checkpoint is None or checkpoint.phase_status != "COMPLETED":
            raise BacktestRecoveryRejectedError(
                "CHECKPOINT_SEQUENCE_INVALID", f"{phase} is not completed"
            )
        value = checkpoint.result_identity.get("hash")
        if not isinstance(value, str):
            raise BacktestRecoveryRejectedError(
                "CHECKPOINT_IDENTITY_MISSING", f"{phase} result hash is missing"
            )
        return value

    def _next_in_range(self, trade_date: date) -> date | None:
        for item in self._dates:
            if item > trade_date:
                return item
        return None

    def _assert_ownership(
        self, lease: BacktestExecutionLease, *, allow_cancel: bool
    ) -> tuple[JobRun, PortfolioBacktestRun]:
        job = self.db.execute(
            select(JobRun)
            .where(JobRun.id == lease.job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        ).scalar_one_or_none()
        run = self.repository.get_run_for_update(lease.run_id)
        metadata_version = (
            dict(job.job_metadata or {}).get("ownership_version")
            if job is not None
            else None
        )
        if (
            run is None
            or job is None
            or run.status != "RUNNING"
            or run.job_id != lease.job_id
            or run.owner_worker_id != lease.worker_id
            or run.ownership_version != lease.ownership_version
            or job.status != "RUNNING"
            or job.worker_id != lease.worker_id
            or metadata_version != lease.ownership_version
        ):
            raise BacktestOwnershipError("backtest execution ownership was lost")
        if job.cancel_requested and not allow_cancel:
            raise _BacktestCancellationRequested(
                "backtest cancellation won at the phase boundary"
            )
        return job, run

    def _cancel_requested(self, job_id: uuid.UUID) -> bool:
        # Scalar-column reads bypass the identity map used by expire_on_commit=False.
        value = self.db.scalar(
            select(JobRun.cancel_requested).where(JobRun.id == job_id)
        )
        return bool(value)

    def _finish_cancelled(self, lease: BacktestExecutionLease) -> None:
        job, run = self._assert_ownership(lease, allow_cancel=True)
        now = datetime.now(UTC)
        run.status = "CANCELLED"
        run.finished_at = now
        run.owner_worker_id = None
        job.status = "CANCELLED"
        job.finished_at = now
        job.step = "cancelled at safe phase boundary"
        self.db.commit()

    def _finish_success(self, lease: BacktestExecutionLease) -> None:
        job, run = self._assert_ownership(lease, allow_cancel=True)
        # The Job row lock is the terminal-state linearization point. A cancel
        # committed before this lock wins; a later cancel observes SUCCESS.
        if job.cancel_requested:
            now = datetime.now(UTC)
            run.status = "CANCELLED"
            run.finished_at = now
            run.owner_worker_id = None
            job.status = "CANCELLED"
            job.finished_at = now
            job.step = "cancelled at final safe phase boundary"
            self.db.commit()
            return
        now = datetime.now(UTC)
        nav = self.repository.list_nav(lease.run_id)
        run.status = "SUCCESS"
        run.finished_at = now
        run.owner_worker_id = None
        run.result_summary = {
            "total_trade_days": len(self._dates),
            "completed_trade_days": len(self._dates),
            "final_trade_date": self._dates[-1].isoformat(),
            "final_nav": str(nav[-1].nav) if nav else None,
            "checkpoint_version": "backtest_phase_input_v1",
        }
        job.status = "SUCCESS"
        job.finished_at = now
        job.step = "backtest complete"
        job.row_count = len(self._dates)
        job.job_metadata = {
            **dict(job.job_metadata or {}),
            "stage": "success",
            "progress_pct": 100,
            "completed_trade_days": len(self._dates),
            "total_trade_days": len(self._dates),
        }
        self.db.commit()

    def _mark_checkpoint_failed(
        self,
        lease: BacktestExecutionLease,
        trade_date: date,
        phase: str,
        exc: Exception,
    ) -> None:
        try:
            job, _ = self._assert_ownership(lease, allow_cancel=True)
        except BacktestOwnershipError:
            self.db.rollback()
            return
        checkpoint = self.repository.get_checkpoint_for_update(
            lease.run_id, trade_date, phase
        )
        if checkpoint is not None and checkpoint.phase_status != "COMPLETED":
            checkpoint.phase_status = "FAILED"
            checkpoint.completed_at = datetime.now(UTC)
            checkpoint.error_code = _error_code(exc)
            checkpoint.error_message = str(exc)[:2048]
        job.step = f"failed at {trade_date} {phase}"
        self.db.commit()

    def _mark_run_failed(
        self,
        lease: BacktestExecutionLease,
        exc: Exception,
    ) -> None:
        self.db.rollback()
        try:
            job, run = self._assert_ownership(lease, allow_cancel=True)
        except BacktestOwnershipError:
            self.db.rollback()
            return
        now = datetime.now(UTC)
        run.status = "FAILED"
        run.finished_at = now
        run.owner_worker_id = None
        run.error_message = str(exc)[:2048]
        run.result_summary = {
            **dict(run.result_summary or {}),
            "stage": "failed",
            "error_code": _error_code(exc),
        }
        if job.status not in _TERMINAL_RUN_STATUSES:
            job.status = "FAILED"
            job.finished_at = now
            job.error_message = str(exc)[:2048]
        self.db.commit()

    def _update_job_progress(
        self, job: JobRun, trade_date: date, phase: str
    ) -> None:
        completed_days = sum(
            item.phase == "DAY_COMPLETED" and item.phase_status == "COMPLETED"
            for item in self.repository.list_checkpoints(
                uuid.UUID(str(job.job_metadata["portfolio_run_id"]))
            )
        )
        total = len(self._dates)
        job.step = f"{trade_date} {phase}"
        job.row_count = completed_days
        job.job_metadata = {
            **dict(job.job_metadata or {}),
            "stage": "running",
            "current_trade_date": trade_date.isoformat(),
            "current_phase": phase,
            "completed_trade_days": completed_days,
            "total_trade_days": total,
            "progress_pct": round(completed_days / total * 100, 2) if total else 0,
        }

    def _fault(self, phase: str, point: str) -> None:
        if self.fault_hook is not None:
            self.fault_hook(phase, point)


def recover_stale_backtest_jobs(
    db: Session,
    *,
    timeout_minutes: float,
    now: datetime | None = None,
    before_lock_hook: Callable[[uuid.UUID], None] | None = None,
) -> int:
    """Fail stale ownership for review; never auto-replay a backtest phase."""
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    cutoff = current - timedelta(minutes=timeout_minutes)
    candidate_ids = list(
        db.execute(
            select(JobRun.id)
            .where(
                JobRun.job_type == BACKTEST_JOB_TYPE,
                JobRun.status == "RUNNING",
                JobRun.heartbeat_at < cutoff,
            )
            .order_by(JobRun.id)
        )
        .scalars()
        .all()
    )
    recovered = 0
    for job_id in candidate_ids:
        if before_lock_hook is not None:
            before_lock_hook(job_id)
        # Candidate discovery is deliberately unlocked. The actual decision is
        # made only after taking the canonical JobRun -> Run locks and refreshing
        # both objects, so a concurrent heartbeat can invalidate the candidate.
        job = db.execute(
            select(JobRun)
            .where(JobRun.id == job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        ).scalar_one_or_none()
        if (
            job is None
            or job.job_type != BACKTEST_JOB_TYPE
            or job.status != "RUNNING"
            or job.heartbeat_at is None
            or job.heartbeat_at >= cutoff
        ):
            continue
        raw_run_id = dict(job.job_metadata or {}).get("portfolio_run_id")
        try:
            run_id = uuid.UUID(str(raw_run_id))
        except (TypeError, ValueError):
            continue
        run = db.execute(
            select(PortfolioBacktestRun)
            .where(PortfolioBacktestRun.id == run_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        ).scalar_one_or_none()
        metadata_version = dict(job.job_metadata or {}).get(
            "ownership_version", run.ownership_version if run is not None else None
        )
        if (
            run is None
            or run.job_id != job.id
            or run.status != "RUNNING"
            or run.owner_worker_id != job.worker_id
            or run.ownership_version != metadata_version
        ):
            continue
        job.status = "FAILED"
        job.finished_at = current
        job.error_message = "WORKER_HEARTBEAT_TIMEOUT: explicit resume required"
        job.step = "worker heartbeat stale; awaiting review"
        run.status = "FAILED"
        run.finished_at = current
        run.owner_worker_id = None
        run.error_message = job.error_message
        run.result_summary = {
            **dict(run.result_summary or {}),
            "stage": "failed",
            "error_code": "WORKER_HEARTBEAT_TIMEOUT",
        }
        recovered += 1
    db.commit()
    return recovered


def _trade_dates(db: Session, run: PortfolioBacktestRun) -> list[date]:
    return list(
        db.execute(
            select(TradeCalendar.cal_date)
            .where(
                TradeCalendar.cal_date >= run.start_date,
                TradeCalendar.cal_date <= run.end_date,
                TradeCalendar.is_open.is_(True),
            )
            .order_by(TradeCalendar.cal_date)
        ).scalars()
    )


def _validate_trade_calendar(
    db: Session, run: PortfolioBacktestRun, dates: tuple[date, ...]
) -> None:
    if not dates:
        raise BacktestRecoveryRejectedError(
            "TRADE_CALENDAR_EMPTY", "run interval has no open trade date"
        )
    rows = {
        row.cal_date: row
        for row in db.execute(
            select(TradeCalendar).where(TradeCalendar.cal_date.in_(dates))
        ).scalars()
    }
    for previous, current in zip(dates, dates[1:], strict=False):
        row = rows.get(current)
        if row is None or row.pretrade_date != previous:
            raise BacktestRecoveryRejectedError(
                "TRADE_CALENDAR_PREDECESSOR_INVALID",
                f"{current} pretrade_date must be {previous}",
            )
    if dates[0] < run.start_date or dates[-1] > run.end_date:
        raise BacktestRecoveryRejectedError(
            "TRADE_CALENDAR_RANGE_INVALID", "open calendar exceeds run interval"
        )


def _json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, Decimal):
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    if isinstance(value, (date, datetime, uuid.UUID)):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_json_value(item) for item in value]
    return value


def _model_payload(row: Any) -> dict[str, Any]:
    return {
        column.name: _json_value(getattr(row, column.name))
        for column in row.__table__.columns
        if column.name not in {"created_at", "updated_at"}
    }


def _order_payload(row: PortfolioOrder) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "run_id": str(row.run_id),
        "rebalance_plan_id": (
            str(row.rebalance_plan_id) if row.rebalance_plan_id else None
        ),
        "child_index": row.child_index,
        "signal_trade_date": row.signal_trade_date.isoformat(),
        "scheduled_trade_date": row.scheduled_trade_date.isoformat(),
        "ts_code": row.ts_code,
        "side": row.side,
        "order_type": row.order_type,
        "target_weight": _json_value(row.target_weight),
        "target_quantity": row.target_quantity,
    }


def _attempt_payload(row: PortfolioOrderAttempt) -> dict[str, Any]:
    return _model_payload(row)


def _fill_payload(row: PortfolioFill) -> dict[str, Any]:
    return _model_payload(row)


def _error_code(exc: Exception) -> str:
    explicit = getattr(exc, "code", None) or getattr(exc, "reason_code", None)
    if explicit:
        return str(explicit)[:64]
    name = type(exc).__name__
    result: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index:
            result.append("_")
        result.append(char.upper())
    return "".join(result)[:64]
