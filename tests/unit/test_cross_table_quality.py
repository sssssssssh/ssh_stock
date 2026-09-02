from datetime import date

from app.models.market_data import (
    IndexDaily,
    SectorFactorDaily,
    StockAdjFactor,
    StockDaily,
    StockDailyBasic,
    StockFactorDaily,
    StockStateDaily,
)
from app.services.quality import daily_quality
from app.services.quality.daily_quality import record_cross_table_quality


def test_cross_table_quality_escalates_severe_missing_to_error(monkeypatch) -> None:
    counts = {
        StockDaily: 5000,
        StockAdjFactor: 5000,
        StockDailyBasic: 5000,
        StockFactorDaily: 1000,
        StockStateDaily: 1000,
        SectorFactorDaily: 0,
        IndexDaily: 3,
    }
    persisted = []
    strategy = {
        "data_quality": {
            "daily": {
                "warning_coverage_rate": 0.98,
                "error_coverage_rate": 0.95,
            },
            "cross_table": {
                "adj_vs_daily": {
                    "warning_coverage_rate": 0.98,
                    "error_coverage_rate": 0.95,
                },
                "basic_vs_daily": {
                    "warning_coverage_rate": 0.98,
                    "error_coverage_rate": 0.95,
                },
                "factor_vs_daily": {
                    "warning_coverage_rate": 0.98,
                    "error_coverage_rate": 0.90,
                },
                "state_vs_factor": {
                    "warning_coverage_rate": 0.98,
                    "error_coverage_rate": 0.90,
                },
            },
        }
    }

    monkeypatch.setattr(
        daily_quality,
        "_count_date",
        lambda db, model, column, trade_date: counts[model],
    )
    monkeypatch.setattr(
        daily_quality,
        "expected_stock_codes",
        lambda db, trade_date: {f"{idx:06d}.SZ" for idx in range(5000)},
    )

    def capture_upsert(db, model, rows, conflict_columns):
        persisted.extend(rows)
        return len(rows)

    monkeypatch.setattr(daily_quality, "upsert_rows", capture_upsert)

    result = record_cross_table_quality(object(), date(2026, 8, 31), strategy=strategy)

    assert result.has_error is True
    assert result.results["factor_vs_daily"] == "ERROR"
    assert result.results["state_vs_factor"] == "PASS"
    factor_row = next(row for row in persisted if row["dataset"] == "factor_vs_daily")
    assert factor_row["status"] == "ERROR"
    assert factor_row["error_count"] == 1
