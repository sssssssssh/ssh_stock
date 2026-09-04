from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import app.api.v1.jobs as jobs_module
import app.services.recalculation as recalculation_module


class _FakeSession:
    def __init__(self, job):
        self.job = job
        self.commits = 0
        self.rollbacks = 0

    def get(self, model, row_id):
        return self.job

    def add(self, row):
        return None

    def commit(self):
        self.commits += 1

    def refresh(self, row):
        return None

    def rollback(self):
        self.rollbacks += 1


class _FakeSessionLocal:
    def __init__(self, db):
        self.db = db

    def __call__(self):
        return self

    def __enter__(self):
        return self.db

    def __exit__(self, exc_type, exc, traceback):
        return False


class _FailingFactorService:
    def __init__(self, db):
        self.db = db

    def recalc(self, start, end, calc_run_id=None):
        raise RuntimeError("factor boom")


class _SuccessfulFactorService:
    calls = []
    factor_values = {"2026-01-04": 10.0}

    def __init__(self, db):
        self.db = db

    def recalc(self, start, end, calc_run_id=None):
        self.calls.append((start, end, calc_run_id))
        self.factor_values["2026-01-04"] = 12.5
        return 2


class _SuccessfulScalarService:
    def __init__(self, db):
        self.db = db

    def recalc(self, start, end, calc_run_id=None):
        return 1


class _SuccessfulTrendService:
    def __init__(self, db):
        self.db = db

    def recalc(self, start, end):
        return {"states": 1, "signals": 1}


def test_dirty_repair_failure_can_retry_and_resolve(monkeypatch) -> None:
    job_id = uuid4()
    job = SimpleNamespace(
        id=job_id,
        job_type="recalculate",
        target_trade_date=date(2026, 1, 5),
        started_at=None,
        finished_at=None,
        status="QUEUED",
        step=None,
        row_count=0,
        error_message=None,
        job_metadata={},
    )
    dirty_range = SimpleNamespace(
        id=1,
        dataset="stock_daily",
        dirty_start_date=date(2026, 1, 3),
        dirty_end_date=date(2026, 1, 3),
        status="OPEN",
        retry_count=0,
        last_error=None,
        last_failed_at=None,
        resolved_at=None,
    )
    db = _FakeSession(job)
    monkeypatch.setattr(recalculation_module, "FactorService", _FailingFactorService)

    try:
        recalculation_module.run_recalculation(
            db,
            job,
            date(2026, 1, 3),
            date(2026, 1, 5),
            evaluate_signals=False,
            mode="dirty_repair",
            dirty_ranges=[dirty_range],
        )
    except RuntimeError:
        jobs_module._mark_background_failed(db, job_id, RuntimeError("factor boom"))

    assert dirty_range.status == "FAILED"
    assert dirty_range.retry_count == 1
    assert dirty_range.last_error == "factor boom"
    assert dirty_range.last_failed_at is not None
    assert job.status == "FAILED"

    job.status = "QUEUED"
    job.finished_at = None
    job.error_message = None
    dirty_range.status = "OPEN"
    _SuccessfulFactorService.calls = []
    _SuccessfulFactorService.factor_values = {"2026-01-04": 10.0}
    monkeypatch.setattr(recalculation_module, "FactorService", _SuccessfulFactorService)
    monkeypatch.setattr(recalculation_module, "MarketService", _SuccessfulScalarService)
    monkeypatch.setattr(recalculation_module, "SectorService", _SuccessfulScalarService)
    monkeypatch.setattr(recalculation_module, "TrendService", _SuccessfulTrendService)

    recalculation_module.run_recalculation(
        db,
        job,
        date(2026, 1, 3),
        date(2026, 1, 5),
        evaluate_signals=False,
        mode="dirty_repair",
        dirty_ranges=[dirty_range],
    )

    assert dirty_range.status == "RESOLVED"
    assert dirty_range.resolved_at is not None
    assert job.status == "SUCCESS"
    assert _SuccessfulFactorService.calls
    assert _SuccessfulFactorService.calls[0][0] == date(2026, 1, 3)
    assert _SuccessfulFactorService.calls[-1][1] == date(2026, 1, 5)
    assert _SuccessfulFactorService.calls[0][2] == job_id
    assert _SuccessfulFactorService.factor_values["2026-01-04"] == 12.5
