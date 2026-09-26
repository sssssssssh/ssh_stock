from collections import defaultdict
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.market_data import ThemeDaily, ThemeFactorDaily, ThemeForwardEval
from app.repositories.replace_slice import replace_slice_rows_with_stats
from app.services.analysis_filters import theme_factor_identity_filters
from app.services.analysis_identity import (
    RESEARCH_EVAL_VERSION,
    RESEARCH_VERSION,
    THEME_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.quality.opportunity_quality import check_opportunity_quality
from app.services.quality.theme_quality import theme_source_status
from app.services.research.forward_eval import evaluate_theme_forward
from app.services.research.opportunity_eval import benchmark_lookup, future_dates
from app.services.theme.membership import resolve_theme_memberships

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
    "strategy_config_hash",
    "theme_calc_version",
    "opportunity_config_hash",
    "research_version",
    "research_config_hash",
    "eval_version",
    "entry_basis",
)


def theme_research_ready_dates(
    db: Session, base_dates: list[date], settings: Any
) -> tuple[list[date], list[date]]:
    strategy_hash = analysis_strategy_hash(settings.strategy)
    opportunity_hash = config_hash(settings.opportunity_config)
    ready: list[date] = []
    skipped: list[date] = []
    for trade_date in base_dates:
        source_status = theme_source_status(db, trade_date, "ths_theme_daily")
        if source_status not in {"PASS", "WARNING"}:
            skipped.append(trade_date)
            continue
        quality = check_opportunity_quality(
            db,
            trade_date,
            strategy_hash=strategy_hash,
            opportunity_hash=opportunity_hash,
            algo_version=settings.algo_version,
            config=settings.opportunity_config,
        )
        if quality.results["theme_factor_vs_theme_daily"] in {"PASS", "WARNING"}:
            ready.append(trade_date)
        else:
            skipped.append(trade_date)
    return ready, skipped


def evaluate_theme_batch(
    db: Session,
    base_dates: list[date],
    settings: Any,
    *,
    progress: Callable[[int], None] | None = None,
) -> dict[str, int]:
    research = settings.research_config
    strategy_hash = analysis_strategy_hash(settings.strategy)
    opportunity_hash = config_hash(settings.opportunity_config)
    research_hash = config_hash(research)
    ready_dates, skipped_dates = theme_research_ready_dates(db, base_dates, settings)
    counts = {
        "base_rows": 0,
        "eval_rows": 0,
        "deleted_rows": 0,
        "benchmark_missing": 0,
        "theme_skipped_source_dates": len(skipped_dates),
    }
    if not ready_dates:
        return counts
    scope_filters = (
        ThemeForwardEval.trade_date.in_(ready_dates),
        ThemeForwardEval.strategy_config_hash == strategy_hash,
        ThemeForwardEval.theme_calc_version == THEME_CALC_VERSION,
        ThemeForwardEval.opportunity_config_hash == opportunity_hash,
        ThemeForwardEval.research_version == RESEARCH_VERSION,
        ThemeForwardEval.research_config_hash == research_hash,
        ThemeForwardEval.eval_version == RESEARCH_EVAL_VERSION,
        ThemeForwardEval.entry_basis == research["theme"]["entry_basis"],
    )
    bases = (
        db.execute(
            select(ThemeFactorDaily).where(
                ThemeFactorDaily.trade_date.in_(ready_dates),
                *theme_factor_identity_filters(
                    settings,
                    strategy_hash=strategy_hash,
                    opportunity_hash=opportunity_hash,
                ),
                ThemeFactorDaily.heat_score.is_not(None),
                ThemeFactorDaily.data_coverage >= research["theme"]["min_data_coverage"],
            )
        )
        .scalars()
        .all()
    )
    counts["base_rows"] = len(bases)
    if not bases:
        stats = replace_slice_rows_with_stats(
            db, ThemeForwardEval, (), scope_filters=scope_filters, key_columns=THEME_KEY
        )
        counts["deleted_rows"] = stats["deleted"]
        return counts
    latest = db.scalar(select(func.max(ThemeDaily.trade_date)))
    dates = future_dates(
        db,
        ready_dates,
        latest,
        max_horizon=max(research["horizons"]),
        executable_exit_search_days=research["executable_exit_search_days"],
    )
    benchmark = benchmark_lookup(db, dates, research["benchmark_code"])
    theme_context = resolve_theme_memberships(db, ready_dates).context_by_date
    by_code: dict[str, list[Any]] = defaultdict(list)
    for base in bases:
        by_code[base.theme_code].append(base)
    codes = sorted(by_code)

    def row_batches() -> Iterator[list[dict[str, Any]]]:
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
                    forward = evaluate_theme_forward(
                        base.trade_date,
                        dates,
                        lookup[code],
                        benchmark,
                        executable_exit_search_days=research["executable_exit_search_days"],
                        trading_cost=research["trading_cost"],
                    )
                    counts["benchmark_missing"] += any(
                        forward[f"ret{h}"] is not None and forward[f"benchmark_ret{h}"] is None
                        for h in (5, 10, 20, 60)
                    )
                    payload.append(
                        {
                            "trade_date": base.trade_date,
                            "theme_code": code,
                            "strategy_config_hash": base.source_strategy_config_hash,
                            "theme_calc_version": base.calc_version,
                            "opportunity_config_hash": opportunity_hash,
                            "research_version": RESEARCH_VERSION,
                            "research_config_hash": research_hash,
                            "eval_version": RESEARCH_EVAL_VERSION,
                            "entry_basis": research["theme"]["entry_basis"],
                            "benchmark_code": research["benchmark_code"],
                            "theme_context_available": bool(
                                theme_context.get(base.trade_date, {}).get("available", False)
                            ),
                            "theme_context_coverage": theme_context.get(
                                base.trade_date, {}
                            ).get("coverage"),
                            **{key: getattr(base, key) for key in SNAPSHOT_COLUMNS},
                            **forward,
                        }
                    )
            yield payload

    stats = replace_slice_rows_with_stats(
        db, ThemeForwardEval, row_batches(), scope_filters=scope_filters, key_columns=THEME_KEY
    )
    counts["eval_rows"] = stats["upserted"]
    counts["deleted_rows"] = stats["deleted"]
    if progress:
        progress(counts["eval_rows"])
    return counts
