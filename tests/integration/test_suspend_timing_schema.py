from datetime import UTC, date, datetime

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from app.models.market_data import StockSuspendDaily
from sqlalchemy.exc import DataError

from tests.integration.m16_6_support import isolated_contract_database

DAY = date(2024, 9, 13)
OLD = "0055_retention_frozen_refs"
NEW = "0056_suspend_timing_text"


@pytest.fixture
def suspend_db(monkeypatch):
    with isolated_contract_database(monkeypatch) as database:
        yield database


def migrate(engine, target, *, downgrade=False):
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if downgrade else command.upgrade)(config, target)


def column(engine):
    return next(c for c in sa.inspect(engine).get_columns("stock_suspend_daily")
                if c["name"] == "suspend_timing")


def snapshot(engine):
    with engine.connect() as c:
        return c.execute(sa.select(StockSuspendDaily.__table__).order_by(
            StockSuspendDaily.trade_date, StockSuspendDaily.ts_code,
            StockSuspendDaily.suspend_type,
        )).all()


def test_fresh_postgresql_head_matches_nullable_text_orm(suspend_db):
    _, engine = suspend_db
    actual = column(engine)
    assert isinstance(actual["type"], sa.Text)
    assert actual["nullable"] is True
    assert isinstance(StockSuspendDaily.__table__.c.suspend_timing.type, sa.Text)
    assert sa.inspect(engine).get_pk_constraint("stock_suspend_daily")["constrained_columns"] == [
        "trade_date", "ts_code", "suspend_type",
    ]
    with engine.connect() as c:
        assert c.scalar(sa.text("SELECT version_num FROM alembic_version")) == NEW


def test_nonempty_upgrade_and_short_roundtrip_preserve_all_fields(suspend_db):
    _, engine = suspend_db
    migrate(engine, OLD, downgrade=True)
    stamp = datetime(2024, 9, 13, 8, tzinfo=UTC)
    with engine.begin() as c:
        c.execute(sa.insert(StockSuspendDaily), [
            dict(trade_date=DAY, ts_code=f"T{i:03}.SZ", suspend_type=kind,
                 suspend_timing=timing, created_at=stamp, updated_at=stamp)
            for i, (kind, timing) in enumerate((("S", None), ("R", "全天"), ("S", "中" * 32)))
        ])
    before = snapshot(engine)
    assert column(engine)["type"].length == 32
    migrate(engine, "head")
    assert snapshot(engine) == before
    assert isinstance(column(engine)["type"], sa.Text)
    migrate(engine, OLD, downgrade=True)
    assert snapshot(engine) == before
    assert column(engine)["type"].length == 32
    migrate(engine, "head")
    assert snapshot(engine) == before


def test_old_real_length_boundary_fails_then_text_accepts_without_truncation(suspend_db):
    _, engine = suspend_db
    migrate(engine, OLD, downgrade=True)
    # Synthetic description with the same measured 35-character length as the real response.
    timing = "09:30-10:00;13:00-13:30;14:00-14:30"
    assert len(timing) == 35
    values = dict(trade_date=DAY, ts_code="T001.SZ", suspend_type="S", suspend_timing=timing)
    with pytest.raises(DataError) as error, engine.begin() as c:
        c.execute(sa.insert(StockSuspendDaily).values(**values))
    assert error.value.orig.sqlstate == "22001"
    assert snapshot(engine) == []
    migrate(engine, "head")
    with engine.begin() as c:
        c.execute(sa.insert(StockSuspendDaily).values(**values))
    assert snapshot(engine)[0].suspend_timing == timing


@pytest.mark.parametrize("length", [33, 100, 500])
def test_downgrade_refuses_long_text_atomically(suspend_db, length):
    _, engine = suspend_db
    with engine.begin() as c:
        c.execute(sa.insert(StockSuspendDaily).values(
            trade_date=DAY, ts_code="T001.SZ", suspend_type="S", suspend_timing="中" * length,
        ))
    before = snapshot(engine)
    with pytest.raises(RuntimeError, match="SUSPEND_TIMING_DOWNGRADE_WOULD_TRUNCATE"):
        migrate(engine, OLD, downgrade=True)
    assert snapshot(engine) == before
    assert isinstance(column(engine)["type"], sa.Text)
    with engine.connect() as c:
        assert c.scalar(sa.text("SELECT version_num FROM alembic_version")) == NEW
