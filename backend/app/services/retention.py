from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from app.models.auth import AuthSession
from app.models.job import JobRun, ProviderApiLog


def run_retention(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    current = now or datetime.now(UTC)
    provider = db.execute(
        delete(ProviderApiLog).where(
            ProviderApiLog.created_at < current - timedelta(days=90)
        )
    ).rowcount
    successful = db.execute(
        delete(JobRun).where(
            JobRun.status.in_(("SUCCESS", "PARTIAL", "CANCELLED")),
            JobRun.finished_at < current - timedelta(days=180),
        )
    ).rowcount
    failed = db.execute(
        delete(JobRun).where(
            JobRun.status == "FAILED",
            JobRun.finished_at < current - timedelta(days=365),
        )
    ).rowcount
    sessions = db.execute(
        delete(AuthSession).where(
            or_(
                AuthSession.expires_at < current - timedelta(days=30),
                AuthSession.revoked_at < current - timedelta(days=30),
            )
        )
    ).rowcount
    db.commit()
    return {
        "provider_api_log": int(provider or 0),
        "successful_jobs": int(successful or 0),
        "failed_jobs": int(failed or 0),
        "auth_sessions": int(sessions or 0),
    }
