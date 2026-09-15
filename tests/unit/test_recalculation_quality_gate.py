from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import app.services.recalculation as recalculation_module
import pytest
from app.services.quality.daily_quality import DataQualityError


class _FakeDb:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def add(self, row):
        return None

    def commit(self):
        self.commits += 1

    def refresh(self, row):
        return None

    def rollback(self):
        self.rollbacks += 1


class _SuccessfulFactorService:
    def __init__(self, db):
        self.db = db

    def recalc(self, start, end, calc_run_id=None):
        return 10


class _SuccessfulScalarService:
    def __init__(self, db):
        self.db = db

    def recalc(self, start, end, calc_run_id=None):
        return 1


class _SuccessfulTrendService:
    def __init__(self, db):
        self.db = db

    def recalc(self, start, end, calc_run_id=None):
        return {"states": 10, "signals": 2}


def _job():
    return SimpleNamespace(
        id=uuid4(),
        status="QUEUED",
        step=None,
        row_count=0,
        error_message=None,
        finished_at=None,
        job_metadata={},
    )


def _patch_successful_calculators(monkeypatch):
    monkeypatch.setattr(recalculation_module, "TradeStatusService", _SuccessfulScalarService)
    monkeypatch.setattr(recalculation_module, "FactorService", _SuccessfulFactorService)
    monkeypatch.setattr(recalculation_module, "MarketService", _SuccessfulScalarService)
    monkeypatch.setattr(recalculation_module, "SectorService", _SuccessfulScalarService)
    monkeypatch.setattr(recalculation_module, "TrendService", _SuccessfulTrendService)


def test_run_recalculation_cross_table_gate_passes_before_success(monkeypatch) -> None:
    _patch_successful_calculators(monkeypatch)
    signal_calls = []
    quality_calls = []

    class SignalEvaluationService:
        def __init__(self, db):
            self.db = db

        def evaluate(self, *, start, end):
            signal_calls.append((start, end))
            return {"evaluated": 3}

    def validate_cross_table_range(db, start, end, **kwargs):
        quality_calls.append((start, end, kwargs))
        return SimpleNamespace(
            has_error=False,
            as_metadata=lambda: {
                "cross_table_checked_days": 2,
                "cross_table_error_days": 0,
                "cross_table_error_dates": [],
                "cross_table_error_datasets": {},
            },
        )

    monkeypatch.setattr(recalculation_module, "SignalEvaluationService", SignalEvaluationService)
    monkeypatch.setattr(
        recalculation_module,
        "validate_cross_table_range",
        validate_cross_table_range,
    )
    job = _job()

    recalculation_module.run_recalculation(
        _FakeDb(),
        job,
        date(2026, 9, 1),
        date(2026, 9, 2),
        evaluate_signals=True,
    )

    assert job.status == "SUCCESS"
    assert quality_calls[0][0:2] == (date(2026, 9, 1), date(2026, 9, 2))
    assert job.job_metadata["cross_table_checked_days"] == 2
    assert signal_calls == [(date(2026, 9, 1), date(2026, 9, 2))]


def test_run_recalculation_cross_table_error_fails_and_skips_signals(monkeypatch) -> None:
    _patch_successful_calculators(monkeypatch)
    signal_calls = []

    class SignalEvaluationService:
        def __init__(self, db):
            self.db = db

        def evaluate(self, *, start, end):
            signal_calls.append((start, end))
            return {"evaluated": 3}

    def validate_cross_table_range(db, start, end, **kwargs):
        db.commit()
        return SimpleNamespace(
            has_error=True,
            error_dates=[date(2026, 9, 2)],
            error_datasets={"2026-09-02": ["factor_vs_daily"]},
            as_metadata=lambda: {
                "cross_table_checked_days": 2,
                "cross_table_error_days": 1,
                "cross_table_error_dates": ["2026-09-02"],
                "cross_table_error_datasets": {"2026-09-02": ["factor_vs_daily"]},
            },
        )

    db = _FakeDb()
    job = _job()
    monkeypatch.setattr(recalculation_module, "SignalEvaluationService", SignalEvaluationService)
    monkeypatch.setattr(
        recalculation_module,
        "validate_cross_table_range",
        validate_cross_table_range,
    )

    with pytest.raises(DataQualityError, match="cross table quality failed"):
        recalculation_module.run_recalculation(
            db,
            job,
            date(2026, 9, 1),
            date(2026, 9, 2),
            evaluate_signals=True,
        )

    assert db.commits >= 1
    assert job.status == "FAILED"
    assert job.job_metadata["cross_table_error_days"] == 1
    assert signal_calls == []
