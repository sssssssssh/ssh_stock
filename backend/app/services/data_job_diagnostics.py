"""Read-only incident evidence. This module deliberately has no unlock operation."""

import hashlib
import re
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select, text

from app.models.data_publication import DataPublication, DataPublicationRow
from app.models.job import JobRun
from app.models.market_data import DataDirtyRange
from app.services.job_guard import INGESTION_JOB_TYPES


def diagnose_data_job(db, job_id: UUID):
    db.execute(text("SET TRANSACTION READ ONLY"))
    db.execute(text("SET LOCAL statement_timeout = '3s'"))
    db.execute(text("SET LOCAL lock_timeout = '1s'"))
    job = db.get(JobRun, job_id)
    if job is None or job.job_type not in INGESTION_JOB_TYPES:
        raise ValueError("DATA_JOB_NOT_FOUND")
    root_id = job.parent_job_id or job.id
    root = db.get(JobRun, root_id)
    children = list(
        db.scalars(
            select(JobRun)
            .where(JobRun.parent_job_id == root_id)
            .order_by(JobRun.started_at, JobRun.id)
        )
    )

    def payload(row):
        message = row.error_message or ""
        state = re.search(r"SQLSTATE ([0-9A-Z]{5})", message)
        code = dict(row.job_metadata or {}).get("execution_error_code", "")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", str(code)):
            code = "JOB_ERROR_RECORDED" if message else None
        return dict(
            id=str(row.id),
            job_type=row.job_type,
            status=row.status,
            worker_id=row.worker_id,
            parent_job_id=str(row.parent_job_id) if row.parent_job_id else None,
            execution_identity_fingerprint=(
                hashlib.sha256(str(row.execution_token).encode()).hexdigest()[:16]
                if row.execution_token
                else None
            ),
            heartbeat_at=row.heartbeat_at,
            last_progress_at=row.last_progress_at,
            cancel_requested=row.cancel_requested,
            cancel_requested_at=row.cancel_requested_at,
            execution_unconfirmed=(
                row.status == "RUNNING"
                and (
                    bool(dict(row.job_metadata or {}).get("execution_unconfirmed"))
                    or row.execution_token is None
                )
            ),
            error_code=code,
            sqlstate=state.group(1) if state else None,
        )

    dirty_ids = {
        value
        for row in [root, *children]
        for value in (dict(row.job_metadata or {}).get("dirty_range_ids") or [])
        if type(value) is int and value > 0
    }
    dirty = (
        db.execute(
            select(
                DataDirtyRange.id,
                DataDirtyRange.status,
                DataDirtyRange.dirty_start_date,
                DataDirtyRange.dirty_end_date,
                DataDirtyRange.retry_count,
            )
            .where(
                or_(
                    DataDirtyRange.source_job_id.in_([root_id, *(row.id for row in children)]),
                    DataDirtyRange.id.in_(sorted(dirty_ids)[:100]),
                )
            )
            .order_by(DataDirtyRange.id)
            .limit(101)
        )
        .mappings()
        .all()
    )
    ledger = db.get(DataPublication, root_id)
    candidates = (
        db.execute(
            select(DataPublicationRow.table_name, func.count().label("rows"))
            .where(DataPublicationRow.publication_id == root_id)
            .group_by(DataPublicationRow.table_name)
        )
        .mappings()
        .all()
    )
    # No query text, query parameters, addresses, DSN or authentication tokens.
    backends = (
        db.execute(
            text("""SELECT pid, backend_start, datid AS database_oid,
        pg_postmaster_start_time() AS postmaster_start, application_name,
        state, xact_start, wait_event_type, wait_event, pg_blocking_pids(pid) AS blocking_pids
        FROM pg_stat_activity WHERE datname=current_database() AND pid <> pg_backend_pid()
        AND (application_name=:application OR application_name ~ :pattern)
        ORDER BY pid LIMIT 101"""),
            {"application": f"space-data/{root_id}",
             "pattern": f"^space2/[mhd]/{UUID(str(root_id)).hex}/[0-9a-f]{{16}}$"},
        )
        .mappings()
        .all()
    )
    from app.services.worker_observation import fingerprint

    registration = dict(root.job_metadata or {}).get("database_sessions") or {}
    valid_registration = (isinstance(registration, dict)
        and registration.get("schema") == "worker.sessions.v1"
        and registration.get("root_job_id") == str(root_id)
        and registration.get("execution_fingerprint") == fingerprint(root.execution_token)
        and registration.get("owner_fingerprint") == fingerprint(root.worker_id))
    facts = []
    if valid_registration and isinstance(registration.get("roles"), dict):
        for role in ("main", "heartbeat", "diagnostic"):
            pair = registration["roles"].get(role, {})
            if isinstance(pair, dict):
                facts.extend(x for key in ("first", "latest")
                             if isinstance(x := pair.get(key), dict))

    def same_backend(row, fact):
        return all((row[key].isoformat() if isinstance(row[key], datetime) else row[key])
                   == fact.get(key) for key in (
                       "pid", "backend_start", "database_oid", "postmaster_start",
                       "application_name"))

    matched = [dict(row, identity_evidence="REGISTERED_BACKEND_FACT_MATCH" if any(
        same_backend(row, fact) for fact in facts) else "NAME_ONLY_UNVERIFIED")
        for row in backends[:100]]
    return dict(
        job=payload(job),
        root=payload(root),
        children=[payload(row) for row in children],
        dirty=[dict(row) for row in dirty[:100]],
        dirty_truncated=len(dirty) > 100,
        publication=(
            {
                "state": ledger.state,
                "identity": str(ledger.job_id),
                "publish_started_at": ledger.publish_started_at,
                "published_at": ledger.published_at,
            }
            if ledger
            else {"state": "LEGACY_NO_PUBLICATION_RECORD"}
        ),
        candidates=[dict(row) for row in candidates],
        matching_database_backends=matched,
        matching_database_backends_truncated=len(backends) > 100,
        session_registration_status="RECORDED_NOT_EXIT_PROOF" if valid_registration
            else "NOT_REGISTERED",
        backend_absence_meaning="NO_MATCH_IS_NOT_PROCESS_EXIT_PROOF",
        queued_count=db.scalar(
            select(func.count())
            .select_from(JobRun)
            .where(
                JobRun.job_type.in_(INGESTION_JOB_TYPES),
                JobRun.status == "QUEUED",
                JobRun.parent_job_id.is_(None),
            )
        ),
        blocks_data_lane=root.status == "RUNNING",
        process_exit_proven=False,
        required_checks=[
            "FREEZE_ENQUEUE_AND_CLAIM",
            "VERIFY_ALL_HOSTS_AND_PROCESSES_STOPPED",
            "VERIFY_PG_WRITE_TRANSACTIONS_STOPPED",
            "RECONCILE_CHILDREN_DIRTY_PUBLICATION",
            "ADMIN_APPROVAL_AND_EXPECTED_IDENTITY_CAS",
        ],
        runbook="docs/runbooks/data_job_manual_reconcile.md",
    )
