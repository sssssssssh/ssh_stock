from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest
from app.repositories.calculation_frame import read_calculation_frame
from pandas.testing import assert_frame_equal
from sqlalchemy import literal, select
from sqlalchemy.exc import OperationalError


class _Result:
    def __init__(self, batches):
        self.batches = batches
        self.closed = False

    def mappings(self):
        return self

    def partitions(self, size):
        assert size == 5000
        yield from self.batches

    def all(self):
        raise AssertionError("must not buffer the whole cursor")

    def close(self):
        self.closed = True


class _Db:
    def __init__(self, result):
        self.result = result

    def execute(self, statement):
        assert statement.get_execution_options()["yield_per"] == 5000
        return self.result


def test_frame_preserves_whole_result_types_order_and_nulls(monkeypatch):
    checks = []
    monkeypatch.setattr("app.repositories.calculation_frame.checkpoint", lambda: checks.append(1))
    rows = [
        {"day": date(2025, 1, 1), "value": None, "flag": None, "money": None},
        {"day": date(2025, 1, 2), "value": 1.5, "flag": False, "money": Decimal("1.23")},
        {"day": date(2025, 1, 3), "value": 0.0, "flag": True, "money": Decimal("0")},
    ]
    result = _Result([rows[:1], rows[1:]])
    actual = read_calculation_frame(_Db(result), select(literal(1)), name="trade_status.daily")
    assert_frame_equal(actual, pd.DataFrame(rows))
    assert result.closed
    assert len(checks) >= 2


def test_empty_frame_keeps_existing_no_column_behavior(monkeypatch):
    monkeypatch.setattr("app.repositories.calculation_frame.checkpoint", lambda: None)
    result = _Result([])
    assert_frame_equal(
        read_calculation_frame(_Db(result), select(literal(1)), name="factors.daily"),
        pd.DataFrame(),
    )
    assert result.closed


def test_partial_read_failure_raises_original_error_and_closes_cursor(monkeypatch):
    monkeypatch.setattr("app.repositories.calculation_frame.checkpoint", lambda: None)
    error = OperationalError("PRIVATE_SQL", {"secret": "PRIVATE_PARAMETER"}, RuntimeError("bad"))

    class FailedResult(_Result):
        def partitions(self, size):
            yield [{"value": 1}]
            raise error

    result = FailedResult([])
    with pytest.raises(OperationalError) as caught:
        read_calculation_frame(_Db(result), select(literal(1)), name="factors.daily")
    assert caught.value is error
    assert error.calculation_query_name == "factors.daily"
    assert result.closed


def test_cancellation_between_batches_closes_cursor(monkeypatch):
    checks = 0

    def checkpoint():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise RuntimeError("synthetic cancellation")

    monkeypatch.setattr("app.repositories.calculation_frame.checkpoint", checkpoint)
    result = _Result([[{"value": 1}], [{"value": 2}]])
    with pytest.raises(RuntimeError, match="synthetic cancellation"):
        read_calculation_frame(_Db(result), select(literal(1)), name="factors.daily")
    assert result.closed


@pytest.mark.parametrize("name", ["PRIVATE TOKEN", "bad;sql", "", "a" * 81])
def test_invalid_log_labels_rejected_before_query(name):
    with pytest.raises(ValueError, match="CALCULATION_READ_NAME_INVALID"):
        read_calculation_frame(SimpleNamespace(), select(literal(1)), name=name)
