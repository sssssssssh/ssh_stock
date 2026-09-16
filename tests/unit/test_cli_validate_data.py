from types import SimpleNamespace

import app.cli as cli_module
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


def test_cli_validate_data_only_enqueues_job(monkeypatch) -> None:
    runner = CliRunner()
    session_local = _FakeSessionLocal()
    monkeypatch.setattr(cli_module, "SessionLocal", session_local)
    job = SimpleNamespace(id="job-1", job_metadata={})
    calls = []
    monkeypatch.setattr(
        cli_module,
        "_queue_cli_job",
        lambda *args, **kwargs: calls.append((args, kwargs)) or job,
    )

    result = runner.invoke(
        cli_module.cli,
        ["validate-data", "--start", "2026-01-01", "--end", "2026-01-02"],
    )

    assert result.exit_code == 0
    assert "queued job_id=job-1" in result.output
    assert len(calls) == 1
    assert session_local.sessions[0].commits == 0
