import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.api.v1.agent import require_agent_user
from app.api.v1.common import envelope
from app.api.v1.decisions import execute, get_paper_db
from app.core.clock import business_today
from app.core.config import get_settings
from app.domain.decision.account_requests import (
    AdvancePaperAccount,
    CreatePaperAccount,
    ReviewPaperAccount,
)
from app.domain.decision.contracts import PaperError
from app.domain.decision.requests import PaperRequest
from app.models.job import JobRun
from app.models.market_data import StockDaily
from app.services.paper.accounts import PaperAccountApplication
from app.services.paper.performance import PaperPerformance
from app.services.paper.queries import PaperQueries, schema_ready
from app.services.paper.queue import PAPER_JOB_TYPES, PaperQueue, job_projection

router = APIRouter()
Collection = Literal[
    "events",
    "runs",
    "days",
    "orders",
    "attempts",
    "fills",
    "ledger",
    "positions",
    "reviews",
    "approvals",
]


def guarded(call):
    try:
        return call()
    except PaperError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail={"code": exc.code, "message": exc.code}
        ) from exc


def ensure_schema(db):
    if not schema_ready(db):
        raise HTTPException(status_code=503, detail={"code": "PAPER_SCHEMA_REQUIRED"})


@router.get("/status")
def status(user=Depends(require_agent_user), db=Depends(get_paper_db)):
    settings = get_settings()
    latest = db.scalar(select(func.max(StockDaily.trade_date)))
    return envelope(
        {
            "mode": "PAPER",
            "enabled": settings.paper_config.enabled,
            "auto_advance": settings.paper_config.auto_advance,
            "auto_approve": False,
            "schema_ready": schema_ready(db),
            "business_date": business_today().isoformat(),
            "latest_raw_date": latest.isoformat() if latest else None,
            "market_data_mode": "POST_EOD_SIMULATED_OPEN",
            "worker_required": True,
            "default_risk": settings.paper_config.policy.risk.model_dump(mode="json"),
        }
    )


@router.post("/accounts")
def create_account(
    body: CreatePaperAccount, user=Depends(require_agent_user), db=Depends(get_paper_db)
):
    return execute(lambda: PaperAccountApplication(db, get_settings()).create(user.id, body))


@router.get("/accounts")
def accounts(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
    user=Depends(require_agent_user),
    db=Depends(get_paper_db),
):
    ensure_schema(db)
    rows, meta = guarded(
        lambda: PaperQueries(db).page(user.id, "accounts", limit=limit, offset=offset)
    )
    return envelope(rows, meta)


@router.get("/accounts/{account_id}")
def account(account_id: uuid.UUID, user=Depends(require_agent_user), db=Depends(get_paper_db)):
    ensure_schema(db)
    return envelope(guarded(lambda: PaperQueries(db).account(user.id, account_id)))


def transition(account_id, body, user, db, state):
    return execute(
        lambda: PaperAccountApplication(db, get_settings()).transition(
            user.id, account_id, body, state
        )
    )


@router.post("/accounts/{account_id}/activate")
def activate(
    account_id: uuid.UUID,
    body: PaperRequest,
    user=Depends(require_agent_user),
    db=Depends(get_paper_db),
):
    return transition(account_id, body, user, db, "ACTIVE")


@router.post("/accounts/{account_id}/pause")
def pause(
    account_id: uuid.UUID,
    body: PaperRequest,
    user=Depends(require_agent_user),
    db=Depends(get_paper_db),
):
    return transition(account_id, body, user, db, "PAUSED")


@router.post("/accounts/{account_id}/close")
def close(
    account_id: uuid.UUID,
    body: PaperRequest,
    user=Depends(require_agent_user),
    db=Depends(get_paper_db),
):
    return transition(account_id, body, user, db, "CLOSED")


@router.post("/accounts/{account_id}/advance")
def advance(
    account_id: uuid.UUID,
    body: AdvancePaperAccount,
    user=Depends(require_agent_user),
    db=Depends(get_paper_db),
):
    return envelope(
        job_projection(
            guarded(lambda: PaperQueue(db, get_settings()).advance(user.id, account_id, body))
        ),
        {"accepted": True},
    )


@router.post("/accounts/{account_id}/review-day")
def review(
    account_id: uuid.UUID,
    body: ReviewPaperAccount,
    user=Depends(require_agent_user),
    db=Depends(get_paper_db),
):
    return envelope(
        job_projection(
            guarded(lambda: PaperQueue(db, get_settings()).review(user.id, account_id, body))
        ),
        {"accepted": True},
    )


@router.get("/accounts/{account_id}/performance")
def performance(account_id: uuid.UUID, user=Depends(require_agent_user), db=Depends(get_paper_db)):
    ensure_schema(db)
    return envelope(
        guarded(lambda: PaperPerformance(db, get_settings()).summary(user.id, account_id))
    )


@router.get("/accounts/{account_id}/jobs")
def jobs(
    account_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
    user=Depends(require_agent_user),
    db=Depends(get_paper_db),
):
    ensure_schema(db)
    guarded(lambda: PaperQueries(db).account(user.id, account_id))
    filters = (
        JobRun.job_type.in_(PAPER_JOB_TYPES),
        JobRun.job_metadata["owner_user_id"].astext == str(user.id),
        JobRun.job_metadata["account_id"].astext == str(account_id),
    )
    rows = list(
        db.scalars(
            select(JobRun)
            .where(*filters)
            .order_by(JobRun.started_at.desc(), JobRun.id)
            .limit(limit)
            .offset(offset)
        )
    )
    total = db.scalar(select(func.count()).select_from(JobRun).where(*filters))
    return envelope(
        [job_projection(row) for row in rows], {"total": total, "limit": limit, "offset": offset}
    )


@router.get("/accounts/{account_id}/{collection}")
def records(
    account_id: uuid.UUID,
    collection: Collection,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
    start: date | None = None,
    end: date | None = None,
    trade_date: date | None = None,
    state: str | None = Query(None, max_length=32, pattern=r"^[A-Z_]+$"),
    user=Depends(require_agent_user),
    db=Depends(get_paper_db),
):
    ensure_schema(db)
    rows, meta = guarded(
        lambda: PaperQueries(db).page(
            user.id,
            collection,
            account_id=account_id,
            limit=limit,
            offset=offset,
            start=start,
            end=end,
            trade_date=trade_date,
            state=state,
        )
    )
    return envelope(rows, meta)


@router.get("/accounts/{account_id}/{collection}/{record_id}")
def record(
    account_id: uuid.UUID,
    collection: Collection,
    record_id: uuid.UUID,
    user=Depends(require_agent_user),
    db=Depends(get_paper_db),
):
    ensure_schema(db)
    queries = PaperQueries(db)
    guarded(lambda: queries.account(user.id, account_id))
    row = guarded(lambda: queries.detail(user.id, collection, record_id))
    if row["account_id"] != str(account_id):
        raise HTTPException(status_code=404, detail={"code": "PAPER_NOT_FOUND"})
    return envelope(row)
