from datetime import date

import pandas as pd
import pytest
from app.services.provider_smoke import run_provider_smoke_test


class _SmokeProvider:
    def get_trade_calendar(self, start, end):
        return pd.DataFrame(
            [{"cal_date": "20260914", "is_open": 1}, {"cal_date": "20260915", "is_open": 1}]
        )

    def get_stock_basic(self):
        return pd.DataFrame([{"ts_code": "000001.SZ", "list_status": "L", "list_date": "19910403"}])

    def get_daily(self, trade_date):
        return pd.DataFrame([{"trade_date": trade_date, "ts_code": "000001.SZ", "close": 10}])

    def get_adj_factor(self, trade_date):
        return pd.DataFrame([{"trade_date": trade_date, "ts_code": "000001.SZ", "adj_factor": 1}])

    def get_daily_basic(self, trade_date):
        return pd.DataFrame(
            [
                {
                    "trade_date": trade_date,
                    "ts_code": "000001.SZ",
                    "close": 10,
                    "total_mv": 100,
                    "circ_mv": 80,
                }
            ]
        )

    def get_index_daily(self, trade_date, codes):
        return pd.DataFrame(
            [{"trade_date": trade_date, "ts_code": codes[0], "close": 10, "pre_close": 9}]
        )

    def get_sector_classification(self):
        return pd.DataFrame([{"index_code": "801010.SI", "level": "L1"}])

    def get_sector_members(self):
        return pd.DataFrame([{"l1_code": "801010.SI", "in_date": "20200101"}])

    def get_stock_st(self, trade_date):
        return pd.DataFrame(columns=["trade_date", "ts_code"])

    def get_suspend_daily(self, trade_date):
        return pd.DataFrame(columns=["ts_code", "trade_date", "suspend_type"])

    def get_stock_limit(self, trade_date):
        return pd.DataFrame(
            [
                {
                    "trade_date": trade_date,
                    "ts_code": "000001.SZ",
                    "up_limit": 11,
                    "down_limit": 9,
                }
            ]
        )

    def get_ths_concepts(self):
        return pd.DataFrame([{"ts_code": "885001.TI", "name": "概念", "type": "N"}])

    def get_ths_daily(self, trade_date):
        return pd.DataFrame(
            [
                {
                    "ts_code": "885001.TI",
                    "trade_date": trade_date,
                    "close": 100,
                    "turnover_rate": 1,
                }
            ]
        )

    def get_ths_concept_members(self, theme_codes):
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "con_code": theme_codes[0],
                    "con_name": "概念",
                }
            ]
        )

    def get_ths_concept_moneyflow(self, trade_date):
        return pd.DataFrame([{"ts_code": "885001.TI", "trade_date": trade_date, "net_amount": 1}])

    def get_limit_concept_list(self, trade_date):
        return pd.DataFrame(
            [
                {
                    "ts_code": "885001.TI",
                    "trade_date": trade_date,
                    "up_nums": 1,
                    "cons_nums": 0,
                }
            ]
        )


def test_provider_smoke_test_checks_all_required_apis() -> None:
    results = run_provider_smoke_test(
        _SmokeProvider(),
        date(2026, 9, 15),
        index_codes=["000300.SH"],
    )

    assert [result.api_name for result in results] == [
        "trade_cal",
        "stock_basic",
        "daily",
        "adj_factor",
        "daily_basic",
        "index_daily",
        "index_classify",
        "index_member_all",
        "stock_st",
        "suspend_d",
        "stk_limit",
        "ths_index",
        "ths_daily",
        "ths_member",
        "moneyflow_cnt_ths",
        "limit_cpt_list",
        "theme_capability",
    ]
    assert results[-1].status == "FULL"


def test_provider_smoke_test_rejects_missing_required_fields() -> None:
    provider = _SmokeProvider()
    provider.get_daily = lambda trade_date: pd.DataFrame([{"ts_code": "000001.SZ"}])

    with pytest.raises(ValueError, match="daily missing required fields"):
        run_provider_smoke_test(
            provider,
            date(2026, 9, 15),
            index_codes=["000300.SH"],
        )


def test_provider_smoke_test_degrades_optional_permission_errors() -> None:
    provider = _SmokeProvider()
    provider.get_ths_concept_moneyflow = lambda trade_date: (_ for _ in ()).throw(
        RuntimeError("permission denied")
    )

    results = run_provider_smoke_test(
        provider,
        date(2026, 9, 15),
        index_codes=["000300.SH"],
    )

    by_name = {result.api_name: result for result in results}
    assert by_name["moneyflow_cnt_ths"].status == "PERMISSION_UNAVAILABLE"
    assert by_name["theme_capability"].status == "NO_MONEYFLOW"
