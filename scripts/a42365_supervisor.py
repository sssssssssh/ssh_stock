"""Supervisor gate and two-stage publication. No JSON success can release a marker."""

import os

from scripts.a42361_contract import canonical, sha
from scripts.a42363_contract import require
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
        from scripts.a42364_manager import CandidateRootManager

        require(type(self.root_manager) is CandidateRootManager,
                "INSTALLED_KERNEL_LAUNCHER_REQUIRED")
        self.journal.append(self.scope, "D_RUN_ATTEMPTED", dict(qualifies=False))
        return self.root_manager.dispatch(os.getuid(), "run", dict(scope=self.scope.model_dump()))

    def terminate(self):
        from scripts.a42364_manager import CandidateRootManager

        require(type(self.root_manager) is CandidateRootManager,
                "INSTALLED_KERNEL_LAUNCHER_REQUIRED")
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
        marker = os.stat(".incomplete", dir_fd=self.fd, follow_symlinks=False)
        raw = canonical(nonqualifying(self.scope, "STAGED", evidence=record))
        self._write("evidence.json", raw)
        manifest = canonical(dict(evidence_sha256=sha(raw), qualifies=False))
        self._write("manifest.json", manifest)
        return self.journal.append(
            self.scope,
            "ARTIFACT_STAGED",
            dict(evidence_sha256=sha(raw), manifest_sha256=sha(manifest),
                 marker_identity=[marker.st_dev, marker.st_ino], qualifies=False),
        )

    def finalize(self, root_journal, absence_journal, reviewer_journal, *,
                 consumer_journal=None, controller_journal=None):
        from scripts.a42366_publication import finalize

        return finalize(self, root_journal, absence_journal, reviewer_journal,
                        consumer_journal, controller_journal)
