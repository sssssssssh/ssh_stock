import os
import subprocess
import sys

import pytest

from scripts.ab_read_experiment_summary_v14_a4_2 import summarize
from scripts.ab_read_experiment_v14_a4_2 import CONTROLS, alternate, source_contract


def test_frozen_backend_migrations_and_a41_evidence_are_unchanged():
    assert source_contract()


def test_alternation_keeps_all_controls_and_not_just_fastest():
    orders = alternate(CONTROLS, 3)
    assert len({tuple(o) for o in orders}) == 3
    assert all(set(o) == set(CONTROLS) for o in orders)


@pytest.mark.parametrize("marker", [None, "not-a-uuid"])
def test_bad_isolation_rejected_before_business_settings(tmp_path, marker):
    env = dict(os.environ, DATABASE_URL="business-must-not-be-imported")
    env.pop("TEST_DATABASE_URL", None)
    env.pop("V14_TEST_INSTANCE", None)
    if marker:
        env["V14_TEST_INSTANCE"] = marker
    result = subprocess.run([sys.executable, "scripts/ab_read_experiment_v14_a4_2.py",
        "--contract-only", "--output", str(tmp_path / "refused.json")],
        env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert '"failure_type": "RuntimeError"' in (tmp_path / "refused.json").read_text()


def test_empty_receipt_cannot_claim_performance_or_authorize_a43():
    result = summarize({})
    assert result["golden"] == "UNPROVEN"
    assert not result["authorize_a4_3"]
    assert result["read_performance_pass"] == "NOT_CLAIMED"
