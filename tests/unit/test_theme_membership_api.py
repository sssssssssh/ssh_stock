from datetime import date
from types import SimpleNamespace

import app.api.v1.opportunities as opportunities_api
import app.api.v1.themes as themes_api
import pandas as pd
from app.services.theme.membership import ThemeMembershipResolution
from sqlalchemy.dialects import postgresql


def _resolution(target: date) -> ThemeMembershipResolution:
    return ThemeMembershipResolution(
        members=pd.DataFrame(
            [
                {
                    "trade_date": target,
                    "theme_code": "T",
                    "ts_code": "000001.SZ",
                    "stock_name": "A",
                    "source": "THS",
                    "membership_source": "INTERVAL",
                }
            ]
        ),
        available_dates={target},
        context_by_date={
            target: {
                "available": True,
                "coverage": 1.0,
                "mode": "INTERVAL",
                "source_snapshot_date": None,
            }
        },
    )


def test_theme_members_api_passes_resolver_codes_to_opportunity_query(monkeypatch) -> None:
    target = date(2026, 9, 24)
    resolution = _resolution(target)
    captured: dict[str, object] = {}
    monkeypatch.setattr(themes_api, "resolve_theme_memberships", lambda *args: resolution)

    def capture_codes(db, codes, *args, **kwargs):
        captured["codes"] = codes
        return []

    monkeypatch.setattr(themes_api, "_member_opportunities", capture_codes)
    monkeypatch.setattr(themes_api, "_member_count", lambda *args, **kwargs: 1)

    class Db:
        def get(self, model, key):
            return SimpleNamespace(theme_code=key)

    response = themes_api.members("T", target, db=Db())

    assert captured["codes"] == {"000001.SZ"}
    assert response["meta"]["member_context_mode"] == "INTERVAL"


def test_opportunity_theme_filter_uses_resolver_codes(monkeypatch) -> None:
    target = date(2026, 9, 24)
    resolution = _resolution(target)
    monkeypatch.setattr(
        opportunities_api, "resolve_theme_memberships", lambda *args: resolution
    )

    class Result:
        def all(self):
            return []

        def scalar_one(self):
            return 0

    class Db:
        def __init__(self):
            self.statements = []

        def execute(self, statement):
            self.statements.append(statement)
            return Result()

    db = Db()
    response = opportunities_api._pool(
        db,
        target,
        [],
        "T",
        None,
        30,
        0,
        opportunities_api.desc(opportunities_api.StockOpportunityDaily.opportunity_score),
    )
    sql = str(
        db.statements[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )

    assert "000001.SZ" in sql
    assert response["meta"]["member_context_mode"] == "INTERVAL"
