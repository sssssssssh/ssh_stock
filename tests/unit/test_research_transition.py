from datetime import date, timedelta
from types import SimpleNamespace

import app.services.research.transition_eval as transition_eval
from app.core.config import get_settings
from app.models.market_data import ResearchTransitionEval, StockStateDaily, TradeCalendar
from app.services.analysis_identity import (
    OPPORTUNITY_CALC_VERSION,
    RESEARCH_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.research.transition_eval import (
    evaluate_transition_batch,
    is_right_side_new,
    left_crossings,
    transition_outcome,
    transition_research_ready_dates,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def _days(count: int) -> list[date]:
    return [date(2026, 1, 1) + timedelta(days=offset) for offset in range(count)]


def test_left_crossing_rebuilds_thresholds_including_score_jump() -> None:
    thresholds = [60, 65, 70, 75, 80, 85]
    today = SimpleNamespace(state="S2", left_reversal_score=82)
    prior = SimpleNamespace(state="S2", left_reversal_score=68)
    assert left_crossings(today, prior, thresholds) == [70, 75, 80]
    assert left_crossings(
        today, SimpleNamespace(state="S0", left_reversal_score=None), thresholds
    ) == [60, 65, 70, 75, 80]
    assert left_crossings(today, None, thresholds) == []
    assert (
        left_crossings(SimpleNamespace(state="S3", left_reversal_score=90), prior, thresholds) == []
    )


def test_right_transition_uses_market_day_offsets_and_independent_failures() -> None:
    dates = _days(21)
    states = {days: "S3" for days in dates[1:]}
    states[dates[3]] = "S4"
    states[dates[8]] = "S5"
    states[dates[12]] = "S1"
    states[dates[15]] = "S6"
    result = transition_outcome(dates[0], dates, states, is_right=True)
    assert result["days_to_s4plus"] == 3
    assert result["days_to_s5"] == 8
    assert result["reached_s4plus_5"] is True
    assert result["reached_s5_5"] is False
    assert result["reached_s5_10"] is True
    assert result["fell_below_s3_20"] is True
    assert result["hit_s6_20"] is True


def test_unmatured_transition_does_not_create_false_20_day_rate() -> None:
    dates = _days(9)
    result = transition_outcome(dates[0], dates, {day: "S4" for day in dates[1:]}, is_right=True)
    assert result["mature5"] is True
    assert result["mature10"] is False
    assert result["mature20"] is False
    assert result["reached_s4plus_5"] is True
    assert result["reached_s4plus_20"] is None
    assert result["fell_below_s3_20"] is None


def test_transition_maturity_requires_continuous_current_state_rows() -> None:
    dates = _days(21)
    complete = {day: "S2" for day in dates[1:]}
    result = transition_outcome(dates[0], dates, complete, is_right=False)
    assert [result[f"mature{h}"] for h in (5, 10, 20)] == [True, True, True]

    missing_day3 = {**complete, dates[2]: "S3", dates[4]: "S3"}
    del missing_day3[dates[3]]
    result = transition_outcome(dates[0], dates, missing_day3, is_right=False)
    assert [result[f"mature{h}"] for h in (5, 10, 20)] == [False, False, False]
    assert result["state5"] is None
    assert result["reached_s3_5"] is None
    assert result["days_to_s3"] == 2

    missing_day3[dates[2]] = "S2"
    result = transition_outcome(dates[0], dates, missing_day3, is_right=False)
    assert result["days_to_s3"] is None

    missing_day7 = dict(complete)
    del missing_day7[dates[7]]
    result = transition_outcome(dates[0], dates, missing_day7, is_right=False)
    assert [result[f"mature{h}"] for h in (5, 10, 20)] == [True, False, False]


def test_right_side_new_requires_consistent_state_transition() -> None:
    assert (
        is_right_side_new(
            SimpleNamespace(opportunity_stage="RIGHT_SIDE_NEW", state="S3", previous_state="S2")
        )
        is True
    )
    assert (
        is_right_side_new(
            SimpleNamespace(opportunity_stage="RIGHT_SIDE_NEW", state="S3", previous_state="S3")
        )
        is False
    )
    assert (
        is_right_side_new(
            SimpleNamespace(opportunity_stage="RIGHT_SIDE", state="S3", previous_state="S2")
        )
        is False
    )


def _readiness_db(days: list[date], latest_state: date) -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    TradeCalendar.__table__.create(engine)
    StockStateDaily.__table__.create(engine)
    settings = get_settings()
    db = Session(engine)
    db.execute(
        TradeCalendar.__table__.insert(),
        [{"cal_date": day, "is_open": True, "exchange": "SSE"} for day in days],
    )
    db.execute(
        StockStateDaily.__table__.insert(),
        [{
            "trade_date": latest_state,
            "ts_code": "000001.SZ",
            "algo_version": settings.algo_version,
            "state": "S4",
            "is_new_state": False,
            "fast_transition": False,
            "calc_version": TREND_CALC_VERSION,
            "config_hash": analysis_strategy_hash(settings.strategy),
        }],
    )
    db.commit()
    return db


def test_transition_readiness_uses_real_previous_open_date(monkeypatch) -> None:
    days = _days(5)
    settings = get_settings()
    db = _readiness_db(days, days[2])
    monkeypatch.setattr(
        transition_eval,
        "opportunity_research_ready_dates",
        lambda db, candidates, settings: ([days[2]], [days[1]]),
    )
    monkeypatch.setattr(transition_eval, "is_core_analysis_complete", lambda *args, **kwargs: True)

    ready, skipped = transition_research_ready_dates(db, [days[2]], settings)

    assert ready == []
    assert skipped == [days[2]]


def test_transition_readiness_rejects_elapsed_future_core_gap(monkeypatch) -> None:
    days = _days(6)
    settings = get_settings()
    db = _readiness_db(days, days[4])
    monkeypatch.setattr(
        transition_eval,
        "opportunity_research_ready_dates",
        lambda db, candidates, settings: (candidates, []),
    )
    monkeypatch.setattr(
        transition_eval,
        "is_core_analysis_complete",
        lambda db, day, **kwargs: day != days[3],
    )

    ready, skipped = transition_research_ready_dates(db, [days[2]], settings)

    assert ready == []
    assert skipped == [days[2]]


def test_transition_readiness_ignores_unelapsed_future_dates(monkeypatch) -> None:
    days = _days(8)
    settings = get_settings()
    db = _readiness_db(days, days[3])
    monkeypatch.setattr(
        transition_eval,
        "opportunity_research_ready_dates",
        lambda db, candidates, settings: (candidates, []),
    )
    checked = []
    monkeypatch.setattr(
        transition_eval,
        "is_core_analysis_complete",
        lambda db, day, **kwargs: checked.append(day) or True,
    )

    ready, skipped = transition_research_ready_dates(db, [days[2]], settings)

    assert ready == [days[2]]
    assert skipped == []
    assert checked == [days[3]]


def test_transition_batch_skipped_date_preserves_existing_slice(monkeypatch) -> None:
    settings = get_settings()
    day = date(2026, 1, 3)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ResearchTransitionEval.__table__.create(engine)
    monkeypatch.setattr(
        transition_eval,
        "transition_research_ready_dates",
        lambda db, dates, settings: ([], dates),
    )
    with Session(engine) as db:
        db.add(
            ResearchTransitionEval(
                id=1,
                event_trade_date=day,
                ts_code="000001.SZ",
                event_type="LEFT_THRESHOLD_CROSS",
                event_key="LEFT_70",
                source_state="S2",
                algo_version=settings.algo_version,
                trend_calc_version=TREND_CALC_VERSION,
                opportunity_calc_version=OPPORTUNITY_CALC_VERSION,
                strategy_config_hash=analysis_strategy_hash(settings.strategy),
                opportunity_config_hash=config_hash(settings.opportunity_config),
                research_version=RESEARCH_VERSION,
                research_config_hash=config_hash(settings.research_config),
                mature5=True,
                mature10=True,
                mature20=True,
            )
        )
        db.commit()

        result = evaluate_transition_batch(db, [day], settings)
        remaining = db.scalar(select(func.count()).select_from(ResearchTransitionEval))

    assert result["transition_skipped_source_dates"] == 1
    assert result["deleted_rows"] == 0
    assert remaining == 1
