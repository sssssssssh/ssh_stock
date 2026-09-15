from datetime import date, timedelta

import app.jobs.backfill_job as backfill_module
from app.jobs.backfill_job import _any_index_daily_incomplete
from app.models.market_data import IndexDaily
from app.services.ingestion.service import _index_range_chunks
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_index_range_is_split_into_two_year_chunks() -> None:
    start = date(2020, 1, 1)
    end = date(2025, 1, 1)

    chunks = _index_range_chunks(start, end)

    assert chunks[0][0] == start
    assert chunks[-1][1] == end
    assert all((chunk_end - chunk_start).days < 730 for chunk_start, chunk_end in chunks)
    assert all(
        left_end + timedelta(days=1) == right_start
        for (_, left_end), (right_start, _) in zip(chunks, chunks[1:], strict=False)
    )


def test_index_completeness_precheck_uses_single_bulk_query(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    IndexDaily.__table__.create(engine)
    db = Session(engine)
    dates = [date(2026, 9, 14), date(2026, 9, 15)]
    settings = type(
        "Settings",
        (),
        {"strategy": {"benchmark": {"market_indices": ["000300.SH"]}}},
    )()
    monkeypatch.setattr(backfill_module, "get_settings", lambda: settings)
    db.add_all(
        [
            IndexDaily(
                trade_date=item,
                ts_code="000300.SH",
                close=1,
                pre_close=1,
            )
            for item in dates
        ]
    )
    db.commit()

    assert _any_index_daily_incomplete(db, dates) is False
    db.query(IndexDaily).filter(IndexDaily.trade_date == dates[-1]).delete()
    db.commit()
    assert _any_index_daily_incomplete(db, dates) is True
