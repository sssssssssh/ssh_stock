from collections import defaultdict
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.market_data import (
    IndexDaily,
    MarketDaily,
    OpportunityForwardEval,
    StockDaily,
    StockFactorDaily,
    StockOpportunityDaily,
    StockTradeStatusDaily,
    TradeCalendar,
)
from app.repositories.replace_slice import replace_slice_rows_with_stats
from app.services.analysis_filters import opportunity_identity_filters
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    MARKET_CALC_VERSION,
    OPPORTUNITY_CALC_VERSION,
    RESEARCH_EVAL_VERSION,
    RESEARCH_VERSION,
    TRADE_STATUS_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.research.forward_eval import evaluate_stock_forward
from app.services.theme.membership import resolve_theme_memberships

STATES = ("S1", "S2", "S3", "S4", "S5")
SNAPSHOT_COLUMNS = (
    "state",
    "previous_state",
    "state_day_count",
    "opportunity_stage",
    "left_reversal_score",
    "left_reversal_new",
    "right_side_score",
    "trend_score",
    "trend_rank_score",
    "position_score",
    "extension_risk",
    "opportunity_score",
    "context_score",
    "market_score",
    "industry_sector_id",
    "industry_heat",
    "industry_lifecycle",
    "primary_theme_code",
    "primary_theme_heat",
    "primary_theme_lifecycle",
    "hot_theme_count",
)
OPPORTUNITY_KEY = (
    "trade_date",
    "ts_code",
    "algo_version",
    "strategy_config_hash",
    "opportunity_calc_version",
    "opportunity_config_hash",
    "research_version",
    "research_config_hash",
    "eval_version",
    "entry_basis",
)


def trade_batches(db: Session, start: date, end: date, size: int) -> Iterator[list[date]]:
    dates = (
        db.execute(
            select(TradeCalendar.cal_date)
            .where(
                TradeCalendar.is_open.is_(True),
                TradeCalendar.cal_date >= start,
                TradeCalendar.cal_date <= end,
            )
            .order_by(TradeCalendar.cal_date)
        )
        .scalars()
        .all()
    )
    for index in range(0, len(dates), size):
        yield dates[index : index + size]


def future_dates(
    db: Session,
    base_dates: list[date],
    latest: date | None,
    *,
    max_horizon: int,
    executable_exit_search_days: int,
) -> list[date]:
    if latest is None or not base_dates:
        return []
    required_count = (
        len(base_dates) + 1 + max_horizon + executable_exit_search_days
    )
    return (
        db.execute(
            select(TradeCalendar.cal_date)
            .where(
                TradeCalendar.is_open.is_(True),
                TradeCalendar.cal_date >= base_dates[0],
                TradeCalendar.cal_date <= latest,
            )
            .order_by(TradeCalendar.cal_date)
            .limit(required_count)
        )
        .scalars()
        .all()
    )


def benchmark_lookup(db: Session, dates: list[date], code: str) -> dict[date, dict[str, Any]]:
    if not dates:
        return {}
    rows = (
        db.execute(
            select(IndexDaily.trade_date, IndexDaily.open, IndexDaily.close).where(
                IndexDaily.ts_code == code,
                IndexDaily.trade_date >= dates[0],
                IndexDaily.trade_date <= dates[-1],
            )
        )
        .mappings()
        .all()
    )
    return {row["trade_date"]: dict(row) for row in rows}


def evaluate_opportunity_batch(
    db: Session,
    base_dates: list[date],
    settings: Any,
    *,
    progress: Callable[[int], None] | None = None,
) -> dict[str, int]:
    strategy_hash = analysis_strategy_hash(settings.strategy)
    opportunity_hash = config_hash(settings.opportunity_config)
    research_hash = config_hash(settings.research_config)
    research = settings.research_config
    scope_filters = (
        OpportunityForwardEval.trade_date.in_(base_dates),
        OpportunityForwardEval.algo_version == settings.algo_version,
        OpportunityForwardEval.strategy_config_hash == strategy_hash,
        OpportunityForwardEval.opportunity_calc_version == OPPORTUNITY_CALC_VERSION,
        OpportunityForwardEval.opportunity_config_hash == opportunity_hash,
        OpportunityForwardEval.research_version == RESEARCH_VERSION,
        OpportunityForwardEval.research_config_hash == research_hash,
        OpportunityForwardEval.eval_version == RESEARCH_EVAL_VERSION,
        OpportunityForwardEval.entry_basis == research["stock"]["entry_basis"],
    )
    bases = (
        db.execute(
            select(StockOpportunityDaily).where(
                StockOpportunityDaily.trade_date.in_(base_dates),
                *opportunity_identity_filters(
                    settings,
                    strategy_hash=strategy_hash,
                    opportunity_hash=opportunity_hash,
                ),
                StockOpportunityDaily.state.in_(STATES),
            )
        )
        .scalars()
        .all()
    )
    counts = {
        "base_rows": len(bases),
        "eval_rows": 0,
        "deleted_rows": 0,
        "entry_nonexecutable": 0,
        "benchmark_missing": 0,
    }
    if not bases:
        stats = replace_slice_rows_with_stats(
            db,
            OpportunityForwardEval,
            (),
            scope_filters=scope_filters,
            key_columns=OPPORTUNITY_KEY,
        )
        counts["deleted_rows"] = stats["deleted"]
        return counts
    latest = db.scalar(select(func.max(StockDaily.trade_date)))
    dates = future_dates(
        db,
        base_dates,
        latest,
        max_horizon=max(research["horizons"]),
        executable_exit_search_days=research["executable_exit_search_days"],
    )
    benchmark = benchmark_lookup(db, dates, research["benchmark_code"])
    market_rows = db.execute(
        select(MarketDaily.trade_date, MarketDaily.regime).where(
            MarketDaily.trade_date.in_(base_dates),
            MarketDaily.calc_version == MARKET_CALC_VERSION,
            MarketDaily.config_hash == strategy_hash,
        )
    ).all()
    regimes = {row.trade_date: row.regime for row in market_rows}
    theme_context = resolve_theme_memberships(db, base_dates).context_by_date
    by_code: dict[str, list[Any]] = defaultdict(list)
    for base in bases:
        by_code[base.ts_code].append(base)
    codes = sorted(by_code)

    def row_batches() -> Iterator[list[dict[str, Any]]]:
        for offset in range(0, len(codes), 250):
            chunk = codes[offset : offset + 250]
            rows_by_code = _stock_rows(db, chunk, dates, strategy_hash)
            payload = []
            for code in chunk:
                stock_rows = rows_by_code.get(code, {})
                for base in by_code[code]:
                    forward = evaluate_stock_forward(
                        base.trade_date,
                        dates,
                        stock_rows,
                        benchmark,
                        executable_exit_search_days=research["executable_exit_search_days"],
                        trading_cost=research["trading_cost"],
                    )
                    counts["entry_nonexecutable"] += forward["entry_executable"] is False
                    counts["benchmark_missing"] += any(
                        forward[f"ret{h}"] is not None and forward[f"benchmark_ret{h}"] is None
                        for h in (5, 10, 20, 60)
                    )
                    payload.append(
                        {
                            "trade_date": base.trade_date,
                            "ts_code": code,
                            "algo_version": base.algo_version,
                            "strategy_config_hash": base.source_strategy_config_hash,
                            "opportunity_calc_version": base.calc_version,
                            "opportunity_config_hash": opportunity_hash,
                            "research_version": RESEARCH_VERSION,
                            "research_config_hash": research_hash,
                            "eval_version": RESEARCH_EVAL_VERSION,
                            "entry_basis": research["stock"]["entry_basis"],
                            "benchmark_code": research["benchmark_code"],
                            "market_regime": regimes.get(base.trade_date),
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
        db,
        OpportunityForwardEval,
        row_batches(),
        scope_filters=scope_filters,
        key_columns=OPPORTUNITY_KEY,
    )
    counts["eval_rows"] = stats["upserted"]
    counts["deleted_rows"] = stats["deleted"]
    if progress:
        progress(counts["eval_rows"])
    return counts


def _stock_rows(
    db: Session,
    codes: list[str],
    dates: list[date],
    strategy_hash: str,
) -> dict[str, dict[date, dict[str, Any]]]:
    result: dict[str, dict[date, dict[str, Any]]] = defaultdict(dict)
    if not dates:
        return result
    start, end = dates[0], dates[-1]
    factors = (
        db.execute(
            select(
                StockFactorDaily.ts_code,
                StockFactorDaily.trade_date,
                StockFactorDaily.adj_open,
                StockFactorDaily.adj_high,
                StockFactorDaily.adj_low,
                StockFactorDaily.adj_close,
            ).where(
                StockFactorDaily.ts_code.in_(codes),
                StockFactorDaily.trade_date.between(start, end),
                StockFactorDaily.calc_version == FACTOR_CALC_VERSION,
                StockFactorDaily.config_hash == strategy_hash,
            )
        )
        .mappings()
        .all()
    )
    for row in factors:
        result[row["ts_code"]][row["trade_date"]].update(row)
    raw = db.execute(
        select(StockDaily.ts_code, StockDaily.trade_date, StockDaily.open).where(
            StockDaily.ts_code.in_(codes),
            StockDaily.trade_date.between(start, end),
        )
    ).all()
    for row in raw:
        result[row.ts_code][row.trade_date]["raw_open"] = row.open
        result[row.ts_code][row.trade_date]["raw_present"] = True
    statuses = (
        db.execute(
            select(
                StockTradeStatusDaily.ts_code,
                StockTradeStatusDaily.trade_date,
                StockTradeStatusDaily.is_suspended,
                StockTradeStatusDaily.tradable,
                StockTradeStatusDaily.up_limit,
                StockTradeStatusDaily.is_limit_down_close,
            ).where(
                StockTradeStatusDaily.ts_code.in_(codes),
                StockTradeStatusDaily.trade_date.between(start, end),
                StockTradeStatusDaily.calc_version == TRADE_STATUS_CALC_VERSION,
                StockTradeStatusDaily.config_hash == strategy_hash,
            )
        )
        .mappings()
        .all()
    )
    for row in statuses:
        result[row["ts_code"]][row["trade_date"]].update(row)
        result[row["ts_code"]][row["trade_date"]]["status_present"] = True
    for code_rows in result.values():
        for row in code_rows.values():
            row.setdefault("raw_present", False)
            row.setdefault("status_present", False)
    return result
