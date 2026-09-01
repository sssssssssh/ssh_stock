from datetime import date

import pandas as pd
from app.services.sector.engine import _prepare_member_factors


def test_sector_membership_uses_historical_valid_window() -> None:
    factors = pd.DataFrame(
        [
            {
                "trade_date": date(2021, 6, 1),
                "ts_code": "000001.SZ",
                "adj_close": 10,
                "ma20": 9,
                "ma60": 8,
                "return1": 0.01,
                "return3": 0.02,
                "return5": 0.03,
                "return20": 0.10,
                "breakout20": True,
                "rps60": 80,
                "amount_ma20": 1000,
                "amount_ratio20": 1.0,
                "eligible": True,
            },
            {
                "trade_date": date(2023, 6, 1),
                "ts_code": "000001.SZ",
                "adj_close": 12,
                "ma20": 11,
                "ma60": 10,
                "return1": 0.01,
                "return3": 0.02,
                "return5": 0.03,
                "return20": 0.10,
                "breakout20": True,
                "rps60": 80,
                "amount_ma20": 1000,
                "amount_ratio20": 1.0,
                "eligible": True,
            },
        ]
    )
    members = pd.DataFrame(
        [
            {
                "sector_id": 1,
                "ts_code": "000001.SZ",
                "valid_from": date(2020, 1, 1),
                "valid_to": date(2021, 12, 31),
                "is_latest": False,
            },
            {
                "sector_id": 2,
                "ts_code": "000001.SZ",
                "valid_from": date(2022, 1, 1),
                "valid_to": None,
                "is_latest": True,
            },
        ]
    )

    prepared = _prepare_member_factors(factors, members)
    sector_by_date = prepared.set_index("trade_date")["sector_id"].to_dict()

    assert sector_by_date[date(2021, 6, 1)] == 1
    assert sector_by_date[date(2023, 6, 1)] == 2
