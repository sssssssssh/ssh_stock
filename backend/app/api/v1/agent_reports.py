import uuid
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.v1.agent import require_agent_user
from app.api.v1.common import envelope
from app.core.config import get_settings
from app.core.db import get_db
from app.domain.agent.frozen_contracts import (
    FrozenContractVerificationResponse,
    VerifyFrozenContractsRequest,
)
from app.domain.agent.report import (
    CreateReportComparison,
    CreateResearchReport,
    ReportType,
)
from app.domain.agent.report_errors import AgentReportError
from app.services.agent.report.application import AgentReportApplication

router = APIRouter()


def get_report_application(db: Session = Depends(get_db)) -> AgentReportApplication:
    return AgentReportApplication(db, get_settings())


@router.post("/reports", status_code=status.HTTP_201_CREATED)
def create_report(
    body: CreateResearchReport,
    user: Any = Depends(require_agent_user),
    service: AgentReportApplication = Depends(get_report_application),
) -> dict[str, Any]:
    try:
        report = service.create_report(user=user, body=body)
    except AgentReportError as exc:
        raise _http_error(exc) from exc
    return envelope(report.model_dump(mode="json"), {"request_id": body.request_id})


@router.get("/reports")
def list_reports(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    report_type: ReportType | None = Query(default=None, alias="type"),
    archived: bool | None = Query(default=None),
    include_archived: bool = False,
    user: Any = Depends(require_agent_user),
    service: AgentReportApplication = Depends(get_report_application),
) -> dict[str, Any]:
    rows, total = service.list_reports(
        user=user,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
        report_type=report_type,
        archived=archived,
    )
    return envelope(
        [row.model_dump(mode="json") for row in rows],
        {"limit": limit, "offset": offset, "total": total},
    )


@router.get("/reports/{report_id}")
def get_report(
    report_id: uuid.UUID,
    user: Any = Depends(require_agent_user),
    service: AgentReportApplication = Depends(get_report_application),
) -> dict[str, Any]:
    try:
        report = service.get_report(user=user, report_id=report_id)
    except AgentReportError as exc:
        raise _http_error(exc) from exc
    return envelope(report.model_dump(mode="json"))


@router.get("/reports/{report_id}/export")
def export_report(
    report_id: uuid.UUID,
    format: Literal["markdown", "html"] = Query(default="markdown"),
    user: Any = Depends(require_agent_user),
    service: AgentReportApplication = Depends(get_report_application),
) -> Response:
    try:
        content, media_type, filename = service.export_report(
            user=user, report_id=report_id, export_format=format
        )
    except AgentReportError as exc:
        raise _http_error(exc) from exc
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'none'",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/reports/{report_id}/contracts")
def list_report_contracts(
    report_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: Any = Depends(require_agent_user),
    service: AgentReportApplication = Depends(get_report_application),
) -> dict[str, Any]:
    try:
        rows, meta = service.report_contracts(
            user=user, report_id=report_id, limit=limit, offset=offset
        )
    except AgentReportError as exc:
        raise _http_error(exc) from exc
    return envelope(rows, meta)


@router.get("/reports/{report_id}/contracts/{contract_id}")
def get_report_contract(
    report_id: uuid.UUID,
    contract_id: uuid.UUID,
    user: Any = Depends(require_agent_user),
    service: AgentReportApplication = Depends(get_report_application),
) -> dict[str, Any]:
    try:
        data = service.report_contract(user=user, report_id=report_id, contract_id=contract_id)
    except AgentReportError as exc:
        raise _http_error(exc) from exc
    return envelope(data)


@router.post("/reports/{report_id}/verify-contracts")
def verify_report_contracts(
    report_id: uuid.UUID,
    body: VerifyFrozenContractsRequest = Body(default_factory=VerifyFrozenContractsRequest),
    user: Any = Depends(require_agent_user),
    service: AgentReportApplication = Depends(get_report_application),
) -> dict[str, Any]:
    try:
        data = service.verify_contracts(user=user, report_id=report_id)
    except AgentReportError as exc:
        raise _http_error(exc) from exc
    return envelope(FrozenContractVerificationResponse.model_validate(data).model_dump(mode="json"))


@router.post("/report-comparisons", status_code=status.HTTP_201_CREATED)
def create_report_comparison(
    body: CreateReportComparison,
    user: Any = Depends(require_agent_user),
    service: AgentReportApplication = Depends(get_report_application),
) -> dict[str, Any]:
    try:
        comparison = service.create_comparison(user=user, body=body)
    except AgentReportError as exc:
        raise _http_error(exc) from exc
    return envelope(comparison.model_dump(mode="json"), {"request_id": body.request_id})


@router.get("/report-comparisons/{comparison_id}")
def get_report_comparison(
    comparison_id: uuid.UUID,
    user: Any = Depends(require_agent_user),
    service: AgentReportApplication = Depends(get_report_application),
) -> dict[str, Any]:
    try:
        comparison = service.get_comparison(user=user, comparison_id=comparison_id)
    except AgentReportError as exc:
        raise _http_error(exc) from exc
    return envelope(comparison.model_dump(mode="json"))


@router.post("/reports/{report_id}/archive")
def archive_report(
    report_id: uuid.UUID,
    user: Any = Depends(require_agent_user),
    service: AgentReportApplication = Depends(get_report_application),
) -> dict[str, Any]:
    try:
        report = service.archive_report(user=user, report_id=report_id)
    except AgentReportError as exc:
        raise _http_error(exc) from exc
    return envelope(report.model_dump(mode="json"))


@router.get("/report-comparisons/{comparison_id}/export")
def export_report_comparison(
    comparison_id: uuid.UUID,
    format: Literal["markdown", "html"] = Query(default="markdown"),
    user: Any = Depends(require_agent_user),
    service: AgentReportApplication = Depends(get_report_application),
) -> Response:
    try:
        content, media_type, filename = service.export_comparison(
            user=user, comparison_id=comparison_id, export_format=format
        )
    except AgentReportError as exc:
        raise _http_error(exc) from exc
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'none'",
            "Cache-Control": "private, no-store",
        },
    )


def _http_error(exc: AgentReportError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )
