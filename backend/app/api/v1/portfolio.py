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
from app.services.portfolio.backtest_application import (
    BacktestApplicationService,
    BacktestConflictError,
    BacktestRecoveryRejectedError,
)
from app.services.portfolio.contracts import PortfolioSourceNotReadyError

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
            "source_ready": batch.source_ready,
            "source_status": batch.source_status.value,
            "source_reason": batch.source_reason,
            "expected_count": batch.expected_count,
            "stock_daily_count": batch.stock_daily_count,
            "factor_count": batch.factor_count,
            "state_count": batch.state_count,
            "opportunity_count": batch.opportunity_count,
            "mismatch_layers": list(batch.mismatch_layers),
            "missing_code_samples": _sample_payload(batch.missing_code_samples),
            "extra_code_samples": _sample_payload(batch.extra_code_samples),
            "count": len(batch.candidates),
        },
    )


@router.post("/targets/preview")
def preview_target(
    request: TargetPreviewRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    service = PortfolioApplicationService(db)
    try:
        target = service.preview_target(request.trade_date)
    except PortfolioSourceNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "PORTFOLIO_SOURCE_NOT_READY",
                "source_status": exc.batch.source_status.value,
                "source_reason": exc.batch.source_reason,
                "expected_count": exc.batch.expected_count,
                "stock_daily_count": exc.batch.stock_daily_count,
                "factor_count": exc.batch.factor_count,
                "state_count": exc.batch.state_count,
                "opportunity_count": exc.batch.opportunity_count,
                "mismatch_layers": list(exc.batch.mismatch_layers),
                "missing_code_samples": _sample_payload(
                    exc.batch.missing_code_samples
                ),
                "extra_code_samples": _sample_payload(exc.batch.extra_code_samples),
            },
        ) from exc
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


@router.post(
    "/backtests/{run_id}/execute", status_code=status.HTTP_202_ACCEPTED
)
def execute_backtest(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    service = BacktestApplicationService(db)
    try:
        run, job = service.execute(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BacktestConflictError as exc:
        raise _backtest_conflict(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "BACKTEST_CONTRACT_INCOMPATIBLE", "message": str(exc)},
        ) from exc
    return envelope(
        {
            "run_id": str(run.id),
            "run_status": run.status,
            "job_id": str(job.id),
            "job_status": job.status,
        },
        {"accepted": True},
    )


@router.post(
    "/backtests/{run_id}/resume", status_code=status.HTTP_202_ACCEPTED
)
def resume_backtest(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    service = BacktestApplicationService(db)
    try:
        run, job = service.resume(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BacktestConflictError as exc:
        raise _backtest_conflict(exc) from exc
    except BacktestRecoveryRejectedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "BACKTEST_RECOVERY_REJECTED", "message": str(exc)},
        ) from exc
    return envelope(
        {
            "run_id": str(run.id),
            "run_status": run.status,
            "job_id": str(job.id),
            "job_status": job.status,
        },
        {"accepted": True, "resume": True},
    )


@router.post("/backtests/{run_id}/cancel")
def cancel_backtest(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    service = BacktestApplicationService(db)
    try:
        run, job = service.cancel(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BacktestConflictError as exc:
        raise _backtest_conflict(exc) from exc
    return envelope(
        {
            "run_id": str(run.id),
            "run_status": run.status,
            "job_id": str(job.id) if job else None,
            "job_status": job.status if job else None,
            "cancel_requested": job.cancel_requested if job else False,
        }
    )


@router.get("/backtests/{run_id}/progress")
def backtest_progress(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        progress = BacktestApplicationService(db).progress(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope(
        {
            "run_id": str(progress.run.id),
            "run_status": progress.run.status,
            "job_id": str(progress.job.id) if progress.job else None,
            "job_status": progress.job.status if progress.job else None,
            "current_trade_date": (
                progress.current_trade_date.isoformat()
                if progress.current_trade_date
                else None
            ),
            "current_phase": progress.current_phase,
            "total_trade_days": progress.total_trade_days,
            "completed_trade_days": progress.completed_trade_days,
            "progress_pct": progress.progress_pct,
            "error_code": progress.error_code,
            "error_message": progress.error_message,
        }
    )


@router.get("/backtests/{run_id}/nav")
def backtest_nav(
    run_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    service = BacktestApplicationService(db)
    row_limit, row_offset = clamp_limit(limit, maximum=500), clamp_offset(offset)
    try:
        rows, total = service.nav_page(
            run_id, limit=row_limit, offset=row_offset
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope(
        [_orm_payload(row) for row in rows],
        {"limit": row_limit, "offset": row_offset, "total": total},
    )


@router.get("/backtests/{run_id}/positions")
def backtest_positions(
    run_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    service = BacktestApplicationService(db)
    row_limit, row_offset = clamp_limit(limit, maximum=500), clamp_offset(offset)
    try:
        rows, total = service.positions_page(
            run_id, limit=row_limit, offset=row_offset
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope(
        [_orm_payload(row) for row in rows],
        {"limit": row_limit, "offset": row_offset, "total": total},
    )


@router.get("/backtests/{run_id}/orders")
def backtest_orders(
    run_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    service = BacktestApplicationService(db)
    row_limit, row_offset = clamp_limit(limit, maximum=500), clamp_offset(offset)
    try:
        rows, total = service.orders_page(
            run_id, limit=row_limit, offset=row_offset
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    attempts = service.repository.list_order_attempts(run_id)
    fills = service.repository.list_fills(run_id)
    attempt_by_order: dict[uuid.UUID, list[dict[str, Any]]] = {}
    fill_by_order: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for item in attempts:
        attempt_by_order.setdefault(item.order_id, []).append(_orm_payload(item))
    for item in fills:
        fill_by_order.setdefault(item.order_id, []).append(_orm_payload(item))
    return envelope(
        [
            {
                **_orm_payload(row),
                "attempts": attempt_by_order.get(row.id, []),
                "fills": fill_by_order.get(row.id, []),
            }
            for row in rows
        ],
        {"limit": row_limit, "offset": row_offset, "total": total},
    )


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


def _sample_payload(samples: dict[str, tuple[str, ...]]) -> dict[str, list[str]]:
    return {layer: list(codes) for layer, codes in samples.items()}


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


def _orm_payload(row: Any) -> dict[str, Any]:
    return {
        column.name: (
            str(value)
            if isinstance(value := getattr(row, column.name), (Decimal, uuid.UUID))
            else iso(value)
        )
        for column in row.__table__.columns
    }


def _backtest_conflict(exc: BacktestConflictError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "BACKTEST_EXECUTION_CONFLICT",
            "message": str(exc),
            "job_id": str(exc.job_id) if exc.job_id else None,
        },
    )
