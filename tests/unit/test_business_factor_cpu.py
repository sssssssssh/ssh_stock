from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest
from app.services.factors.engine import (
    FactorConfig,
    _assign_eligibility,
    _max_drawdown,
    _max_drawdown_array,
    calculate_stock_factors,
)
from pandas.testing import assert_frame_equal, assert_series_equal

from tests.unit.test_factor_engine import _fixture_data, _trade_status


@pytest.mark.parametrize("values", [
    [], [0] * 60, [-1, -2, 0, 1, 2, -3] * 10,
    [1, 2, 3, np.nan] * 15, [np.inf, 1, -np.inf] * 20,
    list(np.random.default_rng(17).normal(size=60)),
])
def test_numpy_drawdown_matches_original_including_zero_negative_nan(values):
    expected = _max_drawdown(pd.Series(values, dtype=float))
    actual = _max_drawdown_array(np.asarray(values, dtype=float))
    if np.isnan(expected):
        assert np.isnan(actual)
    else:
        assert actual == expected


@pytest.mark.parametrize("exclude_st", [True, False])
def test_vectorized_listing_and_nullable_status_boundaries(exclude_st):
    day = date(2025, 1, 2)
    rows = []
    for listed in [None, pd.NaT, day, date(2025, 1, 3), date(2025, 1, 1)]:
        for delisted in [None, pd.NaT, day, date(2025, 1, 1), date(2025, 1, 3)]:
            for active in [None, True, False, pd.NA]:
                rows.append(dict(trade_date=day, ts_code="TEST", list_date=listed,
                    delist_date=delisted, trade_status_present=True, is_active=active,
                    is_st=False, is_suspended=False, st_status_unknown=False,
                    close=20, amount_ma20=1000000))
    frame = pd.DataFrame(rows)
    config = replace(FactorConfig(), exclude_st=exclude_st)
    assert_frame_equal(_assign_eligibility(frame.copy(), config),
                       _assign_eligibility(frame.copy(), config, optimize_cpu=True),
                       check_exact=True)


@pytest.mark.parametrize("missing", [False, True])
def test_factor_full_field_dtype_and_cross_market_rank_golden(missing):
    daily, adj, basic, index = _fixture_data()
    # Distinct returns, NaN/zero, missing adjustment, listing/delisting boundaries.
    if missing:
        daily.loc[daily.index[::71], "close"] = np.nan
        daily.loc[daily.index[::113], "low"] = 0
        adj = adj.drop(adj.index[::97])
        basic.loc[0, "list_date"] = None
        basic.loc[1, "delist_date"] = daily.trade_date.iloc[-5]
    status = _trade_status(daily, {"000003.SZ"})
    status["is_active"] = status["is_active"].astype("boolean")
    status.loc[status.index[::13], "is_active"] = None
    status.loc[status.index[::17], "is_suspended"] = True
    arguments = dict(daily=daily, adj_factor=adj, stock_basic=basic,
        index_daily=index, benchmark_code="000300.SH", start=daily.trade_date.iloc[0],
        end=daily.trade_date.iloc[-1], trade_status=status, config=FactorConfig())
    expected = calculate_stock_factors(**arguments)
    actual = calculate_stock_factors(**arguments, optimize_cpu=True)
    assert_frame_equal(actual, expected, check_exact=True)
    for column in ("rps20", "rps60", "rps120", "rps250"):
        assert_series_equal(actual[column], expected[column], check_exact=True)


def test_factor_compute_checkpoint_does_not_return_partial_result():
    from app.services.job_execution import JobCancelled

    daily, adj, basic, index = _fixture_data()
    calls = []

    def cancelled():
        calls.append(1)
        if len(calls) == 3:
            raise JobCancelled("synthetic cancellation")

    with pytest.raises(JobCancelled):
        calculate_stock_factors(daily, adj, basic, index, "000300.SH",
            daily.trade_date.iloc[0], daily.trade_date.iloc[-1], FactorConfig(),
            trade_status=_trade_status(daily), optimize_cpu=True, check_cancelled=cancelled)
    assert len(calls) == 3
