from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from app.models.job import JobRun
from app.models.market_data import DataQualityDaily
from app.services import recalculation
from sqlalchemy.exc import OperationalError

from tests.integration.m16_6_support import isolated_contract_database


def test_disconnect_rolls_back_before_recording_failure_and_preserves_committed_evidence(
    monkeypatch,
):
    with isolated_contract_database(monkeypatch) as (factory, engine):
        day, job_id = date(2026, 9, 1), uuid4()
        with factory() as db:
            db.add(JobRun(id=job_id, job_type="recalculate", status="RUNNING",
                          row_count=0, job_metadata={}))
            db.commit()
            db.add(DataQualityDaily(trade_date=day, dataset="synthetic_committed_evidence",
                                    status="PASS", expected_rows=1, actual_rows=1, job_id=job_id))
            db.commit()

        original = OperationalError("synthetic interrupted statement", {}, OSError("disconnected"),
                                    connection_invalidated=True)

        class InterruptedStage:
            def __init__(self, db):
                self.db = db

            def recalc(self, *args, **kwargs):
                self.db.connection().invalidate()
                raise original

        monkeypatch.setattr(recalculation, "TradeStatusService", InterruptedStage)
        monkeypatch.setattr(recalculation, "validate_recalculation_raw_prerequisites",
                            lambda *args, **kwargs: None)
        monkeypatch.setattr(recalculation, "_factor_warmup_start", lambda db, start: start)
        with factory() as db:
            job = db.get(JobRun, job_id)
            with pytest.raises(OperationalError) as error:
                recalculation.run_recalculation(db, job, day, day, evaluate_signals=False)
            assert error.value is original
        with factory() as db:
            saved = db.get(JobRun, job_id)
            assert saved.status == "FAILED"
            assert saved.job_metadata["stage"] == "failed"
            assert saved.error_message == "database operation failed: OperationalError/OSError"
            evidence = db.scalar(sa.select(DataQualityDaily).where(
                DataQualityDaily.job_id == job_id,
            ))
            assert evidence.status == "PASS"
            assert evidence.actual_rows == 1


def test_dirty_failure_is_recorded_only_after_rollback(monkeypatch):
    events = []
    original = OperationalError("synthetic", {}, OSError("disconnected"))
    job = SimpleNamespace(id=uuid4(), job_metadata={})
    row = SimpleNamespace(id=1)

    class Db:
        def rollback(self):
            events.append("rollback")

    def interrupted(*args, **kwargs):
        raise original

    def record_dirty(*args, **kwargs):
        assert events == ["rollback"]
        events.append("dirty failed")

    monkeypatch.setattr(recalculation, "_factor_warmup_start", interrupted)
    monkeypatch.setattr(recalculation, "mark_dirty_ranges_failed", record_dirty)
    monkeypatch.setattr(recalculation, "update_job", lambda *a, **kw: events.append(kw["status"]))
    with pytest.raises(OperationalError) as error:
        recalculation.run_recalculation(Db(), job, date(2026, 9, 1), date(2026, 9, 1),
                                        evaluate_signals=False, dirty_ranges=[row])
    assert error.value is original
    assert events == ["rollback", "dirty failed", "FAILED"]
