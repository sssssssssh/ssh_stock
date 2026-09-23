from datetime import date

import app.services.quality.daily_quality as daily_quality_module
import app.services.quality.raw_completeness as raw_module
import pytest
from app.models.market_data import IndexDaily, StockAdjFactor, StockDailyBasic
from app.services.quality.raw_completeness import RawDatasetCompleteness, check_raw_completeness
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_source_warning_keeps_high_coverage_dataset_at_warning() -> None:
    result = raw_module._coverage_dataset(
        object(),
        date(2026, 9, 4),
        "stk_limit",
        {"A", "B"},
        {"A", "B"},
        warning_coverage_rate=0.98,
        error_coverage_rate=0.95,
        job_id=None,
        persist=False,
        source_warnings=["POSSIBLE_TRUNCATION"],
    )

    assert result.status == "WARNING"
    assert result.is_acceptable is True


@pytest.fixture(autouse=True)
def _m9_raw_quality(monkeypatch):
    monkeypatch.setattr(
        raw_module,
        "_event_quality_dataset",
        lambda db, trade_date, dataset, model, **kwargs: RawDatasetCompleteness(
            dataset=dataset,
            status="PASS",
            expected_rows=0,
            actual_rows=0,
            coverage_rate=1.0,
            missing_codes=[],
            extra_codes=[],
        ),
    )
    monkeypatch.setattr(raw_module, "_quality_source_warnings", lambda *args: [])


def test_raw_completeness_requires_dataset_coverage(monkeypatch) -> None:
    expected_stocks = {"000001.SZ", "000002.SZ", "000003.SZ"}
    stock_daily = {"000001.SZ", "000002.SZ", "000003.SZ"}
    adj_factor = {"000001.SZ"}
    daily_basic = {"000001.SZ", "000002.SZ", "000003.SZ"}
    index_daily = {"000300.SH", "000001.SH", "000852.SH"}

    monkeypatch.setattr(
        raw_module, "expected_stock_daily_codes", lambda db, trade_date: expected_stocks
    )
    monkeypatch.setattr(
        raw_module,
        "_codes_for_date",
        lambda db, model, column, trade_date: stock_daily,
    )
    monkeypatch.setattr(
        raw_module,
        "_valid_codes_for_date",
        lambda db, model, column, trade_date, **kwargs: {
            "stock_adj_factor": (adj_factor, set()),
            "stock_daily_basic": (daily_basic, set()),
            "index_daily": (index_daily, set()),
            "stock_limit_daily": (stock_daily, set()),
        }[model.__tablename__],
    )

    result = check_raw_completeness(
        object(),
        date(2026, 8, 31),
        strategy={
            "benchmark": {"market_indices": ["000300.SH", "000001.SH", "000852.SH"]},
            "raw_quality": {
                "adj_factor": {"warning_coverage_rate": 0.98, "error_coverage_rate": 0.95}
            },
        },
    )

    assert result.stock_daily_status == "PASS"
    assert result.adj_factor_status == "ERROR"
    assert result.daily_basic_status == "PASS"
    assert result.index_daily_status == "PASS"
    assert result.is_complete is False


def test_raw_completeness_requires_all_configured_indices(monkeypatch) -> None:
    expected_stocks = {"000001.SZ", "000002.SZ"}
    all_stocks = {"000001.SZ", "000002.SZ"}

    monkeypatch.setattr(
        raw_module, "expected_stock_daily_codes", lambda db, trade_date: expected_stocks
    )
    monkeypatch.setattr(
        raw_module,
        "_codes_for_date",
        lambda db, model, column, trade_date: all_stocks,
    )
    monkeypatch.setattr(
        raw_module,
        "_valid_codes_for_date",
        lambda db, model, column, trade_date, **kwargs: (
            ({"000300.SH", "000001.SH"}, set())
            if model.__tablename__ == "index_daily"
            else (all_stocks, set())
        ),
    )

    result = check_raw_completeness(
        object(),
        date(2026, 8, 31),
        strategy={"benchmark": {"market_indices": ["000300.SH", "000001.SH", "000852.SH"]}},
    )

    assert result.index_daily_status == "ERROR"
    assert result.index_daily.missing_codes == ["000852.SH"]
    assert result.is_complete is False


def test_adj_factor_invalid_values_do_not_count_as_actual(monkeypatch) -> None:
    expected_stocks = {"000001.SZ", "000002.SZ", "000003.SZ"}
    persisted = []
    monkeypatch.setattr(
        raw_module, "expected_stock_daily_codes", lambda db, trade_date: expected_stocks
    )
    monkeypatch.setattr(
        raw_module,
        "_codes_for_date",
        lambda db, model, column, trade_date: expected_stocks,
    )
    monkeypatch.setattr(
        raw_module,
        "_valid_codes_for_date",
        lambda db, model, column, trade_date, **kwargs: {
            "stock_adj_factor": ({"000001.SZ"}, {"000002.SZ", "000003.SZ"}),
            "stock_daily_basic": (expected_stocks, set()),
            "index_daily": ({"000300.SH"}, set()),
            "stock_limit_daily": (expected_stocks, set()),
        }[model.__tablename__],
    )
    monkeypatch.setattr(
        raw_module,
        "persist_coverage_result",
        lambda db, result, **kwargs: persisted.append((result.dataset, result, kwargs)),
    )

    result = check_raw_completeness(
        object(),
        date(2026, 8, 31),
        strategy={
            "benchmark": {"market_indices": ["000300.SH"]},
            "raw_quality": {
                "adj_factor": {"warning_coverage_rate": 0.98, "error_coverage_rate": 0.95}
            },
        },
        persist=True,
    )

    assert result.adj_factor.actual_rows == 1
    assert result.adj_factor.coverage_rate == 1 / 3
    assert result.adj_factor.invalid_count == 2
    assert result.adj_factor.invalid_codes == ["000002.SZ", "000003.SZ"]
    adj_persist = next(item for item in persisted if item[0] == "adj_factor")
    assert adj_persist[2]["extra_issue_codes"]["invalid_count"] == 2
    assert adj_persist[2]["extra_issue_codes"]["invalid_codes"] == [
        "000002.SZ",
        "000003.SZ",
    ]


def test_raw_completeness_preserves_existing_stock_daily_detail_counts(monkeypatch) -> None:
    quality_rows = {
        (date(2026, 8, 31), "stock_daily"): {
            "trade_date": date(2026, 8, 31),
            "dataset": "stock_daily",
            "expected_rows": 1,
            "actual_rows": 1,
            "coverage_rate": 1.0,
            "missing_count": 0,
            "duplicate_count": 3,
            "null_count": 25,
            "warning_count": 0,
            "error_count": 0,
            "status": "PASS",
            "issue_codes": {},
            "job_id": None,
        }
    }

    def fake_upsert_rows(db, model, rows, conflict_columns, update_columns=None, **kwargs):
        for row in rows:
            key = (row["trade_date"], row["dataset"])
            if key not in quality_rows:
                quality_rows[key] = dict(row)
                continue
            columns = update_columns or [
                column for column in row if column not in set(conflict_columns) | {"id"}
            ]
            for column in columns:
                quality_rows[key][column] = row[column]
        return len(rows)

    monkeypatch.setattr(daily_quality_module, "upsert_rows", fake_upsert_rows)
    monkeypatch.setattr(
        raw_module,
        "expected_stock_daily_codes",
        lambda db, trade_date: {"000001.SZ", "000002.SZ"},
    )
    monkeypatch.setattr(
        raw_module,
        "_codes_for_date",
        lambda db, model, column, trade_date: {"000001.SZ"},
    )
    monkeypatch.setattr(
        raw_module,
        "_valid_codes_for_date",
        lambda db, model, column, trade_date, **kwargs: (
            {"000001.SZ"},
            set(),
        )
        if model.__tablename__ != "index_daily"
        else ({"000300.SH"}, set()),
    )

    result = check_raw_completeness(
        object(),
        date(2026, 8, 31),
        strategy={"benchmark": {"market_indices": ["000300.SH"]}},
        persist=True,
    )

    stock_daily_quality = quality_rows[(date(2026, 8, 31), "stock_daily")]
    assert result.stock_daily_status == "ERROR"
    assert stock_daily_quality["expected_rows"] == 2
    assert stock_daily_quality["actual_rows"] == 1
    assert stock_daily_quality["coverage_rate"] == 0.5
    assert stock_daily_quality["status"] == "ERROR"
    assert stock_daily_quality["duplicate_count"] == 3
    assert stock_daily_quality["null_count"] == 25


def test_raw_completeness_overall_status_prioritizes_error_over_warning() -> None:
    dataset = raw_module.RawDatasetCompleteness(
        dataset="test",
        status="PASS",
        expected_rows=1,
        actual_rows=1,
        coverage_rate=1.0,
        missing_codes=[],
        extra_codes=[],
    )
    warning = raw_module.RawDatasetCompleteness(
        dataset="test",
        status="WARNING",
        expected_rows=1,
        actual_rows=1,
        coverage_rate=0.97,
        missing_codes=[],
        extra_codes=[],
    )
    error = raw_module.RawDatasetCompleteness(
        dataset="test",
        status="ERROR",
        expected_rows=1,
        actual_rows=0,
        coverage_rate=0.0,
        missing_codes=["000001.SZ"],
        extra_codes=[],
    )

    warning_result = raw_module.RawCompletenessResult(
        trade_date=date(2026, 8, 31),
        stock_daily=dataset,
        adj_factor=warning,
        daily_basic=dataset,
        index_daily=dataset,
    )
    error_result = raw_module.RawCompletenessResult(
        trade_date=date(2026, 8, 31),
        stock_daily=dataset,
        adj_factor=warning,
        daily_basic=dataset,
        index_daily=error,
    )

    assert warning_result.overall_status == "WARNING"
    assert error_result.overall_status == "ERROR"


def test_stock_daily_expected_universe_excludes_suspended_stocks(monkeypatch) -> None:
    active = {"000001.SZ", "000002.SZ", "000003.SZ"}
    daily = {"000001.SZ", "000003.SZ"}
    monkeypatch.setattr(
        raw_module,
        "expected_stock_daily_codes",
        lambda *args: active - {"000002.SZ"},
    )
    monkeypatch.setattr(
        raw_module,
        "_codes_for_date",
        lambda db, model, column, trade_date: daily,
    )
    monkeypatch.setattr(
        raw_module,
        "_valid_codes_for_date",
        lambda db, model, column, trade_date, **kwargs: {
            "stock_adj_factor": (daily, set()),
            "stock_daily_basic": (daily, set()),
            "index_daily": ({"000300.SH"}, set()),
            "stock_limit_daily": (active, set()),
        }[model.__tablename__],
    )

    result = check_raw_completeness(
        object(),
        date(2026, 8, 31),
        strategy={"benchmark": {"market_indices": ["000300.SH"]}},
    )

    assert result.stock_daily.status == "PASS"
    assert result.stock_daily.expected_rows == 2
    assert result.stock_daily.missing_codes == []


def test_valid_adj_factor_codes_exclude_null_and_non_positive_values() -> None:
    engine = create_engine("sqlite:///:memory:")
    StockAdjFactor.__table__.create(engine)
    with Session(engine) as db:
        db.add_all(
            [
                StockAdjFactor(
                    trade_date=date(2026, 8, 31),
                    ts_code="000001.SZ",
                    adj_factor=1.2,
                ),
                StockAdjFactor(
                    trade_date=date(2026, 8, 31),
                    ts_code="000002.SZ",
                    adj_factor=None,
                ),
                StockAdjFactor(
                    trade_date=date(2026, 8, 31),
                    ts_code="000003.SZ",
                    adj_factor=0,
                ),
            ]
        )
        db.commit()

        valid_codes, invalid_codes = raw_module._valid_codes_for_date(
            db,
            StockAdjFactor,
            StockAdjFactor.trade_date,
            date(2026, 8, 31),
            positive_columns=[StockAdjFactor.adj_factor],
        )

    assert valid_codes == {"000001.SZ"}
    assert invalid_codes == {"000002.SZ", "000003.SZ"}


def test_valid_index_daily_codes_exclude_invalid_close_fields() -> None:
    engine = create_engine("sqlite:///:memory:")
    IndexDaily.__table__.create(engine)
    with Session(engine) as db:
        db.add_all(
            [
                IndexDaily(
                    trade_date=date(2026, 8, 31),
                    ts_code="000300.SH",
                    close=1,
                    pre_close=1,
                ),
                IndexDaily(
                    trade_date=date(2026, 8, 31),
                    ts_code="000001.SH",
                    close=None,
                    pre_close=1,
                ),
                IndexDaily(
                    trade_date=date(2026, 8, 31),
                    ts_code="000852.SH",
                    close=1,
                    pre_close=0,
                ),
            ]
        )
        db.commit()

        valid_codes, invalid_codes = raw_module._valid_codes_for_date(
            db,
            IndexDaily,
            IndexDaily.trade_date,
            date(2026, 8, 31),
            positive_columns=[IndexDaily.close, IndexDaily.pre_close],
        )

    assert valid_codes == {"000300.SH"}
    assert invalid_codes == {"000001.SH", "000852.SH"}


def test_valid_daily_basic_codes_check_only_core_fields() -> None:
    engine = create_engine("sqlite:///:memory:")
    StockDailyBasic.__table__.create(engine)
    with Session(engine) as db:
        db.add_all(
            [
                StockDailyBasic(
                    trade_date=date(2026, 8, 31),
                    ts_code="000001.SZ",
                    close=10,
                    total_mv=100,
                    circ_mv=80,
                    pe=None,
                    pb=None,
                ),
                StockDailyBasic(
                    trade_date=date(2026, 8, 31),
                    ts_code="000002.SZ",
                    close=10,
                    total_mv=None,
                    circ_mv=80,
                ),
            ]
        )
        db.commit()

        valid_codes, invalid_codes = raw_module._valid_codes_for_date(
            db,
            StockDailyBasic,
            StockDailyBasic.trade_date,
            date(2026, 8, 31),
            required_columns=[
                StockDailyBasic.close,
                StockDailyBasic.total_mv,
                StockDailyBasic.circ_mv,
            ],
        )

    assert valid_codes == {"000001.SZ"}
    assert invalid_codes == {"000002.SZ"}
