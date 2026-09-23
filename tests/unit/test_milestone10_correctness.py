from datetime import date, timedelta
from types import SimpleNamespace

import app.jobs.catchup_job as catchup_module
import app.services.ingestion.service as ingestion_module
import app.services.opportunity.engine as opportunity_module
import pandas as pd
import pytest
from app.jobs.catchup_job import CatchUpJob
from app.models.market_data import Theme, ThemeDaily, ThemeLimitDaily, ThemeMoneyflowDaily
from app.providers.tushare_provider import TushareProvider
from app.services.ingestion.service import IngestionService
from app.services.opportunity.engine import _left_scores
from app.services.quality.opportunity_quality import check_opportunity_quality
from app.services.quality.theme_quality import expected_theme_codes_on_date
from app.services.theme.engine import ThemeConfig, _lifecycle, _merge_optional_sources
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def test_historical_theme_universe_uses_catalog_dates() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Theme.__table__.create(engine)
    with Session(engine) as db:
        db.add_all(
            [
                Theme(
                    theme_code="OLD.TI", source="THS", name="Old", theme_type="CONCEPT",
                    is_active=False, list_date=date(2020, 1, 1),
                    first_seen_date=date(2026, 9, 1), last_seen_date=date(2026, 9, 15),
                ),
                Theme(
                    theme_code="NEW.TI", source="THS", name="New", theme_type="CONCEPT",
                    is_active=True, list_date=date(2026, 9, 18),
                    first_seen_date=date(2026, 9, 18), last_seen_date=date(2026, 9, 21),
                ),
            ]
        )
        db.flush()
        assert expected_theme_codes_on_date(db, date(2026, 9, 15)) == {"OLD.TI"}
        assert expected_theme_codes_on_date(db, date(2026, 9, 16)) == set()
        assert expected_theme_codes_on_date(db, date(2026, 9, 18)) == {"NEW.TI"}
    engine.dispose()


@pytest.mark.parametrize(
    ("list_date", "first_seen", "last_seen", "active", "target", "expected"),
    [
        (date(2020, 1, 1), date(2026, 9, 21), date(2026, 9, 21), True,
         date(2026, 5, 1), True),
        (date(2026, 9, 18), date(2026, 9, 18), date(2026, 9, 21), True,
         date(2026, 9, 15), False),
        (None, date(2026, 9, 21), date(2026, 9, 21), True,
         date(2026, 9, 20), False),
        (None, date(2026, 9, 21), date(2026, 9, 21), True,
         date(2026, 9, 21), True),
        (date(2020, 1, 1), date(2026, 9, 1), date(2026, 9, 15), False,
         date(2026, 9, 10), True),
        (date(2020, 1, 1), date(2026, 9, 1), date(2026, 9, 15), False,
         date(2026, 9, 16), False),
        (date(2020, 1, 1), date(2026, 9, 21), None, True,
         date(2026, 9, 10), True),
    ],
)
def test_theme_board_universe_boundaries(
    list_date, first_seen, last_seen, active, target, expected
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Theme.__table__.create(engine)
    with Session(engine) as db:
        db.add(Theme(
            theme_code="A.TI", source="THS", name="A", theme_type="CONCEPT",
            list_date=list_date, first_seen_date=first_seen,
            last_seen_date=last_seen, is_active=active,
        ))
        db.flush()
        assert ("A.TI" in expected_theme_codes_on_date(db, target)) is expected
    engine.dispose()


def test_theme_board_universe_covers_historical_backfill_window() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Theme.__table__.create(engine)
    with Session(engine) as db:
        db.add(Theme(
            theme_code="A.TI", source="THS", name="A", theme_type="CONCEPT",
            list_date=date(2020, 1, 1), first_seen_date=date(2026, 9, 21),
            last_seen_date=date(2026, 9, 21), is_active=True,
        ))
        db.flush()
        start = date(2026, 5, 1)
        assert all(
            "A.TI" in expected_theme_codes_on_date(db, start + timedelta(days=offset))
            for offset in range(120)
        )
    engine.dispose()


def test_historical_theme_daily_sync_uses_list_date_before_first_seen(monkeypatch) -> None:
    target = date(2026, 5, 1)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Theme.__table__.create(engine)
    ThemeDaily.__table__.create(engine)
    with Session(engine) as db:
        db.add(Theme(
            theme_code="A.TI", source="THS", name="A", theme_type="CONCEPT",
            is_active=True, list_date=date(2020, 1, 1),
            first_seen_date=date(2026, 9, 21), last_seen_date=date(2026, 9, 21),
        ))
        db.commit()
        quality = []
        monkeypatch.setattr(
            ingestion_module, "persist_coverage_result",
            lambda session, result: quality.append(result),
        )
        monkeypatch.setattr(
            ingestion_module, "reconcile_daily_snapshot", lambda *args, **kwargs: set()
        )
        monkeypatch.setattr(
            ingestion_module, "record_dirty_range", lambda *args, **kwargs: None
        )

        def insert_rows(session, model, rows, keys):
            session.add_all(model(**row) for row in rows)
            return len(rows)

        monkeypatch.setattr(ingestion_module, "upsert_rows", insert_rows)
        provider = SimpleNamespace(get_ths_daily=lambda day: pd.DataFrame([
            {"ts_code": "A.TI", "trade_date": "20260501", "close": 10}
        ]))
        assert IngestionService(db, provider).sync_theme_daily(target) == 1
        assert db.execute(select(ThemeDaily.theme_code)).scalar_one() == "A.TI"
        assert quality[0].status == "PASS"
    engine.dispose()


def test_historical_theme_catchup_repair_uses_list_date(monkeypatch) -> None:
    target = date(2026, 5, 1)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Theme.__table__.create(engine)
    with Session(engine) as db:
        db.add(Theme(
            theme_code="A.TI", source="THS", name="A", theme_type="CONCEPT",
            is_active=True, list_date=date(2020, 1, 1),
            first_seen_date=date(2026, 9, 21), last_seen_date=date(2026, 9, 21),
        ))
        db.flush()
        job = CatchUpJob.__new__(CatchUpJob)
        job.db = db
        monkeypatch.setattr(catchup_module, "theme_raw_needs_repair", lambda *args: True)
        assert job._theme_repair_dates([target]) == [target]
    engine.dispose()


@pytest.mark.parametrize(
    ("source_status", "source_actual", "persisted", "factor", "expected"),
    [
        ("WARNING", 110, 90, 90, "PASS"),
        ("PASS", 100, 100, 80, "ERROR"),
        ("ERROR", 110, 90, 90, "SKIPPED"),
    ],
)
def test_theme_factor_quality_uses_persisted_daily_rows(
    source_status, source_actual, persisted, factor, expected
) -> None:
    class QualityDb:
        def __init__(self):
            self.queried = []

        def execute(self, statement):
            table = statement.get_final_froms()[0].name
            self.queried.append(table)
            if table == "data_quality_daily":
                return SimpleNamespace(
                    first=lambda: SimpleNamespace(status=source_status, actual_rows=source_actual)
                )
            counts = {
                "stock_state_daily": 1,
                "stock_opportunity_daily": 1,
                "theme_daily": persisted,
                "theme_factor_daily": factor,
            }
            return SimpleNamespace(scalar_one=lambda: counts[table])

    db = QualityDb()
    result = check_opportunity_quality(
        db, date(2026, 9, 21), strategy_hash="strategy", opportunity_hash="opportunity",
        algo_version="v1.1", config={},
    )
    assert result.results["theme_factor_vs_theme_daily"] == expected
    assert result.counts["theme_daily"] == (persisted if source_status != "ERROR" else 0)
    assert ("theme_daily" in db.queried) is (source_status != "ERROR")


def test_catalog_disappearance_preserves_last_real_seen_date(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Theme.__table__.create(engine)
    with Session(engine) as db:
        db.add(Theme(
            theme_code="OLD.TI", source="THS", name="Old", theme_type="CONCEPT",
            is_active=True, first_seen_date=date(2026, 9, 1),
            last_seen_date=date(2026, 9, 15),
        ))
        db.commit()
        provider = SimpleNamespace(get_ths_concepts=lambda: pd.DataFrame([
            {"ts_code": "NEW.TI", "name": "New", "type": "N"}
        ]))
        monkeypatch.setattr(
            ingestion_module, "upsert_rows", lambda *args, **kwargs: 1
        )
        monkeypatch.setattr(
            ingestion_module, "_persist_theme_quality", lambda *args, **kwargs: None
        )
        IngestionService(db, provider).sync_ths_themes(date(2026, 9, 18))
        old = db.execute(select(Theme).where(Theme.theme_code == "OLD.TI")).scalar_one()
        assert old.is_active is False
        assert old.last_seen_date == date(2026, 9, 15)
    engine.dispose()


def test_historical_theme_refresh_keeps_inactive_row(monkeypatch) -> None:
    target = date(2026, 9, 15)
    provider = SimpleNamespace(get_ths_daily=lambda day: pd.DataFrame([
        {"ts_code": "OLD.TI", "trade_date": "20260915", "close": 10},
    ]))
    captured = {}
    monkeypatch.setattr(ingestion_module, "expected_theme_codes_on_date", lambda *args: {"OLD.TI"})
    monkeypatch.setattr(
        ingestion_module, "persist_coverage_result",
        lambda db, result: captured.update(expected=result.expected_rows, status=result.status),
    )
    monkeypatch.setattr(
        ingestion_module, "reconcile_daily_snapshot",
        lambda db, model, rows, **kwargs: captured.update(rows=rows) or set(),
    )
    monkeypatch.setattr(ingestion_module, "upsert_rows", lambda *args, **kwargs: 1)
    monkeypatch.setattr(ingestion_module, "record_dirty_range", lambda *args, **kwargs: None)
    db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)

    assert IngestionService(db, provider).sync_theme_daily(target) == 1
    assert captured["expected"] == 1
    assert captured["status"] == "PASS"
    assert captured["rows"][0]["theme_code"] == "OLD.TI"


@pytest.mark.parametrize("model", [ThemeMoneyflowDaily, ThemeLimitDaily])
def test_optional_historical_theme_uses_date_aware_universe(monkeypatch, model) -> None:
    captured = {}
    monkeypatch.setattr(ingestion_module, "expected_theme_codes_on_date", lambda *args: {"OLD.TI"})
    monkeypatch.setattr(
        ingestion_module, "reconcile_daily_snapshot",
        lambda db, model, rows, **kwargs: captured.update(rows=rows) or set(),
    )
    monkeypatch.setattr(ingestion_module, "upsert_rows", lambda *args, **kwargs: 1)
    monkeypatch.setattr(ingestion_module, "record_dirty_range", lambda *args, **kwargs: None)
    monkeypatch.setattr(ingestion_module, "_persist_theme_quality", lambda *args, **kwargs: None)
    frame = pd.DataFrame([{"theme_code": "OLD.TI"}])
    db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
    status = IngestionService(db, SimpleNamespace())._sync_optional_theme_source(
        date(2026, 9, 15), "optional", lambda day: frame,
        lambda value: [{"theme_code": "OLD.TI", "trade_date": date(2026, 9, 15)}], model,
    )
    assert status == "PASS"
    assert captured["rows"][0]["theme_code"] == "OLD.TI"


@pytest.mark.parametrize("status,expected", [
    (None, True), ("ERROR", True), ("TRANSIENT_ERROR", True),
    ("PERMISSION_UNAVAILABLE", False), ("PASS", False),
])
def test_catchup_theme_retry_status(monkeypatch, status, expected) -> None:
    job = CatchUpJob.__new__(CatchUpJob)
    job.db = object()
    day = date(2026, 9, 15)
    monkeypatch.setattr(catchup_module, "expected_theme_codes_on_date", lambda *args: {"A"})
    monkeypatch.setattr(catchup_module, "theme_raw_needs_repair", lambda *args: expected)
    monkeypatch.setattr(
        catchup_module, "theme_source_status",
        lambda db, day, dataset: status if dataset == "ths_theme_daily" else "PASS",
    )
    assert job._theme_repair_dates([day]) == ([day] if expected else [])


def test_catchup_theme_repair_syncs_daily_and_optional(monkeypatch) -> None:
    day = date(2026, 9, 15)
    calls = []
    job = CatchUpJob.__new__(CatchUpJob)
    job.db = SimpleNamespace(rollback=lambda: None)
    job.ingestion = SimpleNamespace(
        sync_theme_daily=lambda current: calls.append("daily"),
        sync_theme_optional_sources=lambda current: calls.append("optional"),
    )
    monkeypatch.setattr(catchup_module, "theme_raw_needs_repair", lambda *args: True)
    monkeypatch.setattr(
        catchup_module, "theme_source_status",
        lambda *args: "ERROR" if not calls else "PASS",
    )
    assert job._sync_theme_raw_best_effort(day) is True
    assert calls == ["daily", "optional"]


def test_moneyflow_rolling_requires_three_trusted_market_days() -> None:
    days = [date(2026, 9, value) for value in (14, 15, 16)]
    daily = pd.DataFrame([
        {"trade_date": day, "theme_code": "A", "member_count": 5} for day in days
    ])
    flow = pd.DataFrame([
        {"trade_date": day, "theme_code": "A", "net_amount": index + 1, "company_num": 5}
        for index, day in enumerate(days)
    ])
    clean = _merge_optional_sources(daily.copy(), flow, pd.DataFrame(), set(days), set(), days)
    gap = _merge_optional_sources(
        daily.copy(), flow, pd.DataFrame(), {days[0], days[2]}, set(), days
    )
    assert clean.iloc[2]["net_amount_3d"] == 6
    assert pd.isna(gap.iloc[2]["net_amount_3d"])
    assert pd.isna(gap.iloc[1]["net_amount"])
    empty = _merge_optional_sources(daily, flow, pd.DataFrame(), set(), set(), days)
    assert empty["net_amount"].isna().all()


@pytest.mark.parametrize("previous_state,previous_score,expected", [
    ("S0", None, True), ("S6", None, True), ("S2", 70, True), ("S2", 80, False),
])
def test_left_new_uses_previous_state_and_score(
    monkeypatch, previous_state, previous_score, expected
) -> None:
    days = [date(2026, 9, 14), date(2026, 9, 15)]
    values = pd.DataFrame([
        {"trade_date": day, "ts_code": "A", "state": state, "eligible": True,
         "drawdown_high60": -0.1, "ma20_slope5": 0.01, "higher_low": True,
         "rps20": 80, "rps20_delta5_rank": 80, "rps60_delta5_rank": 80,
         "adj_close": 10, "ma20": 9, "ma60": 8, "atr_percentile60": 0.1,
         "amount_ratio20": 1.2, "return20": -0.1, "return20_lag5": -0.1,
         "ma20_slope_prev": -0.01, "cross_above_ma20": True,
         "cross_above_ma60": False, "higher_low_pct": 0.06}
        for day, state in zip(days, (previous_state, "S2"), strict=True)
    ])
    config = opportunity_module.OpportunityConfig({"stabilization": 1.0}, {}, 60, 75)
    monkeypatch.setattr(
        opportunity_module,
        "_stabilization",
        lambda row: previous_score if row["trade_date"] == days[0] else 80,
    )
    actual = _left_scores(values, config, days)
    assert bool(actual.iloc[1]["left_reversal_new"]) is expected


def test_left_new_requires_previous_market_day(monkeypatch) -> None:
    days = [date(2026, 9, 14), date(2026, 9, 15), date(2026, 9, 16)]
    values = pd.DataFrame([
        {"trade_date": days[0], "ts_code": "A", "state": "S0", "eligible": True},
        {"trade_date": days[2], "ts_code": "A", "state": "S2", "eligible": True},
    ])
    for column in (
        "drawdown_high60", "ma20_slope5", "higher_low", "rps20", "rps20_delta5_rank",
        "rps60_delta5_rank", "adj_close", "ma20", "ma60", "atr_percentile60",
        "amount_ratio20", "return20", "return20_lag5", "ma20_slope_prev",
        "cross_above_ma20", "cross_above_ma60", "higher_low_pct",
    ):
        values[column] = None
    monkeypatch.setattr(opportunity_module, "_stabilization", lambda row: 80)
    actual = _left_scores(
        values, opportunity_module.OpportunityConfig({"stabilization": 1}, {}, 60, 75), days
    )
    assert bool(actual.iloc[1]["left_reversal_new"]) is False


def test_lifecycle_explicit_thresholds() -> None:
    base = ThemeConfig("000300.SH", 1, {})
    starting = pd.Series({"heat_score": 55, "prev_heat": 50, "heat_momentum3": 10})
    divergence = pd.Series({"heat_score": 70, "prev_heat": 75, "heat_momentum3": -8})
    assert _lifecycle(starting, base) == "STARTING"
    assert _lifecycle(
        starting, ThemeConfig("000300.SH", 1, {}, lifecycle_starting=58)
    ) != "STARTING"
    assert _lifecycle(divergence, base) == "DIVERGENCE"
    assert _lifecycle(
        divergence, ThemeConfig("000300.SH", 1, {}, lifecycle_divergence_min_heat=75)
    ) != "DIVERGENCE"


def test_configured_member_safe_limit_records_shard_warning() -> None:
    provider = TushareProvider.__new__(TushareProvider)
    provider.provider_name = "tushare"
    provider._safe_limits = {"ths_member": 2}
    provider._call = lambda api_name, **kwargs: pd.DataFrame([
        {"ts_code": kwargs["ts_code"], "con_code": code}
        for code in ("000001.SZ", "000002.SZ")
    ])
    # Exercise the same warning hook used by _call without live network access.
    original_call = provider._call

    def call(api_name, **kwargs):
        frame = original_call(api_name, **kwargs)
        provider._mark_possible_truncation(api_name, frame)
        return frame

    provider._call = call
    result = provider.get_ths_concept_members(["A.TI", "B.TI"])
    assert result.attrs["theme_member_diagnostics"]["warning_codes"] == {
        "A.TI": "POSSIBLE_TRUNCATION",
        "B.TI": "POSSIBLE_TRUNCATION",
    }


def test_member_snapshot_provider_failure_records_error(monkeypatch) -> None:
    class Db:
        def execute(self, statement):
            if statement.is_select and "theme.constituent_count" in str(statement):
                return SimpleNamespace(all=lambda: [("A.TI", 2)])
            return SimpleNamespace(scalar_one_or_none=lambda: None)

        def rollback(self):
            pass

        def commit(self):
            pass

    statuses = []
    monkeypatch.setattr(
        ingestion_module, "_persist_theme_quality",
        lambda db, day, dataset, expected, actual, status, **kwargs: statuses.append(status),
    )
    provider = SimpleNamespace(
        get_ths_concept_members=lambda codes: (_ for _ in ()).throw(
            RuntimeError("ths_member POSSIBLE_TRUNCATION theme_code=A.TI")
        )
    )
    with pytest.raises(RuntimeError, match="POSSIBLE_TRUNCATION"):
        IngestionService(Db(), provider).sync_ths_theme_member_snapshot(date(2026, 9, 21))
    assert statuses == ["ERROR"]
