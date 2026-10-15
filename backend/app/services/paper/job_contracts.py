import uuid

from sqlalchemy import select

from app.domain.decision.contracts import PaperError
from app.models.paper import PaperAccountEvent
from app.services.paper.records import verify_record


def dispatch_identity(job):
    metadata = job.job_metadata or {}
    return {
        "schema_version": "m17-job-dispatch-v1",
        "job_id": str(job.id),
        "job_type": job.job_type,
        "target_trade_date": job.target_trade_date.isoformat() if job.target_trade_date else None,
        **{
            key: metadata.get(key)
            for key in (
                "owner_user_id",
                "account_id",
                "config_hash",
                "mode",
                "market_data_mode",
                "trade_date",
                "asof_date",
                "window_days",
                "source",
                "request_hash",
            )
        },
    }


def verify_dispatch(db, job):
    try:
        metadata = job.job_metadata or {}
        owner = uuid.UUID(metadata["owner_user_id"])
        account_id = uuid.UUID(metadata["account_id"])
        receipt_id = uuid.UUID(metadata["receipt_id"])
        receipt = db.scalar(
            select(PaperAccountEvent).where(
                PaperAccountEvent.id == receipt_id,
                PaperAccountEvent.owner_user_id == owner,
                PaperAccountEvent.account_id == account_id,
            )
        )
        data = verify_record(receipt)
        if (
            data.get("job_identity") != dispatch_identity(job)
            or data.get("job_id") != str(job.id)
            or metadata.get("mode") != "PAPER"
            or metadata.get("market_data_mode") != "POST_EOD_SIMULATED_OPEN"
            or job.target_trade_date is None
        ):
            raise PaperError("PAPER_JOB_IDENTITY_INVALID")
        return owner, account_id
    except (KeyError, TypeError, ValueError, PaperError) as exc:
        raise PaperError("PAPER_JOB_IDENTITY_INVALID") from exc
