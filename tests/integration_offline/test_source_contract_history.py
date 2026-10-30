"""All original historical source safety tests execute, not a performance run."""

import subprocess
from pathlib import Path

import pytest

from scripts.source_contract_governance import HISTORICAL_SHA, development_receipt
from scripts.source_contract_history import run


def test_all_original_historical_source_contract_positives_and_negatives(record_property):
    result = run(Path(__file__).resolve().parents[2])
    assert result == dict(passed=73, failed=0, errors=0, skipped=0, exit_code=0,
                          source_sha=HISTORICAL_SHA, performance_eligible=False,
                          g1_authorized=False)
    record_property("historical_source_sha", HISTORICAL_SHA)
    record_property("historical_original_cases_executed", 73)


@pytest.fixture
def development_copy(tmp_path):
    root = Path(__file__).resolve().parents[2]
    checkout = tmp_path / "current"
    subprocess.run(["git", "-c", "core.autocrlf=false", "clone", "--shared", "--", str(root),
                    str(checkout)], check=True, capture_output=True)
    future = checkout / "backend/app/source_contract_future_fixture.py"
    future.write_text("SYNTHETIC_FUTURE_CHANGE = True\n", encoding="ascii")
    subprocess.run(["git", "-C", str(checkout), "add", "--", str(future)],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(checkout), "-c", "user.name=Contract Test",
                    "-c", "user.email=contract@example.invalid", "commit", "-m",
                    "synthetic future development source"], check=True, capture_output=True)
    return checkout, future


def test_new_development_source_is_valid_without_inheriting_historical_authority(development_copy):
    root, _ = development_copy
    receipt = development_receipt(root)
    assert receipt["head_sha"] != HISTORICAL_SHA
    assert receipt["purpose"] == "DEVELOPMENT_STATIC_ONLY"
    assert all(receipt[key] is False for key in (
        "performance_eligible", "capacity_ready", "g1_authorized",
        "production_read_authorized", "recovery_authorized"))


def test_new_development_source_still_rejects_hidden_uncommitted_bytes(development_copy):
    from scripts.a4235_calibration_adapter_contract import Fault

    root, future = development_copy
    subprocess.run(["git", "-C", str(root), "update-index", "--assume-unchanged", "--",
                    str(future)], check=True, capture_output=True)
    future.write_text("SYNTHETIC_FUTURE_CHANGE = False\n", encoding="ascii")
    with pytest.raises(Fault, match="HEAD_BYTES_MISMATCH"):
        development_receipt(root)


def test_new_development_source_rejects_wrong_target_sha(development_copy):
    from scripts.a4235_calibration_adapter_contract import Fault

    with pytest.raises(Fault, match="HEAD_MISMATCH"):
        development_receipt(development_copy[0], expected_sha=HISTORICAL_SHA)
