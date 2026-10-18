"""Red/green cold-start regressions; all inputs are synthetic, never DB-backed."""

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest
from app.services.factors.engine import FactorConfig, _assign_eligibility, calculate_stock_factors
from app.services.opportunity import engine as opportunity

from scripts.cold_start_comparison import (
    downstream_signals,
    engine,
    evaluate,
    factor_inputs,
    opportunity_inputs,
    status_for,
)


@pytest.mark.parametrize("kind", ["factors", "opportunity"])
def test_complete_golden_matches_frozen_v11(kind):
    expected = evaluate(engine(kind, baseline=True), kind, "complete")
    actual = evaluate(engine(kind), kind, "complete")
    pd.testing.assert_frame_equal(actual, expected, rtol=1e-12, atol=1e-12)
    if kind == "opportunity":
        assert set(actual.opportunity_stage) == {
            "LEFT_REVERSAL",
            "RIGHT_SIDE_NEW",
            "STRONG_TREND",
        }
    else:
        assert downstream_signals(actual) == downstream_signals(expected)


def test_partial_left_join_does_not_exclude_present_status():
    kwargs = factor_inputs()
    status = status_for(kwargs["daily"])
    status = status[status.ts_code != "C.SZ"]
    result = calculate_stock_factors(**kwargs, config=FactorConfig(), trade_status=status)
    by_code = result.set_index("ts_code")
    assert bool(by_code.loc["A.SZ", "eligible"])
    assert bool(by_code.loc["B.SZ", "eligible"])
    assert by_code.loc["C.SZ", "exclusion_reason"] == "TRADE_STATUS_MISSING"
    assert len(result) == 3


@pytest.mark.parametrize("dtype", [object, bool, "boolean"])
def test_missing_status_mask_is_boolean_not_negative_integer(dtype):
    marker = pd.Series([True, False, True], dtype=dtype)
    frame = pd.DataFrame(
        dict(
            ts_code=["A", "B", "C"],
            trade_date=[date(2026, 1, 5)] * 3,
            list_date=[date(2020, 1, 1)] * 3,
            delist_date=[None] * 3,
            close=[10.0] * 3,
            amount_ma20=[100000.0] * 3,
            trade_status_present=marker,
        )
    )
    result = _assign_eligibility(frame, FactorConfig(min_listed_trading_days=1))
    assert result.exclusion_reason.isna().tolist() == [True, False, True]
    assert result.iloc[1].exclusion_reason == "TRADE_STATUS_MISSING"
    assert result.trade_status_present.dtype == bool


@pytest.mark.parametrize("missing", [None, np.nan, pd.NA])
def test_active_null_falls_back_to_listing_facts(missing):
    frame = pd.DataFrame(
        dict(
            ts_code=["A", "B", "C"],
            trade_date=[date(2026, 1, 5)] * 3,
            list_date=[date(2020, 1, 1), date(2026, 1, 6), date(2020, 1, 1)],
            delist_date=[None, None, date(2026, 1, 5)],
            close=[10.0] * 3,
            amount_ma20=[100000.0] * 3,
            trade_status_present=[True] * 3,
            is_active=[missing] * 3,
            is_st=[missing] * 3,
            is_suspended=[missing] * 3,
            st_status_unknown=[missing] * 3,
        )
    )
    result = _assign_eligibility(frame, FactorConfig(min_listed_trading_days=1))
    assert result.exclusion_reason.isna().tolist() == [True, False, True]
    assert result.iloc[1].exclusion_reason == "NOT_ACTIVE_ON_DATE"


def test_duplicate_trade_status_fails_instead_of_multiplying_rows():
    kwargs = factor_inputs()
    status = status_for(kwargs["daily"])
    with pytest.raises(ValueError, match="TRADE_STATUS_DUPLICATE_KEY"):
        calculate_stock_factors(
            **kwargs, config=FactorConfig(), trade_status=pd.concat([status, status.iloc[:1]])
        )


@pytest.mark.parametrize("value", ["False", "True", 2, [], {"x": True}])
def test_invalid_boolean_rejected(value):
    kwargs = factor_inputs()
    status = status_for(kwargs["daily"]).astype({"is_st": object})
    status.at[0, "is_st"] = value
    with pytest.raises(ValueError, match="TRADE_STATUS_INVALID_BOOLEAN"):
        calculate_stock_factors(**kwargs, config=FactorConfig(), trade_status=status)


@pytest.mark.parametrize("missing", [None, np.nan, pd.NA])
@pytest.mark.parametrize(
    "column",
    [
        "drawdown_high60",
        "return20",
        "return20_lag5",
        "ma20_turn",
        "higher_low",
        "rps20_delta5",
        "rps60_delta5",
        "cross_above_ma20",
        "price_recovery",
        "volatility_contraction",
        "volume_structure",
        "primary_theme_heat",
        "industry_heat",
        "position_score",
        "rps60",
        "trend_score",
    ],
)
def test_reason_codes_null_field_has_no_unsupported_reason(column, missing):
    row = pd.Series({column: missing}, dtype=object)
    assert opportunity._reason_codes(row) == {"codes": []}


@pytest.mark.parametrize("missing", [None, np.nan, pd.NA])
def test_real_opportunity_entrypoint_early_indicators_and_nullable_booleans(missing):
    kwargs = opportunity_inputs()
    for column in (
        "rps20_delta5",
        "rps60_delta5",
        "higher_low",
        "cross_above_ma20",
        "cross_above_ma60",
        "atr20_pct",
        "amount_ratio20",
        "ma20",
        "ma60",
    ):
        kwargs["factors"][column] = missing
    result = opportunity.calculate_opportunities(
        **kwargs,
        config=opportunity.OpportunityConfig.from_dict({}),
    )
    json.dumps(result.to_dict(orient="records"), default=str, allow_nan=False)
    assert len(result) == 3
    for reasons in result.reason_codes:
        assert not {"HIGHER_LOW", "CROSS_MA20", "RPS20_RECOVERING", "RPS60_RECOVERING"} & set(
            reasons["codes"]
        )


@pytest.mark.parametrize("missing", [None, np.nan, pd.NA])
def test_extension_risk_volume_null_and_stage_bool(missing):
    row = pd.Series(
        dict(state="S4", adj_close=11.0, ma20=10.0, ma60=9.0, amount_ratio20=missing), dtype=object
    )
    assert opportunity._extension_risk(row, opportunity.PositionConfig()) == "NORMAL"
    row = pd.Series(dict(state="S3", is_new_state=missing), dtype=object)
    assert opportunity._stage(row, opportunity.OpportunityConfig.from_dict({})) == "RIGHT_SIDE"


@pytest.mark.parametrize("bad", ["bad", float("inf"), -float("inf"), [], {"x": 1}])
def test_invalid_opportunity_numeric_is_unavailable(bad):
    assert opportunity._reason_codes(pd.Series(dict(rps60=bad), dtype=object)) == {"codes": []}


@pytest.mark.parametrize("missing", [None, np.nan, pd.NA])
def test_all_nullable_status_flags_and_missing_presence_are_stable(missing):
    frame = pd.DataFrame(
        dict(
            ts_code=["A", "B", "C"],
            trade_date=[date(2026, 1, 5)] * 3,
            list_date=[date(2020, 1, 1)] * 3,
            delist_date=[None] * 3,
            close=[10.0] * 3,
            amount_ma20=[100000.0] * 3,
            trade_status_present=pd.Series([True, missing, False], dtype=object),
            is_st=pd.Series([False, missing, False], dtype="boolean"),
            is_suspended=pd.Series([False, missing, False], dtype="boolean"),
            st_status_unknown=pd.Series([True, missing, False], dtype="boolean"),
        )
    )
    result = _assign_eligibility(frame, FactorConfig(min_listed_trading_days=1))
    assert result.exclusion_reason.tolist() == [
        "ST_STATUS_UNKNOWN",
        "TRADE_STATUS_MISSING",
        "TRADE_STATUS_MISSING",
    ]
    assert result.trade_status_present.dtype == bool


def test_empty_and_single_day_factor_boundaries():
    kwargs = factor_inputs()
    kwargs["daily"] = kwargs["daily"].iloc[:0]
    assert calculate_stock_factors(**kwargs, config=FactorConfig()).empty
    kwargs = factor_inputs()
    kwargs["daily"] = kwargs["daily"].tail(1)
    kwargs["adj_factor"] = kwargs["adj_factor"].tail(1)
    result = calculate_stock_factors(**kwargs, config=FactorConfig(), trade_status=pd.DataFrame())
    assert len(result) == 1
    assert "TRADE_STATUS_MISSING" in result.iloc[0].exclusion_reason
    assert result.iloc[0].rps20 is None


@pytest.mark.parametrize("stage", ["LEFT_REVERSAL", "RIGHT_SIDE", "TREND"])
@pytest.mark.parametrize("missing", [None, np.nan, pd.NA])
def test_missing_scores_never_become_zero_or_fake_rank(stage, missing):
    row = pd.Series(
        dict(
            opportunity_stage=stage,
            left_reversal_score=missing,
            right_side_score=missing,
            context_score=missing,
            market_score=missing,
            trend_rank_score=missing,
            position_score=missing,
        ),
        dtype=object,
    )
    assert opportunity._opportunity_score(row, opportunity.OpportunityConfig.from_dict({})) is None
