import pytest

from scripts.ab_read_benchmark_v14 import compare_runs


def sample():
    return [{"variant": variant, "seconds": elapsed, "rows": 123, "hash": "synthetic",
             "dtypes": {"is_st": "object"}} for variant, elapsed in (("q0", 2), ("q2", 3))]


def test_slower_read_cannot_close_performance():
    result = compare_runs({"runs": sample()})
    assert result["full_fetch_golden"] == "PASS"
    assert result["suggested_50pct_target_met"] is False
    assert result["read_performance"] == "OPEN"


@pytest.mark.parametrize("field,value", [("rows", 122), ("hash", "wrong"), ("dtypes", {})])
def test_any_partial_or_type_difference_blocks_golden(field, value):
    runs = sample()
    runs[-1][field] = value
    with pytest.raises(ValueError, match="V14_GOLDEN_MISMATCH"):
        compare_runs({"runs": runs})


def test_no_rows_receipt_is_not_a_successful_empty_query():
    with pytest.raises(ValueError, match="V14_NO_COMPLETE_FETCH_RECEIPT"):
        compare_runs({"runs": []})
