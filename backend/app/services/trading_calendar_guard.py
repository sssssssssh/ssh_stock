"""A closed-day decision requires a complete calendar, never missing prices."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.market_data import TradeCalendar


class TradingCalendarError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def verified_open_days(db: Session, start: date, end: date) -> tuple[date, ...]:
    if end < start:
        raise TradingCalendarError("INVALID_DATE_RANGE")
    rows = db.execute(select(TradeCalendar.cal_date, TradeCalendar.is_open).where(
        TradeCalendar.cal_date.between(start, end),
    ).order_by(TradeCalendar.cal_date)).all()
    # PK uniqueness plus one row per calendar day proves coverage, including
    # weekends/holidays. No inference from Raw presence or weekday conventions.
    if (len(rows) != (end-start).days + 1
            or any(type(row.is_open) is not bool for row in rows)):
        raise TradingCalendarError("TRADE_CALENDAR_UNVERIFIED")
    return tuple(row.cal_date for row in rows if row.is_open)


def require_recalculation_days(db: Session, start: date, end: date) -> tuple[date, ...]:
    days = verified_open_days(db, start, end)
    if not days:
        raise TradingCalendarError("NO_TRADING_DAYS")
    return days
