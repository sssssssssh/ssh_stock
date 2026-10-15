from datetime import UTC, datetime, timedelta
from time import perf_counter

from loguru import logger
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.retention_config import RetentionPolicy
from app.models import Base
from app.models.auth import AuthSession
from app.models.job import JobRun, ProviderApiLog, ServiceHeartbeat
from app.services.paper.queue import PAPER_JOB_TYPES
from app.services.retention_lineage import (
    JOB_REFERENCES,
    RetentionBlocked,
    assert_reference_schema,
    referenced_job,
)

OPERATIONAL_KEYS = (
    "provider_api_log", "successful_jobs", "failed_jobs", "auth_sessions", "service_heartbeat",
)


def eligible_jobs(current):
    return (
        JobRun.job_type.not_in(PAPER_JOB_TYPES),
        or_(
            (JobRun.status.in_(("SUCCESS", "PARTIAL", "CANCELLED")))
            & (JobRun.finished_at < current - timedelta(days=180)),
            (JobRun.status == "FAILED")
            & (JobRun.finished_at < current - timedelta(days=365)),
        ),
    )


def missing_provenance(policy, execute):
    total, diagnostics, samples = 0, [], []
    for name, field in JOB_REFERENCES:
        table = Base.metadata.tables[name]
        column = table.c[field]
        day = table.c.get("trade_date")
        if day is None:
            day = table.c.get("dirty_start_date")
        condition = (
            column.is_not(None),
            ~select(JobRun.id).where(JobRun.id == column).exists(),
        )
        query = select(column.label("job_id"))
        if day is not None:
            query = query.add_columns(day.label("trade_date"))
        bounded = query.where(*condition).limit(policy.max_missing_references + 1).subquery()
        count = execute(select(func.count()).select_from(bounded)).scalar_one()
        total += count
        if total > policy.max_missing_references:
            raise RetentionBlocked("RETENTION_MISSING_REFERENCE_BUDGET_EXCEEDED")
        if count:
            diagnostics.append({"table": name, "column": field, "missing_rows": count})
            remaining = policy.diagnostic_limit - len(samples)
            if remaining > 0:
                for row in execute(query.where(*condition).order_by(column).limit(remaining)):
                    samples.append({
                        "table": name, "column": field, "job_id": str(row.job_id),
                        "trade_date": str(row.trade_date) if day is not None else None,
                    })
    return total, diagnostics, samples


def run_retention(
    db: Session, *, now: datetime | None = None, dry_run: bool = False,
    policy: RetentionPolicy | None = None, include_diagnostics: bool = False,
) -> dict:
    """One bounded transaction. Job deletion is opt-in; dry-run never writes facts."""
    if db.new or db.dirty or db.deleted:
        raise ValueError("RETENTION_REQUIRES_CLEAN_SESSION")
    policy = policy or RetentionPolicy.model_validate(
        get_settings().app_config.get("retention", {})
    )
    current, started = now or datetime.now(UTC), perf_counter()
    if current.utcoffset() is None:
        raise ValueError("RETENTION_REQUIRES_AWARE_TIME")
    result = dict.fromkeys(OPERATIONAL_KEYS, 0)
    result.update({
        "eligible_success_jobs": None, "eligible_failed_jobs": None,
        "protected_referenced_jobs": None, "deleted_success_jobs": 0,
        "deleted_failed_jobs": 0, "missing_provenance_references": None,
        "candidate_scan_rows": 0, "sql_count": 0, "blocked": False,
        "error_code": None, "dry_run": dry_run,
        "job_deletion_enabled": policy.job_deletion_enabled,
    })

    def execute(statement):
        remaining = int(policy.max_duration_ms - (perf_counter() - started) * 1000)
        if remaining < 1:
            raise RetentionBlocked("RETENTION_DURATION_BUDGET_EXCEEDED")
        db.execute(select(func.set_config(
            "statement_timeout", str(min(policy.statement_timeout_ms, remaining)), True,
        )))
        result["sql_count"] += 2
        return db.execute(statement)

    try:
        if dry_run:
            db.execute(text("SET TRANSACTION READ ONLY"))
        db.execute(select(func.set_config("lock_timeout", str(policy.lock_timeout_ms), True)))
        result["sql_count"] += 1 + int(dry_run)
        execute(select(1))
        assert_reference_schema(db)
        result["sql_count"] += 1
        rows = execute(select(JobRun.id, JobRun.status).where(*eligible_jobs(current)).order_by(
            JobRun.finished_at, JobRun.id,
        ).limit(policy.max_candidate_rows + 1)).all()
        result["candidate_scan_rows"] = len(rows)
        if len(rows) > policy.max_candidate_rows:
            raise RetentionBlocked("RETENTION_CANDIDATE_BUDGET_EXCEEDED")
        ids = [row.id for row in rows]
        result["eligible_failed_jobs"] = sum(row.status == "FAILED" for row in rows)
        result["eligible_success_jobs"] = len(rows) - result["eligible_failed_jobs"]
        result["protected_referenced_jobs"] = execute(select(func.count()).select_from(
            JobRun,
        ).where(JobRun.id.in_(ids), referenced_job())).scalar_one() if ids else 0
        missing, diagnostics, samples = missing_provenance(policy, execute)
        result["missing_provenance_references"] = missing
        if include_diagnostics:
            result["missing_reference_tables"], result["missing_reference_samples"] = (
                diagnostics, samples,
            )
        if dry_run:
            db.rollback()
        else:
            if policy.job_deletion_enabled and ids:
                locked = select(JobRun.id).where(
                    JobRun.id.in_(ids), *eligible_jobs(current), ~referenced_job(),
                ).order_by(JobRun.finished_at, JobRun.id).with_for_update(skip_locked=True).cte(
                    "retention_candidates",
                )
                deleted = execute(delete(JobRun).where(
                    JobRun.id.in_(select(locked.c.id)),
                ).returning(JobRun.status)).scalars().all()
                result["deleted_failed_jobs"] = deleted.count("FAILED")
                result["deleted_success_jobs"] = len(deleted) - result["deleted_failed_jobs"]
                result["successful_jobs"] = result["deleted_success_jobs"]
                result["failed_jobs"] = result["deleted_failed_jobs"]
            operations = (
                ("provider_api_log", delete(ProviderApiLog).where(
                    ProviderApiLog.created_at < current - timedelta(days=90))),
                ("auth_sessions", delete(AuthSession).where(or_(
                    AuthSession.expires_at < current - timedelta(days=30),
                    AuthSession.revoked_at < current - timedelta(days=30)))),
                ("service_heartbeat", delete(ServiceHeartbeat).where(
                    ServiceHeartbeat.heartbeat_at < current - timedelta(days=30))),
            )
            for key, statement in operations:
                result[key] = int(execute(statement).rowcount or 0)
            if (perf_counter() - started) * 1000 >= policy.max_duration_ms:
                raise RetentionBlocked("RETENTION_DURATION_BUDGET_EXCEEDED")
            db.commit()
    except (RetentionBlocked, DBAPIError) as exc:
        db.rollback()
        result.update(dict.fromkeys((*OPERATIONAL_KEYS, "deleted_success_jobs",
                                     "deleted_failed_jobs"), 0))
        result["blocked"] = True
        if isinstance(exc, RetentionBlocked):
            result["error_code"] = str(exc)
        else:
            state = getattr(exc.orig, "sqlstate", None)
            result["error_code"] = (
                "RETENTION_RETRY_REQUIRED" if state in ("55P03", "57014", "23503", "40P01")
                else "RETENTION_DATABASE_ERROR"
            )
    except Exception:
        db.rollback()
        raise
    result["duration_ms"] = round((perf_counter() - started) * 1000, 3)
    logger.info("retention cleanup {}", {
        key: value for key, value in result.items() if not key.startswith("missing_reference_")
    })
    return result
