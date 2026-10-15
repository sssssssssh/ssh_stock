from datetime import timedelta

import pytest
from app.domain.decision.account_requests import CreatePaperAccount
from app.domain.decision.requests import PaperRequest
from app.models.market_data import DataDirtyRange, TradeCalendar
from app.services.paper.accounts import PaperAccountApplication
from sqlalchemy import event

from tests.integration.m16_6_support import isolated_contract_database
from tests.integration.m17_support import DAY, NOW, seed, settings

HIST = DAY - timedelta(days=20)
BRIDGE = DAY - timedelta(days=18)
FIRST = DAY + timedelta(days=1)
SECOND = DAY + timedelta(days=2)
AFTER_HOLIDAY = DAY + timedelta(days=6)
DAYS = (HIST, BRIDGE, DAY, FIRST, SECOND, AFTER_HOLIDAY)


@pytest.fixture
def dirty_paper(monkeypatch):
    with isolated_contract_database(monkeypatch) as (factory, engine):
        def bound(connection):
            connection.exec_driver_sql("SET LOCAL lock_timeout = '10s'")

        event.listen(engine, "begin", bound)
        with factory() as db:
            owner, other, _ = seed(db, days=DAYS, account=False)
            day = HIST
            while day <= AFTER_HOLIDAY:
                if db.get(TradeCalendar, day) is None:
                    db.add(TradeCalendar(cal_date=day, exchange="SSE", is_open=False))
                day += timedelta(days=1)
            db.commit()
            app = PaperAccountApplication(db, settings(), clock=lambda: NOW)
            account = app.create(owner, CreatePaperAccount(
                request_id="create", name="m17.1 synthetic", initial_cash="1000000",
            ))
            app.transition(owner, account.id, PaperRequest(request_id="activate"), "ACTIVE")
            account_id = account.id
        try:
            yield factory, engine, owner, other, account_id
        finally:
            event.remove(engine, "begin", bound)


def add_dirty(db, *, start=HIST, end=HIST, status="FAILED", created_at=None, dataset="stock_daily"):
    row = DataDirtyRange(
        dataset=dataset, dirty_start_date=start, dirty_end_date=end, status=status,
        created_at=created_at or NOW - timedelta(days=30),
    )
    db.add(row)
    db.commit()
    return row
