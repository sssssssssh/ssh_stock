import uuid
from datetime import UTC, datetime, time, timedelta

import pytest
import sqlalchemy as sa
from app.core.retention_config import RetentionPolicy
from app.domain.decision.contracts import PaperError
from app.models import Base
from app.models.job import JobRun
from app.models.market_data import DataDirtyRange, StockFactorDaily, TradeCalendar
from app.models.paper import PaperFill, PaperLedgerEntry, PaperNavDaily, PaperPositionDaily
from app.services.decision.source import DecisionSourceReadiness
from app.services.retention import run_retention

from tests.integration.m17_1_support import FIRST, HIST
from tests.integration.m17_1_support import dirty_paper as dirty_paper
from tests.integration.m17_support import DAY, NOW, settings
from tests.integration.test_m17_1_1_retention import migrate, old_job
from tests.integration.test_m17_1_paper_continuity import (
    FROZEN,
    assert_preserved,
    financial_counts,
    frozen_records,
)
from tests.integration.test_m17_paper_daily import approve, run

OLD = DAY - timedelta(days=400)
ENABLED = RetentionPolicy(job_deletion_enabled=True)


def historical_source(db, *, status="RESOLVED"):
    stamp = datetime.combine(OLD, time(10), UTC)
    job = JobRun(id=uuid.uuid4(), job_type="recalculate", status="SUCCESS",
                 target_trade_date=OLD, started_at=stamp - timedelta(minutes=1),
                 finished_at=stamp + timedelta(minutes=1), job_metadata={})
    db.add(job)
    db.flush()
    # Synthetic, internally consistent source rows; no production algorithm or ledger rewrite.
    for name in (
        "stock_daily", "stock_adj_factor", "stock_daily_basic", "stock_limit_daily",
        "stock_factor_daily", "stock_state_daily", "stock_trade_status_daily",
        "stock_opportunity_daily", "market_daily", "sector_factor_daily", "index_daily",
    ):
        table = Base.metadata.tables[name]
        rows = db.execute(sa.select(table).where(table.c.trade_date == HIST)).mappings().all()
        for row in rows:
            payload = dict(row)
            payload["trade_date"] = OLD
            if "calc_run_id" in payload:
                payload["calc_run_id"], payload["calculated_at"] = job.id, stamp
            if "source_updated_at" in payload:
                payload["source_updated_at"] = stamp - timedelta(minutes=1)
            db.execute(sa.insert(table).values(payload))
    day = OLD
    while day < HIST:
        db.add(TradeCalendar(cal_date=day, exchange="SSE", is_open=day == OLD))
        day += timedelta(days=1)
    db.add(DataDirtyRange(dataset="stock_daily", dirty_start_date=OLD, dirty_end_date=OLD,
                          status=status, source_job_id=job.id,
                          created_at=stamp - timedelta(days=1)))
    db.commit()
    return job.id


@pytest.mark.parametrize("status", ["RESOLVED", "FAILED"])
@pytest.mark.parametrize("budget_block", [False, True])
def test_400_day_history_retention_then_manual_approval_eod_and_replay(
    dirty_paper, status, budget_block,
):
    factory, _, owner, _, account = dirty_paper
    with factory() as db:
        historical = historical_source(db, status=status)
        spare = old_job(db)
        source = DecisionSourceReadiness(db, settings()).capture(DAY, cutoff=NOW)
        before, finance = frozen_records(db), financial_counts(db)
        policy = ENABLED.model_copy(update={"max_candidate_rows": 1}) if budget_block else ENABLED
        result = run_retention(db, now=NOW, policy=policy)
        assert result["blocked"] == budget_block
        if budget_block:
            assert result["error_code"] == "RETENTION_CANDIDATE_BUDGET_EXCEEDED"
            assert db.get(JobRun, spare) is not None
        else:
            assert result["protected_referenced_jobs"] == 1 and result["successful_jobs"] == 1
            assert db.get(JobRun, spare) is None
        assert db.get(JobRun, historical) is not None
        assert DecisionSourceReadiness(db, settings()).capture(DAY, cutoff=NOW) == source
        assert financial_counts(db) == finance
        assert_preserved(db, before)
    approve(factory, owner, account)
    first = run(factory, owner, account, FIRST)
    assert run(factory, owner, account, FIRST).result_hash == first.result_hash
    with factory() as db:
        fill = db.scalar(sa.select(PaperFill))
        nav = db.scalar(sa.select(PaperNavDaily))
        position = db.scalar(sa.select(PaperPositionDaily))
        assert nav.total_assets == nav.cash + position.market_value
        assert nav.cash == db.scalar(sa.select(sa.func.sum(PaperLedgerEntry.cash_delta)))
        assert position.quantity == fill.quantity and position.available_quantity == 0
        assert nav.trading_cost == fill.total_cost
        frozen = frozen_records(db)
        # Repeat cleanup with actual financial history present, not only empty child tables.
        result = run_retention(db, now=NOW, policy=ENABLED)
        assert not result["blocked"] and db.get(JobRun, historical) is not None
        assert_preserved(db, frozen)


def test_preexisting_missing_historical_job_is_diagnosed_and_never_recreated(dirty_paper):
    factory, engine, _, _, _ = dirty_paper
    with factory() as db:
        lost = historical_source(db)
        before, finance = frozen_records(db), financial_counts(db)
    migrate(engine, "0053_m17_decision_paper_foundation", downgrade=True)
    with factory() as db:
        db.execute(sa.delete(JobRun).where(JobRun.id == lost))
        db.commit()
    migrate(engine, "head")
    with factory() as db:
        result = run_retention(db, now=NOW, dry_run=True, include_diagnostics=True)
        assert not result["blocked"] and result["missing_provenance_references"] > 0
        assert any(row["job_id"] == str(lost) for row in result["missing_reference_samples"])
        assert db.get(JobRun, lost) is None
        with pytest.raises(PaperError, match="SOURCE_DERIVED_STALE"):
            DecisionSourceReadiness(db, settings()).capture(DAY, cutoff=NOW)
        assert financial_counts(db) == finance
        assert_preserved(db, before)


@pytest.mark.parametrize("change", ["failed", "scope", "warmup", "version", "order", "open"])
def test_retained_job_does_not_certify_invalid_lineage(dirty_paper, change):
    factory, _, _, _, _ = dirty_paper
    with factory() as db:
        identity = historical_source(db)
        job = db.get(JobRun, identity)
        if change == "failed":
            job.status = "FAILED"
        elif change in ("scope", "warmup"):
            job.target_trade_date = DAY
            job.job_metadata = {"start": DAY.isoformat(), "end": DAY.isoformat()}
            if change == "warmup":
                job.job_metadata["analysis_warmup_start"] = "invalid"
        elif change == "version":
            db.execute(sa.update(StockFactorDaily).where(
                StockFactorDaily.trade_date == OLD,
            ).values(config_hash="wrong-version"))
        elif change == "order":
            # Individually successful, but this repair postdates the historical consumers.
            newer = JobRun(job_type="recalculate", status="SUCCESS", target_trade_date=OLD,
                           started_at=NOW - timedelta(minutes=1), finished_at=NOW)
            db.add(newer)
            db.flush()
            db.execute(sa.update(StockFactorDaily).where(
                StockFactorDaily.trade_date == OLD,
            ).values(calc_run_id=newer.id, calculated_at=NOW - timedelta(seconds=10)))
        else:
            db.add(DataDirtyRange(dataset="stock_daily", dirty_start_date=DAY,
                                  dirty_end_date=DAY, status="OPEN"))
        db.commit()
        before, finance = frozen_records(db), financial_counts(db)
        result = run_retention(db, now=NOW, policy=ENABLED)
        assert not result["blocked"] and db.get(JobRun, identity) is not None
        with pytest.raises(PaperError, match=(
            "SOURCE_DIRTY_RANGE$" if change == "open" else "SOURCE_DERIVED_STALE"
        )):
            DecisionSourceReadiness(db, settings()).capture(DAY, cutoff=NOW)
        assert financial_counts(db) == finance
        assert_preserved(db, before)


def test_nonempty_paper_0053_0054_online_roundtrip_preserves_frozen_json_bytes(dirty_paper):
    from app.services.retention_indexes import prepare_retention_indexes
    from app.services.retention_lineage import assert_reference_schema

    factory, engine, owner, _, account = dirty_paper
    with factory() as db:
        historical_source(db)
    approve(factory, owner, account)
    head = run(factory, owner, account, FIRST)

    def byte_snapshot():
        with factory() as db:
            return {model.__tablename__: [
                (row.id, row.record_hash, row.raw.encode("utf-8"))
                for row in db.execute(sa.select(
                    model.id, model.record_hash, sa.cast(model.record_json, sa.Text).label("raw"),
                ).order_by(model.id))
            ] for model in FROZEN}

    before = byte_snapshot()
    migrate(engine, "0053_m17_decision_paper_foundation", downgrade=True)
    assert byte_snapshot() == before
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        prepare_retention_indexes(connection, apply=True)
    migrate(engine, "head")
    assert byte_snapshot() == before
    with factory() as db:
        assert_reference_schema(db)
        result = run_retention(db, now=NOW, policy=ENABLED)
        assert not result["blocked"] and result["protected_referenced_jobs"] > 0
    assert byte_snapshot() == before
    assert run(factory, owner, account, FIRST).result_hash == head.result_hash
