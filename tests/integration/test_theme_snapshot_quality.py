from datetime import date

import sqlalchemy as sa
from app.core.config import get_settings
from app.services.quality.theme_quality import (
    latest_strict_theme_member_snapshot,
    latest_usable_theme_member_snapshot,
    required_strict_theme_snapshot_dates,
    required_usable_theme_snapshot_dates,
)
from sqlalchemy.orm import Session


def test_strict_and_usable_theme_snapshot_semantics_are_distinct() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(sa.text("""
            CREATE TEMPORARY TABLE data_quality_daily (
                trade_date date NOT NULL,
                dataset varchar(64) NOT NULL,
                status varchar(32) NOT NULL,
                coverage_rate double precision
            ) ON COMMIT DROP
        """))
        connection.execute(
            sa.text("""
                INSERT INTO data_quality_daily
                    (trade_date, dataset, status, coverage_rate)
                VALUES
                    ('2026-09-01', 'ths_theme_member_snapshot', 'PASS', 1.0),
                    ('2026-09-08', 'ths_theme_member_snapshot', 'WARNING', 0.98),
                    ('2026-09-15', 'ths_theme_member_snapshot', 'WARNING', 0.80)
            """)
        )
        with Session(bind=connection) as db:
            target = date(2026, 9, 20)
            assert latest_strict_theme_member_snapshot(db, target) == date(2026, 9, 1)
            assert latest_usable_theme_member_snapshot(db, target) == date(2026, 9, 8)
            assert required_strict_theme_snapshot_dates(
                db, date(2026, 9, 1), target
            ) == [date(2026, 9, 1)]
            assert required_usable_theme_snapshot_dates(
                db, date(2026, 9, 1), target
            ) == [date(2026, 9, 1), date(2026, 9, 8)]
        transaction.rollback()
    engine.dispose()
