"""Supervisor gate and two-stage publication. No JSON success can release a marker."""

import os

from scripts.a42361_contract import canonical, sha
from scripts.a42363_contract import require, scope_hash
from scripts.a42365_contract import nonqualifying


class InstalledSupervisor:
    def __init__(self, scope, authority, root_manager, journal):
        require(journal.domain == "supervisor", "SUPERVISOR_JOURNAL_REQUIRED")
        self.scope, self.authority, self.root_manager, self.journal = (
            scope,
            authority,
            root_manager,
            journal,
        )

    def run(self):
        for kind in ("BOOTSTRAP_AND_BUDGET", "SAFE_VOLUME_DISPOSAL", "TARGET_SESSION_GUC"):
            self.authority.require(kind)
        require(self.root_manager is not None, "INSTALLED_KERNEL_LAUNCHER_REQUIRED")
        self.journal.append(self.scope, "D_RUN_ATTEMPTED", dict(qualifies=False))
        return self.root_manager.dispatch(os.getuid(), "run", dict(scope=self.scope.model_dump()))

    def terminate(self):
        require(self.root_manager is not None, "INSTALLED_KERNEL_LAUNCHER_REQUIRED")
        self.journal.append(self.scope, "D_TERMINATE_ATTEMPTED", dict(qualifies=False))
        return self.root_manager.dispatch(
            os.getuid(), "terminate", dict(scope=self.scope.model_dump())
        )


class StagedPublisher:
    def __init__(self, scope, directory_fd, journal):
        self.scope, self.fd, self.journal = scope, directory_fd, journal
        m = os.fstat(directory_fd)
        require(m.st_uid == os.getuid() and m.st_mode & 0o077 == 0, "ARTIFACT_PRIVATE_DIRECTORY")
        self.identity = (m.st_dev, m.st_ino)

    def _write(self, name, raw):
        require(
            (os.fstat(self.fd).st_dev, os.fstat(self.fd).st_ino) == self.identity,
            "ARTIFACT_DIRECTORY_CHANGED",
        )
        fd = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd
        )
        try:
            offset = 0
            while offset < len(raw):
                n = os.write(fd, raw[offset:])
                require(n > 0, "ARTIFACT_SHORT_WRITE")
                offset += n
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.fd)

    def stage(self, record):
        self._write(".incomplete", b"a42365 pending independent termination and absence\n")
        raw = canonical(nonqualifying(self.scope, "STAGED", evidence=record))
        self._write("evidence.json", raw)
        manifest = canonical(dict(evidence_sha256=sha(raw), qualifies=False))
        self._write("manifest.json", manifest)
        return self.journal.append(
            self.scope,
            "ARTIFACT_STAGED",
            dict(evidence_sha256=sha(raw), manifest_sha256=sha(manifest), qualifies=False),
        )

    def finalize(self, root_journal, absence_journal, reviewer_journal):
        self.journal.read(self.scope, "ARTIFACT_STAGED")
        terminated = root_journal.read(self.scope, "ROOT_V3_TERMINATED")
        absence = absence_journal.read(self.scope, "ABSENT")
        review = reviewer_journal.read(self.scope, "REVIEWED")
        require(
            root_journal.domain == "root_manager"
            and absence_journal.domain == "absence_auditor"
            and reviewer_journal.domain == "supervisor",
            "PUBLICATION_INDEPENDENT_DOMAINS",
        )
        require(
            terminated.record.get("execution_scope_terminated") is True
            and terminated.record.get("scope_sha256") == scope_hash(self.scope)
            and terminated.record.get("epoch") == self.scope.epoch
            and len(absence.record.get("observations", [])) == 8
            and review.record.get("terminated_digest") == terminated.digest
            and review.record.get("absence_digest") == absence.digest
            and review.record.get("qualifies") is False,
            "PUBLICATION_AUDIT_CHAIN",
        )
        staged = self.journal.read(self.scope, "ARTIFACT_STAGED").record
        for name, digest in (
            ("evidence.json", staged["evidence_sha256"]),
            ("manifest.json", staged["manifest_sha256"]),
        ):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
            try:
                require(
                    os.fstat(fd).st_nlink == 1 and sha(os.pread(fd, 65537, 0)) == digest,
                    "ARTIFACT_BYTES_CHANGED",
                )
            finally:
                os.close(fd)
        self.journal.append(self.scope, "PUBLICATION_ATTEMPTED", dict(qualifies=False))
        os.unlink(".incomplete", dir_fd=self.fd)
        os.fsync(self.fd)
        return self.journal.append(self.scope, "PUBLISHED", dict(qualifies=False))
