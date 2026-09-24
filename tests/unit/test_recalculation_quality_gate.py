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
    monkeypatch.setattr(
        recalculation_module,
        "validate_recalculation_raw_prerequisites",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        recalculation_module,
        "_factor_warmup_start",
        lambda db, start: start,
    )
    monkeypatch.setattr(recalculation_module, "TradeStatusService", _SuccessfulScalarService)
    monkeypatch.setattr(recalculation_module, "FactorService", _SuccessfulFactorService)
    monkeypatch.setattr(recalculation_module, "MarketService", _SuccessfulScalarService)
    monkeypatch.setattr(recalculation_module, "SectorService", _SuccessfulScalarService)
    monkeypatch.setattr(recalculation_module, "ThemeFactorService", _SuccessfulScalarService)
    monkeypatch.setattr(recalculation_module, "TrendService", _SuccessfulTrendService)
    monkeypatch.setattr(recalculation_module, "OpportunityService", _SuccessfulScalarService)


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


def test_run_recalculation_warms_all_analysis_but_validates_requested_range(
    monkeypatch,
) -> None:
    requested_start = date(2026, 9, 10)
    warmup_start = date(2026, 8, 3)
    end = date(2026, 9, 16)
    calls = []

    class ScalarService:
        def __init__(self, db):
            self.name = self.__class__.__name__

        def recalc(self, start, finish, calc_run_id=None):
            calls.append((self.name, start, finish, calc_run_id))
            return 1

    class FactorService(ScalarService):
        pass

    class MarketService(ScalarService):
        pass

    class SectorService(ScalarService):
        pass

    class TradeStatusService(ScalarService):
        pass

    class ThemeFactorService(ScalarService):
        pass

    class OpportunityService(ScalarService):
        pass

    class TrendService(ScalarService):
        def recalc(self, start, finish, calc_run_id=None):
            calls.append((self.name, start, finish, calc_run_id))
            return {"states": 1, "signals": 0}

    monkeypatch.setattr(
        recalculation_module,
        "_factor_warmup_start",
        lambda db, start: warmup_start,
    )
    monkeypatch.setattr(
        recalculation_module,
        "validate_recalculation_raw_prerequisites",
        lambda db, start, finish, **kwargs: calls.append(("raw", start, finish, None)),
    )
    monkeypatch.setattr(recalculation_module, "TradeStatusService", TradeStatusService)
    monkeypatch.setattr(recalculation_module, "FactorService", FactorService)
    monkeypatch.setattr(recalculation_module, "MarketService", MarketService)
    monkeypatch.setattr(recalculation_module, "SectorService", SectorService)
    monkeypatch.setattr(recalculation_module, "ThemeFactorService", ThemeFactorService)
    monkeypatch.setattr(recalculation_module, "TrendService", TrendService)
    monkeypatch.setattr(recalculation_module, "OpportunityService", OpportunityService)
    monkeypatch.setattr(
        recalculation_module,
        "validate_cross_table_range",
        lambda db, start, finish, **kwargs: (
            calls.append(("quality", start, finish, kwargs["job_id"]))
            or SimpleNamespace(has_error=False, as_metadata=lambda: {})
        ),
    )

    class SignalService:
        def __init__(self, db):
            pass

        def evaluate(self, *, start, end):
            calls.append(("signal", start, end, None))
            return {"evaluated": 0}

    monkeypatch.setattr(recalculation_module, "SignalEvaluationService", SignalService)
    job = _job()

    recalculation_module.run_recalculation(
        _FakeDb(),
        job,
        requested_start,
        end,
        evaluate_signals=True,
    )

    for service_name in {
        "TradeStatusService",
        "FactorService",
        "MarketService",
        "SectorService",
        "TrendService",
    }:
        service_calls = [call for call in calls if call[0] == service_name]
        assert service_calls
        assert service_calls[0][1] == warmup_start
        assert service_calls[-1][2] == end
        assert all(call[3] == job.id for call in service_calls)
    for service_name in {"ThemeFactorService", "OpportunityService"}:
        service_calls = [call for call in calls if call[0] == service_name]
        assert service_calls == [(service_name, requested_start, end, job.id)]
    assert ("raw", warmup_start, end, None) in calls
    assert ("quality", requested_start, end, job.id) in calls
    assert ("signal", requested_start, end, None) in calls


def test_recalculation_chunks_theme_and_opportunity_by_month(monkeypatch) -> None:
    calls = []

    class ScalarService(_SuccessfulScalarService):
        label = ""

        def recalc(self, start, end, calc_run_id=None):
            calls.append((self.label, start, end))
            return 1

    class ThemeService(ScalarService):
        label = "theme"

    class OpportunityService(ScalarService):
        label = "opportunity"

    _patch_successful_calculators(monkeypatch)
    monkeypatch.setattr(recalculation_module, "ThemeFactorService", ThemeService)
    monkeypatch.setattr(recalculation_module, "OpportunityService", OpportunityService)
    monkeypatch.setattr(
        recalculation_module,
        "validate_cross_table_range",
        lambda *args, **kwargs: SimpleNamespace(has_error=False, as_metadata=lambda: {}),
    )

    recalculation_module.run_recalculation(
        _FakeDb(),
        _job(),
        date(2026, 8, 31),
        date(2026, 9, 1),
        evaluate_signals=False,
    )

    assert [call[1:] for call in calls if call[0] == "theme"] == [
        (date(2026, 8, 31), date(2026, 8, 31)),
        (date(2026, 9, 1), date(2026, 9, 1)),
    ]
    assert [call[1:] for call in calls if call[0] == "opportunity"] == [
        (date(2026, 8, 31), date(2026, 8, 31)),
        (date(2026, 9, 1), date(2026, 9, 1)),
    ]
