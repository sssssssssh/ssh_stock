import uuid

from fastapi import APIRouter, Depends, HTTPException

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
