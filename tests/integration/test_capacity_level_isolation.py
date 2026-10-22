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
    progress = json.loads(path.with_suffix(".progress.json").read_text())
    assert progress["artifact_kind"] == "DIAGNOSTIC_ONLY"
    assert progress["status"] == "DIAGNOSTIC_FINISHED"
    assert progress["completed_table_count"] == 10
    assert sum(t["rows"] for t in progress["tables"].values()) == 164
    assert all(t["commit_count"] == 2 and t["status"] == "MEASURED"
               for t in progress["tables"].values())
    assert progress["phases"]["rollback_probe"]["count"] == 2
    assert progress["phases"]["update_job"]["count"] == 3
    assert progress["phases"]["signal_id_lookup"]["count"] == 2
    assert progress["phases"]["publication_plan"]["count"] == 1
    assert progress["phases"]["payload"]["count"] >= 164
    assert progress["phases"]["record_validation"]["count"] == 2
    assert progress["phases"]["database_cleanup"]["count"] == 1
    assert "first_failure" not in progress


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


@pytest.fixture
def capacity_runtime(monkeypatch):
    from scripts.v14_test_database import isolated_v14_database, verified_test_url

    verified_test_url()  # No business engine construction or DDL before physical proof.
    from app.core.config import get_settings
    from app.models import market_data as m
    from app.models.data_publication import DataPublicationRow
    from app.models.job import JobRun
    from app.repositories.job_run import update_job
    from app.services.data_publication import KEYS, MODELS, record_validation

    from scripts import data_publication_capacity_v12 as capacity
    from tests.integration.test_data_publication import candidate, sample_row

    values = dict(m=m, DataPublicationRow=DataPublicationRow, JobRun=JobRun, update_job=update_job,
                  KEYS=KEYS, MODELS=MODELS, record_validation=record_validation,
                  get_settings=get_settings, isolated_contract_database=isolated_v14_database,
                  candidate=candidate, sample_row=sample_row)
    for name, value in values.items():
        monkeypatch.setattr(capacity, name, value, raising=False)
    return capacity


def test_medium_diagnostic_retains_real_upserts_commits_readers_and_rollback_probes(
    tmp_path, capacity_runtime
):
    from scripts.a42_artifacts import atomic, header

    c = capacity_runtime
    progress = c.CapacityProgress(tmp_path/"diagnostic.progress.json", header("diagnostic-medium"))
    progress.begin_level(600, 3, "DIAGNOSTIC_ONLY")
    with c.observe_capacity(progress):
        result = c.run_level(600, 3, "DIAGNOSTIC_ONLY")
    assert result["rows"] == 3*(6*600+50+100+2)
    assert result["reader_samples"] > 0 and result["reader_errors"] == []
    assert result["final_root_status"] == "SUCCESS" and result["final_ledger_state"] == "PUBLISHED"
    assert {p["mode"] for p in result["rollback_probes"]} == {
        "row_budget", "sql_timeout_after_first_table"}
    assert all(p["a_digest_unchanged"] and p["queue_slot_held"] for p in result["rollback_probes"])
    assert progress.data["completed_table_count"] == len(c.MODELS) == 10
    assert progress.data["tables"]["stock_factor_daily"]["batch_count"] == 6
    assert progress.data["tables"]["stock_factor_daily"]["commit_count"] == 3
    assert all(t["sql"] and t["rows_per_second"] > 0 for t in progress.data["tables"].values())
    assert "first_failure" not in progress.data
    # This arbitrary-size diagnostic is NOT a formal L1/L2/L3 receipt.
    if os.environ.get("CAPACITY_DIAGNOSTIC_OUTPUT"):
        atomic(os.environ["CAPACITY_DIAGNOSTIC_OUTPUT"], dict(
            artifact_kind="DIAGNOSTIC_ONLY", result=result, progress=progress.data))


def test_real_driver_failure_after_candidate_batch_keeps_partial_progress(
    tmp_path, capacity_runtime, monkeypatch
):
    from app.services.data_publication import PublicationWorkspace

    from scripts.a42_artifacts import header

    c = capacity_runtime
    original_candidate = c.candidate
    original_upsert = PublicationWorkspace.upsert
    calls = []

    def fail_next_batch(ws, *args, **kwargs):
        if calls:
            raise RuntimeError("PRIVATE_DSN_AND_BIND")
        result = original_upsert(ws, *args, **kwargs)
        calls.append(True)
        return result

    monkeypatch.setattr(PublicationWorkspace, "upsert", fail_next_batch)
    progress = c.CapacityProgress(tmp_path/"failed.progress.json", header("diagnostic-fault"))
    progress.begin_level(10, 2, "DIAGNOSTIC_ONLY")
    try:
        with c.observe_capacity(progress):
            c.run_level(10, 2, "DIAGNOSTIC_ONLY")
    except RuntimeError as error:
        progress.fail(error)
    else:
        pytest.fail("the injected driver error must escape")
    data = json.loads(progress.path.read_text())
    assert data["status"] == "INCOMPLETE" and data["completed_table_count"] == 0
    assert data["tables"]["stock_trade_status_daily"]["rows"] == 10
    assert data["tables"]["stock_trade_status_daily"]["commit_count"] == 1
    assert data["first_failure"]["phase"] == "workspace_upsert"
    assert "PRIVATE" not in progress.path.read_text()
    assert c.candidate is original_candidate  # Lab wrappers are restored, including on failure.
