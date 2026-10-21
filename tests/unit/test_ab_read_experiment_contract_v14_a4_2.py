"""Unique basename preserves the repository's existing pytest import mode."""

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


def trial(seconds):
    return dict(scope="full",variant="S3",rows=10,hash="synthetic",dtypes={"a":"object"},
        columns=["a"],window_days=None,cursor_fraction="0.1",read_plus_final_seconds=seconds,
        protection="E0",cursors=[dict(name="synthetic",closed=True,until_eof_seconds=1,
                                      fetches=[dict(rows=10),dict(rows=0)])])


def test_slow_outlier_is_kept_and_no_automatic_production_permission():
    result = summarize({"runs":[trial(1),trial(2),trial(999)]})
    assert result["tables"][0]["p50"] == 2
    assert result["tables"][0]["p95"] > 899
    assert result["tables"][0]["samples"] == [1,2,999]
    assert not result["authorize_a4_3"]


@pytest.mark.parametrize("damage", ["rows","hash","dtypes","columns","closed","eof"])
def test_summary_refuses_incomplete_cursor_or_different_output(damage):
    rows = [trial(1),trial(2),trial(3)]
    if damage in {"rows","hash","dtypes","columns"}:
        rows[-1][damage] = "corrupted"
    elif damage=="closed":
        rows[-1]["cursors"][0]["closed"] = False
    else:
        rows[-1]["cursors"][0].pop("until_eof_seconds")
    with pytest.raises(ValueError):
        summarize({"runs":rows})


def test_resource_measurements_are_positive_not_synthetic_placeholders():
    from scripts.ab_read_resources_v14_a4_2 import (
        cpu_sample,
        current_rss_bytes,
        host_memory_bytes,
    )

    assert host_memory_bytes() > 0
    assert current_rss_bytes() > 0
    sample = cpu_sample(os.getpid())
    assert sample["backend_cpu_seconds"] >= 0
    assert sample["host_total_seconds"] >= sample["host_idle_seconds"]


def test_window_matrix_must_match_full_read_not_just_other_windows():
    full, window = trial(1), trial(2)
    window.update(scope="window_matrix", window_days=5, hash="lost-closed-day")
    with pytest.raises(ValueError, match="A42_GOLDEN_MISMATCH"):
        summarize({"runs":[full,window]})


def test_partial_receipt_is_not_complete_even_if_observed_groups_have_three_runs():
    result = summarize({"runs":[trial(1),trial(2),trial(3)],
                        "experiment_complete":True,"failure_type":"QueryCanceled"})
    assert result["measured_groups_complete"]
    assert not result["experiment_complete"]
    assert not result["authorize_a4_3"]
