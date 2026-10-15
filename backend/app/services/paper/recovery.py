from datetime import timedelta

from sqlalchemy import func, select

from app.core.config import get_settings
from app.domain.decision.contracts import PaperError, content_hash
from app.models.job import JobRun
from app.models.paper import PaperAccount, PaperAccountEvent
from app.services.paper.job_contracts import verify_dispatch
from app.services.paper.queue import PAPER_JOB_TYPES
from app.services.paper.records import make_record, utc_now


def recover_stale_paper_jobs(db, *, timeout_minutes, now=None, settings=None):
    config = settings or get_settings()
    if not config.paper_config.enabled:
        return 0
    current = now or utc_now()
    cutoff = current - timedelta(minutes=timeout_minutes)
    candidates = list(
        db.scalars(
            select(JobRun)
            .where(
                JobRun.job_type.in_(PAPER_JOB_TYPES),
                JobRun.status == "RUNNING",
                func.coalesce(JobRun.heartbeat_at, JobRun.started_at) < cutoff,
            )
            .order_by(JobRun.id)
        )
    )
    recovered = 0
    for candidate in candidates:
        worker = candidate.worker_id
        account, owner, code = None, None, "PAPER_WORKER_HEARTBEAT_TIMEOUT"
        try:
            owner, account_id = verify_dispatch(db, candidate)
            # Active work owns the account lock; skip it even if a heartbeat is delayed.
            account = db.scalar(
                select(PaperAccount)
                .where(
                    PaperAccount.id == account_id,
                    PaperAccount.owner_user_id == owner,
                )
                .with_for_update(skip_locked=True)
            )
            if account is None:
                continue
        except PaperError:
            code = "PAPER_JOB_IDENTITY_INVALID"
        job = db.scalar(
            select(JobRun)
            .where(JobRun.id == candidate.id)
            .execution_options(populate_existing=True)
            .with_for_update(skip_locked=True)
        )
        if (
            job is None
            or job.status != "RUNNING"
            or job.worker_id != worker
            or (job.heartbeat_at or job.started_at) >= cutoff
        ):
            continue
        job.status, job.finished_at, job.error_message = "FAILED", current, code
        job.step = "paper worker expired; explicit retry required"
        job.job_metadata = {**dict(job.job_metadata or {}), "stage": "failed", "error_code": code}
        if account is not None:
            request_id = "job-timeout:" + content_hash([str(job.id), worker])
            old = db.scalar(
                select(PaperAccountEvent).where(
                    PaperAccountEvent.owner_user_id == owner,
                    PaperAccountEvent.request_id == request_id,
                )
            )
            if old is None:
                db.add(
                    make_record(
                        PaperAccountEvent,
                        owner,
                        request_id,
                        now=current,
                        data={
                            "kind": "PAPER_JOB_RECOVERED",
                            "job_id": str(job.id),
                            "reason_code": code,
                        },
                        account_id=account.id,
                        from_state=account.state,
                        to_state=account.state,
                        request_id=request_id,
                        request_hash=content_hash([str(job.id), worker, code]),
                    )
                )
        recovered += 1
    db.commit()
    return recovered
