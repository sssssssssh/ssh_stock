from datetime import date
from types import SimpleNamespace

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
from app.services.ingestion.service import IngestionService, ThemeMemberSnapshotQualityError


class _SnapshotResult:
    def __init__(self, *, rows=None, scalar=None):
        self.rows = rows or []
        self.scalar = scalar

    def all(self):
        return self.rows

    def scalar_one_or_none(self):
        return self.scalar

    def scalar_one(self):
        return self.scalar


class _SnapshotDb:
    def __init__(self, catalog, existing_quality=None, existing_count=0):
        self.catalog = catalog
        self.existing_quality = existing_quality
        self.existing_count = existing_count
        self.commits = 0
        self.rollbacks = 0
        self.delete_count = 0

    def execute(self, statement):
        sql = str(statement)
        if statement.is_select and "theme.constituent_count" in sql:
            return _SnapshotResult(rows=self.catalog)
        if statement.is_select and "FROM data_quality_daily" in sql:
            return _SnapshotResult(scalar=self.existing_quality)
        if statement.is_select and "count(" in sql:
            return _SnapshotResult(scalar=self.existing_count)
        if "DELETE FROM theme_member_snapshot" in sql:
            self.delete_count += 1
        return _SnapshotResult()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _MemberProvider:
    def __init__(self, returned_codes, *, failed_codes=None):
        self.returned_codes = returned_codes
        self.failed_codes = failed_codes or {}

    def get_ths_concept_members(self, concept_codes):
        frame = pd.DataFrame([
            {"ts_code": code, "con_code": f"{index:06}.SZ", "con_name": "Stock"}
            for index, code in enumerate(self.returned_codes, start=1)
        ])
        frame.attrs["theme_member_diagnostics"] = {
            "requested_codes": concept_codes,
            "empty_codes": sorted(set(concept_codes) - set(self.returned_codes)),
            "failed_codes": self.failed_codes,
            "warning_codes": {},
        }
        return frame


def _capture_snapshot_writes(monkeypatch):
    writes = []
    monkeypatch.setattr(
        ingestion_module,
        "upsert_rows",
        lambda db, model, rows, *args, **kwargs: writes.append((model, list(rows)))
        or len(writes[-1][1]),
    )
    return writes


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


def test_member_fetch_isolates_failed_shard_after_one_extra_retry(monkeypatch) -> None:
    provider = TushareProvider.__new__(TushareProvider)
    calls = []

    def fake_call(api_name: str, **kwargs):
        calls.append(kwargs["ts_code"])
        if kwargs["ts_code"] == "BAD.TI":
            raise RuntimeError("provider shard failed")
        return pd.DataFrame(
            [{"ts_code": kwargs["ts_code"], "con_code": "000001.SZ", "con_name": "平安"}]
        )

    monkeypatch.setattr(provider, "_call", fake_call)

    result = provider.get_ths_concept_members(["GOOD.TI", "BAD.TI"])

    assert set(result["ts_code"]) == {"GOOD.TI"}
    assert calls.count("BAD.TI") == 2
    assert result.attrs["theme_member_diagnostics"]["failed_codes"] == {
        "BAD.TI": "provider shard failed"
    }


def test_member_snapshot_saves_partial_rows_as_warning(monkeypatch) -> None:
    class Result:
        def __init__(self, rows=None):
            self.rows = rows or []

        def all(self):
            return self.rows

        def scalar_one_or_none(self):
            return None

    class Db:
        commits = 0
        rollbacks = 0

        def execute(self, statement):
            if statement.is_select and "theme.constituent_count" in str(statement):
                return Result([(f"T{index:03}.TI", 1) for index in range(100)])
            return Result()

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    class Provider:
        def get_ths_concept_members(self, concept_codes):
            frame = pd.DataFrame([
                {
                    "ts_code": code,
                    "con_code": f"{index:06}.SZ",
                    "con_name": "Stock",
                }
                for index, code in enumerate(concept_codes[:98], start=1)
            ])
            frame.attrs["theme_member_diagnostics"] = {
                "requested_codes": concept_codes,
                "empty_codes": concept_codes[98:],
                "failed_codes": {},
                "warning_codes": {},
            }
            return frame

    writes = []
    monkeypatch.setattr(
        ingestion_module,
        "upsert_rows",
        lambda db, model, rows, *args, **kwargs: writes.append((model, list(rows)))
        or len(writes[-1][1]),
    )
    db = Db()

    count = IngestionService(db, Provider()).sync_ths_theme_member_snapshot(
        date(2026, 9, 17)
    )

    assert count == 98
    assert db.rollbacks == 0
    assert db.commits == 1
    assert len(writes[0][1]) == 98
    quality_row = writes[1][1][0]
    assert quality_row["status"] == "WARNING"
    assert quality_row["expected_rows"] == 100
    assert quality_row["missing_count"] == 2
    assert quality_row["issue_codes"]["missing_theme_codes"] == ["T098.TI", "T099.TI"]


def test_member_fetch_empty_retry_can_recover(monkeypatch) -> None:
    provider = TushareProvider.__new__(TushareProvider)
    calls = 0

    def fake_call(api_name: str, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return pd.DataFrame()
        return pd.DataFrame([{"ts_code": kwargs["ts_code"], "con_code": "000001.SZ"}])

    monkeypatch.setattr(provider, "_call", fake_call)
    result = provider.get_ths_concept_members(["A.TI"])

    assert calls == 2
    assert len(result) == 1
    assert result.attrs["theme_member_diagnostics"]["empty_codes"] == []


def test_theme_member_normalizer_keeps_only_current_members_when_flags_are_valid() -> None:
    target = date(2026, 9, 17)
    rows = normalize_theme_members(
        pd.DataFrame(
            [
                {"ts_code": "A.TI", "con_code": "000001.SZ", "is_new": "Y"},
                {"ts_code": "A.TI", "con_code": "000002.SZ", "is_new": "N"},
            ]
        ),
        target,
    )

    assert [row["ts_code"] for row in rows] == ["000001.SZ"]
    assert rows[0]["is_new"] is True


def test_theme_member_normalizer_keeps_all_members_when_flags_are_empty() -> None:
    target = date(2026, 9, 17)
    rows = normalize_theme_members(
        pd.DataFrame(
            [
                {"ts_code": "A.TI", "con_code": "000001.SZ", "is_new": None},
                {"ts_code": "A.TI", "con_code": "000002.SZ", "is_new": ""},
            ]
        ),
        target,
    )

    assert {row["ts_code"] for row in rows} == {"000001.SZ", "000002.SZ"}
    assert all(row["is_new"] is None for row in rows)


def test_theme_member_normalizer_applies_is_new_per_theme() -> None:
    rows = normalize_theme_members(
        pd.DataFrame(
            [
                {"ts_code": "A.TI", "con_code": "000001.SZ", "is_new": "Y"},
                {"ts_code": "A.TI", "con_code": "000002.SZ", "is_new": "N"},
                {"ts_code": "B.TI", "con_code": "000003.SZ", "is_new": None},
                {"ts_code": "B.TI", "con_code": "000004.SZ", "is_new": None},
            ]
        ),
        date(2026, 9, 23),
    )

    by_theme = {
        theme_code: [row for row in rows if row["theme_code"] == theme_code]
        for theme_code in {row["theme_code"] for row in rows}
    }
    assert [row["ts_code"] for row in by_theme["A.TI"]] == ["000001.SZ"]
    assert by_theme["A.TI"][0]["is_new"] is True
    assert {row["ts_code"] for row in by_theme["B.TI"]} == {
        "000003.SZ",
        "000004.SZ",
    }
    assert all(row["is_new"] is None for row in by_theme["B.TI"])


def test_theme_member_normalizer_all_n_does_not_filter_unflagged_theme() -> None:
    rows = normalize_theme_members(
        pd.DataFrame(
            [
                {"ts_code": "A.TI", "con_code": "000001.SZ", "is_new": "N"},
                {"ts_code": "A.TI", "con_code": "000002.SZ", "is_new": "N"},
                {"ts_code": "B.TI", "con_code": "000003.SZ", "is_new": None},
                {"ts_code": "B.TI", "con_code": "000004.SZ", "is_new": ""},
            ]
        ),
        date(2026, 9, 23),
    )

    assert {row["theme_code"] for row in rows} == {"B.TI"}
    assert {row["ts_code"] for row in rows} == {"000003.SZ", "000004.SZ"}
    assert all(row["is_new"] is None for row in rows)


def test_theme_member_normalizer_drops_missing_required_codes() -> None:
    rows = normalize_theme_members(
        pd.DataFrame(
            [
                {"ts_code": None, "con_code": "000001.SZ", "is_new": "Y"},
                {"ts_code": "", "con_code": "000002.SZ", "is_new": "Y"},
                {"ts_code": "A.TI", "con_code": None, "is_new": "Y"},
                {"ts_code": "A.TI", "con_code": "", "is_new": "Y"},
                {"ts_code": "B.TI", "con_code": "000003.SZ", "is_new": None},
            ]
        ),
        date(2026, 9, 23),
    )

    assert [(row["theme_code"], row["ts_code"]) for row in rows] == [
        ("B.TI", "000003.SZ")
    ]


def test_complete_member_snapshot_is_pass(monkeypatch) -> None:
    codes = ["A.TI", "B.TI", "C.TI"]
    db = _SnapshotDb([(code, 1) for code in codes])
    writes = _capture_snapshot_writes(monkeypatch)

    count = IngestionService(db, _MemberProvider(codes)).sync_ths_theme_member_snapshot(
        date(2026, 9, 23)
    )

    assert count == 3
    assert db.delete_count == 1
    assert writes[-1][1][0]["status"] == "PASS"
    assert writes[-1][1][0]["issue_codes"]["snapshot_mode"] == "FULL"


def test_large_member_snapshot_gap_is_error_without_destructive_replace(monkeypatch) -> None:
    codes = [f"T{index:03}.TI" for index in range(100)]
    db = _SnapshotDb([(code, 1) for code in codes])
    writes = _capture_snapshot_writes(monkeypatch)

    with pytest.raises(ThemeMemberSnapshotQualityError, match="snapshot ERROR"):
        IngestionService(db, _MemberProvider(codes[:50])).sync_ths_theme_member_snapshot(
            date(2026, 9, 23)
        )

    assert db.delete_count == 0
    assert len(writes) == 1
    assert writes[0][1][0]["status"] == "ERROR"


def test_failed_member_shard_can_produce_usable_warning(monkeypatch) -> None:
    codes = [f"T{index:03}.TI" for index in range(100)]
    failed = {codes[-1]: "provider shard failed"}
    db = _SnapshotDb([(code, 1) for code in codes])
    writes = _capture_snapshot_writes(monkeypatch)

    count = IngestionService(
        db, _MemberProvider(codes[:-1], failed_codes=failed)
    ).sync_ths_theme_member_snapshot(date(2026, 9, 23))

    quality = writes[-1][1][0]
    assert count == 99
    assert quality["status"] == "WARNING"
    assert quality["issue_codes"]["failed_theme_count"] == 1
    assert quality["issue_codes"]["failed_themes"] == failed


def test_existing_pass_snapshot_is_not_replaced_by_partial_result(monkeypatch) -> None:
    codes = [f"T{index:03}.TI" for index in range(100)]
    db = _SnapshotDb(
        [(code, 1) for code in codes],
        existing_quality=SimpleNamespace(status="PASS", coverage_rate=1.0),
        existing_count=100,
    )
    writes = _capture_snapshot_writes(monkeypatch)

    count = IngestionService(db, _MemberProvider(codes[:98])).sync_ths_theme_member_snapshot(
        date(2026, 9, 23)
    )

    assert count == 100
    assert db.delete_count == 0
    assert writes == []


def test_warning_snapshot_is_replaced_when_source_recovers_to_pass(monkeypatch) -> None:
    codes = ["A.TI", "B.TI", "C.TI"]
    db = _SnapshotDb(
        [(code, 1) for code in codes],
        existing_quality=SimpleNamespace(status="WARNING", coverage_rate=2 / 3),
        existing_count=2,
    )
    writes = _capture_snapshot_writes(monkeypatch)

    count = IngestionService(db, _MemberProvider(codes)).sync_ths_theme_member_snapshot(
        date(2026, 9, 23)
    )

    assert count == 3
    assert db.delete_count == 1
    assert writes[-1][1][0]["status"] == "PASS"
    assert writes[-1][1][0]["missing_count"] == 0
