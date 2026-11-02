"""Small PG17 diagnostic equivalence, explicitly not a million-row benchmark."""

import pandas as pd
from app.models.market_data import StockDaily
from app.repositories.calculation_frame import read_calculation_frame
from app.services.execution_diagnostics import ExecutionDiagnostics, active_diagnostics
from sqlalchemy import select

from scripts.v14_test_database import isolated_v14_database
from tests.integration.test_business_recalc_performance import seed


def test_opt_in_read_metrics_preserve_actual_frame_values_dtypes_and_cursor_rows(monkeypatch):
    with isolated_v14_database(monkeypatch) as (factory, _):
        seed(factory, include_closed=False, history_days=40)
        query = select(*StockDaily.__table__.columns).order_by(
            StockDaily.trade_date, StockDaily.ts_code)
        with factory() as db:
            expected = read_calculation_frame(db, query, name="trade_status.stock_daily")
            recorder = ExecutionDiagnostics()
            token = active_diagnostics.set(recorder)
            try:
                actual = read_calculation_frame(db, query, name="trade_status.stock_daily")
            finally:
                active_diagnostics.reset(token)
        pd.testing.assert_frame_equal(expected, actual, check_exact=True)
        measured = {phase: value for (_, phase), value in recorder.totals.items()}
        assert set(measured) == {"query", "fetch", "frame"}
        assert measured["fetch"]["rows"] == len(actual)
        assert measured["query"]["calls"] == measured["frame"]["calls"] == 1
