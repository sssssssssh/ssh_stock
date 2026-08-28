from datetime import date

import pandas as pd
from app.services.sector import SectorConfig, calculate_sector_factors


def _sector_fixture() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, date]:
    dates = pd.bdate_range("2025-01-01", periods=30).date
    factors = []
    members = []
    for sector_id, codes, drift in [
        (1, ["000001.SZ", "000002.SZ"], 0.02),
        (2, ["000003.SZ", "000004.SZ"], -0.01),
    ]:
        for ts_code in codes:
            members.append(
                {
                    "sector_id": sector_id,
                    "ts_code": ts_code,
                    "valid_from": date(2020, 1, 1),
                    "valid_to": None,
                    "is_latest": True,
                }
            )
        for idx, trade_date in enumerate(dates):
            for code_idx, ts_code in enumerate(codes):
                strength = drift + code_idx * 0.005 + idx * 0.0005
                factors.append(
                    {
                        "trade_date": trade_date,
                        "ts_code": ts_code,
                        "adj_close": 20 + idx,
                        "ma20": 19,
                        "ma60": 18 if sector_id == 1 else 22,
                        "return1": strength,
                        "return3": strength * 2,
                        "return5": strength * 3,
                        "return20": strength * 6,
                        "breakout20": sector_id == 1,
                        "rps60": 90 if sector_id == 1 else 40,
                        "amount_ma20": 100000,
                        "amount_ratio20": 1.2 if sector_id == 1 else 0.8,
                        "eligible": True,
                    }
                )

    index_daily = pd.DataFrame(
        [
            {"trade_date": trade_date, "ts_code": "000300.SH", "close": 3000 + idx}
            for idx, trade_date in enumerate(dates)
        ]
    )
    return pd.DataFrame(factors), pd.DataFrame(members), index_daily, dates[-1]


def test_calculate_sector_factors_ranks_hot_sector_first() -> None:
    factors, members, index_daily, target = _sector_fixture()

    result = calculate_sector_factors(
        factors=factors,
        members=members,
        index_daily=index_daily,
        start=target,
        end=target,
        config=SectorConfig(),
    )

    ranked = result.sort_values("heat_rank")
    assert ranked.iloc[0]["sector_id"] == 1
    assert ranked.iloc[0]["heat_rank"] == 1
    assert ranked.iloc[0]["heat_score"] > ranked.iloc[1]["heat_score"]
    assert ranked.iloc[0]["lifecycle"] in {"MAIN_UP", "CLIMAX", "HEATING"}


def test_calculate_sector_factors_filters_invalid_membership() -> None:
    factors, members, index_daily, target = _sector_fixture()
    members.loc[members["ts_code"] == "000002.SZ", "valid_to"] = date(2024, 12, 31)

    result = calculate_sector_factors(
        factors=factors,
        members=members,
        index_daily=index_daily,
        start=target,
        end=target,
        config=SectorConfig(),
    )

    sector_one = result[result["sector_id"] == 1].iloc[0]
    assert sector_one["member_count"] == 1
    assert sector_one["eligible_member_count"] == 1


def test_calculate_sector_factors_allows_missing_moving_averages() -> None:
    factors, members, index_daily, target = _sector_fixture()
    factors.loc[factors["ts_code"] == "000001.SZ", "ma20"] = None
    factors.loc[factors["ts_code"] == "000001.SZ", "ma60"] = None

    result = calculate_sector_factors(
        factors=factors,
        members=members,
        index_daily=index_daily,
        start=target,
        end=target,
        config=SectorConfig(),
    )

    assert not result.empty
    assert result[result["sector_id"] == 1].iloc[0]["eligible_member_count"] == 2
