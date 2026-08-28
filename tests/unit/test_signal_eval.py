from datetime import date, timedelta

import pytest
from app.services.research import evaluate_forward_returns


def test_evaluate_forward_returns_calculates_closed_horizons() -> None:
    base = date(2026, 1, 1)
    rows = [
        {"trade_date": base + timedelta(days=offset), "adj_close": 100.0 + offset}
        for offset in range(0, 22)
    ]

    result = evaluate_forward_returns(base, rows)

    assert result is not None
    assert result["ret5"] == pytest.approx(0.05)
    assert result["ret10"] == pytest.approx(0.10)
    assert result["ret20"] == pytest.approx(0.20)
    assert result["ret60"] is None
    assert result["mfe20"] == pytest.approx(0.20)
    assert result["mae20"] == pytest.approx(0.01)
    assert result["evaluated_until_date"] == base + timedelta(days=21)


def test_evaluate_forward_returns_requires_exact_signal_date_close() -> None:
    base = date(2026, 1, 1)
    rows = [{"trade_date": base + timedelta(days=1), "adj_close": 101.0}]

    assert evaluate_forward_returns(base, rows) is None
