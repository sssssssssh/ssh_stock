from datetime import date
from uuid import uuid4

import app.api.v1.dashboard as dashboard_module
import app.api.v1.stocks as stocks_module
import app.services.quality.daily_quality as quality_module
import app.services.trend.service as trend_module
import pandas as pd
from app.models.market_data import (
    MarketDaily,
    SectorFactorDaily,
    StockAdjFactor,
    StockDaily,
    StockDailyBasic,
    StockFactorDaily,
    StockStateDaily,
)
from app.services.analysis_identity import analysis_strategy_hash
from app.services.quality.daily_quality import record_cross_table_quality
from app.services.trend.service import TrendService


def test_state_api_latest_dates_are_scoped_to_requested_algo_version(monkeypatch) -> None:
    captured = []

    def fake_latest(db, column, *criteria):
        captured.extend(str(item) for item in criteria)
        return None

    monkeypatch.setattr(stocks_module, "latest_date", fake_latest)
    monkeypatch.setattr(dashboard_module, "latest_date", fake_latest)

    stocks_module._state_pool(
        db=object(),
        trade_date=None,
        states=["S3"],
        new_only=False,
        limit=10,
        offset=0,
        algo_version="v-test",
    )
    dashboard_module.summary(algo_version="v-test", db=object())

    assert len(captured) == 6
    assert sum("algo_version" in criterion for criterion in captured) == 2
    assert sum("calc_version" in criterion for criterion in captured) == 2
    assert sum("config_hash" in criterion for criterion in captured) == 2


def test_cross_table_quality_counts_only_current_versions(monkeypatch) -> None:
    captured: dict[type, list[str]] = {}
    counts = {
        StockDaily: 10,
        StockAdjFactor: 10,
        StockDailyBasic: 10,
        StockFactorDaily: 10,
        StockStateDaily: 10,
        SectorFactorDaily: 1,
        MarketDaily: 1,
    }

    def fake_count(db, model, column, trade_date, *criteria):
        captured[model] = [str(item) for item in criteria]
        return counts[model]

    monkeypatch.setattr(quality_module, "_count_date", fake_count)
    monkeypatch.setattr(
        quality_module,
        "expected_stock_daily_codes",
        lambda db, trade_date: {f"{index:06d}.SZ" for index in range(10)},
    )
    monkeypatch.setattr(quality_module, "upsert_rows", lambda *args, **kwargs: 1)

    record_cross_table_quality(object(), date(2026, 9, 15), strategy={"version": "test"})

    assert any("calc_version" in value for value in captured[StockFactorDaily])
    assert any("config_hash" in value for value in captured[StockFactorDaily])
    assert any("calc_version" in value for value in captured[MarketDaily])
    assert any("config_hash" in value for value in captured[SectorFactorDaily])
    assert any("algo_version" in value for value in captured[StockStateDaily])


def test_trend_service_writes_state_and_signal_run_metadata(monkeypatch) -> None:
    run_id = uuid4()
    captured: dict[type, list[dict]] = {}

    class FakeDb:
        def commit(self):
            return None

    service = TrendService(FakeDb())
    empty = pd.DataFrame()
    monkeypatch.setattr(service, "_read_factors", lambda *args: empty)
    monkeypatch.setattr(service, "_read_market", lambda *args: empty)
    monkeypatch.setattr(service, "_read_sector_members", lambda: empty)
    monkeypatch.setattr(service, "_read_sector_factors", lambda *args: empty)
    monkeypatch.setattr(service, "_read_previous_states", lambda *args: empty)
    state = {
        "trade_date": date(2026, 9, 15),
        "ts_code": "000001.SZ",
        "algo_version": service.settings.algo_version,
        "state": "S3",
    }
    signal = {
        "trade_date": date(2026, 9, 15),
        "ts_code": "000001.SZ",
        "signal_type": "RIGHT_SIDE_NEW",
        "algo_version": service.settings.algo_version,
    }
    monkeypatch.setattr(
        trend_module,
        "calculate_stock_states",
        lambda **kwargs: pd.DataFrame([state]),
    )
    monkeypatch.setattr(
        trend_module,
        "generate_strategy_signals",
        lambda *args: pd.DataFrame([signal]),
    )

    def capture_replace(db, model, rows, **kwargs):
        captured[model] = rows
        return len(rows)

    monkeypatch.setattr(trend_module, "replace_slice_rows", capture_replace)

    service.recalc(date(2026, 9, 15), date(2026, 9, 15), calc_run_id=run_id)

    state_row = captured[trend_module.StockStateDaily][0]
    signal_row = captured[trend_module.StrategySignal][0]
    assert state_row["calc_version"] == "trend_v1"
    assert signal_row["calc_version"] == "signal_v1"
    assert state_row["calc_run_id"] == signal_row["calc_run_id"] == run_id
    expected_hash = analysis_strategy_hash(service.settings.strategy)
    assert state_row["config_hash"] == signal_row["config_hash"] == expected_hash
