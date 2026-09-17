from datetime import date

import app.services.ingestion.service as ingestion_module
import pandas as pd
import pytest
from app.providers.tushare_provider import TushareProvider
from app.services.ingestion.normalizers import (
    normalize_theme_daily,
    normalize_theme_limit,
    normalize_theme_members,
    normalize_theme_moneyflow,
    normalize_themes,
)
from app.services.ingestion.service import IngestionService


def test_theme_normalizers_use_verified_provider_fields() -> None:
    target = date(2026, 9, 16)
    themes = normalize_themes(
        pd.DataFrame(
            [
                {
                    "ts_code": "885001.TI",
                    "name": "机器人",
                    "count": 20,
                    "exchange": "A",
                    "list_date": "20200101",
                    "type": "N",
                }
            ]
        ),
        target,
    )
    members = normalize_theme_members(
        pd.DataFrame([{"ts_code": "885001.TI", "con_code": "000001.SZ", "con_name": "平安"}]),
        target,
    )
    daily = normalize_theme_daily(
        pd.DataFrame([{"ts_code": "885001.TI", "trade_date": "20260916", "close": 100}])
    )
    flow = normalize_theme_moneyflow(
        pd.DataFrame(
            [
                {
                    "ts_code": "885001.TI",
                    "trade_date": "20260916",
                    "industry_index": 100,
                    "pct_change_stock": 3.2,
                    "net_amount": 500,
                }
            ]
        )
    )
    limits = normalize_theme_limit(
        pd.DataFrame(
            [
                {
                    "ts_code": "885001.TI",
                    "trade_date": "20260916",
                    "up_nums": 5,
                    "cons_nums": 2,
                    "rank": 1,
                }
            ]
        )
    )

    assert themes[0]["theme_type"] == "CONCEPT"
    assert members[0]["is_new"] is None
    assert daily[0]["trade_date"] == target
    assert flow[0]["theme_index"] == 100
    assert flow[0]["lead_stock_pct_change"] == 3.2
    assert limits[0]["up_nums"] == 5


def test_member_fetch_fails_whole_snapshot_when_any_shard_fails(monkeypatch) -> None:
    provider = TushareProvider.__new__(TushareProvider)

    def fake_call(api_name: str, **kwargs):
        if kwargs["ts_code"] == "BAD.TI":
            raise RuntimeError("provider shard failed")
        return pd.DataFrame(
            [{"ts_code": kwargs["ts_code"], "con_code": "000001.SZ", "con_name": "平安"}]
        )

    monkeypatch.setattr(provider, "_call", fake_call)

    with pytest.raises(RuntimeError, match="provider shard failed"):
        provider.get_ths_concept_members(["GOOD.TI", "BAD.TI"])


def test_member_snapshot_does_not_pass_when_a_theme_is_missing(monkeypatch) -> None:
    class Result:
        def scalars(self):
            return self

        def all(self):
            return ["A.TI", "B.TI"]

    class Db:
        commits = 0
        rollbacks = 0

        def execute(self, statement):
            return Result()

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    class Provider:
        def get_ths_concept_members(self, concept_codes):
            return pd.DataFrame(
                [{"ts_code": "A.TI", "con_code": "000001.SZ", "con_name": "Stock"}]
            )

    quality = []
    monkeypatch.setattr(
        ingestion_module,
        "persist_coverage_result",
        lambda db, result, **kwargs: quality.append(result),
    )
    db = Db()

    with pytest.raises(ValueError, match="snapshot incomplete"):
        IngestionService(db, Provider()).sync_ths_theme_member_snapshot(date(2026, 9, 17))

    assert db.rollbacks == 1
    assert db.commits == 1
    assert quality[0].status == "ERROR"
    assert quality[0].expected_rows == 2
