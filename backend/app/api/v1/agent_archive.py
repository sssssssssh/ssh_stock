import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.api.v1.agent import require_agent_user
from app.api.v1.common import envelope
from app.core.agent_db import agent_db_session
from app.core.config import get_settings
from app.domain.agent.archive import (
    ArchiveEnvelope,
    ArchiveEvidenceSummary,
    ArchiveVerifyView,
    EvidenceDetailView,
    TurnArchiveView,
    VerifyArchiveRequest,
)
from app.domain.agent.chat_errors import AgentChatError
from app.domain.agent.report_errors import AgentReportError
from app.services.agent.archive.application import AgentArchiveApplication

router = APIRouter()


def get_archive_application():
    settings = get_settings()
    with agent_db_session(
        settings, remaining_seconds=settings.agent_config.archive.verify_timeout_seconds
    ) as db:
        yield AgentArchiveApplication(db, settings)


def _safe_call(method, **kwargs):
    try:
        return method(**kwargs)
    except (AgentChatError, AgentReportError) as exc:
        raise HTTPException(
            status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}
        ) from exc


@router.get(
    "/chats/{chat_id}/turn-archives/{request_id:path}",
    response_model=ArchiveEnvelope[TurnArchiveView],
)
def turn_archive(
    chat_id: uuid.UUID,
    request_id: str = Path(min_length=1, max_length=128),
    user: Any = Depends(require_agent_user),
    service=Depends(get_archive_application),
):
    return envelope(
        _safe_call(service.turn_archive, user=user, chat_id=chat_id, request_id=request_id)
    )


@router.get(
    "/reports/{report_id}/evidence", response_model=ArchiveEnvelope[list[ArchiveEvidenceSummary]]
)
def report_evidence(
    report_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: Any = Depends(require_agent_user),
    service=Depends(get_archive_application),
):
    rows, meta = _safe_call(
        service.report_evidence, user=user, report_id=report_id, limit=limit, offset=offset
    )
    return envelope(rows, meta)


@router.get(
    "/reports/{report_id}/evidence/{evidence_id}",
    response_model=ArchiveEnvelope[EvidenceDetailView],
)
def evidence_detail(
    report_id: uuid.UUID,
    evidence_id: str = Path(min_length=1, max_length=128),
    user: Any = Depends(require_agent_user),
    service=Depends(get_archive_application),
):
    return envelope(
        _safe_call(service.evidence_detail, user=user, report_id=report_id, evidence_id=evidence_id)
    )


@router.post("/reports/{report_id}/verify", response_model=ArchiveEnvelope[ArchiveVerifyView])
def verify_report(
    report_id: uuid.UUID,
    body: VerifyArchiveRequest,
    user: Any = Depends(require_agent_user),
    service=Depends(get_archive_application),
):
    return envelope(
        _safe_call(service.verify_report_archive, user=user, report_id=report_id, body=body)
    )
