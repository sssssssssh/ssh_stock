"""Real PG17 fetch deadlines, without touching any business database."""

import pandas as pd
import pytest
from app.repositories.calculation_frame import read_calculation_frame
from pandas.testing import assert_frame_equal
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError

from tests.integration.m16_6_support import isolated_contract_database


def test_pg17_streamed_fetches_keep_sql_timeout_and_full_result(monkeypatch):
    with isolated_contract_database(monkeypatch) as (factory, engine):
        # The original buffered SELECT exceeds the same unchanged SQL deadline.
        statement = text("SELECT n, pg_sleep(0.01) AS delay FROM generate_series(1, 100) n")
        with factory() as db:
            db.execute(text("SET LOCAL statement_timeout='500ms'"))
            with pytest.raises(OperationalError) as caught:
                db.execute(statement).all()
            assert caught.value.orig.sqlstate == "57014"
            assert "statement timeout" in caught.value.orig.diag.message_primary
            db.rollback()

        # A real named PostgreSQL cursor receives bounded batches instead of
        # waiting for all network output in one timed statement.
        cursors = []

        def observe(connection, cursor, statement, parameters, context, executemany):
            if context.execution_options.get("yield_per"):
                cursors.append(type(cursor).__name__)

        event.listen(engine, "before_cursor_execute", observe)
        try:
            with factory() as db:
                db.execute(text("SET LOCAL statement_timeout='500ms'"))
                # Cap each FETCH at five synthetic slow rows for this fixture.
                monkeypatch.setattr("app.repositories.calculation_frame.FETCH_ROWS", 5)
                result = read_calculation_frame(db, statement, name="diagnostic.slow_select")
                assert list(result["n"]) == list(range(1, 101))
                assert db.scalar(text("SHOW statement_timeout")) == "500ms"
                assert cursors == ["ServerCursor"]
                db.rollback()
        finally:
            event.remove(engine, "before_cursor_execute", observe)

        with factory() as db:
            statement = text("""SELECT n, CASE WHEN n=2 THEN NULL ELSE n::numeric/10 END AS value,
                                n%2=0 AS flag FROM generate_series(1, 13) n ORDER BY n DESC""")
            expected = pd.DataFrame(db.execute(statement).mappings().all())
            actual = read_calculation_frame(db, statement, name="diagnostic.ordered_select")
            assert_frame_equal(actual, expected)
            assert db.scalar(text("SELECT 1")) == 1
