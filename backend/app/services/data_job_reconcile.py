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
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    revoked_at: datetime | None = None


def _validate_approval_time(approval):
    # The original internal v1 authority contract is retained for compatibility;
    # it remains uninstalled. Any supplied v2 time bounds must be complete, fresh
    # and nonrevoked. Neither version installs an authority or proves exit.
    if any(x is not None for x in (approval.valid_from, approval.valid_until, approval.revoked_at)):
        start, end = approval.valid_from, approval.valid_until
        if (not isinstance(start, datetime) or not isinstance(end, datetime)
                or start.tzinfo is None or end.tzinfo is None
                or not start <= datetime.now(UTC) < end
                or not 0 < (end-start).total_seconds() <= 300
                or approval.revoked_at is not None):
            raise ValueError("RECOVERY_APPROVAL_EXPIRED_OR_REVOKED")


def _matching_recovery_receipt(root, ledger, approval):
    if (root is None or ledger is None or root.status != "FAILED"
            or root.parent_job_id is not None or root.job_type not in INGESTION_JOB_TYPES
            or (root.worker_id, root.execution_token) != (approval.worker_id, approval.token)
            or ledger.state != "ABORTED" or ledger.execution_token != approval.token
            or ledger.publish_started_at is not None or ledger.published_at is not None):
        return False
    metadata = root.job_metadata
    audit = metadata.get("manual_reconciliations", []) if isinstance(metadata, dict) else []
    if not isinstance(audit, list):
        return False
    fingerprint = hashlib.sha256(str(approval.token).encode()).hexdigest()[:16]
    return any(isinstance(item, dict)
        and item.get("approval_id") == approval.approval_id
        and item.get("operator_id") == approval.operator_id
        and item.get("evidence_sha256") == approval.evidence_sha256
        and item.get("execution_identity_fingerprint") == fingerprint
        and item.get("previous_status") == "RUNNING"
        and item.get("new_status") == "FAILED" for item in audit)


def _active_recovery_child(db, root_id):
    return db.scalar(select(JobRun.id).where(JobRun.parent_job_id == root_id,
        JobRun.status.in_(("RUNNING", "QUEUED"))).limit(1)) is not None


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
    _validate_approval_time(approval)
    try:
        db.execute(text("SET LOCAL lock_timeout='1s'"))
        db.execute(text("SET LOCAL statement_timeout='3s'"))
        _acquire_ingestion_advisory_lock(db)
        root = db.scalar(select(JobRun).where(JobRun.id == approval.job_id)
                         .with_for_update())
        if (root is None or root.parent_job_id is not None
                or root.job_type not in INGESTION_JOB_TYPES
                or (root.worker_id, root.execution_token) != (
                    approval.worker_id, approval.token)):
            raise ValueError("RECOVERY_IDENTITY_CHANGED")
        # FOR UPDATE on the parent also conflicts with FK KEY SHARE from a
        # newly arriving child; NO KEY UPDATE did not close that insertion race.
        ledger = db.scalar(select(DataPublication).where(DataPublication.job_id == root.id)
                           .with_for_update())
        if root.status == "FAILED" and ledger is not None and ledger.state == "ABORTED":
            if not _matching_recovery_receipt(root, ledger, approval):
                raise ValueError("RECOVERY_PUBLICATION_UNCONFIRMED")
            if _active_recovery_child(db, root.id):
                raise ValueError("RECOVERY_CHILD_IDENTITY_CHANGED")
            db.rollback()
            return "ALREADY_RECONCILED"
        if (root.status != "RUNNING" or ledger is None or ledger.state != "PREPARING"
                or ledger.execution_token != approval.token
                or ledger.publish_started_at is not None):
            raise ValueError("RECOVERY_PUBLICATION_UNCONFIRMED")
        children = list(db.scalars(select(JobRun).where(JobRun.parent_job_id == root.id)
                                  .order_by(JobRun.id).with_for_update(key_share=True)))
        if any(child.status == "QUEUED" or (child.status == "RUNNING" and
               (child.worker_id, child.execution_token) != (approval.worker_id, approval.token))
               for child in children):
            raise ValueError("RECOVERY_CHILD_IDENTITY_CHANGED")
        if authority.verify_exit_and_commits(approval) is not True:
            raise ValueError("EXECUTION_UNCONFIRMED")
        _validate_approval_time(approval)
        # These checks are necessary, not proof of remote executor death. The
        # trusted authority is additionally responsible for legacy/unlabelled SQL.
        if (db.scalar(text("SELECT count(*) FROM pg_prepared_xacts "
                           "WHERE database=current_database()"))
                or db.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE "
                                  "datname=current_database() AND pid<>pg_backend_pid() "
                                  "AND (application_name=:app OR application_name ~ :pattern)"),
                             {"app": f"space-data/{root.id}",
                              "pattern": f"^space2/[mhd]/{root.id.hex}/[0-9a-f]{{16}}$"})):
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
        _validate_approval_time(approval)
        # A frozen dataclass cannot reflect revocation by an independent authority.
        # Recheck its live evidence immediately before committing any changes.
        if authority.verify_exit_and_commits(approval) is not True:
            raise ValueError("EXECUTION_UNCONFIRMED")
        _validate_approval_time(approval)
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
    waits = report["matching_database_backends"]
    report.update(dry_run=True, decision="EXECUTION_UNCONFIRMED", release_allowed=False,
                  other_running_writers=[str(value) for value in others[:100]],
                  other_running_writers_truncated=len(others) > 100,
                  prepared_transactions=prepared,
                  database_waits=[{key: row[key] for key in (
                      "pid", "wait_event_type", "wait_event", "blocking_pids",
                      "identity_evidence")} for row in waits],
                  database_waits_truncated=report["matching_database_backends_truncated"],
                  database_commit_certainty="UNKNOWN",
                  process_evidence="NOT_COLLECTED_NO_EXECUTOR_AUTHORITY",
                  next_action="INDEPENDENT_EXIT_AND_COMMIT_REVIEW_REQUIRED")
    return report


def recovery_commit_status(db, approval: RecoveryApproval):
    """Fresh-connection read-only reconciliation of a lost maintenance COMMIT ACK.

    Never calls the authority, finish_publication, audit append or COMMIT. A
    matching immutable receipt confirms only this abort, not permission to retry.
    A caller must close its old unknown connection and supply a new Session.
    """
    if db.in_transaction() or not isinstance(approval, RecoveryApproval):
        raise ValueError("RECOVERY_READ_REQUIRES_FRESH_SESSION")
    db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
    db.execute(text("SET LOCAL lock_timeout='1s'"))
    db.execute(text("SET LOCAL statement_timeout='3s'"))
    root = db.get(JobRun, approval.job_id)
    ledger = db.get(DataPublication, approval.job_id)
    if not _matching_recovery_receipt(root, ledger, approval):
        return "RECOVERY_COMMIT_UNCONFIRMED"
    if _active_recovery_child(db, root.id):
        return "RECOVERY_COMMIT_UNCONFIRMED"
    return "RECONCILED_ABORTED"
