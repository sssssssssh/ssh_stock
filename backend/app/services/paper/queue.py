from sqlalchemy import func, select

from app.domain.decision.contracts import PaperError, content_hash, stable_id
from app.models.job import JobRun
from app.models.market_data import TradeCalendar
from app.models.paper import PaperAccount, PaperAccountEvent, PaperDayRun, PaperNavDaily
from app.repositories.paper import PaperRepository
from app.services.paper.account_state import account_settings
from app.services.paper.job_contracts import dispatch_identity, verify_dispatch
from app.services.paper.records import (
    close_cutoff,
    make_record,
    next_open,
    replay,
    request_hash,
    request_lock,
    utc_now,
    verify_record,
)

PAPER_DAILY = "PAPER_DAILY"
PAPER_OBSERVATION = "PAPER_OBSERVATION"
PAPER_REVIEW = "PAPER_REVIEW"
PAPER_JOB_TYPES = (PAPER_DAILY, PAPER_OBSERVATION, PAPER_REVIEW)


class PaperQueue:
    def __init__(self, db, settings, *, clock=utc_now):
        self.db, self.settings, self.clock = db, settings, clock
        self.repo = PaperRepository(db)

    def advance(self, owner, account_id, body, *, source="manual"):
        if not self.settings.paper_config.enabled:
            raise PaperError("PAPER_DISABLED", status_code=403)
        try:
            request_lock(self.db, owner, "account-event", body.request_id)
            digest = content_hash([str(account_id), request_hash(owner, "advance", body)])
            existing = replay(
                self.repo.by_request(PaperAccountEvent, owner, body.request_id), digest
            )
            if existing:
                data = verify_record(existing)
                job = self._owned_job(owner, data["job_id"])
                self.db.commit()
                return job
            account = self.repo.owned(PaperAccount, owner, account_id, lock=True)
            account_settings(account, self.settings)
            if account.state != "ACTIVE":
                raise PaperError("PAPER_ACCOUNT_NOT_ACTIVE")
            now, day = self.clock(), body.trade_date
            calendar = self.db.get(TradeCalendar, day)
            if (
                not calendar
                or not calendar.is_open
                or calendar.exchange not in ("SSE", "SZSE")
                or now < close_cutoff(day)
            ):
                raise PaperError("SOURCE_EOD_NOT_READY")
            job = self.db.scalar(
                select(JobRun)
                .where(
                    JobRun.job_type == PAPER_DAILY,
                    JobRun.job_metadata["owner_user_id"].astext == str(owner),
                    JobRun.job_metadata["account_id"].astext == str(account.id),
                    JobRun.target_trade_date == day,
                    JobRun.status.in_(("QUEUED", "RUNNING", "SUCCESS")),
                )
                .order_by(JobRun.started_at.desc())
                .limit(1)
            )
            if job is None:
                latest = self.db.scalar(
                    select(func.max(PaperNavDaily.trade_date)).where(
                        PaperNavDaily.account_id == account.id, PaperNavDaily.owner_user_id == owner
                    )
                )
                expected = next_open(self.db, latest) if latest else account.first_trade_date
                if day != expected:
                    raise PaperError("PAPER_DAY_GAP")
                if latest is not None:
                    previous = self.db.scalar(
                        select(PaperDayRun).where(
                            PaperDayRun.account_id == account.id,
                            PaperDayRun.trade_date == latest,
                            PaperDayRun.phase == "DAY_COMPLETED",
                        )
                    )
                    if previous is None or previous.status != "SUCCESS":
                        raise PaperError("PAPER_SOURCE_DRIFT")
                    verify_record(previous)
                job = JobRun(
                    id=stable_id(owner, PAPER_DAILY, f"{account.id}:{day}:{body.request_id}"),
                    job_type=PAPER_DAILY,
                    target_trade_date=day,
                    started_at=now,
                    status="QUEUED",
                    step="paper queued",
                    row_count=0,
                    cancel_requested=False,
                    job_metadata={
                        "owner_user_id": str(owner),
                        "account_id": str(account.id),
                        "trade_date": day.isoformat(),
                        "source": source,
                        "mode": "PAPER",
                        "market_data_mode": "POST_EOD_SIMULATED_OPEN",
                        "config_hash": account.config_hash,
                        "request_hash": digest,
                        "stage": "queued",
                        "progress_pct": 0,
                    },
                )
                self.db.add(job)
                self.db.flush()
            receipt = self.repo.add(
                make_record(
                    PaperAccountEvent,
                    owner,
                    body.request_id,
                    now=now,
                    data={
                        "kind": "PAPER_DAILY_REQUESTED",
                        "job_id": str(job.id),
                        "trade_date": day,
                        "job_identity": dispatch_identity(job),
                    },
                    account_id=account.id,
                    from_state=account.state,
                    to_state=account.state,
                    request_id=body.request_id,
                    request_hash=digest,
                )
            )
            self._bind_receipt(job, receipt)
            self.db.commit()
            return job
        except Exception:
            self.db.rollback()
            raise

    def _owned_job(self, owner, job_id):
        import uuid

        row = self.db.scalar(
            select(JobRun).where(
                JobRun.id == uuid.UUID(str(job_id)),
                JobRun.job_type.in_(PAPER_JOB_TYPES),
                JobRun.job_metadata["owner_user_id"].astext == str(owner),
            )
        )
        if row is None:
            raise PaperError("PAPER_NOT_FOUND", status_code=404)
        verify_dispatch(self.db, row)
        return row

    def review(self, owner, account_id, body):
        if not self.settings.paper_config.enabled:
            raise PaperError("PAPER_DISABLED", status_code=403)
        try:
            request_lock(self.db, owner, "account-event", body.request_id)
            digest = content_hash([str(account_id), request_hash(owner, "review-request", body)])
            old = replay(self.repo.by_request(PaperAccountEvent, owner, body.request_id), digest)
            if old:
                job = self._owned_job(owner, verify_record(old)["job_id"])
                self.db.commit()
                return job
            account = self.repo.owned(PaperAccount, owner, account_id, lock=True)
            account_settings(account, self.settings)
            completed = self.db.scalar(
                select(PaperDayRun.id).where(
                    PaperDayRun.account_id == account.id,
                    PaperDayRun.trade_date == body.asof_date,
                    PaperDayRun.phase == "DAY_COMPLETED",
                    PaperDayRun.status == "SUCCESS",
                )
            )
            if completed is None:
                raise PaperError("PAPER_ACCOUNT_SNAPSHOT_NOT_READY")
            now = self.clock()
            job = JobRun(
                id=stable_id(owner, PAPER_REVIEW, body.request_id),
                job_type=PAPER_REVIEW,
                target_trade_date=body.asof_date,
                started_at=now,
                status="QUEUED",
                step="paper review queued",
                cancel_requested=False,
                row_count=0,
                job_metadata={
                    "owner_user_id": str(owner),
                    "account_id": str(account.id),
                    "asof_date": body.asof_date.isoformat(),
                    "window_days": body.window_days,
                    "config_hash": account.config_hash,
                    "mode": "PAPER",
                    "market_data_mode": "POST_EOD_SIMULATED_OPEN",
                    "request_hash": digest,
                    "source": "manual",
                    "stage": "queued",
                    "progress_pct": 0,
                },
            )
            self.db.add(job)
            self.db.flush()
            receipt = self.repo.add(
                make_record(
                    PaperAccountEvent,
                    owner,
                    body.request_id,
                    now=now,
                    data={
                        "kind": "PAPER_REVIEW_REQUESTED",
                        "job_id": str(job.id),
                        "job_identity": dispatch_identity(job),
                    },
                    account_id=account.id,
                    from_state=account.state,
                    to_state=account.state,
                    request_id=body.request_id,
                    request_hash=digest,
                )
            )
            self._bind_receipt(job, receipt)
            self.db.commit()
            return job
        except Exception:
            self.db.rollback()
            raise

    def _bind_receipt(self, job, receipt):
        if not (job.job_metadata or {}).get("receipt_id"):
            job.job_metadata = {**dict(job.job_metadata or {}), "receipt_id": str(receipt.id)}

    def observation(self, owner, account_id, body):
        if not self.settings.paper_config.enabled:
            raise PaperError("PAPER_DISABLED", status_code=403)
        try:
            request_lock(self.db, owner, "account-event", body.request_id)
            digest = content_hash([str(account_id), request_hash(owner, "observe-request", body)])
            old = replay(self.repo.by_request(PaperAccountEvent, owner, body.request_id), digest)
            if old:
                job = self._owned_job(owner, verify_record(old)["job_id"])
                self.db.commit()
                return job
            account = self.repo.owned(PaperAccount, owner, account_id, lock=True)
            account_settings(account, self.settings)
            if account.state != "ACTIVE" or body.account_id != account.id or body.include_codes:
                raise PaperError("PAPER_ACCOUNT_NOT_ACTIVE")
            now = self.clock()
            job = JobRun(
                id=stable_id(owner, PAPER_OBSERVATION, body.request_id),
                job_type=PAPER_OBSERVATION,
                target_trade_date=body.signal_date,
                started_at=now,
                status="QUEUED",
                step="paper observation queued",
                row_count=0,
                cancel_requested=False,
                job_metadata={
                    "owner_user_id": str(owner),
                    "account_id": str(account.id),
                    "trade_date": body.signal_date.isoformat(),
                    "config_hash": account.config_hash,
                    "mode": "PAPER",
                    "market_data_mode": "POST_EOD_SIMULATED_OPEN",
                    "source": "scheduler",
                    "request_hash": digest,
                    "stage": "queued",
                    "progress_pct": 0,
                },
            )
            self.db.add(job)
            self.db.flush()
            receipt = self.repo.add(
                make_record(
                    PaperAccountEvent,
                    owner,
                    body.request_id,
                    now=now,
                    data={
                        "kind": "PAPER_OBSERVATION_REQUESTED",
                        "job_id": str(job.id),
                        "job_identity": dispatch_identity(job),
                    },
                    account_id=account.id,
                    from_state=account.state,
                    to_state=account.state,
                    request_id=body.request_id,
                    request_hash=digest,
                )
            )
            self._bind_receipt(job, receipt)
            self.db.commit()
            return job
        except Exception:
            self.db.rollback()
            raise

    def cancel(self, owner, account_id, job_id, body):
        if not self.settings.paper_config.enabled:
            raise PaperError("PAPER_DISABLED", status_code=403)
        try:
            request_lock(self.db, owner, "account-event", body.request_id)
            account = self.repo.owned(PaperAccount, owner, account_id)
            digest = content_hash(
                [str(account.id), str(job_id), request_hash(owner, "cancel", body)]
            )
            old = replay(self.repo.by_request(PaperAccountEvent, owner, body.request_id), digest)
            job = self._owned_job(owner, job_id)
            verified_owner, verified_account = verify_dispatch(self.db, job)
            if verified_owner != owner or verified_account != account.id:
                raise PaperError("PAPER_NOT_FOUND", status_code=404)
            if old:
                self.db.commit()
                return job
            job = self.db.scalar(
                select(JobRun)
                .where(JobRun.id == job.id)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
            if verify_dispatch(self.db, job) != (owner, account.id):
                raise PaperError("PAPER_NOT_FOUND", status_code=404)
            if job.status not in ("QUEUED", "RUNNING"):
                raise PaperError("PAPER_JOB_NOT_CANCELLABLE")
            job.cancel_requested = True
            job.step = "paper cancellation requested"
            if job.status == "QUEUED":
                job.status, job.finished_at = "CANCELLED", self.clock()
            self.repo.add(
                make_record(
                    PaperAccountEvent,
                    owner,
                    body.request_id,
                    now=self.clock(),
                    data={"kind": "PAPER_JOB_CANCEL_REQUESTED", "job_id": str(job.id)},
                    account_id=account.id,
                    from_state=account.state,
                    to_state=account.state,
                    request_id=body.request_id,
                    request_hash=digest,
                )
            )
            self.db.commit()
            return job
        except Exception:
            self.db.rollback()
            raise


def job_projection(row):
    metadata = row.job_metadata or {}
    return {
        "id": str(row.id),
        "mode": "PAPER",
        "job_type": row.job_type,
        "trade_date": row.target_trade_date.isoformat() if row.target_trade_date else None,
        "status": row.status,
        "step": row.step,
        "started_at": row.started_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "heartbeat_at": row.heartbeat_at.isoformat() if row.heartbeat_at else None,
        "error_code": metadata.get("error_code"),
        "progress_pct": metadata.get("progress_pct", 0),
        "stage": metadata.get("stage"),
        "cancel_requested": bool(row.cancel_requested),
        "account_id": metadata.get("account_id"),
        "market_data_mode": "POST_EOD_SIMULATED_OPEN",
    }
