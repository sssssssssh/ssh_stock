from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.market_data import (
    ResearchTransitionEval,
    StockFactorDaily,
    StockOpportunityDaily,
    StockStateDaily,
    TradeCalendar,
)
from app.repositories.replace_slice import replace_slice_rows_with_stats
from app.services.analysis_filters import opportunity_identity_filters
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    OPPORTUNITY_CALC_VERSION,
    RESEARCH_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.quality.analysis_readiness import is_core_analysis_complete
from app.services.quality.opportunity_quality import check_opportunity_quality
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


@dataclass(frozen=True)
class TransitionCandidate:
    base: Any
    event_type: str
    event_key: str
    threshold_value: int | None
    source_score: float | None


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


def transition_opportunity_source_complete(
    db: Session, trade_date: date, settings: Any
) -> bool:
    if not is_core_analysis_complete(
        db,
        trade_date,
        strategy=settings.strategy,
        algo_version=settings.algo_version,
    ):
        return False
    quality = check_opportunity_quality(
        db,
        trade_date,
        strategy_hash=analysis_strategy_hash(settings.strategy),
        opportunity_hash=config_hash(settings.opportunity_config),
        algo_version=settings.algo_version,
        config=settings.opportunity_config,
    )
    state_count = quality.counts["state"]
    return state_count > 0 and quality.counts["opportunity"] == state_count


def _transition_calendar(
    db: Session,
    base_dates: list[date],
    latest_state: date | None,
    *,
    max_horizon: int,
) -> tuple[dict[date, date], dict[date, list[date]]]:
    if not base_dates:
        return {}, {}
    first_prior = db.scalar(
        select(TradeCalendar.cal_date)
        .where(
            TradeCalendar.is_open.is_(True),
            TradeCalendar.cal_date < min(base_dates),
        )
        .order_by(TradeCalendar.cal_date.desc())
        .limit(1)
    )
    calendar_start = first_prior or min(base_dates)
    calendar_end = max(max(base_dates), latest_state) if latest_state else max(base_dates)
    open_dates = list(
        db.execute(
            select(TradeCalendar.cal_date)
            .where(
                TradeCalendar.is_open.is_(True),
                TradeCalendar.cal_date >= calendar_start,
                TradeCalendar.cal_date <= calendar_end,
            )
            .order_by(TradeCalendar.cal_date)
        )
        .scalars()
        .all()
    )
    positions = {day: index for index, day in enumerate(open_dates)}
    prior_by_date = {
        day: open_dates[positions[day] - 1]
        for day in base_dates
        if day in positions and positions[day] > 0
    }
    elapsed_future_by_date: dict[date, list[date]] = {}
    for day in base_dates:
        position = positions.get(day)
        elapsed_future_by_date[day] = (
            [
                future_day
                for future_day in open_dates[position + 1 : position + 1 + max_horizon]
                if latest_state is not None and future_day <= latest_state
            ]
            if position is not None
            else []
        )
    return prior_by_date, elapsed_future_by_date


def transition_research_ready_dates(
    db: Session, base_dates: list[date], settings: Any
) -> tuple[list[date], list[date]]:
    if not base_dates:
        return [], []
    strategy_hash = analysis_strategy_hash(settings.strategy)
    latest_state = db.scalar(
        select(func.max(StockStateDaily.trade_date)).where(
            StockStateDaily.algo_version == settings.algo_version,
            StockStateDaily.calc_version == TREND_CALC_VERSION,
            StockStateDaily.config_hash == strategy_hash,
        )
    )
    prior_by_date, elapsed_future_by_date = _transition_calendar(
        db,
        base_dates,
        latest_state,
        max_horizon=max(settings.research_config["transition_horizons"]),
    )
    source_dates = sorted(set(base_dates) | set(prior_by_date.values()))
    source_complete = {
        day: transition_opportunity_source_complete(db, day, settings)
        for day in source_dates
    }
    future_dates_to_check = sorted(
        {future for dates in elapsed_future_by_date.values() for future in dates}
    )
    core_ready = {
        day: is_core_analysis_complete(
            db,
            day,
            strategy=settings.strategy,
            algo_version=settings.algo_version,
        )
        for day in future_dates_to_check
    }
    ready: list[date] = []
    skipped: list[date] = []
    for day in base_dates:
        prior = prior_by_date.get(day)
        if (
            not source_complete.get(day, False)
            or prior is None
            or not source_complete.get(prior, False)
            or not all(core_ready[future] for future in elapsed_future_by_date[day])
        ):
            skipped.append(day)
        else:
            ready.append(day)
    return ready, skipped


def build_transition_candidates(
    bases: list[Any],
    previous_by_key: dict[tuple[date, str], Any],
    prior_by_date: dict[date, date],
    thresholds: list[int],
) -> list[TransitionCandidate]:
    candidates: list[TransitionCandidate] = []
    for base in bases:
        previous = previous_by_key.get((prior_by_date.get(base.trade_date), base.ts_code))
        candidates.extend(
            TransitionCandidate(
                base=base,
                event_type="LEFT_THRESHOLD_CROSS",
                event_key=f"LEFT_{threshold}",
                threshold_value=threshold,
                source_score=base.left_reversal_score,
            )
            for threshold in left_crossings(base, previous, thresholds)
        )
        if is_right_side_new(base):
            candidates.append(
                TransitionCandidate(
                    base=base,
                    event_type="RIGHT_SIDE_NEW",
                    event_key="RIGHT_SIDE_NEW",
                    threshold_value=None,
                    source_score=base.right_side_score,
                )
            )
    return candidates


def transition_event_stock_state_integrity(
    db: Session,
    candidates: list[TransitionCandidate],
    elapsed_future_dates_by_date: dict[date, list[date]],
    settings: Any,
) -> tuple[set[date], dict[date, list[tuple[str, date]]]]:
    candidate_codes_by_date: dict[date, set[str]] = defaultdict(set)
    for candidate in candidates:
        candidate_codes_by_date[candidate.base.trade_date].add(candidate.base.ts_code)
    candidate_codes = sorted(
        {code for codes in candidate_codes_by_date.values() for code in codes}
    )
    elapsed_dates = sorted(
        {
            future
            for event_date in candidate_codes_by_date
            for future in elapsed_future_dates_by_date.get(event_date, [])
        }
    )
    if not candidate_codes or not elapsed_dates:
        return set(), {}

    strategy_hash = analysis_strategy_hash(settings.strategy)
    factor_rows = db.execute(
        select(StockFactorDaily.ts_code, StockFactorDaily.trade_date).where(
            StockFactorDaily.ts_code.in_(candidate_codes),
            StockFactorDaily.trade_date.in_(elapsed_dates),
            StockFactorDaily.calc_version == FACTOR_CALC_VERSION,
            StockFactorDaily.config_hash == strategy_hash,
        )
    ).all()
    factor_pairs = {(row.ts_code, row.trade_date) for row in factor_rows}
    state_rows = db.execute(
        select(StockStateDaily.ts_code, StockStateDaily.trade_date).where(
            StockStateDaily.ts_code.in_(candidate_codes),
            StockStateDaily.trade_date.in_(elapsed_dates),
            StockStateDaily.algo_version == settings.algo_version,
            StockStateDaily.calc_version == TREND_CALC_VERSION,
            StockStateDaily.config_hash == strategy_hash,
        )
    ).all()
    state_pairs = {(row.ts_code, row.trade_date) for row in state_rows}

    missing_by_date: dict[date, list[tuple[str, date]]] = {}
    for event_date, codes in candidate_codes_by_date.items():
        expected_pairs = {
            (code, future)
            for code in codes
            for future in elapsed_future_dates_by_date.get(event_date, [])
            if (code, future) in factor_pairs
        }
        missing = sorted(expected_pairs - state_pairs)
        if missing:
            missing_by_date[event_date] = missing
    return set(missing_by_date), missing_by_date


def evaluate_transition_batch(
    db: Session, base_dates: list[date], settings: Any
) -> dict[str, int]:
    strategy_hash = analysis_strategy_hash(settings.strategy)
    opportunity_hash = config_hash(settings.opportunity_config)
    research_hash = config_hash(settings.research_config)
    date_ready_dates, skipped_source_dates = transition_research_ready_dates(
        db, base_dates, settings
    )
    counts = {
        "base_rows": 0,
        "eval_rows": 0,
        "deleted_rows": 0,
        "transition_skipped_source_dates": len(skipped_source_dates),
        "transition_skipped_event_stock_dates": 0,
    }
    if not date_ready_dates:
        return counts

    latest_state = db.scalar(
        select(func.max(StockStateDaily.trade_date)).where(
            StockStateDaily.algo_version == settings.algo_version,
            StockStateDaily.calc_version == TREND_CALC_VERSION,
            StockStateDaily.config_hash == strategy_hash,
        )
    )
    prior_by_date, elapsed_future_by_date = _transition_calendar(
        db,
        date_ready_dates,
        latest_state,
        max_horizon=max(settings.research_config["transition_horizons"]),
    )
    preliminary_bases = (
        db.execute(
            select(StockOpportunityDaily).where(
                StockOpportunityDaily.trade_date.in_(date_ready_dates),
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
    prior_dates = set(prior_by_date.values())
    prior_rows = (
        db.execute(
            select(StockOpportunityDaily).where(
                StockOpportunityDaily.trade_date.in_(prior_dates),
                *opportunity_identity_filters(
                    settings,
                    strategy_hash=strategy_hash,
                    opportunity_hash=opportunity_hash,
                ),
                StockOpportunityDaily.ts_code.in_(
                    {base.ts_code for base in preliminary_bases}
                ),
            )
        )
        .scalars()
        .all()
        if preliminary_bases and prior_dates
        else []
    )
    previous_by_key = {(row.trade_date, row.ts_code): row for row in prior_rows}
    candidates = build_transition_candidates(
        preliminary_bases,
        previous_by_key,
        prior_by_date,
        settings.research_config["left_thresholds"],
    )
    unsafe_dates, _missing_pairs = transition_event_stock_state_integrity(
        db, candidates, elapsed_future_by_date, settings
    )
    final_ready_dates = [day for day in date_ready_dates if day not in unsafe_dates]
    counts["transition_skipped_event_stock_dates"] = len(unsafe_dates)
    counts["transition_skipped_source_dates"] += len(unsafe_dates)
    if not final_ready_dates:
        return counts

    final_ready_set = set(final_ready_dates)
    bases = [base for base in preliminary_bases if base.trade_date in final_ready_set]
    final_candidates = [
        candidate
        for candidate in candidates
        if candidate.base.trade_date in final_ready_set
    ]
    counts["base_rows"] = len(bases)
    scope_filters = (
        ResearchTransitionEval.event_trade_date.in_(final_ready_dates),
        ResearchTransitionEval.algo_version == settings.algo_version,
        ResearchTransitionEval.trend_calc_version == TREND_CALC_VERSION,
        ResearchTransitionEval.opportunity_calc_version == OPPORTUNITY_CALC_VERSION,
        ResearchTransitionEval.strategy_config_hash == strategy_hash,
        ResearchTransitionEval.opportunity_config_hash == opportunity_hash,
        ResearchTransitionEval.research_version == RESEARCH_VERSION,
        ResearchTransitionEval.research_config_hash == research_hash,
    )
    dates = future_dates(
        db,
        final_ready_dates,
        latest_state,
        max_horizon=max(settings.research_config["transition_horizons"]),
        executable_exit_search_days=0,
    )
    candidates_by_code: dict[str, list[TransitionCandidate]] = defaultdict(list)
    for candidate in final_candidates:
        candidates_by_code[candidate.base.ts_code].append(candidate)
    codes = sorted(candidates_by_code)

    def row_batches() -> Iterator[list[dict[str, Any]]]:
        for offset in range(0, len(codes), 250):
            chunk = codes[offset : offset + 250]
            state_rows = (
                db.execute(
                    select(
                        StockStateDaily.ts_code,
                        StockStateDaily.trade_date,
                        StockStateDaily.state,
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
            payload: list[dict[str, Any]] = []
            for code in chunk:
                for candidate in candidates_by_code[code]:
                    base = candidate.base
                    payload.append(
                        {
                            "event_trade_date": base.trade_date,
                            "ts_code": code,
                            "event_type": candidate.event_type,
                            "event_key": candidate.event_key,
                            "threshold_value": candidate.threshold_value,
                            "source_state": base.state,
                            "source_score": candidate.source_score,
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
                                is_right=candidate.event_type == "RIGHT_SIDE_NEW",
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
