import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.orm import Session

from app.api.v1.common import envelope
from app.core.db import get_db
from app.services.experiment import (
    ExperimentApplicationError,
    ExperimentApplicationService,
)

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


class ExperimentGrid(StrictRequest):
    candidate: CandidateGrid = Field(default_factory=CandidateGrid)
    construction: ConstructionGrid = Field(default_factory=ConstructionGrid)


class ExperimentDefinitionRequest(StrictRequest):
    name: str | None = Field(default=None, max_length=128)
    start_date: date
    end_date: date
    initial_cash_cny: Decimal | None = Field(default=None, gt=0)
    benchmark_code: str | None = Field(default=None, min_length=1, max_length=16)
    grid: ExperimentGrid = Field(default_factory=ExperimentGrid)


TrialState = Literal["PLANNED", "CREATED", "RUNNING", "SUCCESS", "FAILED", "CANCELLED"]


@router.post("/experiments", status_code=status.HTTP_201_CREATED)
def create_experiment(
    request: ExperimentDefinitionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    service = ExperimentApplicationService(db)
    try:
        result = service.create(
            name=request.name,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_cash=request.initial_cash_cny,
            benchmark_code=request.benchmark_code,
            grid=_grid_mapping(request.grid),
        )
    except ExperimentApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(result)


@router.post("/experiments/{experiment_id}/start", status_code=status.HTTP_202_ACCEPTED)
def start_experiment(
    experiment_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = ExperimentApplicationService(db).start(experiment_id)
    except ExperimentApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(result, {"accepted": True})


@router.get("/experiments/{experiment_id}")
def get_experiment(
    experiment_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = ExperimentApplicationService(db).get(experiment_id)
    except ExperimentApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(result)


@router.get("/experiments/{experiment_id}/trials")
def list_experiment_trials(
    experiment_id: uuid.UUID,
    state: TrialState | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        rows, total = ExperimentApplicationService(db).trials(
            experiment_id,
            state=state,
            limit=limit,
            offset=offset,
        )
    except ExperimentApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(
        rows,
        {"state": state, "limit": limit, "offset": offset, "total": total},
    )


@router.get("/experiments/{experiment_id}/trials/{trial_id}")
def get_experiment_trial(
    experiment_id: uuid.UUID,
    trial_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = ExperimentApplicationService(db).trial(experiment_id, trial_id)
    except ExperimentApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(result)


@router.post("/experiments/{experiment_id}/cancel")
def cancel_experiment(
    experiment_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = ExperimentApplicationService(db).cancel(experiment_id)
    except ExperimentApplicationError as exc:
        raise _http_error(exc) from exc
    return envelope(result)


def _grid_mapping(grid: ExperimentGrid) -> dict[str, list[Any]]:
    values: dict[str, list[Any]] = {}
    for section_name in ("candidate", "construction"):
        section = getattr(grid, section_name)
        for name, value in section.model_dump(exclude_none=True).items():
            values[f"{section_name}.{name}"] = value
    return values


def _http_error(exc: ExperimentApplicationError) -> HTTPException:
    if exc.code == "EXPERIMENT_NOT_FOUND":
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code in {
        "EXPERIMENT_CONFIG_INVALID",
        "EXPERIMENT_GRID_INVALID",
        "EXPERIMENT_TRIAL_LIMIT_EXCEEDED",
    }:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        status_code = status.HTTP_409_CONFLICT
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": str(exc)},
    )
