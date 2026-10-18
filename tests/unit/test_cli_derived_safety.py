import app.cli as cli_module
import pytest
from typer.testing import CliRunner

COMMANDS = [
    [name, "--start", "2026-01-01", "--end", "2026-01-02"]
    for name in ("recalc-factors", "recalc-market", "recalc-sectors", "recalc-states")
] + [["evaluate-signals", "--signal-type", "TREND", "--limit", "5",
      "--eval-version", "eval_v3", "--entry-basis", "NEXT_OPEN"]]


@pytest.mark.parametrize("command", COMMANDS)
def test_disabled_cli_never_opens_a_session(monkeypatch, command):
    def forbidden():
        pytest.fail("Rejected CLI must not even open a DB session")
    monkeypatch.setattr(cli_module, "SessionLocal", forbidden)
    result = CliRunner().invoke(cli_module.cli, command)
    assert result.exit_code == 1
    assert "UNSAFE_DIRECT_DERIVED_WRITE_DISABLED" in result.output
    assert "no request has been queued" in result.output


@pytest.mark.parametrize("command", COMMANDS)
def test_disabled_cli_help_explains_safety(command):
    result = CliRunner().invoke(cli_module.cli, [command[0], "--help"])
    assert result.exit_code == 0 and "Disabled" in result.output


def test_explicit_full_recalculation_enqueues_without_dropping_parameters(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    calls = []
    monkeypatch.setattr(cli_module, "SessionLocal", lambda: nullcontext(object()))
    monkeypatch.setattr(cli_module, "_queue_cli_job", lambda *a: (
        calls.append(a) or SimpleNamespace(id="synthetic")))
    result = CliRunner().invoke(cli_module.cli, ["recalculate", "--start", "2026-01-01",
        "--end", "2026-01-02", "--no-evaluate-signals"])
    assert result.exit_code == 0 and "FULL recalculation" in result.output
    assert calls[0][1] == "recalculate"
    assert calls[0][3] == dict(start="2026-01-01", end="2026-01-02",
                             evaluate_signals=False, mode="manual")
