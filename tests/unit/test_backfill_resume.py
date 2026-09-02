from datetime import date
from unittest.mock import Mock

from app.jobs.backfill_job import _raw_data_complete


def _result(value: object, scalar_method: str = "scalar_one") -> Mock:
    result = Mock()
    getattr(result, scalar_method).return_value = value
    return result


def test_raw_data_complete_when_all_raw_tables_have_rows() -> None:
    db = Mock()
    db.execute.side_effect = [
        _result(5000),
        _result(5000),
        _result(5000),
        _result(3),
        _result("PASS", "scalar_one_or_none"),
    ]

    assert _raw_data_complete(db, date(2026, 6, 24)) is True


def test_raw_data_is_not_complete_when_any_raw_table_is_missing() -> None:
    db = Mock()
    db.execute.side_effect = [
        _result(5000),
        _result(0),
        _result(5000),
        _result(3),
        _result("PASS", "scalar_one_or_none"),
    ]

    assert _raw_data_complete(db, date(2026, 6, 24)) is False


def test_raw_data_is_not_complete_when_quality_failed() -> None:
    db = Mock()
    db.execute.side_effect = [
        _result(5000),
        _result(5000),
        _result(5000),
        _result(3),
        _result("ERROR", "scalar_one_or_none"),
    ]

    assert _raw_data_complete(db, date(2026, 6, 24)) is False
