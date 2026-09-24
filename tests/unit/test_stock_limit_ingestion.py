from datetime import date

import app.services.ingestion.service as ingestion_module
import pandas as pd
import pytest
from app.models.market_data import StockBasic, StockLimitDaily, TradeCalendar
from app.services.ingestion.service import IngestionService
from app.services.price_limit import PriceLimitValidation
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


class _Provider:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def get_stock_limit(self, trade_date: date) -> pd.DataFrame:
        return self.frame


def _frame(codes: list[str], target: date) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "trade_date": target.strftime("%Y%m%d"),
            "ts_code": code,
            "pre_close": 10,
            "up_limit": 11,
            "down_limit": 9,
        }
        for code in codes
    ])


def _patch_dependencies(
    monkeypatch,
    expected_codes,
    captured_quality,
    *,
    patch_validation: bool = True,
) -> None:
    monkeypatch.setattr(
        ingestion_module, "expected_stock_daily_codes", lambda *args: set(expected_codes)
    )
    monkeypatch.setattr(
        ingestion_module,
        "persist_coverage_result",
        lambda db, result, **kwargs: captured_quality.append((result, kwargs)),
    )
    monkeypatch.setattr(ingestion_module, "record_dirty_range", lambda *args, **kwargs: None)
    if patch_validation:
        monkeypatch.setattr(
            ingestion_module,
            "validate_price_limit_rows",
            _strict_price_limit_validation,
        )


def _strict_price_limit_validation(db, *, trade_date, rows) -> PriceLimitValidation:
    normal = {
        str(row["ts_code"])
        for row in rows
        if row["up_limit"] is not None
        and row["up_limit"] > 0
        and row["down_limit"] is not None
        and row["down_limit"] > 0
    }
    codes = {str(row["ts_code"]) for row in rows}
    return PriceLimitValidation(
        normal_valid_codes=frozenset(normal),
        invalid_codes=frozenset(codes - normal),
    )


def test_stock_limit_provider_warning_with_high_coverage_is_acceptable(monkeypatch) -> None:
    target = date(2026, 9, 4)
    codes = [f"{index:06}.SZ" for index in range(1000)]
    frame = _frame(codes, target)
    frame.attrs["provider_warning"] = "POSSIBLE_TRUNCATION"
    quality = []
    _patch_dependencies(monkeypatch, codes, quality)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    StockLimitDaily.__table__.create(engine)

    with Session(engine) as db:
        count = IngestionService(db, _Provider(frame)).sync_stock_limit(target)

    assert count == 1000
    assert quality[0][0].status == "WARNING"
    assert quality[0][1]["extra_issue_codes"]["source_warnings"] == [
        "POSSIBLE_TRUNCATION"
    ]


def test_stock_limit_persists_only_target_stock_universe(monkeypatch) -> None:
    target = date(2026, 9, 4)
    targets = [f"{index:06}.SZ" for index in range(1000)]
    extras = [f"X{index:06}.OTC" for index in range(2000)]
    quality = []
    _patch_dependencies(monkeypatch, targets, quality)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    StockLimitDaily.__table__.create(engine)

    with Session(engine) as db:
        count = IngestionService(db, _Provider(_frame(targets + extras, target))).sync_stock_limit(
            target
        )
        stored = set(db.execute(select(StockLimitDaily.ts_code)).scalars().all())

    diagnostics = quality[0][1]["extra_issue_codes"]
    assert count == 1000
    assert stored == set(targets)
    assert quality[0][0].expected_rows == 1000
    assert quality[0][0].coverage_rate == 1.0
    assert diagnostics["extra_source_count"] == 2000
    assert len(diagnostics["extra_source_codes"]) == 100


def test_stock_limit_bse_listing_day_sentinel_is_valid_and_preserved(monkeypatch) -> None:
    target = date(2026, 9, 23)
    code = "920025.BJ"
    frame = pd.DataFrame([
        {
            "trade_date": "20260923",
            "ts_code": code,
            "pre_close": 4.26,
            "up_limit": 99999.99,
            "down_limit": 0.0,
        }
    ])
    quality = []
    _patch_dependencies(
        monkeypatch,
        [code],
        quality,
        patch_validation=False,
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    StockBasic.__table__.create(engine)
    TradeCalendar.__table__.create(engine)
    StockLimitDaily.__table__.create(engine)

    with Session(engine) as db:
        db.add(StockBasic(ts_code=code, exchange="BSE", list_date=target))
        db.add(TradeCalendar(cal_date=target, is_open=True, exchange="SSE"))
        db.commit()

        count = IngestionService(db, _Provider(frame)).sync_stock_limit(target)
        stored = db.get(StockLimitDaily, (target, code))

    diagnostics = quality[0][1]["extra_issue_codes"]
    assert count == 1
    assert quality[0][0].status == "PASS"
    assert quality[0][0].coverage_rate == 1.0
    assert diagnostics["fatal_issues"] == []
    assert diagnostics["price_limit_exempt_count"] == 1
    assert diagnostics["price_limit_exempt_codes"] == [code]
    assert diagnostics["price_limit_exempt_reasons"] == {code: "IPO_LISTING_DAY"}
    assert stored is not None
    assert stored.up_limit == 99999.99
    assert stored.down_limit == 0.0


def test_stock_limit_empty_universe_refuses_destructive_reconcile(monkeypatch) -> None:
    target = date(2026, 9, 4)
    quality = []
    _patch_dependencies(monkeypatch, [], quality)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    StockLimitDaily.__table__.create(engine)

    with Session(engine) as db:
        db.add(
            StockLimitDaily(
                trade_date=target,
                ts_code="000001.SZ",
                pre_close=10,
                up_limit=11,
                down_limit=9,
            )
        )
        db.commit()

        with pytest.raises(ValueError, match="authoritative universe is empty"):
            IngestionService(db, _Provider(_frame([], target))).sync_stock_limit(target)

        stored = db.execute(
            select(StockLimitDaily).where(
                StockLimitDaily.trade_date == target,
                StockLimitDaily.ts_code == "000001.SZ",
            )
        ).scalar_one_or_none()

    assert stored is not None
    assert quality == []


def test_stock_limit_low_coverage_still_blocks(monkeypatch) -> None:
    target = date(2026, 9, 4)
    expected = [f"{index:06}.SZ" for index in range(100)]
    quality = []
    _patch_dependencies(monkeypatch, expected, quality)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    StockLimitDaily.__table__.create(engine)

    with Session(engine) as db, pytest.raises(ValueError, match="coverage"):
        IngestionService(db, _Provider(_frame(expected[:10], target))).sync_stock_limit(target)

    assert quality[0][0].status == "ERROR"


@pytest.mark.parametrize(
    "malformation",
    (
        "duplicate",
        "missing_required",
        "zero_down_limit",
        "null_up_limit",
        "negative_down_limit",
    ),
)
def test_stock_limit_structural_errors_still_block(monkeypatch, malformation) -> None:
    target = date(2026, 9, 4)
    expected = ["000001.SZ"]
    frame = _frame(expected, target)
    if malformation == "duplicate":
        frame = pd.concat([frame, frame], ignore_index=True)
        expected_issue = "DUPLICATE_NATURAL_KEY"
    elif malformation == "missing_required":
        frame.loc[0, "ts_code"] = None
        expected_issue = "INVALID_REQUIRED_FIELDS"
    elif malformation == "zero_down_limit":
        frame.loc[0, "down_limit"] = 0
        expected_issue = "INVALID_LIMIT_VALUE"
    elif malformation == "null_up_limit":
        frame.loc[0, "up_limit"] = None
        expected_issue = "INVALID_LIMIT_VALUE"
    else:
        frame.loc[0, "down_limit"] = -1
        expected_issue = "INVALID_LIMIT_VALUE"
    quality = []
    _patch_dependencies(monkeypatch, expected, quality)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    StockLimitDaily.__table__.create(engine)

    with Session(engine) as db, pytest.raises(ValueError, match="fatal_issues"):
        IngestionService(db, _Provider(frame)).sync_stock_limit(target)

    assert quality[0][0].status == "ERROR"
    assert expected_issue in quality[0][1]["extra_issue_codes"]["fatal_issues"]
