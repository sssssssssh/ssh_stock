from collections import defaultdict
from collections.abc import Iterator
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.market_data import (
    ResearchTransitionEval,
    StockOpportunityDaily,
    StockStateDaily,
    TradeCalendar,
)
from app.repositories.replace_slice import replace_slice_rows_with_stats
from app.services.analysis_filters import opportunity_identity_filters
from app.services.analysis_identity import (
    OPPORTUNITY_CALC_VERSION,
    RESEARCH_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.research.opportunity_eval import STATES, future_dates

TRANSITION_KEY = (
    "event_trade_date",
    "ts_code",
    "event_key",
    "algo_version",
    "trend_calc_version",
    "opportunity_calc_version",
    "strategy_config_hash",
    "opportunity_config_hash",
    "research_version",
    "research_config_hash",
)


def left_crossings(today: Any, previous: Any | None, thresholds: list[int]) -> list[int]:
    if previous is None or today.state not in {"S1", "S2"}:
        return []
    score = today.left_reversal_score
    if score is None:
        return []
    return [
        threshold
        for threshold in thresholds
        if score >= threshold
        and (
            previous.state not in {"S1", "S2"}
            or previous.left_reversal_score is None
            or previous.left_reversal_score < threshold
        )
    ]


def is_right_side_new(today: Any) -> bool:
    return (
        today.opportunity_stage == "RIGHT_SIDE_NEW"
        and today.state == "S3"
        and today.previous_state != "S3"
    )


def transition_outcome(
    event_date: date,
    market_dates: list[date],
    states: dict[date, str],
    *,
    is_right: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "days_to_s3": None,
        "days_to_s4plus": None,
        "days_to_s5": None,
        "hit_s0_20": None,
        "hit_s6_20": None,
        "fell_below_s3_20": None,
    }
    if event_date not in market_dates:
        future = []
    else:
        future = market_dates[market_dates.index(event_date) + 1 :]
    for offset, day in enumerate(future[:20], start=1):
        if day not in states:
            break
        state = states[day]
        if state == "S3" and result["days_to_s3"] is None:
            result["days_to_s3"] = offset
        if state in {"S4", "S5"} and result["days_to_s4plus"] is None:
            result["days_to_s4plus"] = offset
        if state == "S5" and result["days_to_s5"] is None:
            result["days_to_s5"] = offset
    for horizon in (5, 10, 20):
        mature = len(future) >= horizon and all(day in states for day in future[:horizon])
        result[f"mature{horizon}"] = mature
        result[f"state{horizon}"] = states.get(future[horizon - 1]) if mature else None
        window = [states[day] for day in future[:horizon]] if mature else []
        for target, matches in (
            ("s3", {"S3"}),
            ("s4plus", {"S4", "S5"}),
            ("s5", {"S5"}),
        ):
            result[f"reached_{target}_{horizon}"] = (
                any(state in matches for state in window) if mature else None
            )
    if result["mature20"]:
        window20 = [states[day] for day in future[:20]]
        result["hit_s0_20"] = "S0" in window20
        result["hit_s6_20"] = "S6" in window20
        result["fell_below_s3_20"] = (
            any(state in {"S0", "S1", "S2"} for state in window20) if is_right else None
        )
    return result


def evaluate_transition_batch(db: Session, base_dates: list[date], settings: Any) -> dict[str, int]:
    strategy_hash = analysis_strategy_hash(settings.strategy)
    opportunity_hash = config_hash(settings.opportunity_config)
    research_hash = config_hash(settings.research_config)
    scope_filters = (
        ResearchTransitionEval.event_trade_date.in_(base_dates),
        ResearchTransitionEval.algo_version == settings.algo_version,
        ResearchTransitionEval.trend_calc_version == TREND_CALC_VERSION,
        ResearchTransitionEval.opportunity_calc_version == OPPORTUNITY_CALC_VERSION,
        ResearchTransitionEval.strategy_config_hash == strategy_hash,
        ResearchTransitionEval.opportunity_config_hash == opportunity_hash,
        ResearchTransitionEval.research_version == RESEARCH_VERSION,
        ResearchTransitionEval.research_config_hash == research_hash,
    )
    previous_date = db.scalar(
        select(TradeCalendar.cal_date)
        .where(
            TradeCalendar.is_open.is_(True),
            TradeCalendar.cal_date < base_dates[0],
        )
        .order_by(TradeCalendar.cal_date.desc())
        .limit(1)
    )
    latest = db.scalar(
        select(func.max(StockStateDaily.trade_date)).where(
            StockStateDaily.algo_version == settings.algo_version,
            StockStateDaily.calc_version == TREND_CALC_VERSION,
            StockStateDaily.config_hash == strategy_hash,
        )
    )
    dates = future_dates(
        db,
        base_dates,
        latest,
        max_horizon=max(settings.research_config["transition_horizons"]),
        executable_exit_search_days=0,
    )
    all_dates = ([previous_date] if previous_date else []) + dates
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
    prior_by_date = {day: all_dates[index - 1] for index, day in enumerate(all_dates) if index > 0}
    prior_dates = {prior_by_date[day] for day in base_dates if day in prior_by_date}
    previous: dict[tuple[date, str], Any] = {}
    if all_dates and bases:
        prior_rows = (
            db.execute(
                select(StockOpportunityDaily).where(
                    StockOpportunityDaily.trade_date.in_(prior_dates),
                    *opportunity_identity_filters(
                        settings,
                        strategy_hash=strategy_hash,
                        opportunity_hash=opportunity_hash,
                    ),
                    StockOpportunityDaily.ts_code.in_({base.ts_code for base in bases}),
                )
            )
            .scalars()
            .all()
        )
        previous = {(row.trade_date, row.ts_code): row for row in prior_rows}
    by_code: dict[str, list[Any]] = defaultdict(list)
    for base in bases:
        by_code[base.ts_code].append(base)
    counts = {"base_rows": len(bases), "eval_rows": 0, "deleted_rows": 0}
    codes = sorted(by_code)

    def row_batches() -> Iterator[list[dict[str, Any]]]:
        for offset in range(0, len(codes), 250):
            chunk = codes[offset : offset + 250]
            state_rows = (
                db.execute(
                    select(
                        StockStateDaily.ts_code, StockStateDaily.trade_date, StockStateDaily.state
                    ).where(
                        StockStateDaily.ts_code.in_(chunk),
                        StockStateDaily.trade_date.between(dates[0], dates[-1]),
                        StockStateDaily.algo_version == settings.algo_version,
                        StockStateDaily.calc_version == TREND_CALC_VERSION,
                        StockStateDaily.config_hash == strategy_hash,
                    )
                ).all()
                if dates
                else []
            )
            states: dict[str, dict[date, str]] = defaultdict(dict)
            for row in state_rows:
                states[row.ts_code][row.trade_date] = row.state
            payload = []
            for code in chunk:
                for base in by_code[code]:
                    prior = previous.get((prior_by_date.get(base.trade_date), code))
                    left_events = left_crossings(
                        base, prior, settings.research_config["left_thresholds"]
                    )
                    events = [
                        ("LEFT_THRESHOLD_CROSS", f"LEFT_{value}", value, base.left_reversal_score)
                        for value in left_events
                    ]
                    if is_right_side_new(base):
                        events.append(
                            ("RIGHT_SIDE_NEW", "RIGHT_SIDE_NEW", None, base.right_side_score)
                        )
                    for event_type, event_key, threshold, score in events:
                        payload.append(
                            {
                                "event_trade_date": base.trade_date,
                                "ts_code": code,
                                "event_type": event_type,
                                "event_key": event_key,
                                "threshold_value": threshold,
                                "source_state": base.state,
                                "source_score": score,
                                "algo_version": settings.algo_version,
                                "trend_calc_version": TREND_CALC_VERSION,
                                "opportunity_calc_version": OPPORTUNITY_CALC_VERSION,
                                "strategy_config_hash": base.source_strategy_config_hash,
                                "opportunity_config_hash": opportunity_hash,
                                "research_version": RESEARCH_VERSION,
                                "research_config_hash": research_hash,
                                **transition_outcome(
                                    base.trade_date,
                                    dates,
                                    states[code],
                                    is_right=event_type == "RIGHT_SIDE_NEW",
                                ),
                            }
                        )
            yield payload

    stats = replace_slice_rows_with_stats(
        db,
        ResearchTransitionEval,
        row_batches(),
        scope_filters=scope_filters,
        key_columns=TRANSITION_KEY,
    )
    counts["eval_rows"] = stats["upserted"]
    counts["deleted_rows"] = stats["deleted"]
    return counts
