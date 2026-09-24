from datetime import date

import pytest
from app.models.market_data import StockBasic, TradeCalendar
from app.services.price_limit import (
    IPO_FIRST_5_TRADING_DAYS,
    IPO_LISTING_DAY,
    price_limit_exemptions,
    validate_price_limit_rows,
)
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

LIST_DATE = date(2026, 9, 18)
OPEN_DATES = [
    date(2026, 9, 18),
    date(2026, 9, 21),
    date(2026, 9, 23),
    date(2026, 9, 24),
    date(2026, 9, 25),
    date(2026, 9, 28),
]


def _session(*stocks: StockBasic) -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    StockBasic.__table__.create(engine)
    TradeCalendar.__table__.create(engine)
    db = Session(engine)
    db.add_all(stocks)
    calendar = []
    for day in range(18, 29):
        current = date(2026, 9, day)
        calendar.append(
            TradeCalendar(
                cal_date=current,
                is_open=current in OPEN_DATES,
                exchange="SSE",
            )
        )
    db.add_all(calendar)
    db.commit()
    return db


@pytest.mark.parametrize(
    ("exchange", "suffix"),
    [("SSE", "SH"), ("SZSE", "SZ")],
)
@pytest.mark.parametrize("nth_trade_day", [1, 2, 3, 4, 5])
def test_sse_szse_ipo_first_five_open_days_are_exempt(
    exchange: str,
    suffix: str,
    nth_trade_day: int,
) -> None:
    code = f"001234.{suffix}"
    with _session(
        StockBasic(ts_code=code, exchange=exchange, list_date=LIST_DATE)
    ) as db:
        result = price_limit_exemptions(
            db,
            trade_date=OPEN_DATES[nth_trade_day - 1],
            ts_codes={code},
        )[code]

    assert result.exempt is True
    assert result.reason == IPO_FIRST_5_TRADING_DAYS


@pytest.mark.parametrize(
    ("exchange", "code"),
    [("SSE", "001234.SH"), ("SZSE", "001234.SZ")],
)
def test_sse_szse_ipo_sixth_open_day_is_not_exempt(exchange: str, code: str) -> None:
    with _session(
        StockBasic(ts_code=code, exchange=exchange, list_date=LIST_DATE)
    ) as db:
        result = price_limit_exemptions(
            db,
            trade_date=OPEN_DATES[5],
            ts_codes={code},
        )[code]

    assert result.exempt is False
    assert result.reason is None


def test_bse_only_first_open_trading_day_is_exempt() -> None:
    code = "920025.BJ"
    with _session(
        StockBasic(ts_code=code, exchange="BSE", list_date=LIST_DATE)
    ) as db:
        listing_day = price_limit_exemptions(
            db,
            trade_date=OPEN_DATES[0],
            ts_codes={code},
        )[code]
        next_day = price_limit_exemptions(
            db,
            trade_date=OPEN_DATES[1],
            ts_codes={code},
        )[code]

    assert listing_day.exempt is True
    assert listing_day.reason == IPO_LISTING_DAY
    assert next_day.exempt is False


def test_closed_days_do_not_consume_ipo_window() -> None:
    code = "001234.SZ"
    with _session(
        StockBasic(ts_code=code, exchange="SZSE", list_date=LIST_DATE)
    ) as db:
        result = price_limit_exemptions(
            db,
            trade_date=date(2026, 9, 25),
            ts_codes={code},
        )[code]

    assert result.exempt is True
    assert result.evidence is not None
    assert result.evidence["qualifying_trade_dates"] == [
        "2026-09-18",
        "2026-09-21",
        "2026-09-23",
        "2026-09-24",
        "2026-09-25",
    ]


def test_missing_list_date_cannot_prove_exemption() -> None:
    code = "920025.BJ"
    with _session(StockBasic(ts_code=code, exchange="BSE", list_date=None)) as db:
        result = price_limit_exemptions(
            db,
            trade_date=OPEN_DATES[0],
            ts_codes={code},
        )[code]

    assert result.exempt is False
    assert result.evidence == {"diagnostic": "LIST_DATE_MISSING", "exchange": "BSE"}


def test_exchange_metadata_conflict_cannot_prove_exemption() -> None:
    code = "920025.BJ"
    with _session(
        StockBasic(ts_code=code, exchange="SSE", list_date=LIST_DATE)
    ) as db:
        result = price_limit_exemptions(
            db,
            trade_date=OPEN_DATES[0],
            ts_codes={code},
        )[code]

    assert result.exempt is False
    assert result.evidence is not None
    assert result.evidence["diagnostic"] == "EXCHANGE_METADATA_CONFLICT"


def test_exchange_suffix_is_used_when_metadata_is_missing() -> None:
    code = "920025.BJ"
    with _session(
        StockBasic(ts_code=code, exchange=None, list_date=LIST_DATE)
    ) as db:
        result = price_limit_exemptions(
            db,
            trade_date=OPEN_DATES[0],
            ts_codes={code},
        )[code]

    assert result.exempt is True
    assert result.reason == IPO_LISTING_DAY


def test_price_limit_exemption_uses_two_batch_queries() -> None:
    codes = {f"{index:06}.SZ" for index in range(20)}
    stocks = [
        StockBasic(
            ts_code=code,
            exchange="SZSE",
            list_date=LIST_DATE,
        )
        for code in codes
    ]
    with _session(*stocks) as db:
        statements: list[str] = []

        def record_statement(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(db.get_bind(), "before_cursor_execute", record_statement)
        try:
            results = price_limit_exemptions(
                db,
                trade_date=OPEN_DATES[0],
                ts_codes=codes,
            )
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", record_statement)

    assert len(results) == 20
    assert len(statements) == 2


def test_unclassified_zero_down_limit_remains_invalid() -> None:
    code = "000001.SZ"
    with _session(
        StockBasic(ts_code=code, exchange="SZSE", list_date=date(2020, 1, 1))
    ) as db:
        result = validate_price_limit_rows(
            db,
            trade_date=OPEN_DATES[0],
            rows=[{"ts_code": code, "up_limit": 99999.99, "down_limit": 0}],
        )

    assert result.valid_codes == set()
    assert result.invalid_codes == frozenset({code})
    assert result.unclassified_codes == frozenset({code})
