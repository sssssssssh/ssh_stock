from datetime import date

import pytest
from app.services.quality.daily_quality import check_daily_coverage


@pytest.mark.parametrize(
    ("actual_count", "expected_count", "expected_status"),
    [
        (100, 100, "PASS"),
        (99, 100, "PASS"),
        (97, 100, "WARNING"),
        (90, 100, "ERROR"),
    ],
)
def test_daily_coverage_status_thresholds(
    actual_count: int,
    expected_count: int,
    expected_status: str,
) -> None:
    expected_codes = {f"{idx:06d}.SZ" for idx in range(expected_count)}
    actual_codes = set(list(expected_codes)[:actual_count])

    result = check_daily_coverage(
        trade_date=date(2026, 8, 31),
        actual_codes=actual_codes,
        expected_codes=expected_codes,
        warning_coverage_rate=0.98,
        error_coverage_rate=0.95,
    )

    assert result.status == expected_status
    assert result.actual_rows == actual_count
    assert result.expected_rows == expected_count
    assert result.coverage_rate == pytest.approx(actual_count / expected_count)
