import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.common import clamp_limit, clamp_offset, envelope, iso
from app.core.db import get_db
from app.services.performance.application import (
    PerformanceApplicationService,
    PerformanceConflictError,
)

router = APIRouter()


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


def _orm_payload(row: Any) -> dict[str, Any]:
    return {
        column.name: (
            str(value)
            if isinstance(value := getattr(row, column.name), (Decimal, uuid.UUID))
            else iso(value)
        )
        for column in row.__table__.columns
    }
