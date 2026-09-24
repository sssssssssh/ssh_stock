from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.job import JobRun
from app.repositories.job_run import (
    cancel_requested,
    finish_cancelled,
    start_job,
    update_job,
)
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    MARKET_CALC_VERSION,
    OPPORTUNITY_CALC_VERSION,
    RESEARCH_EVAL_VERSION,
    RESEARCH_VERSION,
    THEME_CALC_VERSION,
    TRADE_STATUS_CALC_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.job_guard import (
    ResearchQueueConflictError,
    _acquire_research_advisory_lock,
    recover_stale_research_jobs,
    research_can_run,
)
from app.services.research.opportunity_eval import evaluate_opportunity_batch, trade_batches
from app.services.research.theme_eval import evaluate_theme_batch
from app.services.research.transition_eval import evaluate_transition_batch

RESEARCH_JOB_TYPE = "RESEARCH_EVAL"
RESEARCH_IDENTITY_KEYS = (
    "algo_version",
    "strategy_config_hash",
    "source_strategy_config_hash",
    "opportunity_config_hash",
    "research_config_hash",
    "research_version",
    "research_eval_version",
    "factor_calc_version",
    "market_calc_version",
    "trade_status_calc_version",
    "theme_calc_version",
    "trend_calc_version",
    "opportunity_calc_version",
    "benchmark_code",
    "stock_entry_basis",
    "theme_entry_basis",
)


def current_research_identity(settings: Any) -> dict[str, str]:
    strategy_hash = analysis_strategy_hash(settings.strategy)
    return {
        "algo_version": settings.algo_version,
        "strategy_config_hash": strategy_hash,
        "source_strategy_config_hash": strategy_hash,
        "opportunity_config_hash": config_hash(settings.opportunity_config),
        "research_config_hash": config_hash(settings.research_config),
        "research_version": RESEARCH_VERSION,
        "research_eval_version": RESEARCH_EVAL_VERSION,
        "factor_calc_version": FACTOR_CALC_VERSION,
        "market_calc_version": MARKET_CALC_VERSION,
        "trade_status_calc_version": TRADE_STATUS_CALC_VERSION,
        "theme_calc_version": THEME_CALC_VERSION,
        "trend_calc_version": TREND_CALC_VERSION,
        "opportunity_calc_version": OPPORTUNITY_CALC_VERSION,
        "benchmark_code": settings.research_config["benchmark_code"],
        "stock_entry_basis": settings.research_config["stock"]["entry_basis"],
        "theme_entry_basis": settings.research_config["theme"]["entry_basis"],
    }


def queue_research_eval(
    db: Session,
    start: date,
    end: date,
    *,
    mode: str = "manual",
    opportunity_only: bool = False,
    theme_only: bool = False,
    transition_only: bool = False,
) -> JobRun:
    if start > end:
        raise ValueError("start must be <= end")
    if sum((opportunity_only, theme_only, transition_only)) > 1:
        raise ValueError("only one research-only flag is allowed")
    _acquire_research_advisory_lock(db)
    recovered = recover_stale_research_jobs(db, commit=False)
    active = db.scalar(
        select(JobRun)
        .where(
            JobRun.job_type == RESEARCH_JOB_TYPE,
            JobRun.status.in_(("QUEUED", "RUNNING")),
        )
        .limit(1)
    )
    if active is not None or not research_can_run(db):
        if recovered:
            db.commit()
        else:
            db.rollback()
        reason = "active research job exists" if active is not None else "production job is active"
        raise ResearchQueueConflictError(reason)
    settings = get_settings()
    return start_job(
        db,
        RESEARCH_JOB_TYPE,
        end,
        status="QUEUED",
        step="queued research evaluation",
        metadata={
            "source": mode,
            "mode": mode,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "opportunity_only": opportunity_only,
            "theme_only": theme_only,
            "transition_only": transition_only,
            **current_research_identity(settings),
            "opportunity_rows": 0,
            "opportunity_deleted_rows": 0,
            "theme_rows": 0,
            "theme_deleted_rows": 0,
            "transition_rows": 0,
            "transition_deleted_rows": 0,
            "warnings": [],
            "progress_pct": 0,
        },
    )


def run_research_eval(db: Session, job: JobRun) -> dict[str, Any]:
    if not research_can_run(db):
        job.status = "QUEUED"
        job.step = "waiting for production jobs"
        job.worker_id = None
        job.heartbeat_at = None
        db.add(job)
        db.commit()
        return {}
    settings = get_settings()
    metadata = dict(job.job_metadata or {})
    current_identity = current_research_identity(settings)
    changed = [key for key in RESEARCH_IDENTITY_KEYS if metadata.get(key) != current_identity[key]]
    if changed:
        update_job(
            db,
            job,
            status="FAILED",
            step="research identity changed since queue",
            error_message="RESEARCH_IDENTITY_CHANGED_SINCE_QUEUE: " + ", ".join(changed),
            metadata={**metadata, "identity_changed_fields": changed},
        )
        return {}
    start, end = date.fromisoformat(metadata["start"]), date.fromisoformat(metadata["end"])
    batches = list(trade_batches(db, start, end, settings.research_config["batch_trade_days"]))
    totals = {
        "opportunity_base_rows": 0,
        "opportunity_rows": 0,
        "opportunity_deleted_rows": 0,
        "entry_nonexecutable": 0,
        "benchmark_missing": 0,
        "theme_base_rows": 0,
        "theme_rows": 0,
        "theme_deleted_rows": 0,
        "transition_base_rows": 0,
        "transition_rows": 0,
        "transition_deleted_rows": 0,
    }
    update_job(db, job, status="RUNNING", step="research evaluation started", metadata=metadata)
    for index, dates in enumerate(batches, start=1):
        try:
            should_cancel = cancel_requested(db, job.id)
        except AttributeError:
            should_cancel = bool(getattr(job, "cancel_requested", False))
        if should_cancel:
            finish_cancelled(db, job, metadata={**metadata, "stage": "cancelled"})
            return totals
        if not metadata.get("theme_only") and not metadata.get("transition_only"):
            result = evaluate_opportunity_batch(db, dates, settings)
            totals["opportunity_base_rows"] += result["base_rows"]
            totals["opportunity_rows"] += result["eval_rows"]
            totals["opportunity_deleted_rows"] += result["deleted_rows"]
            totals["entry_nonexecutable"] += result["entry_nonexecutable"]
            totals["benchmark_missing"] += result["benchmark_missing"]
            if result["base_rows"] and not result["eval_rows"]:
                raise RuntimeError("opportunity research input rows > 0 but eval rows = 0")
        if not metadata.get("opportunity_only") and not metadata.get("transition_only"):
            result = evaluate_theme_batch(db, dates, settings)
            totals["theme_base_rows"] += result["base_rows"]
            totals["theme_rows"] += result["eval_rows"]
            totals["theme_deleted_rows"] += result["deleted_rows"]
            totals["benchmark_missing"] += result["benchmark_missing"]
            if result["base_rows"] and not result["eval_rows"]:
                raise RuntimeError("theme research input rows > 0 but eval rows = 0")
        if not metadata.get("opportunity_only") and not metadata.get("theme_only"):
            result = evaluate_transition_batch(db, dates, settings)
            totals["transition_base_rows"] += result["base_rows"]
            totals["transition_rows"] += result["eval_rows"]
            totals["transition_deleted_rows"] += result["deleted_rows"]
        metadata = {
            **metadata,
            **totals,
            "batch_index": index,
            "batch_count": len(batches),
            "current_trade_date": dates[-1].isoformat(),
            "progress_pct": round(index / len(batches) * 100, 1),
            "warnings": ["BENCHMARK_DATA_MISSING"] if totals["benchmark_missing"] else [],
        }
        update_job(
            db,
            job,
            status="RUNNING",
            step=f"research batch {index}/{len(batches)}",
            row_count=totals["opportunity_rows"] + totals["theme_rows"] + totals["transition_rows"],
            metadata=metadata,
        )
    metadata = {**metadata, **totals, "progress_pct": 100}
    update_job(
        db,
        job,
        status="SUCCESS",
        step="research evaluation complete",
        row_count=totals["opportunity_rows"] + totals["theme_rows"] + totals["transition_rows"],
        metadata=metadata,
    )
    return totals
