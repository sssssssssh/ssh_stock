from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.domain.decision.contracts import PaperError
from app.services.decision.dependencies import check_dirty_dependencies, job_covers_scope
from app.services.decision.source import DecisionSourceReadiness
from app.services.dirty import blocking_dirty_range_id, invalid_dirty_range_id
from sqlalchemy.dialects import postgresql

D = date(2026, 10, 15)
NOW = datetime(2026, 10, 15, 10, tzinfo=UTC)


class ScalarDb:
    def __init__(self, *results):
        self.results = iter(results)
        self.sql = []

    def scalar(self, statement):
        self.sql.append(str(statement.compile(dialect=postgresql.dialect())))
        return next(self.results)

    def get(self, *args):
        return SimpleNamespace(exchange="SSE", is_open=True)


def test_closed_dirty_query_is_ordered_bounded_and_not_json_loading():
    db = ScalarDb(0)
    assert blocking_dirty_range_id(db, D) == 0
    sql = db.sql[0]
    assert "dirty_start_date <=" in sql and "dirty_end_date >=" in sql
    assert "ORDER BY data_dirty_range.dirty_start_date, data_dirty_range.id" in sql
    assert "LIMIT" in sql and "record_json" not in sql


@pytest.mark.parametrize("invalid,expected", [(0, "SOURCE_DIRTY_RANGE_INVALID"),
                                               (None, "SOURCE_DIRTY_RANGE")])
def test_zero_id_still_blocks_source(invalid, expected):
    db = ScalarDb(invalid, 0)
    config = SimpleNamespace(paper_config=SimpleNamespace(decision=None))
    with pytest.raises(PaperError, match=expected):
        DecisionSourceReadiness(db, config)._capture(db, D, NOW, ())


def test_invalid_dirty_query_checks_reversed_missing_dates_and_unknown_state():
    db = ScalarDb(None)
    assert invalid_dirty_range_id(db) is None
    assert "dirty_start_date > data_dirty_range.dirty_end_date" in db.sql[0]
    assert "IS NULL" in db.sql[0] and "NOT IN" in db.sql[0] and "LIMIT" in db.sql[0]


def test_no_dirty_dependency_fast_path_does_not_read_history():
    db = ScalarDb(None)
    check_dirty_dependencies(db, D, NOW, None, {}, "hash")
    assert len(db.sql) == 1 and "min(data_dirty_range.dirty_start_date)" in db.sql[0]


@pytest.mark.parametrize("budget", ["calendar", "jobs"])
def test_historical_capacity_refuses_before_job_metadata_or_row_load(budget):
    config = SimpleNamespace(algo_version="test", paper_config=SimpleNamespace(
        decision=SimpleNamespace(max_source_rows=100),
    ))
    db = ScalarDb(D - timedelta(days=101) if budget == "calendar" else D - timedelta(days=1),
                  2, 101)
    with pytest.raises(PaperError, match="DECISION_SOURCE_CAPACITY_EXCEEDED"):
        check_dirty_dependencies(db, D, NOW, config, {}, "hash")
    assert not any("job_metadata" in sql or "record_json" in sql for sql in db.sql)


def test_historical_dependency_queries_compile_with_explicit_correlation():
    from app.models.market_data import (
        MarketDaily,
        SectorFactorDaily,
        StockFactorDaily,
        StockStateDaily,
        StockTradeStatusDaily,
    )

    class CompilingDb(ScalarDb):
        def scalar(self, statement):
            self.sql.append(str(statement.compile(dialect=postgresql.dialect())))
            return next(self.results, None)

        def execute(self, statement):
            self.sql.append(str(statement.compile(dialect=postgresql.dialect())))
            return SimpleNamespace(all=lambda: [])

    from app.core.config import get_settings

    db = CompilingDb(D - timedelta(days=1), 2, 0)
    versions = {model: "test" for model in (
        StockFactorDaily, StockStateDaily, StockTradeStatusDaily, MarketDaily, SectorFactorDaily,
    )}
    check_dirty_dependencies(db, D, NOW, get_settings(), versions, "hash")
    assert len(db.sql) <= 16
    assert any("upstream" in sql and "downstream" in sql for sql in db.sql)
    assert not any("record_json" in sql for sql in db.sql)


@pytest.mark.parametrize("change", [
    {"status": "FAILED"}, {"job_type": "PAPER_DAILY"}, {"started_at": None},
    {"finished_at": None}, {"finished_at": NOW + timedelta(seconds=1)},
    {"started_at": NOW + timedelta(seconds=1)}, {"start": "2026-02-30"},
    {"start": "20261001"}, {"start": None}, {"end": "2026-10-14"},
    {"start": "2026-10-16"},
])
def test_historical_job_proof_fails_closed(change):
    job = SimpleNamespace(
        status="SUCCESS", job_type="recalculate", target_trade_date=D - timedelta(days=1),
        started_at=NOW - timedelta(minutes=3), finished_at=NOW,
        start="2026-10-01", end="2026-10-15",
    )
    job.__dict__.update(change)
    assert not job_covers_scope(job, D - timedelta(days=10), D, NOW)


def test_real_target_or_validated_full_iso_range_are_required():
    job = SimpleNamespace(
        status="SUCCESS", job_type="daily", target_trade_date=D,
        started_at=NOW - timedelta(minutes=3), finished_at=NOW, start=None, end=None,
    )
    assert job_covers_scope(job, D, D, NOW)
    assert not job_covers_scope(job, D - timedelta(days=1), D, NOW)
    job.start, job.end = "2026-10-01", "2026-10-15"
    assert job_covers_scope(job, D - timedelta(days=10), D, NOW)


def test_existing_recalculation_warmup_is_an_explicit_foundation_date_scope():
    job = SimpleNamespace(
        status="SUCCESS", job_type="recalculate", target_trade_date=D,
        started_at=NOW - timedelta(minutes=3), finished_at=NOW,
        start="2026-10-15", end="2026-10-15", analysis_start="2026-10-01",
    )
    assert job_covers_scope(job, D - timedelta(days=10), D, NOW)
    for invalid in ("2026-10-16", "2026-02-30", "20261001"):
        job.analysis_start = invalid
        assert not job_covers_scope(job, D - timedelta(days=10), D, NOW)
