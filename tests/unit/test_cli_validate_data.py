from types import SimpleNamespace

import app.cli as cli_module
from app.services.quality.history_quality import HistoricalQualitySummary
from typer.testing import CliRunner


class _FakeDb:
    def __init__(self, store: list[str]) -> None:
        self.store = store
        self.pending: list[str] = []
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def commit(self) -> None:
        self.commits += 1
        self.store.extend(self.pending)
        self.pending.clear()

    def rollback(self) -> None:
        self.rollbacks += 1
        self.pending.clear()

    def quality_rows(self) -> list[str]:
        return list(self.store)


class _FakeSessionLocal:
    def __init__(self) -> None:
        self.store: list[str] = []
        self.sessions: list[_FakeDb] = []

    def __call__(self) -> _FakeDb:
        session = _FakeDb(self.store)
        self.sessions.append(session)
        return session


class _SuccessfulHistoricalDataQualityService:
    def __init__(self, db, strategy) -> None:
        self.db = db

    def validate(self, start, end):
        self.db.pending.append("data_quality_daily")
        return HistoricalQualitySummary(
            total_days=1,
            completed_days=1,
            pass_days=1,
            warning_days=0,
            error_days=0,
        )


class _FailingHistoricalDataQualityService:
    def __init__(self, db, strategy) -> None:
        self.db = db

    def validate(self, start, end):
        self.db.pending.append("data_quality_daily")
        raise RuntimeError("validate failed")


def test_cli_validate_data_commits_quality_result(monkeypatch) -> None:
    runner = CliRunner()
    session_local = _FakeSessionLocal()
    monkeypatch.setattr(cli_module, "SessionLocal", session_local)
    job = SimpleNamespace(job_metadata={})
    monkeypatch.setattr(cli_module, "_queue_cli_job", lambda *args, **kwargs: job)

    def run_validate(db, current_job, metadata):
        db.pending.append("data_quality_daily")
        db.commit()
        current_job.job_metadata = {
            "total_days": 1,
            "pass_days": 1,
            "warning_days": 0,
            "error_days": 0,
        }

    monkeypatch.setattr(cli_module, "run_validate_data_job", run_validate)

    result = runner.invoke(
        cli_module.cli,
        ["validate-data", "--start", "2026-01-01", "--end", "2026-01-02"],
    )

    assert result.exit_code == 0
    assert session_local.sessions[0].commits == 1
    with session_local() as db:
        assert db.quality_rows() == ["data_quality_daily"]


def test_cli_validate_data_rolls_back_on_error(monkeypatch) -> None:
    runner = CliRunner()
    session_local = _FakeSessionLocal()
    monkeypatch.setattr(cli_module, "SessionLocal", session_local)
    job = SimpleNamespace(job_metadata={})
    monkeypatch.setattr(cli_module, "_queue_cli_job", lambda *args, **kwargs: job)

    def fail_validate(db, current_job, metadata):
        db.pending.append("data_quality_daily")
        raise RuntimeError("validate failed")

    monkeypatch.setattr(cli_module, "run_validate_data_job", fail_validate)

    result = runner.invoke(
        cli_module.cli,
        ["validate-data", "--start", "2026-01-01", "--end", "2026-01-02"],
    )

    assert result.exit_code == 1
    assert session_local.sessions[0].rollbacks == 1
    with session_local() as db:
        assert db.quality_rows() == []
