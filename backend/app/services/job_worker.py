import os
import socket
import threading
import time
import uuid
from datetime import UTC, date, datetime
from typing import Any

from loguru import logger
from sqlalchemy import or_, select, update
from sqlalchemy.exc import DBAPIError, PendingRollbackError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal, database_error_summary
from app.jobs.backfill_job import BackfillJob
from app.jobs.basic_info_job import BasicInfoJob
from app.jobs.catchup_job import CatchUpJob
from app.jobs.daily_job import DailyJob
from app.jobs.research_job import RESEARCH_JOB_TYPE, run_research_eval
from app.models.job import JobRun
from app.models.market_data import DataDirtyRange
from app.providers.gateway import market_data_gateway
from app.providers.logging_provider import LoggingMarketDataProvider
from app.repositories.job_run import touch_job_heartbeat, update_job
from app.services.calculation_progress import CalculationProgress, current_progress
from app.services.dirty import recover_stale_processing_ranges
from app.services.experiment_evaluation.application import (
    EXPERIMENT_EVALUATION_JOB_TYPE,
    ExperimentEvaluationApplicationService,
)
from app.services.experiment_evaluation.recovery import (
    recover_stale_experiment_evaluation_jobs,
)
from app.services.job_execution import (
    Execution,
    JobCancelled,
    JobExecutionUnconfirmed,
    JobOwnershipLost,
    checkpoint,
    current_execution,
    uncertain_database_error,
)
from app.services.job_guard import (
    INGESTION_JOB_TYPES,
    _acquire_ingestion_advisory_lock,
    data_queue_identity,
    production_can_run,
    recover_stale_ingestion_jobs,
    recover_stale_research_jobs,
    research_can_run,
    scheduler_setting,
)
from app.services.paper.job_application import PaperJobApplication, safe_error_code
from app.services.paper.queue import PAPER_JOB_TYPES
from app.services.paper.recovery import recover_stale_paper_jobs
from app.services.performance.application import (
    PERFORMANCE_JOB_TYPE,
    PerformanceApplicationService,
)
from app.services.performance.period_application import (
    PERFORMANCE_PERIOD_JOB_TYPE,
    PerformancePeriodApplicationService,
)
from app.services.performance.period_recovery import recover_stale_performance_period_jobs
from app.services.performance.recovery import recover_stale_performance_jobs
from app.services.performance.risk_application import (
    PERFORMANCE_RISK_JOB_TYPE,
    PerformanceRiskApplicationService,
)
from app.services.performance.risk_recovery import (
    recover_stale_performance_risk_jobs,
)
from app.services.performance.trade_application import (
    PERFORMANCE_TRADE_JOB_TYPE,
    PerformanceTradeApplicationService,
)
from app.services.performance.trade_recovery import (
    recover_stale_performance_trade_jobs,
)
from app.services.portfolio.backtest_application import (
    BACKTEST_JOB_TYPE,
    BacktestRunner,
    recover_stale_backtest_jobs,
)
from app.services.quality.history_quality import (
    HistoricalDataQualityService,
    HistoricalQualitySummary,
)
from app.services.recalculation import run_recalculation
from app.services.service_heartbeat import start_service_heartbeat
from app.services.walk_forward.application import (
    WALK_FORWARD_VALIDATION_JOB_TYPE,
    WalkForwardApplicationService,
)
from app.services.walk_forward.recovery import (
    recover_stale_walk_forward_validation_jobs,
)

WORKER_JOB_TYPES = (
    "daily",
    "sync_basic",
    "backfill",
    "recalculate",
    "validate_data",
    "catchup",
    RESEARCH_JOB_TYPE,
    BACKTEST_JOB_TYPE,
    PERFORMANCE_JOB_TYPE,
    PERFORMANCE_RISK_JOB_TYPE,
    PERFORMANCE_TRADE_JOB_TYPE,
    PERFORMANCE_PERIOD_JOB_TYPE,
    EXPERIMENT_EVALUATION_JOB_TYPE,
    WALK_FORWARD_VALIDATION_JOB_TYPE,
    *PAPER_JOB_TYPES,
)


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def claim_next_job(db: Session, worker_id: str) -> uuid.UUID | None:
    _acquire_ingestion_advisory_lock(db)
    allowed = list(WORKER_JOB_TYPES)
    if not get_settings().paper_config.enabled:
        allowed = [kind for kind in allowed if kind not in PAPER_JOB_TYPES]
    if not research_can_run(db):
        allowed.remove(RESEARCH_JOB_TYPE)
    if not production_can_run(db):
        allowed = [
            job_type for job_type in allowed if job_type not in INGESTION_JOB_TYPES
        ]
    if db.scalar(select(JobRun.id).where(
        JobRun.job_type.in_(INGESTION_JOB_TYPES), JobRun.status == "RUNNING",
        JobRun.parent_job_id.is_(None),
    ).limit(1)):
        allowed = [kind for kind in allowed if kind not in INGESTION_JOB_TYPES]
    completed_dependencies = select(JobRun.id).where(JobRun.status.in_(
        ("SUCCESS", "PARTIAL", "FAILED", "CANCELLED", "BLOCKED"),
    ))
    statement = (
            select(JobRun)
            .where(
                JobRun.status == "QUEUED",
                JobRun.job_type.in_(allowed),
                JobRun.parent_job_id.is_(None),
                or_(JobRun.depends_on_job_id.is_(None),
                    JobRun.depends_on_job_id.in_(completed_dependencies)),
            )
            .order_by(JobRun.started_at, JobRun.id)
            .limit(1)
    )
    candidate = db.execute(statement).scalars().first()
    if candidate is None:
        return None
    if candidate.job_type in INGESTION_JOB_TYPES:
        # Never overtake a temporarily locked data queue head.
        statement = statement.where(JobRun.id == candidate.id).with_for_update()
    else:
        # Adjacent PAPER/analytics lanes keep their existing SKIP LOCKED policy;
        # that policy must never skip a locked data head and take a later Writer.
        statement = statement.where(JobRun.job_type.not_in(INGESTION_JOB_TYPES))
        statement = statement.with_for_update(skip_locked=True)
    job = db.execute(statement.execution_options(populate_existing=True)).scalars().first()
    if job is None:
        return None
    now = datetime.now(UTC)
    if job.job_type in INGESTION_JOB_TYPES:
        if job.depends_on_job_id:
            dependency = db.get(JobRun, job.depends_on_job_id)
            if dependency.status != "SUCCESS":
                job.status = "BLOCKED"
                job.error_message = "JOB_DEPENDENCY_FAILED"
                job.finished_at = now
                db.commit()
                return None
        identity = dict(job.job_metadata or {}).get("queue_identity")
        legacy_hash = dict(job.job_metadata or {}).get("config_hash")
        if identity is None:
            # An old analysis hash is checkable, but does not prove the other
            # queued versions. Retain the record and require explicit resubmit.
            job.status = "FAILED"
            job.finished_at = now
            job.error_message = ("JOB_CONFIG_CHANGED" if legacy_hash and
                legacy_hash != data_queue_identity()["analysis"] else "JOB_CONFIG_SNAPSHOT_MISSING")
            db.commit()
            return None
        if identity is not None and identity != data_queue_identity():
            job.status = "FAILED"
            job.finished_at = now
            job.error_message = "JOB_CONFIG_CHANGED"
            db.commit()
            return None
        job.execution_token = uuid.uuid4()
        job.execution_started_at = now
        job.last_progress_at = now
        db.info["data_claim"] = (job.id, worker_id, job.execution_token)
    job.status = "RUNNING"
    job.worker_id = worker_id
    job.heartbeat_at = now
    job.step = "claimed by worker"
    db.add(job)
    db.commit()
    return job.id


def execute_claimed_job(
    db: Session, job_id: uuid.UUID, *,
    expected_worker: str | None = None, expected_token: uuid.UUID | None = None,
) -> None:
    job = db.get(JobRun, job_id)
    if job is None:
        return
    if job.status != "RUNNING":
        return
    context_token = None
    progress_token = None
    if job.job_type in INGESTION_JOB_TYPES and getattr(job, "execution_token", None):
        if (job.worker_id, job.execution_token) != (expected_worker, expected_token):
            logger.warning("data dispatch no longer owns claim job_id={}", job_id)
            return
        context_token = current_execution.set(Execution(
            job.id, job.worker_id, job.execution_token, db.get_bind(),
        ))
        # Applied to each transaction of this dedicated Session only.
        db.info["data_task_timeouts"] = True
        db.info["data_execution_job_id"] = job.id
        progress_token = current_progress.set(CalculationProgress())
    metadata = dict(job.job_metadata or {})
    stop_heartbeat = threading.Event()
    heartbeat_thread: threading.Thread | None = None
    publication_workspace = None
    worker_id = getattr(job, "worker_id", None)
    try:
        if context_token is not None:
            db.commit()
        if job.status == "RUNNING" and worker_id:
            heartbeat_thread = threading.Thread(
                target=_run_heartbeat_loop,
                args=(job.id, worker_id, stop_heartbeat),
                kwargs={"execution_token": getattr(job, "execution_token", None),
                        "progress": current_progress.get() if progress_token else None},
                daemon=True,
                name=f"job-heartbeat-{job.id}",
            )
            heartbeat_thread.start()
        checkpoint()
        if (context_token is not None and isinstance(db, Session)
                and job.job_type in {"daily", "recalculate", "catchup"}):
            from app.services.data_publication import PublicationWorkspace

            publication_workspace = PublicationWorkspace(db, job)
            publication_workspace.open()
            db.refresh(job)
        if job.job_type in PAPER_JOB_TYPES:
            PaperJobApplication(db, get_settings()).run_job(job.id)
        elif job.job_type == "daily":
            provider = _provider(db)
            target = job.target_trade_date or _metadata_date(metadata, "trade_date")
            DailyJob(db, provider).run(target, job=job)
        elif job.job_type == "sync_basic":
            provider = _provider(db)
            BasicInfoJob(db, provider).run(job=job, source=str(metadata.get("source", "worker")))
        elif job.job_type == "backfill":
            provider = _provider(db)
            BackfillJob(db, provider).run(
                _metadata_date(metadata, "start"),
                _metadata_date(metadata, "end"),
                job=job,
            )
        elif job.job_type == "recalculate":
            run_recalculation(
                db,
                job,
                _metadata_date(metadata, "start"),
                _metadata_date(metadata, "end"),
                evaluate_signals=bool(metadata.get("evaluate_signals", True)),
                mode=str(metadata.get("mode", "manual")),
                dirty_ranges=_load_dirty_ranges(db, metadata.get("dirty_range_ids", [])),
            )
        elif job.job_type == "validate_data":
            run_validate_data_job(db, job, metadata)
        elif job.job_type == "catchup":
            provider = _provider(db)
            target = job.target_trade_date or _metadata_date(metadata, "trade_date")
            catchup = CatchUpJob(db, provider)
            catchup.parent_job = job
            plan = catchup.run(target)
            update_job(
                db,
                job,
                status="SUCCESS",
                step="catchup complete",
                metadata={
                    **metadata,
                    "raw_required_days": len(plan.raw_required_dates),
                    "analysis_required_days": len(plan.analysis_required_dates),
                    "refresh_days": len(plan.refresh_dates),
                    "skipped": plan.skipped,
                    "skip_reason": plan.reason,
                    "stage": "eod_deferred" if plan.deferred_trade_date else "success",
                    "deferred_trade_date": plan.deferred_trade_date.isoformat()
                    if plan.deferred_trade_date
                    else None,
                    "deferred_reason": plan.deferred_reason,
                },
            )
        elif job.job_type == RESEARCH_JOB_TYPE:
            run_research_eval(db, job)
        elif job.job_type == BACKTEST_JOB_TYPE:
            BacktestRunner(db).run_job(job.id)
        elif job.job_type == PERFORMANCE_JOB_TYPE:
            PerformanceApplicationService(db).run_job(job.id)
        elif job.job_type == PERFORMANCE_RISK_JOB_TYPE:
            PerformanceRiskApplicationService(db).run_job(job.id)
        elif job.job_type == PERFORMANCE_TRADE_JOB_TYPE:
            PerformanceTradeApplicationService(db).run_job(job.id)
        elif job.job_type == PERFORMANCE_PERIOD_JOB_TYPE:
            PerformancePeriodApplicationService(db).run_job(job.id)
        elif job.job_type == EXPERIMENT_EVALUATION_JOB_TYPE:
            ExperimentEvaluationApplicationService(db).run_job(job.id)
        elif job.job_type == WALK_FORWARD_VALIDATION_JOB_TYPE:
            WalkForwardApplicationService(db).run_validation_job(job.id)
        else:
            raise ValueError(f"unsupported worker job type: {job.job_type}")
    except JobExecutionUnconfirmed as exc:
        _hold_unconfirmed_execution(db, str(exc))
    except JobCancelled:
        db.rollback()
        try:
            _finish_data_cancellation(db, job)
        except JobOwnershipLost:
            db.rollback()
            logger.warning("cancelling worker lost ownership job_id={}", job_id)
    except JobOwnershipLost:
        db.rollback()
        logger.warning("data worker lost execution ownership job_id={}", job_id)
    except Exception as exc:
        if uncertain_database_error(exc):
            _hold_unconfirmed_execution(db, database_error_summary(exc))
            return
        db.rollback()
        failed = db.get(JobRun, job_id)
        if job.job_type in PAPER_JOB_TYPES:
            code = safe_error_code(exc)
            if failed is not None and failed.status == "RUNNING" and failed.worker_id == worker_id:
                update_job(
                    db, failed, status="FAILED", step="paper failed; explicit retry required",
                    error_message=code,
                    metadata={**dict(failed.job_metadata or {}), "stage": "failed",
                              "error_code": code},
                )
            logger.warning("paper worker failure job_id={} code={}", job_id, code)
            return
        if (
            failed is not None
            and job.job_type != BACKTEST_JOB_TYPE
            and failed.status not in {"SUCCESS", "FAILED", "CANCELLED"}
        ):
            update_job(
                db,
                failed,
                status="FAILED",
                step=failed.step or "worker execution failed",
                error_message=(
                    database_error_summary(exc)
                    if isinstance(exc, SQLAlchemyError) else str(exc)
                ),
                metadata=(
                    {
                        **dict(failed.job_metadata or {}),
                        "stage": "failed",
                        **(
                            {"error_code": str(exc.code)}
                            if getattr(exc, "code", None)
                            else {}
                        ),
                    }
                    if job.job_type
                    in {
                        PERFORMANCE_RISK_JOB_TYPE,
                        PERFORMANCE_TRADE_JOB_TYPE,
                        PERFORMANCE_PERIOD_JOB_TYPE,
                        EXPERIMENT_EVALUATION_JOB_TYPE,
                        WALK_FORWARD_VALIDATION_JOB_TYPE,
                    }
                    else None
                ),
            )
        if isinstance(exc, SQLAlchemyError):
            logger.error("worker job database failure job_id={} error={}",
                         job_id, database_error_summary(exc))
        else:
            logger.exception("worker job failed job_id={} type={}", job_id, job.job_type)
    finally:
        stop_heartbeat.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=5)
        if publication_workspace is not None:
            try:
                publication_workspace.close()
            except SQLAlchemyError as error:
                logger.error("candidate connection cleanup failed job_id={} error={}",
                             job_id, database_error_summary(error))
        if context_token is not None:
            current_execution.reset(context_token)
            db.info.pop("data_task_timeouts", None)
            db.info.pop("data_execution_job_id", None)
        if progress_token is not None:
            current_progress.reset(progress_token)


def _hold_unconfirmed_execution(db: Session, reason: str) -> None:
    execution = current_execution.get()
    assert execution is not None
    logger.error("data execution response unconfirmed; never release RUNNING job_id={} error={}",
                 execution.job_id, reason)
    try:
        db.rollback()
        db.execute(update(JobRun).where(
            JobRun.id == execution.job_id, JobRun.status == "RUNNING",
            JobRun.worker_id == execution.worker_id, JobRun.execution_token == execution.token,
        ).values(error_message=reason, job_metadata=JobRun.job_metadata.op("||")({
            "execution_unconfirmed": True, "execution_error_code": "DATABASE_EXECUTION_UNCONFIRMED",
        })).execution_options(synchronize_session=False))
        db.commit()
    except SQLAlchemyError:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        logger.error("unconfirmed execution audit unavailable; keep RUNNING job_id={}",
                     execution.job_id)


def _finish_data_cancellation(db: Session, job: JobRun) -> None:
    from app.repositories.job_run import finish_cancelled
    from app.services.dirty import reopen_dirty_ranges_after_cancel

    children = list(db.scalars(select(JobRun).where(
        JobRun.parent_job_id == job.id, JobRun.status == "RUNNING",
    )))
    for current in [*children, job]:
        ranges = _load_dirty_ranges(db, dict(current.job_metadata or {}).get("dirty_range_ids", []))
        if ranges:
            reopen_dirty_ranges_after_cancel(db, ranges)
        finish_cancelled(db, current,
                         metadata={**dict(current.job_metadata or {}), "stage": "cancelled"})


def _run_heartbeat_loop(
    job_id: uuid.UUID,
    worker_id: str,
    stop_event: threading.Event,
    *,
    interval_seconds: float | None = None,
    execution_token: object | None = None,
    progress: CalculationProgress | None = None,
) -> None:
    interval = interval_seconds or float(scheduler_setting("worker_heartbeat_interval_seconds", 45))
    while not stop_event.wait(interval):
        try:
            snapshot = progress.snapshot() if progress is not None else None
            if snapshot:
                operation_age = (datetime.now(UTC) - datetime.fromisoformat(
                    snapshot["operation_started_at"],
                )).total_seconds()
                logger.info("calculation activity job_id={} name={} phase={} batch={}/{} "
                            "rows={}/{} operation_elapsed_seconds={:.1f}",
                            job_id, snapshot["name"], snapshot["phase"],
                            snapshot["batch_index"], snapshot["batch_count"],
                            snapshot["completed_rows"], snapshot["total_rows"], operation_age)
            with SessionLocal() as heartbeat_db:
                telemetry = {"calculation_progress": snapshot} if snapshot else {}
                if not touch_job_heartbeat(heartbeat_db, job_id, worker_id,
                                           execution_token=execution_token, **telemetry):
                    return
        except SQLAlchemyError as exc:
            logger.error("worker heartbeat database unavailable job_id={} error={}",
                         job_id, database_error_summary(exc))
        except Exception:
            logger.exception("worker heartbeat failed job_id={} worker_id={}", job_id, worker_id)


def run_worker() -> None:
    service_stop, service_thread = start_service_heartbeat("worker")
    try:
        while True:
            try:
                _run_worker_loop()
            except (DBAPIError, PendingRollbackError) as exc:
                # Session context managers close the failed connection. Restart
                # polling with fresh sessions, never replay the interrupted job.
                logger.error("worker database unavailable error={}", database_error_summary(exc))
                time.sleep(max(1.0, float(scheduler_setting("worker_poll_seconds", 2))))
    finally:
        service_stop.set()
        service_thread.join(timeout=5)


def _run_worker_loop() -> None:
    poll_seconds = float(scheduler_setting("worker_poll_seconds", 2))
    recovery_interval = float(scheduler_setting("stale_recovery_interval_seconds", 60))
    worker_id = worker_identity()
    last_recovery = 0.0
    while True:
        with SessionLocal() as db:
            now = time.monotonic()
            if now - last_recovery >= recovery_interval:
                recovered_paper = recover_stale_paper_jobs(
                    db, timeout_minutes=float(
                        scheduler_setting("running_heartbeat_timeout_minutes", 15)
                    ),
                )
                if recovered_paper:
                    logger.warning("paper jobs recovered count={}", recovered_paper)
                recovered_jobs = recover_stale_ingestion_jobs(db)
                recovered_research = recover_stale_research_jobs(db)
                recovered_backtests = recover_stale_backtest_jobs(
                    db,
                    timeout_minutes=float(
                        scheduler_setting(
                            "running_heartbeat_timeout_minutes", 15
                        )
                    ),
                )
                recovered_performance = recover_stale_performance_jobs(
                    db,
                    timeout_minutes=float(
                        scheduler_setting(
                            "running_heartbeat_timeout_minutes", 15
                        )
                    ),
                )
                recovered_performance_risk = recover_stale_performance_risk_jobs(
                    db,
                    timeout_minutes=float(
                        scheduler_setting(
                            "running_heartbeat_timeout_minutes", 15
                        )
                    ),
                )
                recovered_performance_trade = recover_stale_performance_trade_jobs(
                    db,
                    timeout_minutes=float(
                        scheduler_setting(
                            "running_heartbeat_timeout_minutes", 15
                        )
                    ),
                )
                recovered_performance_period = recover_stale_performance_period_jobs(
                    db,
                    timeout_minutes=float(
                        scheduler_setting("running_heartbeat_timeout_minutes", 15)
                    ),
                )
                recovered_experiment_evaluation = (
                    recover_stale_experiment_evaluation_jobs(
                        db,
                        timeout_minutes=float(
                            scheduler_setting(
                                "running_heartbeat_timeout_minutes", 15
                            )
                        ),
                    )
                )
                recovered_walk_forward_validation = (
                    recover_stale_walk_forward_validation_jobs(
                        db,
                        timeout_minutes=float(
                            scheduler_setting(
                                "running_heartbeat_timeout_minutes", 15
                            )
                        ),
                    )
                )
                data_writer = db.scalar(select(JobRun.id).where(
                    JobRun.job_type.in_(INGESTION_JOB_TYPES), JobRun.status == "RUNNING",
                ).limit(1))
                recovered_dirty = 0 if data_writer else recover_stale_processing_ranges(
                    db,
                    stale_minutes=float(
                        scheduler_setting("dirty_processing_timeout_minutes", 30)
                    ),
                )
                logger.info(
                    "worker recovery id={} recovered_jobs={} "
                    "recovered_research={} recovered_backtests={} "
                    "recovered_performance={} recovered_performance_risk={} "
                    "recovered_performance_trade={} "
                    "recovered_performance_period={} "
                    "recovered_experiment_evaluation={} "
                    "recovered_walk_forward_validation={} "
                    "recovered_dirty={}",
                    worker_id,
                    recovered_jobs,
                    recovered_research,
                    recovered_backtests,
                    recovered_performance,
                    recovered_performance_risk,
                    recovered_performance_trade,
                    recovered_performance_period,
                    recovered_experiment_evaluation,
                    recovered_walk_forward_validation,
                    recovered_dirty,
                )
                last_recovery = now
            job_id = claim_next_job(db, worker_id)
            ownership = db.info.pop("data_claim", None)
        if job_id is None:
            time.sleep(poll_seconds)
            continue
        with SessionLocal() as db:
            if ownership:
                _, owner, token = ownership
                execute_claimed_job(db, job_id, expected_worker=owner, expected_token=token)
            else:
                execute_claimed_job(db, job_id)


def run_validate_data_job(db: Session, job: JobRun, metadata: dict[str, Any]) -> None:
    start = _metadata_date(metadata, "start")
    end = _metadata_date(metadata, "end")
    base_metadata: dict[str, Any] = {
        **metadata,
        "stage": "validate_data",
        "progress_pct": 0,
        "total_trade_days": 0,
        "completed_trade_days": 0,
        "pass_days": 0,
        "warning_days": 0,
        "error_days": 0,
    }
    update_job(
        db,
        job,
        status="RUNNING",
        step="00 start validate data",
        metadata=base_metadata,
    )

    def progress(
        summary: HistoricalQualitySummary,
        trade_date: date,
        result: object,
    ) -> None:
        progress_pct = (
            round(summary.completed_days / summary.total_days * 100, 1)
            if summary.total_days
            else 100
        )
        raw_metadata = result.as_metadata() if hasattr(result, "as_metadata") else {}
        update_job(
            db,
            job,
            status="RUNNING",
            step=f"70 validate raw data {trade_date}",
            row_count=summary.completed_days,
            metadata={
                **base_metadata,
                **summary.as_dict(),
                **raw_metadata,
                "current_trade_date": trade_date.isoformat(),
                "last_completed_stage": "validate_data",
                "last_completed_start": trade_date.isoformat(),
                "last_completed_end": trade_date.isoformat(),
                "progress_pct": progress_pct,
            },
        )

    summary = HistoricalDataQualityService(db, get_settings().strategy).validate(
        start,
        end,
        job_id=job.id,
        progress_callback=progress,
    )
    update_job(
        db,
        job,
        status="SUCCESS",
        step="200 validate data complete",
        row_count=summary.completed_days,
        metadata={
            **base_metadata,
            **summary.as_dict(),
            "stage": "success",
            "progress_pct": 100,
        },
    )


def _metadata_date(metadata: dict[str, Any], key: str) -> date:
    value = metadata.get(key)
    if isinstance(value, date):
        return value
    if not value:
        raise ValueError(f"job metadata missing date: {key}")
    return date.fromisoformat(str(value))


def _load_dirty_ranges(db: Session, ids: object) -> list[DataDirtyRange]:
    values = [int(value) for value in ids] if isinstance(ids, list) else []
    if not values:
        return []
    return list(
        db.execute(select(DataDirtyRange).where(DataDirtyRange.id.in_(values))).scalars().all()
    )


def _provider(db: Session) -> LoggingMarketDataProvider:
    return market_data_gateway(db)
