import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.v1.common import clamp_limit, clamp_offset, envelope, iso
from app.core.db import get_db
from app.domain.portfolio import PortfolioTarget, SignalCandidate
from app.models.portfolio import PortfolioBacktestRun
from app.services.portfolio.application import PortfolioApplicationService

router = APIRouter()


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TargetPreviewRequest(StrictRequest):
    trade_date: date


class BacktestDefinitionRequest(StrictRequest):
    name: str | None = Field(default=None, max_length=128)
    start_date: date
    end_date: date
    initial_cash_cny: Decimal | None = Field(default=None, gt=0)
    benchmark_code: str | None = Field(default=None, min_length=1, max_length=16)


@router.get("/config")
def config_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    service = PortfolioApplicationService(db)
    return envelope(service.get_config_status(), service.identity_meta())


@router.get("/candidates")
def candidates(
    trade_date: date,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    service = PortfolioApplicationService(db)
    batch = service.list_candidates(trade_date)
    return envelope(
        [_candidate_payload(item) for item in batch.candidates],
        {
            **service.identity_meta(),
            "trade_date": trade_date.isoformat(),
            "source_available": batch.source_available,
            "count": len(batch.candidates),
        },
    )


@router.post("/targets/preview")
def preview_target(
    request: TargetPreviewRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    service = PortfolioApplicationService(db)
    target = service.preview_target(request.trade_date)
    return envelope(_target_payload(target), service.identity_meta())


@router.post("/backtests", status_code=status.HTTP_201_CREATED)
def create_backtest(
    request: BacktestDefinitionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    service = PortfolioApplicationService(db)
    try:
        run = service.create_backtest_definition(
            name=request.name,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_cash=request.initial_cash_cny,
            benchmark_code=request.benchmark_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return envelope(_run_payload(run), service.identity_meta())


@router.get("/backtests")
def list_backtests(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    service = PortfolioApplicationService(db)
    row_limit, row_offset = clamp_limit(limit), clamp_offset(offset)
    rows = service.list_backtests(limit=row_limit, offset=row_offset)
    return envelope(
        [_run_payload(row) for row in rows],
        {**service.identity_meta(), "limit": row_limit, "offset": row_offset},
    )


@router.get("/backtests/{run_id}")
def get_backtest(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    service = PortfolioApplicationService(db)
    run = service.get_backtest(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="portfolio backtest run not found")
    return envelope(_run_payload(run), service.identity_meta())


def _candidate_payload(candidate: SignalCandidate) -> dict[str, Any]:
    return {
        "trade_date": candidate.trade_date.isoformat(),
        "ts_code": candidate.ts_code,
        "stage": candidate.stage,
        "state": candidate.state,
        "score": str(candidate.score),
        "rank_score": str(candidate.rank_score),
        "extension_risk": candidate.extension_risk,
        "industry_sector_id": candidate.industry_sector_id,
        "primary_theme_code": candidate.primary_theme_code,
        "source_identity": {
            "algo_version": candidate.source_identity.algo_version,
            "opportunity_calc_version": (
                candidate.source_identity.opportunity_calc_version
            ),
            "opportunity_config_hash": candidate.source_identity.opportunity_config_hash,
            "source_strategy_config_hash": (
                candidate.source_identity.source_strategy_config_hash
            ),
        },
        "reason_codes": list(candidate.reason_codes),
    }


def _target_payload(target: PortfolioTarget) -> dict[str, Any]:
    return {
        "signal_trade_date": target.signal_trade_date.isoformat(),
        "source_available": target.source_available,
        "target_cash_ratio": str(target.target_cash_ratio),
        "targets": [
            {
                "ts_code": item.ts_code,
                "target_weight": str(item.target_weight),
                "source_score": str(item.source_score),
                "reason_codes": list(item.reason_codes),
            }
            for item in target.targets
        ],
    }


def _run_payload(run: PortfolioBacktestRun) -> dict[str, Any]:
    return {
        column.name: (
            str(value)
            if isinstance(value := getattr(run, column.name), (Decimal, uuid.UUID))
            else iso(value)
        )
        for column in PortfolioBacktestRun.__table__.columns
    }
