"""Fresh independent evidence and monotonic, recoverable artifact finalization.

SQLite and directory changes are NOT one transaction. A permanent approval and
PUBLISHED receipt precede marker removal; FINALIZED follows directory fsync.
Without the independently installed Reviewer channel, the public path is closed.
"""

import os
import re
import stat

from scripts.a42361_contract import canonical, sha
from scripts.a42362_contract import file_identity, resources
from scripts.a42363_contract import require, scope_hash, verify_receipt
from scripts.a42365_contract import runtime_receipt


def validate_absence(scope, terminated, absence, consumer, controller):
    require(
        terminated == runtime_receipt("root_manager", scope, "ROOT_V3_TERMINATED",
                                      terminated.sequence, terminated.record)
        and terminated.record.get("execution_scope_terminated") is True
        and terminated.record.get("scope_sha256") == scope_hash(scope)
        and terminated.record.get("epoch") == scope.epoch,
        "PUBLICATION_ROOT_TERMINATION",
    )
    verify_receipt(absence, "absence_auditor", scope, "ABSENT")
    rows = absence.record.get("observations")
    require(type(rows) is list and len(rows) == 8, "PUBLICATION_TWO_ROUNDS")
    require(consumer is not None and controller is not None, "PUBLICATION_FRESH_BC_REQUIRED")
    consumed = consumer.read(scope, "CONSUMED")
    destroyed = controller.read(scope, "RECONCILED")
    requested = controller.read(scope, "DESTROY_REQUESTED")
    verify_receipt(consumed, "consumer", scope, "CONSUMED")
    verify_receipt(destroyed, "controller", scope, "RECONCILED")
    verify_receipt(requested, "controller", scope, "DESTROY_REQUESTED")
    record = destroyed.record
    require(
        requested.sequence < destroyed.sequence
        and record.get("status") == "DESTROYED_PENDING_INDEPENDENT_E"
        and type(record.get("destroyed_ns")) is int and record["destroyed_ns"] > 0
        and not record.get("first_error") and not record.get("cleanup_codes")
        and absence.record.get("scope_sha256") == scope_hash(scope)
        and absence.record.get("epoch") == scope.epoch
        and absence.record.get("requested_digest") == requested.digest
        and absence.record.get("destruction_digest") == destroyed.digest
        and absence.record.get("consumption_digest") == consumed.digest,
        "PUBLICATION_DESTRUCTION_BINDING",
    )
    originals = {}
    for item in resources(scope):
        original = controller.read(scope, item.kind + "_ORIGINAL")
        verify_receipt(original, "controller", scope, item.kind + "_ORIGINAL")
        require(
            original.record.get("raw_sha256") == sha(canonical(original.record.get("raw")))
            and type(original.record.get("identity_sha256")) is str
            and re.fullmatch(r"[0-9a-f]{64}", original.record["identity_sha256"]) is not None,
            "PUBLICATION_ORIGINAL_IDENTITY",
        )
        originals[item.kind] = original.digest
        removed = controller.read(scope, item.kind + "_REMOVE_DONE")
        verify_receipt(removed, "controller", scope, item.kind + "_REMOVE_DONE")
        require(original.sequence < removed.sequence < destroyed.sequence,
                "PUBLICATION_REMOVAL_ORDER")
    require(record.get("original_digests") == originals, "PUBLICATION_ORIGINAL_SET")
    previous = record["destroyed_ns"]
    visibility_binding = None
    for index, (item, row) in enumerate(zip(resources(scope) * 2, rows, strict=True)):
        require(type(row) is dict, "PUBLICATION_OBSERVATION")
        raw, visibility = row.get("raw"), row.get("visibility")
        require(
            row.get("resource") == item.model_dump()
            and type(row.get("round")) is int and row["round"] == index // 4 + 1
            and row.get("result") == "ABSENT"
            and raw == dict(status="ABSENT", code=1, identity=None)
            and type(raw["code"]) is int
            and row.get("original_digest") == originals[item.kind]
            and type(row.get("observed_ns")) is int and row["observed_ns"] > previous
            and type(visibility) is dict
            and visibility.get("readonly") is True
            and visibility.get("epoch") == scope.epoch
            and visibility.get("namespace_sha256") == scope.namespace_sha256
            and visibility.get("controller_uid") == scope.controller_uid
            and type(row.get("observer_uid")) is int
            and row["observer_uid"] == visibility.get("observer_uid")
            and row["observer_uid"] != scope.controller_uid,
            "PUBLICATION_OBSERVATION",
        )
        if visibility_binding is None:
            visibility_binding = visibility
        require(visibility == visibility_binding, "PUBLICATION_VISIBILITY_DRIFT")
        previous = row["observed_ns"]
    require(
        consumer.read(scope, "CONSUMED") == consumed
        and controller.read(scope, "RECONCILED") == destroyed
        and controller.read(scope, "DESTROY_REQUESTED") == requested,
        "PUBLICATION_STALE_BC",
    )
    return dict(terminated_digest=terminated.digest, absence_digest=absence.digest,
                consumption_digest=consumed.digest, destruction_digest=destroyed.digest,
                original_digests=originals, scope_sha256=scope_hash(scope), epoch=scope.epoch)


def _artifact(publisher, name, digest):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=publisher.fd)
    try:
        m = os.fstat(fd)
        require(stat.S_ISREG(m.st_mode) and m.st_nlink == 1 and m.st_size <= 65536
                and sha(os.pread(fd, 65537, 0)) == digest, "ARTIFACT_BYTES_CHANGED")
        require(file_identity(os.fstat(fd)) == file_identity(m), "ARTIFACT_BYTES_CHANGED")
    finally:
        os.close(fd)


def _committed(journal, scope, event, record):
    old = journal.maybe_read(scope, event)
    if old is not None:
        require(old.record == record, "PUBLICATION_RECOVERY_BINDING")
        return old
    return journal.append(scope, event, record)


def _commit_finalization(publisher, approval):
    """Internal crash-recovery primitive; approval is obtained by finalize, not RPC.

    This function does not issue or validate a physical qualification. Callers must
    never expose it as a separate command. Tests of this primitive are fault models.
    """
    scope, j = publisher.scope, publisher.journal
    _committed(j, scope, "AUDIT_VERIFIED", approval)
    intent = _committed(j, scope, "PUBLISH_INTENT", approval)
    published = _committed(j, scope, "PUBLISHED", dict(
        approval_digest=j.read(scope, "AUDIT_VERIFIED").digest,
        intent_digest=intent.digest, qualifies=False,
    ))
    # A committed SQLite FULL receipt exists before an irreversible directory edit.
    # ACK loss is recovered by a fresh read, not a second INSERT or new approval.
    require(j.read(scope, "PUBLISHED") == published, "PUBLICATION_COMMIT_UNKNOWN")
    try:
        marker = os.stat(".incomplete", dir_fd=publisher.fd, follow_symlinks=False)
    except FileNotFoundError:
        marker = None  # May have been removed after a committed receipt before a crash.
    if marker is not None:
        require(stat.S_ISREG(marker.st_mode) and marker.st_nlink == 1,
                "PUBLICATION_MARKER_CHANGED")
        staged = j.read(scope, "ARTIFACT_STAGED").record
        require([marker.st_dev, marker.st_ino] == staged.get("marker_identity"),
                "PUBLICATION_MARKER_CHANGED")
        os.unlink(".incomplete", dir_fd=publisher.fd)
    os.fsync(publisher.fd)
    return _committed(j, scope, "FINALIZED", dict(
        published_digest=published.digest, qualifies=False,
    ))


def finalize(publisher, root, absence, reviewer, consumer=None, controller=None):
    staged = publisher.journal.read(publisher.scope, "ARTIFACT_STAGED")
    terminated = root.read(publisher.scope, "ROOT_V3_TERMINATED")
    absent = absence.read(publisher.scope, "ABSENT")
    facts = validate_absence(publisher.scope, terminated, absent, consumer, controller)
    from scripts.a42366_reviewer import IndependentReviewSource

    require(type(reviewer) is IndependentReviewSource, "PUBLICATION_INDEPENDENT_REVIEWER_REQUIRED")
    require(
        (os.fstat(publisher.fd).st_dev, os.fstat(publisher.fd).st_ino) == publisher.identity,
        "ARTIFACT_DIRECTORY_CHANGED",
    )
    for name, field in (("evidence.json", "evidence_sha256"), ("manifest.json", "manifest_sha256")):
        _artifact(publisher, name, staged.record[field])
    approval = dict(facts, staged_digest=staged.digest, qualifies=False)
    review = reviewer.review(publisher.scope, approval)
    approval["reviewer_digest"] = sha(canonical(review))
    # No supervisor-generated REVIEWED record or caller dictionary is a substitute.
    require(root.read(publisher.scope, "ROOT_V3_TERMINATED") == terminated
            and absence.read(publisher.scope, "ABSENT") == absent,
            "PUBLICATION_AUDIT_CHANGED")
    validate_absence(publisher.scope, terminated, absent, consumer, controller)
    reviewer.revalidate()
    return _commit_finalization(publisher, approval)
