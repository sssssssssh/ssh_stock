import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.v1.common import clamp_limit, clamp_offset, envelope, iso
from app.core.db import get_db
from app.core.performance_risk_config import RISK_VERSION
from app.services.performance.application import (
    PerformanceApplicationService,
    PerformanceConflictError,
    PerformanceRunNotSuccessError,
)
from app.services.performance.risk_application import (
    PerformanceRiskApplicationService,
    PerformanceRiskConflictError,
)
from app.services.performance.risk_source import PerformanceRiskSourceError

router = APIRouter()


class PerformanceRiskCalculateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    performance_id: uuid.UUID | None = None


@router.post(
    "/backtests/{run_id}/performance/calculate",
    status_code=status.HTTP_202_ACCEPTED,
)
def calculate_performance(
    run_id: uuid.UUID, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        job = PerformanceApplicationService(db).queue_calculation(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PerformanceRunNotSuccessError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except PerformanceConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PERFORMANCE_CALCULATION_CONFLICT",
                "message": str(exc),
                "job_id": str(exc.job_id) if exc.job_id else None,
            },
        ) from exc
    return envelope(
        {
            "run_id": str(run_id),
            "job_id": str(job.id),
            "job_status": job.status,
        },
        {"accepted": True},
    )


@router.get("/backtests/{run_id}/performance")
def performance_report(
    run_id: uuid.UUID, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        report = PerformanceApplicationService(db).get_report(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope(_orm_payload(report))


@router.get("/backtests/{run_id}/performance/daily")
def performance_daily(
    run_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row_limit, row_offset = clamp_limit(limit, maximum=500), clamp_offset(offset)
    try:
        report, rows, total = PerformanceApplicationService(db).daily_page(
            run_id, limit=row_limit, offset=row_offset
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope(
        [_orm_payload(row) for row in rows],
        {
            "performance_id": str(report.id),
            "source_hash": report.source_hash,
            "limit": row_limit,
            "offset": row_offset,
            "total": total,
        },
    )


@router.post(
    "/backtests/{run_id}/performance/risk/calculate",
    status_code=status.HTTP_202_ACCEPTED,
)
def calculate_performance_risk(
    run_id: uuid.UUID,
    request: PerformanceRiskCalculateRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    service = PerformanceRiskApplicationService(db)
    try:
        requested_performance_id = request.performance_id if request else None
        job = service.queue_calculation(run_id, requested_performance_id)
        selected_performance_id = uuid.UUID(job.job_metadata["performance_id"])
    except PerformanceRiskSourceError as exc:
        http_status = 404 if exc.code == "PERFORMANCE_BASE_NOT_FOUND" else 409
        raise HTTPException(
            status_code=http_status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except PerformanceRiskConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": exc.code,
                "message": str(exc),
                "job_id": str(exc.job_id) if exc.job_id else None,
            },
        ) from exc
    return envelope(
        {
            "run_id": str(run_id),
            "performance_id": str(selected_performance_id),
            "job_id": str(job.id),
            "job_status": job.status,
            "risk_version": RISK_VERSION,
        },
        {"accepted": True},
    )


@router.get("/backtests/{run_id}/performance/risk")
def performance_risk_report(
    run_id: uuid.UUID,
    performance_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        report = PerformanceRiskApplicationService(db).get_report(
            run_id, performance_id
        )
    except PerformanceRiskSourceError as exc:
        http_status = 404 if exc.code == "PERFORMANCE_BASE_NOT_FOUND" else 409
        raise HTTPException(
            status_code=http_status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope(_orm_payload(report))


@router.get("/backtests/{run_id}/performance/risk/daily")
def performance_risk_daily(
    run_id: uuid.UUID,
    performance_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row_limit, row_offset = clamp_limit(limit, maximum=500), clamp_offset(offset)
    try:
        report, rows, total = PerformanceRiskApplicationService(db).daily_page(
            run_id,
            performance_id=performance_id,
            limit=row_limit,
            offset=row_offset,
        )
    except PerformanceRiskSourceError as exc:
        http_status = 404 if exc.code == "PERFORMANCE_BASE_NOT_FOUND" else 409
        raise HTTPException(
            status_code=http_status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope(
        [_orm_payload(row) for row in rows],
        {
            "risk_id": str(report.id),
            "performance_id": str(report.performance_id),
            "risk_version": report.risk_version,
            "benchmark_code": report.benchmark_code,
            "benchmark_source_hash": report.benchmark_source_hash,
            "risk_source_hash": report.risk_source_hash,
            "limit": row_limit,
            "offset": row_offset,
            "total": total,
        },
    )


def _orm_payload(row: Any) -> dict[str, Any]:
    return {
        column.name: (
            str(value)
            if isinstance(value := getattr(row, column.name), (Decimal, uuid.UUID))
            else iso(value)
        )
        for column in row.__table__.columns
    }
