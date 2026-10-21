"""Capacity single-level uses the unmodified workload on a new physical PG17 child."""

import json
import os
import subprocess
import sys

import pytest

from scripts.a42_receipt_contract import physical, validate_capacity


def test_l1_single_level_real_publication_and_two_rollback_probes(tmp_path):
    path = tmp_path/"l1.json"
    result = subprocess.run([sys.executable, "scripts/data_publication_capacity_v12.py",
        "--confirm-synthetic", "--level", "L1", "--output", str(path)],
        capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr[-3000:]
    receipt = json.loads(path.read_text())
    physical(receipt)
    assert receipt["status"] == "COMPLETE" and len(receipt["results"]) == 1
    validate_capacity(receipt["results"][0], "L1")


@pytest.mark.parametrize("field,value", [
    ("V14_TEST_INSTANCE", "ed921260-8adc-4d83-966a-6d904b788676"),
    ("V14_TEST_SYSTEM_IDENTIFIER", "0")])
def test_misidentified_physical_target_refused_before_create(tmp_path, field, value):
    from sqlalchemy import create_engine, text

    from scripts.v14_test_database import verified_test_url

    engine = create_engine(verified_test_url(), hide_parameters=True)
    with engine.connect() as db:
        before = set(db.scalars(text("SELECT datname FROM pg_database")))
    path = tmp_path/"refused.json"
    result = subprocess.run([sys.executable, "scripts/data_publication_capacity_v12.py",
        "--confirm-synthetic", "--level", "L1", "--output", str(path)],
        env={**os.environ, field:value}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert json.loads(path.read_text())["status"] == "INCOMPLETE"
    with engine.connect() as db:
        assert set(db.scalars(text("SELECT datname FROM pg_database"))) == before
    engine.dispose()
