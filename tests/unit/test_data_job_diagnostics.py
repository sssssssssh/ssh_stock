import pytest
from app.cli import cli
from typer.testing import CliRunner


@pytest.mark.parametrize(
    "args",
    [
        ["--job-id", "invalid-id"],
        ["--job-id", "00000000-0000-0000-0000-000000000001", "--apply"],
        ["--job-id", "00000000-0000-0000-0000-000000000001", "--force"],
    ],
)
def test_diagnostics_rejects_invalid_or_write_arguments_without_connecting(monkeypatch, args):
    def forbidden():
        pytest.fail("diagnostic must reject invalid/write input before opening a database")

    monkeypatch.setattr("app.cli.SessionLocal", forbidden)
    result = CliRunner().invoke(cli, ["data-job-diagnose", *args])
    assert result.exit_code == 2
