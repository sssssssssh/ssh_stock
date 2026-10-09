import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.orm import Session

from app.api.v1.common import envelope
from app.core.db import get_db
from app.core.experiment_evaluation_config import EvaluationPolicyConfig
from app.services.walk_forward import (
    WalkForwardApplicationError,
    WalkForwardApplicationService,
    WalkForwardConflictError,
)
from app.services.walk_forward.orchestration import WindowState

router = APIRouter()


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


FiniteDecimal = Annotated[Decimal, Field(allow_inf_nan=False)]


class CandidateGrid(StrictRequest):
    min_score: list[FiniteDecimal] | None = None
    top_n: list[StrictInt] | None = None


class ConstructionGrid(StrictRequest):
    max_positions: list[StrictInt] | None = None
    max_single_position_weight: list[FiniteDecimal] | None = None
    min_cash_ratio: list[FiniteDecimal] | None = None
    max_new_positions_per_day: list[StrictInt] | None = None


class WalkForwardGrid(StrictRequest):
    candidate: CandidateGrid = Field(default_factory=CandidateGrid)
    construction: ConstructionGrid = Field(default_factory=ConstructionGrid)


class WalkForwardDefinitionRequest(StrictRequest):
    name: str | None = Field(default=None, max_length=128)
    start_date: date
    end_date: date
    mode: Literal["ROLLING", "EXPANDING"]
    train_trade_days: StrictInt = Field(gt=0)
    test_trade_days: StrictInt = Field(gt=0)
    step_trade_days: StrictInt = Field(gt=0)
    initial_cash_cny: FiniteDecimal | None = Field(default=None, gt=0)
    benchmark_code: str | None = Field(default=None, min_length=1, max_length=16)
    grid: WalkForwardGrid = Field(default_factory=WalkForwardGrid)
    train_evaluation_policy: EvaluationPolicyConfig | None = None


@router.post("/walk-forwards", status_code=status.HTTP_201_CREATED)
def create_walk_forward(
    request: WalkForwardDefinitionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = WalkForwardApplicationService(db).create(
            name=request.name,
            start_date=request.start_date,
            end_date=request.end_date,
            mode=request.mode,
            train_trade_days=request.train_trade_days,
            test_trade_days=request.test_trade_days,
            step_trade_days=request.step_trade_days,
            initial_cash=request.initial_cash_cny,
            benchmark_code=request.benchmark_code,
            grid=_grid_mapping(request.grid),
            train_evaluation_policy=request.train_evaluation_policy,
        )
    except WalkForwardApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(result)


@router.get("/walk-forwards/{study_id}")
def get_walk_forward(
    study_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = WalkForwardApplicationService(db).get(study_id)
    except WalkForwardApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(result)


@router.get("/walk-forwards/{study_id}/windows")
def list_walk_forward_windows(
    study_id: uuid.UUID,
    window_state: WindowState | None = Query(default=None, alias="state"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        rows, total = WalkForwardApplicationService(db).windows(
            study_id,
            state=window_state,
            limit=limit,
            offset=offset,
        )
    except WalkForwardApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(
        rows,
        {"state": window_state, "limit": limit, "offset": offset, "total": total},
    )


@router.post("/walk-forwards/{study_id}/advance")
def advance_walk_forward(
    study_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = WalkForwardApplicationService(db).advance(study_id)
    except WalkForwardApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(result)


@router.post("/walk-forwards/{study_id}/cancel")
def cancel_walk_forward(
    study_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = WalkForwardApplicationService(db).cancel(study_id)
    except WalkForwardApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(result)


@router.get("/walk-forwards/{study_id}/validation/readiness")
def walk_forward_validation_readiness(
    study_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = WalkForwardApplicationService(db).validation_readiness(study_id)
    except WalkForwardApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(result)


@router.post(
    "/walk-forwards/{study_id}/validation/calculate",
    status_code=status.HTTP_202_ACCEPTED,
)
def calculate_walk_forward_validation(
    study_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        job = WalkForwardApplicationService(db).queue_validation(study_id)
    except WalkForwardApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(
        {
            "study_id": str(study_id),
            "job_id": str(job.id),
            "job_status": job.status,
            "walk_forward_version": job.job_metadata["walk_forward_version"],
            "source_hash": job.job_metadata["source_hash"],
        },
        {"accepted": True},
    )


@router.get("/walk-forwards/{study_id}/validations/{validation_id}")
def get_walk_forward_validation(
    study_id: uuid.UUID,
    validation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = WalkForwardApplicationService(db).validation_detail(
            study_id, validation_id
        )
    except WalkForwardApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(result)


@router.get("/walk-forwards/{study_id}/validations")
def list_walk_forward_validations(
    study_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        rows, total = WalkForwardApplicationService(db).validation_history(
            study_id, limit=limit, offset=offset
        )
    except WalkForwardApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(rows, {"limit": limit, "offset": offset, "total": total})


@router.get("/walk-forwards/{study_id}/validations/{validation_id}/windows")
def list_walk_forward_validation_windows(
    study_id: uuid.UUID,
    validation_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        rows, total = WalkForwardApplicationService(db).validation_windows(
            study_id, validation_id, limit=limit, offset=offset
        )
    except WalkForwardApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(rows, {"limit": limit, "offset": offset, "total": total})


@router.get("/walk-forwards/{study_id}/validations/{validation_id}/stability")
def get_walk_forward_validation_stability(
    study_id: uuid.UUID,
    validation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        rows = WalkForwardApplicationService(db).validation_stability(
            study_id, validation_id
        )
    except WalkForwardApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(
        rows,
        {"study_id": str(study_id), "validation_id": str(validation_id)},
    )


def _grid_mapping(grid: WalkForwardGrid) -> dict[str, list[Any]]:
    values: dict[str, list[Any]] = {}
    for section_name in ("candidate", "construction"):
        section = getattr(grid, section_name)
        for name, value in section.model_dump(exclude_none=True).items():
            values[f"{section_name}.{name}"] = value
    return values


def _http_error(exc: WalkForwardApplicationError) -> HTTPException:
    if exc.code.endswith("_NOT_FOUND"):
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code in {
        "WALK_FORWARD_CONFIG_INVALID",
        "WALK_FORWARD_CALENDAR_INCOMPLETE",
        "WALK_FORWARD_INSUFFICIENT_WINDOWS",
        "WALK_FORWARD_WINDOW_LIMIT_EXCEEDED",
    }:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        status_code = status.HTTP_409_CONFLICT
    detail = {"code": exc.code, "message": str(exc)}
    detail.update(exc.details)
    if isinstance(exc, WalkForwardConflictError) and exc.job_id:
        detail["job_id"] = str(exc.job_id)
    return HTTPException(status_code=status_code, detail=detail)
