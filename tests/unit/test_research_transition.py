from datetime import date, timedelta
from types import SimpleNamespace

from app.services.research.transition_eval import (
    is_right_side_new,
    left_crossings,
    transition_outcome,
)


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
    result = transition_outcome(dates[0], dates, {dates[3]: "S4"}, is_right=True)
    assert result["mature5"] is True
    assert result["mature10"] is False
    assert result["mature20"] is False
    assert result["reached_s4plus_5"] is True
    assert result["reached_s4plus_20"] is None
    assert result["fell_below_s3_20"] is None


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
