from datetime import date

import numpy as np
import pandas as pd
import pytest
from app.services.ingestion.normalizers import normalize_stock_suspend
from loguru import logger


def frame(**changes):
    row = dict(trade_date="20240913", ts_code="000001.SZ", suspend_type="S",
               suspend_timing="全天")
    row.update(changes)
    return pd.DataFrame([row], dtype=object)


@pytest.mark.parametrize("value", [None, float("nan"), np.nan, pd.NA, "", " ", "\t\n"])
def test_suspend_missing_descriptions_become_null(value):
    assert normalize_stock_suspend(frame(suspend_timing=value))[0]["suspend_timing"] is None


def test_suspend_missing_description_field_becomes_null():
    assert normalize_stock_suspend(frame().drop(columns="suspend_timing"))[0][
        "suspend_timing"
    ] is None


@pytest.mark.parametrize("value", ["0", "无", "全天", " 上午 09:30 - 10:00； 午后 ",
                                  "中" * 32, "中" * 33, "文; A " * 20, "文; A " * 100])
def test_suspend_valid_descriptions_are_not_trimmed_or_truncated(value):
    result = normalize_stock_suspend(frame(suspend_timing=value))
    assert result[0]["suspend_timing"] == value
    assert result[0]["trade_date"] == date(2024, 9, 13)
    assert result[0]["ts_code"] == "000001.SZ"


@pytest.mark.parametrize("kind", ["S", "R"])
def test_suspend_types_preserve_business_identity(kind):
    assert normalize_stock_suspend(frame(suspend_type=kind))[0]["suspend_type"] == kind


@pytest.mark.parametrize("value", [None, np.nan, pd.NA, "", " ", "X", "s", " S", 1, []])
def test_suspend_invalid_or_missing_type_is_not_defaulted_to_s(value):
    with pytest.raises(ValueError, match="SUSPEND_INVALID"):
        normalize_stock_suspend(frame(suspend_type=value))


def test_suspend_absent_type_is_rejected():
    with pytest.raises(ValueError, match="SUSPEND_INVALID"):
        normalize_stock_suspend(frame().drop(columns="suspend_type"))


@pytest.mark.parametrize("value", [[], {}, ("全天",), {"全天"}, np.array([1, 2]),
                                  pd.Series([1]), 123, 0.5, True, date(2024, 9, 13)])
def test_suspend_complex_or_nontext_description_is_rejected(value):
    with pytest.raises(ValueError, match="SUSPEND_INVALID"):
        normalize_stock_suspend(frame(suspend_timing=value))


@pytest.mark.parametrize("value", [None, np.nan, pd.NA, "", " "])
def test_suspend_missing_primary_date_falls_back_without_boolean_na(value):
    rows = normalize_stock_suspend(frame(trade_date=value, suspend_date="20240913"))
    assert rows[0]["trade_date"] == date(2024, 9, 13)


def test_suspend_date_alias_and_business_date_are_supported():
    assert normalize_stock_suspend(frame(suspend_date="20240913").drop(columns="trade_date"))[
        0
    ]["trade_date"] == date(2024, 9, 13)
    assert normalize_stock_suspend(frame(trade_date=date(2024, 9, 13)))[0][
        "trade_date"
    ] == date(2024, 9, 13)


@pytest.mark.parametrize("changes", [
    {"trade_date": None}, {"trade_date": "20240230"}, {"trade_date": "2024-09-13"},
    {"trade_date": [], "suspend_date": "20240913"}, {"ts_code": None},
    {"ts_code": np.nan}, {"ts_code": pd.NA}, {"ts_code": " "},
    {"ts_code": " 000001.SZ"}, {"ts_code": "x" * 17}, {"ts_code": []},
])
def test_suspend_invalid_keys_are_not_dropped_or_rewritten(changes):
    with pytest.raises(ValueError, match="SUSPEND_INVALID"):
        normalize_stock_suspend(frame(**changes))


def test_suspend_diagnostics_are_aggregate_and_do_not_log_descriptions():
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)))
    try:
        rows = normalize_stock_suspend(pd.DataFrame([
            dict(trade_date="20240913", ts_code="T1.SZ", suspend_type="S",
                 suspend_timing=np.nan),
            dict(trade_date="20240913", ts_code="T2.SZ", suspend_type="R",
                 suspend_timing="private-description-must-not-log" * 3),
        ]))
    finally:
        logger.remove(sink)
    assert len(rows) == 2
    output = "".join(messages)
    assert "normalized_null_count=1" in output
    assert "over_32_count=1" in output
    assert "private-description" not in output


def test_suspend_empty_successful_response_remains_empty():
    assert normalize_stock_suspend(pd.DataFrame()) == []
