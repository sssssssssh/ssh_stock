from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.job import JobRun
from app.repositories.job_run import start_job, update_job
from app.services.analysis_identity import RESEARCH_VERSION
from app.services.calc_metadata import config_hash
from app.services.job_guard import research_can_run
from app.services.research.opportunity_eval import evaluate_opportunity_batch, trade_batches
from app.services.research.theme_eval import evaluate_theme_batch
from app.services.research.transition_eval import evaluate_transition_batch

RESEARCH_JOB_TYPE = "RESEARCH_EVAL"


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
            "research_version": RESEARCH_VERSION,
            "research_config_hash": config_hash(settings.research_config),
            "strategy_config_hash": config_hash(settings.strategy),
            "opportunity_config_hash": config_hash(settings.opportunity_config),
            "benchmark_code": settings.research_config["benchmark_code"],
            "opportunity_rows": 0,
            "theme_rows": 0,
            "transition_rows": 0,
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
    start, end = date.fromisoformat(metadata["start"]), date.fromisoformat(metadata["end"])
    batches = list(trade_batches(db, start, end, settings.research_config["batch_trade_days"]))
    totals = {
        "opportunity_base_rows": 0,
        "opportunity_rows": 0,
        "entry_nonexecutable": 0,
        "benchmark_missing": 0,
        "theme_base_rows": 0,
        "theme_rows": 0,
        "transition_base_rows": 0,
        "transition_rows": 0,
    }
    update_job(db, job, status="RUNNING", step="research evaluation started", metadata=metadata)
    for index, dates in enumerate(batches, start=1):
        if not metadata.get("theme_only") and not metadata.get("transition_only"):
            result = evaluate_opportunity_batch(db, dates, settings)
            totals["opportunity_base_rows"] += result["base_rows"]
            totals["opportunity_rows"] += result["eval_rows"]
            totals["entry_nonexecutable"] += result["entry_nonexecutable"]
            totals["benchmark_missing"] += result["benchmark_missing"]
            if result["base_rows"] and not result["eval_rows"]:
                raise RuntimeError("opportunity research input rows > 0 but eval rows = 0")
        if not metadata.get("opportunity_only") and not metadata.get("transition_only"):
            result = evaluate_theme_batch(db, dates, settings)
            totals["theme_base_rows"] += result["base_rows"]
            totals["theme_rows"] += result["eval_rows"]
            totals["benchmark_missing"] += result["benchmark_missing"]
            if result["base_rows"] and not result["eval_rows"]:
                raise RuntimeError("theme research input rows > 0 but eval rows = 0")
        if not metadata.get("opportunity_only") and not metadata.get("theme_only"):
            result = evaluate_transition_batch(db, dates, settings)
            totals["transition_base_rows"] += result["base_rows"]
            totals["transition_rows"] += result["eval_rows"]
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
