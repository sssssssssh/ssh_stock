import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "target",
    [
        None,
        "postgresql+psycopg://synthetic@production.invalid/business",
        "postgresql+psycopg://synthetic@127.0.0.1/stock_db",
    ],
)
def test_benchmark_rejects_business_target_before_importing_settings(target):
    env = {**os.environ, "DATABASE_URL": "must-not-be-loaded"}
    env.pop("TEST_DATABASE_URL", None)
    if target:
        env["TEST_DATABASE_URL"] = target
    result = subprocess.run(
        [
            sys.executable,
            "scripts/publication_candidate_benchmark_v13.py",
            "--confirm-synthetic",
            "--rows",
            "1000",
            "--output",
            "unused.json",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "EXPLICIT_LOOPBACK_SYNTHETIC_TEST_DATABASE_REQUIRED" in result.stderr
    assert "Traceback" not in result.stderr


def test_memory_measurement_is_real_and_positive():
    from scripts.publication_candidate_benchmark_v13 import rss_bytes

    assert rss_bytes() > 0
