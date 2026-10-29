"""Real marked PG17 duplicate-recovery evidence; never the incident database."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.models.data_publication import DataPublication
from app.models.job import JobRun
from app.services.data_job_reconcile import (
    RecoveryApproval,
    abort_confirmed_writer,
    recovery_commit_status,
)
from sqlalchemy import func, select

from scripts.v14_test_database import isolated_v14_database


@pytest.fixture
def committed_receipt(monkeypatch):
    with isolated_v14_database(monkeypatch) as (factory, _):
        identity, token = uuid4(), uuid4()
        approval = RecoveryApproval(identity, "synthetic-r4", token,
                                    "r4-approval", "r4-operator", "b" * 64)
        with factory() as db:
            db.add(JobRun(id=identity, job_type="recalculate", status="RUNNING",
                worker_id=approval.worker_id, execution_token=token,
                error_message="ORIGINAL_ERROR", job_metadata={"first_error": "preserved"}))
            db.flush()
            db.add(DataPublication(job_id=identity, execution_token=token,
                                   state="PREPARING", identity={}, row_counts={}))
            db.commit()
        with factory() as db:
            assert abort_confirmed_writer(db, approval, authority=SimpleNamespace(
                verify_exit_and_commits=lambda _: True)) == "RECONCILED_ABORTED"
        yield factory, approval


def snapshot(factory, approval):
    with factory() as db:
        root, ledger = db.get(JobRun, approval.job_id), db.get(DataPublication, approval.job_id)
        return (root.status, root.error_message, deepcopy(root.job_metadata), root.finished_at,
                ledger.state, ledger.execution_token, ledger.publish_started_at,
                ledger.published_at,
                db.scalar(select(func.count()).select_from(JobRun)))


@pytest.mark.parametrize("scenario", ["ledger_token", "active_child", "audit_fingerprint",
                                     "audit_transition", "published_timestamp"])
def test_real_duplicate_and_unknown_ack_refuse_inconsistent_receipt(committed_receipt, scenario):
    factory, approval = committed_receipt
    with factory() as db:
        root = db.get(JobRun, approval.job_id)
        if scenario in {"ledger_token", "published_timestamp"}:
            # Terminal evidence is immutable. Seed a separate inconsistent
            # imported snapshot instead of disabling its protection trigger.
            approval = replace(approval, job_id=uuid4())
            contradictory = JobRun(id=approval.job_id, job_type="recalculate", status="FAILED",
                worker_id=approval.worker_id, execution_token=approval.token,
                error_message=root.error_message, finished_at=root.finished_at,
                job_metadata=deepcopy(root.job_metadata))
            db.add(contradictory)
            db.flush()
            db.add(DataPublication(job_id=approval.job_id, state="ABORTED", identity={},
                row_counts={}, execution_token=uuid4() if scenario == "ledger_token"
                else approval.token, published_at=root.finished_at
                if scenario == "published_timestamp" else None))
        elif scenario == "active_child":
            db.add(JobRun(job_type="recalculate", status="RUNNING", parent_job_id=root.id,
                          worker_id="another-owner", execution_token=uuid4(), job_metadata={}))
        elif scenario in {"audit_fingerprint", "audit_transition"}:
            metadata = deepcopy(root.job_metadata)
            audit = metadata["manual_reconciliations"][0]
            if scenario == "audit_fingerprint":
                audit.pop("execution_identity_fingerprint")
            else:
                audit["new_status"] = "SUCCESS"
            root.job_metadata = metadata
        db.commit()
    before = snapshot(factory, approval)
    with factory() as db, pytest.raises(ValueError, match="RECOVERY_"):
        abort_confirmed_writer(db, approval, authority=SimpleNamespace(
            verify_exit_and_commits=lambda _: pytest.fail("No duplicate authority consumption")))
    with factory() as reader:
        assert recovery_commit_status(reader, approval) == "RECOVERY_COMMIT_UNCONFIRMED"
    assert snapshot(factory, approval) == before


def test_real_valid_duplicate_keeps_one_audit_and_only_reads_ack(committed_receipt):
    factory, approval = committed_receipt
    before = snapshot(factory, approval)
    for _ in range(2):
        with factory() as db:
            assert abort_confirmed_writer(db, approval, authority=object()) == "ALREADY_RECONCILED"
        with factory() as reader:
            assert recovery_commit_status(reader, approval) == "RECONCILED_ABORTED"
    assert snapshot(factory, approval) == before
    assert len(before[2]["manual_reconciliations"]) == 1
