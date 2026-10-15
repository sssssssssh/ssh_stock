import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.decision.account_requests import ReviewPaperAccount
from app.domain.decision.contracts import PaperError
from app.domain.decision.requests import CreateObservation
from app.models.job import JobRun
from app.models.paper import PaperAccount
from app.repositories.paper import PaperRepository
from app.services.decision.application import DecisionApplication
from app.services.paper.daily import PaperDailyApplication
from app.services.paper.job_contracts import verify_dispatch
from app.services.paper.queue import PAPER_DAILY, PAPER_OBSERVATION, PAPER_REVIEW
from app.services.paper.records import request_lock, utc_now
from app.services.paper.reviews import PaperReviews


def safe_error_code(exc):
    code = exc.code if isinstance(exc, PaperError) else "PAPER_EXECUTION_FAILED"
    return code if re.fullmatch(r"[A-Z][A-Z0-9_]{1,79}", code) else "PAPER_EXECUTION_FAILED"


class PaperJobApplication:
    def __init__(self, db, settings, *, clock=utc_now, fault_hook=None):
        self.db, self.settings, self.clock = db, settings, clock
        self.fault_hook = fault_hook or (lambda phase: None)
        self.owner, self.account_id, self.worker_id, self.job_id = None, None, None, None

    def run_job(self, job_id):
        job = self.db.get(JobRun, job_id)
        if job is None:
            raise PaperError("PAPER_JOB_NOT_FOUND")
        self.job_id, self.worker_id = job.id, job.worker_id
        try:
            if not self.settings.paper_config.enabled:
                raise PaperError("PAPER_DISABLED", status_code=403)
            self.owner, self.account_id = verify_dispatch(self.db, job)
            if job.status == "SUCCESS":
                return job
            if job.status != "RUNNING" or not self.worker_id:
                raise PaperError("PAPER_JOB_LEASE_LOST")
            metadata = dict(job.job_metadata or {})
            result_request = f"job-result:{job.id}"
            if job.job_type == PAPER_REVIEW:
                request_lock(self.db, self.owner, "account-event", result_request)
            elif job.job_type == PAPER_OBSERVATION:
                request_lock(self.db, self.owner, "observe", result_request)
            account = PaperRepository(self.db).owned(
                PaperAccount, self.owner, self.account_id, lock=True
            )
            if metadata.get("config_hash") != account.config_hash:
                raise PaperError("PAPER_JOB_IDENTITY_INVALID")
            self._progress("source", 15)
            if job.job_type == PAPER_DAILY:
                day = date.fromisoformat(metadata["trade_date"])
                if day != job.target_trade_date:
                    raise PaperError("PAPER_JOB_IDENTITY_INVALID")
                result = PaperDailyApplication(
                    self.db,
                    self.settings,
                    clock=self.clock,
                    fault_hook=self._phase,
                    commit_guard=self._complete,
                ).run(self.owner, account.id, day, job_id=job.id)
            elif job.job_type == PAPER_REVIEW:
                body = ReviewPaperAccount(
                    request_id=result_request,
                    asof_date=metadata["asof_date"],
                    window_days=metadata["window_days"],
                )
                if body.asof_date != job.target_trade_date:
                    raise PaperError("PAPER_JOB_IDENTITY_INVALID")
                result = PaperReviews(
                    self.db,
                    self.settings,
                    clock=self.clock,
                    commit_guard=self._complete,
                ).create(self.owner, account.id, body)
            elif job.job_type == PAPER_OBSERVATION:
                if account.state != "ACTIVE":
                    raise PaperError("PAPER_ACCOUNT_NOT_ACTIVE")
                body = CreateObservation(
                    request_id=result_request,
                    signal_date=metadata["trade_date"],
                    account_id=account.id,
                )
                if body.signal_date != job.target_trade_date:
                    raise PaperError("PAPER_JOB_IDENTITY_INVALID")
                result = DecisionApplication(
                    self.db,
                    self.settings,
                    clock=self.clock,
                    commit_guard=self._complete,
                ).observe(self.owner, body)
            else:
                raise PaperError("PAPER_JOB_IDENTITY_INVALID")
            return result
        except Exception as exc:
            self.db.rollback()
            self._fail(safe_error_code(exc))
            raise

    def _phase(self, phase):
        stages = {
            "before_orders": ("execution", 40),
            "before_nav": ("close", 70),
            "before_commit": ("committing", 90),
        }
        if phase in stages:
            self._progress(*stages[phase])
        self.fault_hook(phase)

    def _progress(self, stage, percent):
        # Progress commits separately; financial state stays in the account transaction.
        with Session(bind=self.db.get_bind()) as progress:
            # Financial day heads hold FK KEY SHARE on JobRun until the day commits.
            job = progress.scalar(
                select(JobRun).where(JobRun.id == self.job_id).with_for_update(key_share=True)
            )
            self._assert_claim(progress, job)
            job.step = f"paper {stage}"
            job.heartbeat_at = self.clock()
            job.job_metadata = {
                **dict(job.job_metadata or {}),
                "stage": stage,
                "progress_pct": percent,
            }
            progress.commit()

    def _assert_claim(self, db, job):
        if job is None or job.status != "RUNNING" or job.worker_id != self.worker_id:
            raise PaperError("PAPER_JOB_LEASE_LOST")
        owner, account = verify_dispatch(db, job)
        if owner != self.owner or account != self.account_id:
            raise PaperError("PAPER_JOB_IDENTITY_INVALID")
        if job.cancel_requested:
            raise PaperError("PAPER_JOB_CANCELLED")

    def _complete(self, result):
        job = self.db.scalar(
            select(JobRun)
            .where(JobRun.id == self.job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        self._assert_claim(self.db, job)
        job.status, job.finished_at, job.heartbeat_at = "SUCCESS", self.clock(), self.clock()
        job.step, job.row_count, job.error_message = "paper complete", 1, None
        job.job_metadata = {
            **dict(job.job_metadata or {}),
            "stage": "success",
            "progress_pct": 100,
            "result_id": str(result.id),
            "result_hash": getattr(result, "result_hash", None) or result.record_hash,
            "error_code": None,
        }

    def _fail(self, code):
        if self.owner is not None and self.account_id is not None:
            PaperRepository(self.db).owned(PaperAccount, self.owner, self.account_id, lock=True)
        job = self.db.scalar(
            select(JobRun)
            .where(JobRun.id == self.job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if job is not None and job.status == "RUNNING" and job.worker_id == self.worker_id:
            cancelled = code == "PAPER_JOB_CANCELLED" or job.cancel_requested
            job.status = "CANCELLED" if cancelled else "FAILED"
            job.finished_at, job.error_message = self.clock(), code
            job.step = "paper cancelled" if cancelled else "paper failed; explicit retry required"
            job.job_metadata = {
                **dict(job.job_metadata or {}),
                "stage": job.status.lower(),
                "error_code": code,
            }
        self.db.commit()
