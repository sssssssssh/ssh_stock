from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.common import envelope, iso
from app.core.config import get_settings
from app.core.db import get_db
from app.jobs.research_job import queue_research_eval
from app.models.market_data import (
    OpportunityForwardEval,
    SignalForwardEval,
    StrategySignal,
    ThemeForwardEval,
)
from app.services.analysis_identity import SIGNAL_CALC_VERSION
from app.services.calc_metadata import config_hash
from app.services.research import analytics

router = APIRouter()


class ResearchEvalRequest(BaseModel):
    start: date
    end: date
    opportunity_only: bool = False
    theme_only: bool = False
    transition_only: bool = False


@router.post("/evaluate")
def enqueue_research_eval(
    payload: ResearchEvalRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        job = queue_research_eval(
            db,
            payload.start,
            payload.end,
            mode="api",
            opportunity_only=payload.opportunity_only,
            theme_only=payload.theme_only,
            transition_only=payload.transition_only,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return envelope({"id": str(job.id), "status": job.status}, {"accepted": True})


def _research_meta(start: date | None, end: date | None) -> dict[str, Any]:
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start must be <= end")
    settings = get_settings()
    return {
        "start": iso(start),
        "end": iso(end),
        "research_version": settings.research_config["version"],
        "research_config_hash": config_hash(settings.research_config),
    }


@router.get("/status")
def research_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    return envelope(analytics.research_status(db, get_settings()))


@router.get("/opportunities/stats")
def opportunity_research_stats(
    stage: str | None = None,
    start: date | None = None,
    end: date | None = None,
    market_regime: str | None = None,
    industry_lifecycle: str | None = None,
    theme_lifecycle: str | None = None,
    extension_risk: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    meta = _research_meta(start, end)
    stages = {
        "LEFT_WATCH",
        "LEFT_REVERSAL",
        "RIGHT_SIDE_NEW",
        "RIGHT_SIDE",
        "TREND",
        "STRONG_TREND",
    }
    if stage and stage not in stages:
        raise HTTPException(status_code=422, detail="unsupported stage")
    filters = {
        key: value
        for key, value in {
            "market_regime": market_regime,
            "industry_lifecycle": industry_lifecycle,
            "primary_theme_lifecycle": theme_lifecycle,
            "extension_risk": extension_risk,
        }.items()
        if value is not None
    }
    return envelope(
        analytics.opportunity_stats(db, get_settings(), start, end, stage=stage, filters=filters),
        {**meta, "stage": stage, **filters},
    )


@router.get("/opportunities/buckets")
def opportunity_research_buckets(
    field: str = "opportunity_score",
    research_type: str = "ALL",
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    meta = _research_meta(start, end)
    if field not in analytics.OPPORTUNITY_BUCKETS:
        raise HTTPException(status_code=422, detail="unsupported bucket field")
    if research_type not in analytics.RESEARCH_TYPES:
        raise HTTPException(status_code=422, detail="unsupported research_type")
    return envelope(
        analytics.bucket_stats(
            db, get_settings(), start, end, model=OpportunityForwardEval, field=field,
            research_type=research_type,
        ),
        {**meta, "field": field, "research_type": research_type},
    )


@router.get("/left/thresholds")
def left_thresholds(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return envelope(
        analytics.transition_stats(db, get_settings(), start, end, left=True),
        _research_meta(start, end),
    )


@router.get("/right/transitions")
def right_transitions(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return envelope(
        analytics.transition_stats(db, get_settings(), start, end, left=False),
        _research_meta(start, end),
    )


@router.get("/trends/topn")
def trend_topn(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return envelope(
        analytics.topn_stats(db, get_settings(), start, end, theme=False),
        _research_meta(start, end),
    )


@router.get("/positions/stats")
def position_stats(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return envelope(
        analytics.position_stats(db, get_settings(), start, end), _research_meta(start, end)
    )


@router.get("/themes/stats")
def theme_research_stats(
    start: date | None = None,
    end: date | None = None,
    lifecycle: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return envelope(
        analytics.theme_stats(db, get_settings(), start, end, lifecycle),
        {**_research_meta(start, end), "lifecycle": lifecycle},
    )


@router.get("/themes/buckets")
def theme_research_buckets(
    field: str = "heat_score",
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    meta = _research_meta(start, end)
    if field not in analytics.THEME_BUCKETS:
        raise HTTPException(status_code=422, detail="unsupported bucket field")
    return envelope(
        analytics.bucket_stats(db, get_settings(), start, end, model=ThemeForwardEval, field=field),
        {**meta, "field": field},
    )


@router.get("/themes/topn")
def theme_topn(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return envelope(
        analytics.topn_stats(db, get_settings(), start, end, theme=True),
        _research_meta(start, end),
    )


@router.get("/themes/lifecycle")
def theme_lifecycle(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return envelope(
        analytics.theme_lifecycle_stats(db, get_settings(), start, end),
        _research_meta(start, end),
    )


@router.get("/context")
def research_context(
    group_by: str = "market_regime",
    research_type: str = "ALL",
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    meta = _research_meta(start, end)
    if group_by not in {
        "market_regime",
        "industry_lifecycle",
        "primary_theme_lifecycle",
        "extension_risk",
    }:
        raise HTTPException(status_code=422, detail="unsupported group_by")
    if research_type not in analytics.RESEARCH_TYPES:
        raise HTTPException(status_code=422, detail="unsupported research_type")
    return envelope(
        analytics.context_stats(db, get_settings(), start, end, group_by, research_type),
        {**meta, "group_by": group_by, "research_type": research_type},
    )


@router.get("/signals/stats")
def signal_stats(
    signal_type: str = "RIGHT_SIDE_NEW",
    algo_version: str | None = None,
    start: date | None = None,
    end: date | None = None,
    eval_version: str = "eval_v3",
    entry_basis: str = "NEXT_OPEN",
    executable_only: bool = False,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    version = algo_version or get_settings().algo_version
    rows = _read_eval_rows(
        db,
        signal_type,
        version,
        start,
        end,
        eval_version=eval_version,
        entry_basis=entry_basis,
        executable_only=executable_only,
    )
    executable_count = sum(row.get("entry_executable") is True for row in rows)
    data = {
        "signal_type": signal_type,
        "algo_version": version,
        "eval_version": eval_version,
        "entry_basis": entry_basis,
        "count": len(rows),
        "executable_count": executable_count,
        "non_executable_count": len(rows) - executable_count,
        "avg_ret5": _avg(rows, "ret5"),
        "avg_ret10": _avg(rows, "ret10"),
        "avg_ret20": _avg(rows, "ret20"),
        "avg_ret60": _avg(rows, "ret60"),
        "win_rate5": _win_rate(rows, "ret5"),
        "win_rate10": _win_rate(rows, "ret10"),
        "win_rate20": _win_rate(rows, "ret20"),
        "win_rate60": _win_rate(rows, "ret60"),
        "avg_mfe20": _avg(rows, "mfe20"),
        "avg_mae20": _avg(rows, "mae20"),
        "median_ret20": _quantile(rows, "ret20", 0.5),
        "p25_ret20": _quantile(rows, "ret20", 0.25),
        "p75_ret20": _quantile(rows, "ret20", 0.75),
        "latest_evaluated_until_date": _max_date(rows, "evaluated_until_date"),
    }
    return envelope(
        data,
        {
            "start": iso(start),
            "end": iso(end),
            "executable_only": executable_only,
        },
    )


@router.get("/signals/buckets")
def signal_buckets(
    signal_type: str = "RIGHT_SIDE_NEW",
    algo_version: str | None = None,
    bucket_field: str = "opportunity_score",
    bucket_size: int = 10,
    start: date | None = None,
    end: date | None = None,
    eval_version: str = "eval_v3",
    entry_basis: str = "NEXT_OPEN",
    executable_only: bool = False,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    version = algo_version or get_settings().algo_version
    if bucket_field not in {"score", "opportunity_score"}:
        bucket_field = "opportunity_score"
    size = max(1, min(bucket_size, 50))
    rows = _read_eval_rows(
        db,
        signal_type,
        version,
        start,
        end,
        eval_version=eval_version,
        entry_basis=entry_basis,
        executable_only=executable_only,
    )

    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        score = row.get(bucket_field)
        if score is None:
            label = "NA"
        else:
            lower = int(float(score) // size) * size
            upper = lower + size
            label = f"{lower}-{upper}"
        buckets.setdefault(label, []).append(row)

    sorted_buckets = sorted(
        buckets.items(),
        key=lambda item: _bucket_sort_key(item[0]),
    )
    data = [
        {
            "bucket": bucket,
            "count": len(bucket_rows),
            "executable_count": sum(row.get("entry_executable") is True for row in bucket_rows),
            "avg_ret5": _avg(bucket_rows, "ret5"),
            "avg_ret10": _avg(bucket_rows, "ret10"),
            "avg_ret20": _avg(bucket_rows, "ret20"),
            "avg_ret60": _avg(bucket_rows, "ret60"),
            "win_rate20": _win_rate(bucket_rows, "ret20"),
            "avg_mfe20": _avg(bucket_rows, "mfe20"),
            "avg_mae20": _avg(bucket_rows, "mae20"),
            "median_ret20": _quantile(bucket_rows, "ret20", 0.5),
            "p25_ret20": _quantile(bucket_rows, "ret20", 0.25),
            "p75_ret20": _quantile(bucket_rows, "ret20", 0.75),
        }
        for bucket, bucket_rows in sorted_buckets
    ]
    return envelope(
        data,
        {
            "signal_type": signal_type,
            "algo_version": version,
            "eval_version": eval_version,
            "entry_basis": entry_basis,
            "executable_only": executable_only,
            "bucket_field": bucket_field,
            "bucket_size": size,
            "start": iso(start),
            "end": iso(end),
        },
    )


def _read_eval_rows(
    db: Session,
    signal_type: str,
    algo_version: str,
    start: date | None,
    end: date | None,
    *,
    eval_version: str,
    entry_basis: str,
    executable_only: bool,
) -> list[dict[str, Any]]:
    hash_value = config_hash(get_settings().strategy)
    filters = [
        SignalForwardEval.signal_type == signal_type,
        SignalForwardEval.algo_version == algo_version,
        SignalForwardEval.eval_version == eval_version,
        SignalForwardEval.entry_basis == entry_basis,
        StrategySignal.calc_version == SIGNAL_CALC_VERSION,
        StrategySignal.config_hash == hash_value,
    ]
    if executable_only:
        filters.append(SignalForwardEval.entry_executable.is_(True))
    if start:
        filters.append(SignalForwardEval.trade_date >= start)
    if end:
        filters.append(SignalForwardEval.trade_date <= end)
    stmt = (
        select(
            SignalForwardEval.id,
            SignalForwardEval.signal_id,
            SignalForwardEval.trade_date,
            SignalForwardEval.ts_code,
            SignalForwardEval.signal_type,
            SignalForwardEval.algo_version,
            SignalForwardEval.eval_version,
            SignalForwardEval.entry_basis,
            SignalForwardEval.horizon_basis,
            SignalForwardEval.entry_trade_date,
            SignalForwardEval.entry_price,
            SignalForwardEval.entry_executable,
            SignalForwardEval.exit_executable,
            SignalForwardEval.non_executable_reason,
            SignalForwardEval.ret5,
            SignalForwardEval.ret10,
            SignalForwardEval.ret20,
            SignalForwardEval.ret60,
            SignalForwardEval.mfe20,
            SignalForwardEval.mae20,
            SignalForwardEval.evaluated_until_date,
            StrategySignal.score,
            StrategySignal.opportunity_score,
        )
        .join(StrategySignal, SignalForwardEval.signal_id == StrategySignal.id)
        .where(*filters)
        .order_by(SignalForwardEval.trade_date, SignalForwardEval.ts_code)
    )
    return [dict(row) for row in db.execute(stmt).mappings().all()]


def _avg(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [row[key] for row in rows if row.get(key) is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _win_rate(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [row[key] for row in rows if row.get(key) is not None]
    if not values:
        return None
    return sum(1 for value in values if value > 0) / len(values)


def _quantile(rows: list[dict[str, Any]], key: str, quantile: float) -> float | None:
    values = sorted(float(row[key]) for row in rows if row.get(key) is not None)
    if not values:
        return None
    position = (len(values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _max_date(rows: list[dict[str, Any]], key: str) -> str | None:
    values = [row[key] for row in rows if row.get(key) is not None]
    if not values:
        return None
    return max(values).isoformat()


def _bucket_sort_key(bucket: str) -> tuple[int, str]:
    if bucket == "NA":
        return (10_000, bucket)
    return (int(bucket.split("-", 1)[0]), bucket)
