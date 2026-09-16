from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.common import envelope, iso
from app.core.config import get_settings
from app.core.db import get_db
from app.models.market_data import SignalForwardEval, StrategySignal
from app.services.analysis_identity import SIGNAL_CALC_VERSION
from app.services.calc_metadata import config_hash

router = APIRouter()


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
            "executable_count": sum(
                row.get("entry_executable") is True for row in bucket_rows
            ),
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
