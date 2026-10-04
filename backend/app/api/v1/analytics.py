import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.v1.common import clamp_limit, clamp_offset, envelope, iso
from app.core.db import get_db
from app.core.performance_period_config import PERIOD_VERSION
from app.services.performance.analytics_bundle import AnalyticsBundleError
from app.services.performance.analytics_compare import (
    AnalyticsCompareApplicationService,
    AnalyticsCompareError,
    AnalyticsCompareSelection,
)
from app.services.performance.analytics_read import AnalyticsReadApplicationService
from app.services.performance.analytics_series import (
    AnalyticsSeriesError,
    AnalyticsSeriesReadApplicationService,
)
from app.services.performance.period_application import (
    PerformancePeriodApplicationService,
    PerformancePeriodConflictError,
)
from app.services.performance.period_source import PerformancePeriodSourceError

router = APIRouter()


class PeriodCalculateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    performance_id: uuid.UUID | None = None
    risk_id: uuid.UUID | None = None
    trade_id: uuid.UUID | None = None


class CompareItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: uuid.UUID
    performance_id: uuid.UUID | None = None
    risk_id: uuid.UUID | None = None
    trade_id: uuid.UUID | None = None


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CompareItemRequest]


def _error(exc: Exception, *, not_found: bool = False) -> HTTPException:
    code = str(getattr(exc, "code", "ANALYTICS_ERROR"))
    detail: dict[str, Any] = {"code": code, "message": str(exc)}
    mismatch_fields = getattr(exc, "mismatch_fields", None)
    if mismatch_fields:
        detail["mismatch_fields"] = mismatch_fields
    return HTTPException(status_code=404 if not_found else 409, detail=detail)


@router.post(
    "/backtests/{run_id}/performance/period/calculate",
    status_code=status.HTTP_202_ACCEPTED,
)
def calculate_period(
    run_id: uuid.UUID,
    request: PeriodCalculateRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    requested = request or PeriodCalculateRequest()
    try:
        job, bundle = PerformancePeriodApplicationService(db).queue_calculation(
            run_id,
            performance_id=requested.performance_id,
            risk_id=requested.risk_id,
            trade_id=requested.trade_id,
        )
    except AnalyticsBundleError as exc:
        raise _error(exc, not_found=exc.code == "ANALYTICS_BASE_NOT_FOUND") from exc
    except PerformancePeriodConflictError as exc:
        error = _error(exc)
        error.detail["job_id"] = str(exc.job_id) if exc.job_id else None
        raise error from exc
    return envelope(
        {
            "run_id": str(run_id),
            "performance_id": str(bundle.performance.id),
            "risk_id": str(bundle.risk.id),
            "trade_id": str(bundle.trade.id),
            "job_id": str(job.id),
            "job_status": job.status,
            "period_version": PERIOD_VERSION,
        },
        {"accepted": True},
    )


@router.get("/backtests/{run_id}/performance/period")
def period_rows(
    run_id: uuid.UUID,
    performance_id: uuid.UUID | None = Query(default=None),
    risk_id: uuid.UUID | None = Query(default=None),
    trade_id: uuid.UUID | None = Query(default=None),
    period_id: uuid.UUID | None = Query(default=None),
    period_type: str | None = Query(default=None, pattern="^(MONTH|YEAR)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row_limit, row_offset = clamp_limit(limit, maximum=500), clamp_offset(offset)
    try:
        report, rows, total = PerformancePeriodApplicationService(db).page(
            run_id,
            performance_id=performance_id,
            risk_id=risk_id,
            trade_id=trade_id,
            period_id=period_id,
            period_type=period_type,
            limit=row_limit,
            offset=row_offset,
        )
    except (AnalyticsBundleError, PerformancePeriodSourceError) as exc:
        raise _error(exc, not_found=getattr(exc, "code", "") == "ANALYTICS_BASE_NOT_FOUND") from exc
    return envelope(
        [_row_payload(row) for row in rows],
        {
            "period_id": str(report.id),
            "performance_id": str(report.performance_id),
            "risk_id": str(report.risk_id),
            "trade_id": str(report.trade_id),
            "period_version": report.period_version,
            "period_source_hash": report.period_source_hash,
            "period_type": period_type,
            "limit": row_limit,
            "offset": row_offset,
            "total": total,
        },
    )


@router.get("/backtests/{run_id}/analytics/series")
def analytics_series(
    run_id: uuid.UUID,
    performance_id: uuid.UUID = Query(...),
    risk_id: uuid.UUID = Query(...),
    trade_id: uuid.UUID | None = Query(default=None),
    period_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row_limit, row_offset = clamp_limit(limit, maximum=500), clamp_offset(offset)
    try:
        page = AnalyticsSeriesReadApplicationService(db).page(
            run_id,
            performance_id=performance_id,
            risk_id=risk_id,
            trade_id=trade_id,
            period_id=period_id,
            limit=row_limit,
            offset=row_offset,
        )
    except AnalyticsBundleError as exc:
        raise _error(exc, not_found=exc.code == "ANALYTICS_BASE_NOT_FOUND") from exc
    except AnalyticsSeriesError as exc:
        raise _error(exc) from exc
    return envelope(
        [row.model_dump(mode="json") for row in page.rows],
        page.meta.model_dump(mode="json"),
    )


@router.get("/backtests/{run_id}/analytics/summary")
def analytics_summary(
    run_id: uuid.UUID,
    performance_id: uuid.UUID | None = Query(default=None),
    risk_id: uuid.UUID | None = Query(default=None),
    trade_id: uuid.UUID | None = Query(default=None),
    period_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = AnalyticsReadApplicationService(db).summary(
            run_id,
            performance_id=performance_id,
            risk_id=risk_id,
            trade_id=trade_id,
            period_id=period_id,
        )
    except AnalyticsBundleError as exc:
        raise _error(exc, not_found=exc.code == "ANALYTICS_BASE_NOT_FOUND") from exc
    return envelope(result.model_dump(mode="json"))


@router.get("/backtests/{run_id}/analytics/artifacts")
def analytics_artifacts(
    run_id: uuid.UUID, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        result = AnalyticsReadApplicationService(db).history(run_id)
    except AnalyticsBundleError as exc:
        raise _error(exc, not_found=exc.code == "ANALYTICS_BASE_NOT_FOUND") from exc
    return envelope(result)


@router.get("/backtests/{run_id}/analytics/context")
def analytics_context(
    run_id: uuid.UUID,
    performance_id: uuid.UUID | None = Query(default=None),
    risk_id: uuid.UUID | None = Query(default=None),
    trade_id: uuid.UUID | None = Query(default=None),
    period_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = AnalyticsReadApplicationService(db).context(
            run_id,
            performance_id=performance_id,
            risk_id=risk_id,
            trade_id=trade_id,
            period_id=period_id,
        )
    except AnalyticsBundleError as exc:
        raise _error(exc, not_found=exc.code == "ANALYTICS_BASE_NOT_FOUND") from exc
    return envelope(result.model_dump(mode="json"))


@router.post("/analytics/compare")
def analytics_compare(
    request: CompareRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    selections = [AnalyticsCompareSelection(**item.model_dump()) for item in request.items]
    try:
        result = AnalyticsCompareApplicationService(db).compare(selections)
    except (AnalyticsBundleError, AnalyticsCompareError) as exc:
        raise _error(exc, not_found=getattr(exc, "code", "") == "ANALYTICS_BASE_NOT_FOUND") from exc
    return envelope(result)


def _row_payload(row: Any) -> dict[str, Any]:
    return {
        column.name: (
            str(value)
            if isinstance(value := getattr(row, column.name), (Decimal, uuid.UUID))
            else iso(value)
        )
        for column in row.__table__.columns
    }
