import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.agent import require_agent_user
from app.api.v1.common import envelope
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.domain.decision.contracts import PaperError
from app.domain.decision.requests import (
    ApproveProposal,
    CreateObservation,
    CreateProposal,
    RejectProposal,
)
from app.services.decision.application import DecisionApplication
from app.services.decision.approval import ApprovalApplication
from app.services.paper.queries import PaperQueries, schema_ready

router = APIRouter()


def get_paper_db():
    with SessionLocal() as db:
        yield db


def execute(call):
    try:
        row = call()
    except PaperError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail={"code": exc.code, "message": exc.code}
        ) from exc
    return envelope(
        {
            "id": str(row.id),
            "mode": "PAPER",
            "record_hash": row.record_hash,
            "state": getattr(row, "state", None),
            "decision": getattr(row, "decision", None),
        }
    )


@router.post("/observations")
def observe(body: CreateObservation, user=Depends(require_agent_user), db=Depends(get_paper_db)):
    return execute(lambda: DecisionApplication(db, get_settings()).observe(user.id, body))


@router.post("/proposals")
def propose(body: CreateProposal, user=Depends(require_agent_user), db=Depends(get_paper_db)):
    return execute(lambda: DecisionApplication(db, get_settings()).propose(user.id, body))


@router.post("/proposals/{proposal_id}/approve")
def approve(
    proposal_id: uuid.UUID,
    body: ApproveProposal,
    user=Depends(require_agent_user),
    db=Depends(get_paper_db),
):
    return execute(
        lambda: ApprovalApplication(db, get_settings()).approve(user.id, proposal_id, body)
    )


@router.post("/proposals/{proposal_id}/reject")
def reject(
    proposal_id: uuid.UUID,
    body: RejectProposal,
    user=Depends(require_agent_user),
    db=Depends(get_paper_db),
):
    return execute(
        lambda: ApprovalApplication(db, get_settings()).reject(user.id, proposal_id, body)
    )


@router.get("/{collection}")
def records(
    collection: Literal["observations", "proposals"],
    account_id: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
    start: date | None = None,
    end: date | None = None,
    state: str | None = Query(None, max_length=32, pattern=r"^[A-Z_]+$"),
    stage: str | None = Query(None, max_length=24, pattern=r"^[A-Z_]+$"),
    user=Depends(require_agent_user),
    db=Depends(get_paper_db),
):
    if not schema_ready(db):
        raise HTTPException(status_code=503, detail={"code": "PAPER_SCHEMA_REQUIRED"})
    try:
        rows, meta = PaperQueries(db).page(
            user.id,
            collection,
            account_id=account_id,
            limit=limit,
            offset=offset,
            start=start,
            end=end,
            state=state,
            stage=stage,
        )
    except PaperError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code}) from exc
    return envelope(rows, meta)


@router.get("/{collection}/{record_id}")
def record(
    collection: Literal["observations", "proposals"],
    record_id: uuid.UUID,
    user=Depends(require_agent_user),
    db=Depends(get_paper_db),
):
    if not schema_ready(db):
        raise HTTPException(status_code=503, detail={"code": "PAPER_SCHEMA_REQUIRED"})
    try:
        return envelope(PaperQueries(db).detail(user.id, collection, record_id))
    except PaperError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code}) from exc
