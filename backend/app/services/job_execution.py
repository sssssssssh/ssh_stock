"""Cooperative cancellation for the data lane only; never force-kill a Writer."""

from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, PendingRollbackError
from sqlalchemy.orm import Session

from app.models.job import JobRun


class JobCancelled(BaseException):
    """Not a business/provider failure; best-effort Exception handlers must not swallow it."""


class JobOwnershipLost(BaseException):
    pass


class JobExecutionUnconfirmed(BaseException):
    pass


def uncertain_database_error(error: BaseException) -> bool:
    if current_execution.get() is None:
        return False
    if isinstance(error, PendingRollbackError):
        return True
    if not isinstance(error, DBAPIError):
        return False
    state = getattr(error.orig, "sqlstate", None)
    return error.connection_invalidated or state is None or str(state).startswith("08")


def preserve_execution_on_disconnect(error: BaseException) -> None:
    if uncertain_database_error(error):
        from app.core.db import database_error_summary

        raise JobExecutionUnconfirmed(database_error_summary(error)) from None


@dataclass(frozen=True)
class Execution:
    job_id: UUID
    worker_id: str
    token: UUID
    bind: object


current_execution: ContextVar[Execution | None] = ContextVar("data_job_execution", default=None)


def checkpoint() -> None:
    execution = current_execution.get()
    if execution is None:
        return
    # A separate short transaction sees cancellation even while the business
    # Session has a snapshot or uncommitted writes. It takes no business locks.
    with Session(bind=execution.bind) as observer:
        row = observer.execute(
            select(
                JobRun.status,
                JobRun.worker_id,
                JobRun.execution_token,
                JobRun.cancel_requested,
            ).where(JobRun.id == execution.job_id)
        ).one_or_none()
    if row is None or (row.status, row.worker_id, row.execution_token) != (
        "RUNNING",
        execution.worker_id,
        execution.token,
    ):
        raise JobOwnershipLost("JOB_OWNERSHIP_LOST")
    if row.cancel_requested:
        raise JobCancelled("JOB_CANCEL_REQUESTED")
