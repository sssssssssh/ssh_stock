import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.job import JobRun
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    MARKET_CALC_VERSION,
    OPPORTUNITY_CALC_VERSION,
    SECTOR_CALC_VERSION,
    THEME_CALC_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash

INGESTION_JOB_TYPES = (
    "daily",
    "sync_basic",
    "backfill",
    "recalculate",
    "validate_data",
    "catchup",
)
ACTIVE_JOB_STATUSES = ("QUEUED", "RUNNING")
RESEARCH_JOB_TYPE = "RESEARCH_EVAL"
PRODUCTION_MUTATING_JOB_TYPES = ("daily", "sync_basic", "backfill", "recalculate", "catchup")
INGESTION_ADVISORY_LOCK_KEY = 7_307_202_609_15
RESEARCH_ADVISORY_LOCK_KEY = 7_307_202_609_19


class QueueCapacityError(RuntimeError):
    pass


def data_queue_identity() -> dict[str, str]:
    settings = get_settings()
    return {"analysis": analysis_strategy_hash(settings.strategy),
            "opportunity": config_hash(settings.opportunity_config),
            "algo": settings.algo_version, "factor": FACTOR_CALC_VERSION,
            "raw_quality": config_hash(settings.strategy.get("raw_quality", {})),
            "data_quality": config_hash(settings.strategy.get("data_quality", {})),
            "provider_limits": config_hash(settings.app_config.get("provider", {}).get(
                "tushare", {}).get("safe_limits", {})),
            "market": MARKET_CALC_VERSION, "sector": SECTOR_CALC_VERSION,
            "theme": THEME_CALC_VERSION, "trend": TREND_CALC_VERSION,
            "opportunity_calc": OPPORTUNITY_CALC_VERSION}


def request_fingerprint(job_type: str, target: date | None, metadata: dict[str, Any]) -> str:
    params = {key: metadata[key] for key in (
        "start", "end", "evaluate_signals", "mode", "dirty_range_ids", "depends_on_job_id",
    ) if key in metadata and metadata[key] is not None}
    if "dirty_range_ids" in params:
        params["dirty_range_ids"] = sorted(params["dirty_range_ids"])
    if job_type == "recalculate":
        params.setdefault("evaluate_signals", True)
        params.setdefault("mode", "manual")
    canonical = {"type": job_type, "target": target.isoformat() if target else None,
                 "parameters": params,
                 "identity": metadata.get("queue_identity", data_queue_identity())}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


class ResearchQueueConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class ActiveIngestionJobError(RuntimeError):
    job_id: str
    job_type: str
    status: str

    def __str__(self) -> str:
        return f"active ingestion job exists: {self.job_id} ({self.job_type} {self.status})"


def scheduler_setting(name: str, default: Any) -> Any:
    scheduler = get_settings().app_config.get("app", {}).get("scheduler", {})
    if not isinstance(scheduler, dict):
        return default
    return scheduler.get(name, default)


def active_ingestion_jobs(db: Session) -> list[JobRun]:
    return list(
        db.execute(
            select(JobRun)
            .where(
                JobRun.job_type.in_(INGESTION_JOB_TYPES),
                JobRun.status.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(JobRun.started_at)
        )
        .scalars()
        .all()
    )


def recover_stale_ingestion_jobs(
    db: Session,
    *,
    stale_job_hours: float | None = None,
    queued_stale_hours: float | None = None,
    running_heartbeat_timeout_minutes: float | None = None,
    now: datetime | None = None,
) -> int:
    # A missing heartbeat cannot prove that the old Writer has stopped.
    # Leave RUNNING (including legacy rows) blocking the lane for operator
    # reconciliation; legitimate QUEUED jobs have no implicit expiry.
    return 0


def recover_stale_research_jobs(
    db: Session,
    *,
    queued_stale_hours: float | None = None,
    running_heartbeat_timeout_minutes: float | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> int:
    jobs = db.execute(
        select(JobRun).where(
            JobRun.job_type == RESEARCH_JOB_TYPE,
            JobRun.status.in_(ACTIVE_JOB_STATUSES),
        )
    ).scalars().all()
    return _recover_stale_jobs(
        db,
        jobs,
        queued_stale_hours=queued_stale_hours,
        running_heartbeat_timeout_minutes=running_heartbeat_timeout_minutes,
        now=now,
        commit=commit,
    )


def _recover_stale_jobs(
    db: Session,
    jobs: list[JobRun],
    *,
    stale_job_hours: float | None = None,
    queued_stale_hours: float | None = None,
    running_heartbeat_timeout_minutes: float | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> int:
    queued_hours = float(
        queued_stale_hours
        or stale_job_hours
        or scheduler_setting("queued_stale_hours", 24)
    )
    running_minutes = float(
        running_heartbeat_timeout_minutes
        or (stale_job_hours * 60 if stale_job_hours is not None else 0)
        or scheduler_setting("running_heartbeat_timeout_minutes", 15)
    )
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    recovered = 0
    for job in jobs:
        if job.status == "RUNNING":
            # Do not unblock production while an unconfirmed old research
            # executor might still be reading/writing the same derived slice.
            continue
        original_status = job.status
        reference_at = (
            (getattr(job, "heartbeat_at", None) or job.started_at)
            if job.status == "RUNNING"
            else job.started_at
        )
        if reference_at is None:
            continue
        if reference_at.tzinfo is None:
            reference_at = reference_at.replace(tzinfo=UTC)
        timeout = (
            timedelta(minutes=running_minutes)
            if job.status == "RUNNING"
            else timedelta(hours=queued_hours)
        )
        if reference_at > current - timeout:
            continue
        job.status = "FAILED"
        job.finished_at = current
        job.error_message = (
            "stale RUNNING job recovered after heartbeat timeout"
            if original_status == "RUNNING"
            else "stale QUEUED job recovered after queue timeout"
        )
        db.add(job)
        recovered += 1
    if recovered and commit:
        db.commit()
    return recovered


def research_can_run(db: Session, *, running_only: bool = False) -> bool:
    return not bool(db.scalar(
        select(func.count()).select_from(JobRun).where(
            JobRun.job_type.in_(INGESTION_JOB_TYPES),
            JobRun.status.in_(("RUNNING",) if running_only else ACTIVE_JOB_STATUSES),
        )
    ))


def production_can_run(db: Session) -> bool:
    return not bool(db.scalar(
        select(func.count()).select_from(JobRun).where(
            JobRun.job_type == RESEARCH_JOB_TYPE,
            JobRun.status == "RUNNING",
        )
    ))


def find_active_ingestion_job(
    db: Session,
    *,
    recover_stale: bool = True,
) -> JobRun | None:
    if recover_stale:
        recover_stale_ingestion_jobs(db)
    jobs = active_ingestion_jobs(db)
    return jobs[0] if jobs else None


def reject_if_active_ingestion_job(db: Session) -> None:
    active = find_active_ingestion_job(db)
    if active:
        raise ActiveIngestionJobError(
            job_id=str(active.id),
            job_type=active.job_type,
            status=active.status,
        )


def create_queued_ingestion_job(
    db: Session,
    job_type: str,
    target_trade_date: date | None,
    *,
    step: str,
    metadata: dict[str, Any],
    _before_commit=None,
) -> JobRun:
    _acquire_ingestion_advisory_lock(db)
    identity = data_queue_identity()
    metadata = {**metadata, "queue_identity": identity}
    fingerprint = request_fingerprint(job_type, target_trade_date, metadata)
    existing = db.scalar(select(JobRun).where(
        JobRun.request_fingerprint == fingerprint, JobRun.status.in_(ACTIVE_JOB_STATUSES),
    ))
    if existing:
        if _before_commit is not None:
            _before_commit(existing)
        db.commit()
        existing._queue_deduplicated = True
        return existing
    count = db.scalar(select(func.count()).select_from(JobRun).where(
        JobRun.job_type.in_(INGESTION_JOB_TYPES), JobRun.parent_job_id.is_(None),
        JobRun.status == "QUEUED",
    ))
    if count >= int(scheduler_setting("data_queue_capacity", 100)):
        db.rollback()
        raise QueueCapacityError("QUEUE_CAPACITY_EXCEEDED")
    dependency = metadata.get("depends_on_job_id")
    if dependency:
        parent = db.get(JobRun, dependency)
        if parent is None or parent.job_type not in INGESTION_JOB_TYPES or parent.parent_job_id:
            db.rollback()
            raise ValueError("JOB_DEPENDENCY_NOT_FOUND")
    # The same advisory lock serializes every supported enqueue path. The
    # partial unique index also rejects duplicate inserts from other clients.
    job = JobRun(job_type=job_type, target_trade_date=target_trade_date, status="QUEUED",
                 started_at=func.clock_timestamp(),
                 step=step, job_metadata=metadata, request_fingerprint=fingerprint,
                 depends_on_job_id=dependency)
    db.add(job)
    try:
        if _before_commit is not None:
            db.flush()
            _before_commit(job)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = db.scalar(select(JobRun).where(
            JobRun.request_fingerprint == fingerprint, JobRun.status.in_(ACTIVE_JOB_STATUSES),
        ))
        if existing is None:
            if dependency and getattr(exc.orig, "sqlstate", None) in {"23503", "23514"}:
                raise ValueError("JOB_DEPENDENCY_NOT_FOUND") from None
            raise
        if _before_commit is not None:
            _before_commit(existing)
            db.commit()
        existing._queue_deduplicated = True
        return existing
    db.refresh(job)
    job._queue_deduplicated = False
    return job


def _acquire_ingestion_advisory_lock(db: Session) -> None:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(select(func.set_config(
        "lock_timeout", str(int(scheduler_setting("data_lock_timeout_ms", 5000))), True,
    ))).scalar_one()
    db.execute(select(func.set_config(
        "statement_timeout", str(int(scheduler_setting("data_statement_timeout_ms", 300000))), True,
    ))).scalar_one()
    db.execute(
        select(func.pg_advisory_xact_lock(INGESTION_ADVISORY_LOCK_KEY))
    ).scalar_one()


def _acquire_research_advisory_lock(db: Session) -> None:
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(select(func.pg_advisory_xact_lock(RESEARCH_ADVISORY_LOCK_KEY))).scalar_one()
