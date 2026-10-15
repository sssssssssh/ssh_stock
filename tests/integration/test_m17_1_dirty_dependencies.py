from datetime import timedelta

import pytest
from app.domain.decision.contracts import PaperError
from app.domain.decision.requests import CreateObservation
from app.models.job import JobRun
from app.models.market_data import (
    DataDirtyRange,
    MarketDaily,
    SectorFactorDaily,
    StockDaily,
    StockFactorDaily,
    StockOpportunityDaily,
    StockStateDaily,
    StockTradeStatusDaily,
    TradeCalendar,
)
from app.models.paper import DecisionObservation, PaperFill, PaperLedgerEntry, PaperNavDaily
from app.services.decision.application import DecisionApplication
from app.services.decision.source import DecisionSourceReadiness
from app.services.dirty import blocking_dirty_range_id, record_dirty_range
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from tests.integration.m17_1_support import BRIDGE, HIST, add_dirty
from tests.integration.m17_1_support import dirty_paper as dirty_paper
from tests.integration.m17_support import CODES, DAY, NOW, settings


def counts(db):
    return tuple(db.scalar(select(func.count()).select_from(model)) for model in (
        DecisionObservation, PaperFill, PaperLedgerEntry, PaperNavDaily,
    ))


@pytest.mark.parametrize("start,end,status,blocked", [
    (DAY, DAY, "OPEN", True), (DAY - timedelta(days=2), DAY, "PROCESSING", True),
    (DAY, DAY + timedelta(days=2), "FAILED", True),
    (HIST, BRIDGE, "FAILED", False),
    (DAY + timedelta(days=1), DAY + timedelta(days=3), "OPEN", False),
    (HIST, DAY, "OPEN", True), (DAY, DAY + timedelta(days=1), "PROCESSING", True),
    (DAY, DAY, "RESOLVED", False),
])
def test_closed_intersections_and_proven_non_intersections(
    dirty_paper, start, end, status, blocked
):
    factory, _, owner, _, _ = dirty_paper
    with factory() as db:
        before = counts(db)
        add_dirty(db, start=start, end=end, status=status)
        service = DecisionApplication(db, settings(), clock=lambda: NOW)
        body = CreateObservation(request_id="observe", signal_date=DAY)
        if blocked:
            with pytest.raises(PaperError, match="SOURCE_DIRTY_RANGE$"):
                service.observe(owner, body)
            assert counts(db) == before
        else:
            row = service.observe(owner, body)
            assert service.observe(owner, body).id == row.id
            assert row.source_status == "READY"
            assert counts(db)[1:] == before[1:]


def test_multiple_ranges_choose_first_closed_intersection_deterministically(dirty_paper):
    factory, _, _, _, _ = dirty_paper
    with factory() as db:
        add_dirty(db)
        second = add_dirty(db, start=DAY, end=DAY, status="OPEN")
        first = add_dirty(db, start=BRIDGE, end=DAY, status="FAILED")
        add_dirty(db, start=DAY + timedelta(days=1), end=DAY + timedelta(days=3))
        assert first.id != second.id and blocking_dirty_range_id(db, DAY) == first.id
        with pytest.raises(PaperError, match="SOURCE_DIRTY_RANGE$"):
            DecisionSourceReadiness(db, settings()).capture(DAY, cutoff=NOW)


@pytest.mark.parametrize("change", ["reversed", "unknown_state", "null_start", "null_end"])
def test_malformed_dirty_fails_closed_or_database_refuses_null(dirty_paper, change):
    factory, _, _, _, _ = dirty_paper
    with factory() as db:
        before = counts(db)
        if change.startswith("null"):
            field = "dirty_start_date" if change == "null_start" else "dirty_end_date"
            row = DataDirtyRange(dataset="stock_daily", dirty_start_date=HIST,
                                 dirty_end_date=HIST, status="OPEN")
            setattr(row, field, None)
            db.add(row)
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
        else:
            add_dirty(db, start=DAY, end=HIST if change == "reversed" else DAY,
                      status="OPEN" if change == "reversed" else "UNKNOWN")
            with pytest.raises(PaperError, match="SOURCE_DIRTY_RANGE_INVALID"):
                DecisionSourceReadiness(db, settings()).capture(DAY, cutoff=NOW)
        assert counts(db) == before


@pytest.mark.parametrize("layer", [
    StockFactorDaily, StockStateDaily, StockTradeStatusDaily, MarketDaily, SectorFactorDaily,
])
def test_new_d_row_cannot_hide_unrepaired_historical_inputs(dirty_paper, layer):
    factory, _, owner, _, _ = dirty_paper
    with factory() as db:
        before = counts(db)
        add_dirty(db, created_at=NOW - timedelta(days=10))
        with pytest.raises(PaperError, match="SOURCE_DERIVED_STALE"):
            DecisionApplication(db, settings(), clock=lambda: NOW).observe(
                owner, CreateObservation(request_id="stale", signal_date=DAY),
            )
        assert counts(db) == before
        # A real successful range Job identity and actual rebuilt rows certify the repair.
        job = JobRun(job_type="recalculate", status="SUCCESS", target_trade_date=DAY,
                     started_at=NOW - timedelta(minutes=10), finished_at=NOW - timedelta(seconds=5),
                     job_metadata={"start": HIST.isoformat(), "end": DAY.isoformat()})
        db.add(job)
        db.flush()
        for model in (StockFactorDaily, StockStateDaily, StockTradeStatusDaily,
                      MarketDaily, SectorFactorDaily):
            for row in db.scalars(select(model).where(model.trade_date.between(HIST, DAY))):
                row.calc_run_id, row.calculated_at = job.id, NOW - timedelta(minutes=1)
        # Removing one required historical input is still not a completed repair.
        missing = db.scalar(select(layer).where(layer.trade_date == BRIDGE).limit(1))
        db.delete(missing)
        db.commit()
        with pytest.raises(PaperError, match="SOURCE_DERIVED_STALE"):
            DecisionSourceReadiness(db, settings()).capture(DAY, cutoff=NOW)


def test_historical_repair_restores_readiness_without_rewriting_old_observation(dirty_paper):
    factory, _, owner, _, _ = dirty_paper
    with factory() as db:
        service = DecisionApplication(db, settings(), clock=lambda: NOW)
        old = service.observe(owner, CreateObservation(request_id="old", signal_date=DAY))
        old_id, old_hash = old.id, old.record_hash
        row = db.get(StockDaily, (HIST, CODES[0]))
        row.close = 10.5
        row.source_updated_at = NOW - timedelta(minutes=20)
        dirty = record_dirty_range(db, dataset="stock_daily", dirty_dates={HIST}, reason="repair")
        dirty.created_at = NOW - timedelta(minutes=20)
        db.commit()
        with pytest.raises(PaperError, match="SOURCE_DERIVED_STALE"):
            service.observe(owner, CreateObservation(request_id="blocked", signal_date=DAY))
        job = JobRun(job_type="recalculate", status="SUCCESS", target_trade_date=DAY,
                     started_at=NOW - timedelta(minutes=15), finished_at=NOW - timedelta(seconds=5),
                     job_metadata={"start": HIST.isoformat(), "end": DAY.isoformat()})
        db.add(job)
        db.flush()
        for model in (StockFactorDaily, StockStateDaily, StockTradeStatusDaily,
                      MarketDaily, SectorFactorDaily, StockOpportunityDaily):
            for derived in db.scalars(select(model).where(model.trade_date.between(HIST, DAY))):
                derived.calc_run_id, derived.calculated_at = job.id, NOW - timedelta(minutes=1)
        # Even a lingering FAILED record outside D is not a permanent block after proven repair.
        dirty.status = "FAILED"
        db.commit()
        new = service.observe(owner, CreateObservation(request_id="repaired", signal_date=DAY))
        assert new.id != old_id
        db.expire_all()
        assert db.get(DecisionObservation, old_id).record_hash == old_hash
        assert db.get(DataDirtyRange, dirty.id).status == "FAILED"


@pytest.mark.parametrize("change", ["job_failed", "bad_scope", "old_identity", "calendar_gap"])
def test_nonintersecting_dirty_never_bypasses_lineage(dirty_paper, change):
    factory, _, _, _, _ = dirty_paper
    with factory() as db:
        add_dirty(db)
        row = db.scalar(select(StockFactorDaily).where(
            StockFactorDaily.trade_date == BRIDGE,
        ).limit(1))
        if change == "calendar_gap":
            db.delete(db.get(TradeCalendar, HIST + timedelta(days=1)))
        elif change == "old_identity":
            row.config_hash = "old"
        else:
            job = db.get(JobRun, row.calc_run_id)
            if change == "job_failed":
                job.status = "FAILED"
            else:
                job.target_trade_date, job.job_metadata = DAY, {"start": "bad", "end": "bad"}
        db.commit()
        error = "SOURCE_DERIVED_STALE|SOURCE_CALC_LINEAGE_UNAVAILABLE"
        with pytest.raises(PaperError, match=error):
            DecisionSourceReadiness(db, settings()).capture(DAY, cutoff=NOW)


def test_later_upstream_repair_requires_downstream_recalculation(dirty_paper):
    factory, _, _, _, _ = dirty_paper
    with factory() as db:
        add_dirty(db)
        newer = JobRun(job_type="recalculate", status="SUCCESS", target_trade_date=HIST,
                       started_at=NOW - timedelta(minutes=1), finished_at=NOW,
                       job_metadata={})
        db.add(newer)
        db.flush()
        for row in db.scalars(select(StockFactorDaily).where(StockFactorDaily.trade_date == HIST)):
            row.calc_run_id, row.calculated_at = newer.id, NOW - timedelta(seconds=10)
        db.commit()
        # Every row/job is individually valid and newer than the original dirty event.
        # But the later factor repair was not available to the earlier downstream jobs.
        with pytest.raises(PaperError, match="SOURCE_DERIVED_STALE"):
            DecisionSourceReadiness(db, settings()).capture(DAY, cutoff=NOW)


def test_multiple_nonintersections_and_datasets_do_not_change_frozen_source_hash(dirty_paper):
    factory, _, _, _, _ = dirty_paper
    with factory() as db:
        reader = DecisionSourceReadiness(db, settings())
        before = reader.capture(DAY, cutoff=NOW)
        add_dirty(db, start=HIST, end=BRIDGE, dataset="index_daily")
        add_dirty(db, start=BRIDGE, end=BRIDGE, status="PROCESSING", dataset="stock_adj_factor")
        add_dirty(db, start=DAY + timedelta(days=1), end=DAY + timedelta(days=3),
                  dataset="theme_daily", status="OPEN")
        after = reader.capture(DAY, cutoff=NOW)
        assert after == before
