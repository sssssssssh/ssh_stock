"""Explicit read-only operator preflight; never infer process death from age."""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select, text, update

from app.models.data_publication import DataPublication
from app.models.job import JobRun
from app.services.data_job_diagnostics import diagnose_data_job
from app.services.job_guard import INGESTION_JOB_TYPES, _acquire_ingestion_advisory_lock


@dataclass(frozen=True)
class RecoveryApproval:
    """Supplied by a separately installed operator authority, never by this CLI.

    A signed approval alone cannot prove execution/commit termination. The
    independent authority must verify the referenced physical evidence afresh.
    """

    job_id: UUID
    worker_id: str
    token: UUID
    approval_id: str
    operator_id: str
    evidence_sha256: str


def abort_confirmed_writer(db, approval: RecoveryApproval, *, authority=None):
    """Maintenance primitive; one transaction, no replay on unknown commit ACK.

    There is deliberately no HTTP/CLI apply entry point or boolean proof switch.
    authority.verify_exit_and_commits must independently verify all hosts,
    executor identity, frozen claims and absence of pending transactions. No
    production authority is provided by this task; missing capability refuses.
    The caller owns a new Session, and an exception means no automatic replay.
    """
    if db.in_transaction() or authority is None:
        raise ValueError("EXECUTION_UNCONFIRMED")
    if (not isinstance(approval, RecoveryApproval)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", approval.approval_id)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", approval.operator_id)
            or not re.fullmatch(r"[0-9a-f]{64}", approval.evidence_sha256)):
        raise ValueError("RECOVERY_APPROVAL_INVALID")
    try:
        db.execute(text("SET LOCAL lock_timeout='1s'"))
        db.execute(text("SET LOCAL statement_timeout='3s'"))
        _acquire_ingestion_advisory_lock(db)
        root = db.scalar(select(JobRun).where(JobRun.id == approval.job_id)
                         .with_for_update(key_share=True))
        if (root is None or root.parent_job_id is not None
                or root.job_type not in INGESTION_JOB_TYPES
                or (root.worker_id, root.execution_token) != (
                    approval.worker_id, approval.token)):
            raise ValueError("RECOVERY_IDENTITY_CHANGED")
        ledger = db.get(DataPublication, root.id)
        if root.status == "FAILED" and ledger is not None and ledger.state == "ABORTED":
            prior = dict(root.job_metadata or {}).get("manual_reconciliations", [])
            if any(item.get("approval_id") == approval.approval_id
                   and item.get("evidence_sha256") == approval.evidence_sha256 for item in prior):
                db.rollback()
                return "ALREADY_RECONCILED"
        if (root.status != "RUNNING" or ledger is None or ledger.state != "PREPARING"
                or ledger.execution_token != approval.token
                or ledger.publish_started_at is not None):
            raise ValueError("RECOVERY_PUBLICATION_UNCONFIRMED")
        children = list(db.scalars(select(JobRun).where(JobRun.parent_job_id == root.id)
                                  .order_by(JobRun.id).with_for_update(key_share=True)))
        if any(child.status == "RUNNING" and
               (child.worker_id, child.execution_token) != (approval.worker_id, approval.token)
               for child in children):
            raise ValueError("RECOVERY_CHILD_IDENTITY_CHANGED")
        if authority.verify_exit_and_commits(approval) is not True:
            raise ValueError("EXECUTION_UNCONFIRMED")
        # These checks are necessary, not proof of remote executor death. The
        # trusted authority is additionally responsible for legacy/unlabelled SQL.
        if (db.scalar(text("SELECT count(*) FROM pg_prepared_xacts "
                           "WHERE database=current_database()"))
                or db.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE "
                                  "datname=current_database() AND pid<>pg_backend_pid() "
                                  "AND application_name=:app"), {"app": f"space-data/{root.id}"})):
            raise ValueError("RECOVERY_DATABASE_UNCONFIRMED")
        from app.services.data_publication import finish_publication

        original = db.info.get("publication_workspace")
        db.info["publication_workspace"] = SimpleNamespace(
            ready=True, job_id=root.id, token=approval.token)
        try:
            publication = finish_publication(db, root, "FAILED")
        finally:
            if original is None:
                db.info.pop("publication_workspace", None)
            else:
                db.info["publication_workspace"] = original
        now = datetime.now(UTC)
        for row in [*children, root]:
            if row.status != "RUNNING":
                continue
            audit = dict(approval_id=approval.approval_id, operator_id=approval.operator_id,
                         evidence_sha256=approval.evidence_sha256, at=now.isoformat(),
                         previous_status="RUNNING", new_status="FAILED",
                         execution_identity_fingerprint=hashlib.sha256(
                             str(approval.token).encode()).hexdigest()[:16])
            metadata = dict(row.job_metadata or {})
            audit_log = list(metadata.get("manual_reconciliations", [])) + [audit]
            changed = db.execute(update(JobRun).where(
                JobRun.id == row.id, JobRun.status == "RUNNING",
                JobRun.worker_id == approval.worker_id, JobRun.execution_token == approval.token,
            ).values(status="FAILED", finished_at=now, job_metadata=JobRun.job_metadata.op("||")({
                "manual_reconciliations": audit_log,
                **({"publication": publication} if row.id == root.id else {}),
            })).execution_options(synchronize_session=False))
            if changed.rowcount != 1:
                raise ValueError("RECOVERY_IDENTITY_CHANGED")
        db.commit()  # Unknown ACK propagates. Never retry this call automatically.
        return "RECONCILED_ABORTED"
    except BaseException:
        db.rollback()
        raise


def reconcile_data_job(db, job_id):
    report = diagnose_data_job(db, job_id)
    # Legacy diagnostic keeps its API shape. This stricter operator report does
    # not emit host names, raw owner tokens, original exceptions or arbitrary metadata.
    for row in [report["job"], report["root"], *report["children"]]:
        owner = row.pop("worker_id", None)
        row["owner_fingerprint"] = hashlib.sha256(owner.encode()).hexdigest() if owner else None
    others = list(db.scalars(select(JobRun.id).where(
        JobRun.job_type.in_(INGESTION_JOB_TYPES), JobRun.status == "RUNNING",
        JobRun.parent_job_id.is_(None), JobRun.id != report["root"]["id"],
    ).order_by(JobRun.id).limit(101)))
    prepared = db.scalar(text(
        "SELECT count(*) FROM pg_prepared_xacts WHERE database=current_database()"))
    waits = db.execute(text("SELECT pid, wait_event_type, wait_event, "
        "pg_blocking_pids(pid) AS blocking_pids FROM pg_stat_activity "
        "WHERE datname=current_database() AND pid<>pg_backend_pid() "
        "AND application_name=:app ORDER BY pid LIMIT 101"),
        {"app": f"space-data/{report['root']['id']}"}).mappings().all()
    report.update(dry_run=True, decision="EXECUTION_UNCONFIRMED", release_allowed=False,
                  other_running_writers=[str(value) for value in others[:100]],
                  other_running_writers_truncated=len(others) > 100,
                  prepared_transactions=prepared,
                  database_waits=[dict(row) for row in waits[:100]],
                  database_waits_truncated=len(waits) > 100,
                  database_commit_certainty="UNKNOWN",
                  process_evidence="NOT_COLLECTED_NO_EXECUTOR_AUTHORITY",
                  next_action="INDEPENDENT_EXIT_AND_COMMIT_REVIEW_REQUIRED")
    return report
