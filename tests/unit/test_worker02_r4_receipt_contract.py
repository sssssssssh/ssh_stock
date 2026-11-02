"""Pure control-flow regressions; no PostgreSQL or production authority."""

import hashlib
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.models.data_publication import DataPublication
from app.models.job import JobRun
from app.services import data_job_reconcile as recovery


def receipt_case(scenario):
    token, job_id = uuid4(), uuid4()
    approval = recovery.RecoveryApproval(job_id, "synthetic-owner", token,
        "r4-approval", "r4-operator", "a" * 64)
    audit = dict(approval_id=approval.approval_id, operator_id=approval.operator_id,
        evidence_sha256=approval.evidence_sha256, previous_status="RUNNING", new_status="FAILED",
        execution_identity_fingerprint=hashlib.sha256(str(token).encode()).hexdigest()[:16])
    root = SimpleNamespace(id=job_id, parent_job_id=None, job_type="recalculate",
        status="FAILED", worker_id=approval.worker_id, execution_token=token,
        job_metadata={"first_error": "preserved", "manual_reconciliations": [audit]})
    ledger = SimpleNamespace(state="ABORTED", execution_token=token,
                             publish_started_at=None, published_at=None)
    if scenario == "ledger_token":
        ledger.execution_token = uuid4()
    elif scenario == "audit_fingerprint":
        audit.pop("execution_identity_fingerprint")
    elif scenario == "audit_transition":
        audit["new_status"] = "SUCCESS"
    elif scenario == "published_timestamp":
        ledger.published_at = "synthetic-contradiction"
    elif scenario == "publishing_timestamp":
        ledger.publish_started_at = "synthetic-unknown-commit"
    return approval, root, ledger


class ReceiptSession:
    def __init__(self, root, ledger, active_child=False):
        self.root, self.ledger, self.active_child = root, ledger, active_child
        self.reads = 0
        self.rollbacks = 0
        self.statements = []
        self.get_mode = False

    def in_transaction(self):
        return False

    def execute(self, statement):
        self.statements.append(str(statement))

    def scalar(self, statement):
        self.reads += 1
        if self.get_mode:
            return self.root.id if self.active_child else None
        if self.reads == 1:
            return self.root
        if self.reads == 2:
            return self.ledger
        return self.root.id if self.active_child else None

    def get(self, model, identity):
        self.get_mode = True
        assert identity == self.root.id
        return self.root if model is JobRun else self.ledger if model is DataPublication else None

    def rollback(self):
        self.rollbacks += 1

    def commit(self):
        raise AssertionError("Receipt verification must not commit or replay recovery")


@pytest.mark.parametrize("scenario", ["ledger_token", "active_child", "audit_fingerprint",
    "audit_transition", "published_timestamp", "publishing_timestamp"])
def test_duplicate_recovery_refuses_inconsistent_receipt_without_writes(monkeypatch, scenario):
    approval, root, ledger = receipt_case(scenario)
    db = ReceiptSession(root, ledger, active_child=scenario == "active_child")
    before = deepcopy(root.job_metadata)
    monkeypatch.setattr(recovery, "_acquire_ingestion_advisory_lock", lambda _: None)
    authority = SimpleNamespace(verify_exit_and_commits=lambda _: pytest.fail(
        "A duplicate receipt must not consume/replay an authority approval"))
    code = "RECOVERY_(PUBLICATION_UNCONFIRMED|CHILD_IDENTITY_CHANGED)"
    with pytest.raises(ValueError, match=code):
        recovery.abort_confirmed_writer(db, approval, authority=authority)
    assert root.job_metadata == before and root.status == "FAILED"
    assert db.rollbacks == 1


def test_valid_duplicate_is_readonly_and_does_not_append_audit(monkeypatch):
    approval, root, ledger = receipt_case("valid")
    db = ReceiptSession(root, ledger)
    monkeypatch.setattr(recovery, "_acquire_ingestion_advisory_lock", lambda _: None)
    assert recovery.abort_confirmed_writer(db, approval, authority=object()) == "ALREADY_RECONCILED"
    assert db.rollbacks == 1 and len(root.job_metadata["manual_reconciliations"]) == 1


@pytest.mark.parametrize("scenario", ["ledger_token", "audit_fingerprint", "audit_transition",
                                     "published_timestamp", "publishing_timestamp"])
def test_unknown_ack_reader_uses_the_same_receipt_boundary(scenario):
    approval, root, ledger = receipt_case(scenario)
    db = ReceiptSession(root, ledger)
    assert recovery.recovery_commit_status(db, approval) == "RECOVERY_COMMIT_UNCONFIRMED"
    assert all(statement.startswith("SET ") for statement in db.statements)
