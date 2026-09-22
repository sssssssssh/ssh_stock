from collections import defaultdict
from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.market_data import ThemeDaily, ThemeFactorDaily, ThemeForwardEval
from app.repositories.upsert import upsert_rows
from app.services.analysis_identity import (
    RESEARCH_EVAL_VERSION,
    RESEARCH_VERSION,
    THEME_CALC_VERSION,
)
from app.services.calc_metadata import config_hash
from app.services.research.forward_eval import evaluate_theme_forward
from app.services.research.opportunity_eval import benchmark_lookup, future_dates

SNAPSHOT_COLUMNS = (
    "heat_score",
    "heat_rank",
    "heat_momentum1",
    "heat_momentum3",
    "rank_change",
    "lifecycle",
    "return1",
    "return5",
    "return20",
    "moneyflow_score",
    "net_amount",
    "net_amount_3d",
    "limit_strength_score",
    "limit_up_count",
    "continuous_limit_count",
    "breadth20",
    "breadth60",
    "rps60_median",
    "source_coverage",
    "data_coverage",
)
THEME_KEY = (
    "trade_date",
    "theme_code",
    "opportunity_config_hash",
    "research_version",
    "research_config_hash",
    "eval_version",
    "entry_basis",
)


def evaluate_theme_batch(
    db: Session,
    base_dates: list[date],
    settings: Any,
    *,
    progress: Callable[[int], None] | None = None,
) -> dict[str, int]:
    research = settings.research_config
    opportunity_hash = config_hash(settings.opportunity_config)
    research_hash = config_hash(research)
    bases = (
        db.execute(
            select(ThemeFactorDaily).where(
                ThemeFactorDaily.trade_date.in_(base_dates),
                ThemeFactorDaily.calc_version == THEME_CALC_VERSION,
                ThemeFactorDaily.config_hash == opportunity_hash,
                ThemeFactorDaily.heat_score.is_not(None),
                ThemeFactorDaily.data_coverage >= research["theme"]["min_data_coverage"],
            )
        )
        .scalars()
        .all()
    )
    if not bases:
        return {"base_rows": 0, "eval_rows": 0, "benchmark_missing": 0}
    latest = db.scalar(select(func.max(ThemeDaily.trade_date)))
    dates = future_dates(db, base_dates, latest)
    benchmark = benchmark_lookup(db, dates, research["benchmark_code"])
    by_code: dict[str, list[Any]] = defaultdict(list)
    for base in bases:
        by_code[base.theme_code].append(base)
    codes = sorted(by_code)
    counts = {"base_rows": len(bases), "eval_rows": 0, "benchmark_missing": 0}
    for offset in range(0, len(codes), 250):
        chunk = codes[offset : offset + 250]
        raw = (
            db.execute(
                select(
                    ThemeDaily.theme_code,
                    ThemeDaily.trade_date,
                    ThemeDaily.close,
                    ThemeDaily.high,
                    ThemeDaily.low,
                ).where(
                    ThemeDaily.theme_code.in_(chunk),
                    ThemeDaily.trade_date.between(dates[0], dates[-1]),
                )
            )
            .mappings()
            .all()
            if dates
            else []
        )
        lookup: dict[str, dict[date, dict[str, Any]]] = defaultdict(dict)
        for row in raw:
            lookup[row["theme_code"]][row["trade_date"]] = dict(row)
        payload = []
        for code in chunk:
            for base in by_code[code]:
                forward = evaluate_theme_forward(base.trade_date, dates, lookup[code], benchmark)
                counts["benchmark_missing"] += any(
                    forward[f"ret{h}"] is not None and forward[f"benchmark_ret{h}"] is None
                    for h in (5, 10, 20, 60)
                )
                payload.append(
                    {
                        "trade_date": base.trade_date,
                        "theme_code": code,
                        "theme_calc_version": base.calc_version,
                        "opportunity_config_hash": opportunity_hash,
                        "research_version": RESEARCH_VERSION,
                        "research_config_hash": research_hash,
                        "eval_version": RESEARCH_EVAL_VERSION,
                        "entry_basis": research["theme"]["entry_basis"],
                        "benchmark_code": research["benchmark_code"],
                        **{key: getattr(base, key) for key in SNAPSHOT_COLUMNS},
                        **forward,
                    }
                )
        counts["eval_rows"] += upsert_rows(db, ThemeForwardEval, payload, THEME_KEY)
        if progress:
            progress(counts["eval_rows"])
    return counts
