from datetime import date
from types import SimpleNamespace

import app.jobs.backfill_job as backfill_job_module
from app.jobs.backfill_job import _raw_data_complete


def _completeness(is_complete: bool):
    return SimpleNamespace(is_complete=is_complete)


def test_raw_data_complete_uses_raw_completeness(monkeypatch) -> None:
    calls = []

    def fake_check(db, trade_date, **kwargs):
        calls.append((db, trade_date, kwargs))
        return _completeness(True)

    monkeypatch.setattr(backfill_job_module, "check_raw_completeness", fake_check)

    assert _raw_data_complete(object(), date(2026, 6, 24)) is True
    assert calls[0][1] == date(2026, 6, 24)
    assert calls[0][2]["persist"] is True


def test_raw_data_incomplete_when_any_raw_dataset_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        backfill_job_module,
        "check_raw_completeness",
        lambda *args, **kwargs: _completeness(False),
    )

    assert _raw_data_complete(object(), date(2026, 6, 24)) is False
