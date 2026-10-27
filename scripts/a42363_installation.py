"""Read-only trusted-FD validation and an honest machine-readable capability matrix.

No installer or activation flag. Supplying a valid FD establishes only its source
binding; it neither approves a protocol nor creates a database, namespace or cgroup.
"""

import fcntl
import os
import stat
from dataclasses import dataclass

from scripts.a4235_calibration_adapter_contract import Hash, Strict
from scripts.a42361_contract import Positive, checked, decode, sha
from scripts.a42362_contract import file_identity
from scripts.a42362_service_host import Domain
from scripts.a42363_contract import require

CAPABILITIES = {
    "registry": frozenset(),
    "approval": frozenset(),
    "consumer": frozenset(),
    "pg_owner": frozenset(("owner_connection", "owner_runtime")),
    "controller": frozenset(("ledger", "resource_driver", "consumption", "fixture")),
    "absence_auditor": frozenset(("observer", "controller_store", "ledger")),
    "supervisor": frozenset(("root_manager", "scope", "publisher")),
}


class FDDocumentBody(Strict):
    schema_version: str
    domain: Domain
    uid: Positive
    scope_sha256: Hash
    epoch: str
    source_sha256: Hash
    capability_digests: dict[str, Hash]
    expires_at: Positive


@dataclass(frozen=True)
class InstalledFDDocument:
    domain: str
    uid: int
    digest: str
    record: dict

    @classmethod
    def read(cls, fd, expected_digest, domain, expected_uid):
        require(
            type(fd) is int and type(expected_uid) is int and expected_uid > 0,
            "INSTALLATION_FD_REQUIRED",
        )
        m = os.fstat(fd)
        require(
            stat.S_ISREG(m.st_mode)
            and m.st_uid == 0
            and m.st_nlink == 1
            and m.st_mode & 0o277 == 0
            and 0 < m.st_size <= 65536
            and fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY,
            "INSTALLATION_FD_UNTRUSTED",
        )
        raw = os.pread(fd, 65537, 0)
        require(
            len(raw) == m.st_size
            and sha(raw) == expected_digest
            and file_identity(os.fstat(fd)) == file_identity(m),
            "INSTALLATION_CHANGED",
        )
        body = checked(FDDocumentBody, decode(raw)).model_dump()
        require(
            body["schema_version"] == "a42363.installed-fds.v1"
            and body["domain"] == domain
            and body["uid"] == expected_uid,
            "INSTALLATION_PRINCIPAL",
        )
        require(
            set(body["capability_digests"]) == CAPABILITIES[domain], "INSTALLATION_CAPABILITIES"
        )
        return cls(domain, expected_uid, expected_digest, body)

    def verify_scope(self, scope, now):
        from scripts.a42363_contract import scope_hash

        require(
            type(now) is int
            and type(self.record["expires_at"]) is int
            and now < self.record["expires_at"]
            and self.record["scope_sha256"] == scope_hash(scope)
            and self.record["epoch"] == scope.epoch
            and self.record["source_sha256"] == scope.binding.identity.source_sha256,
            "INSTALLATION_BINDING",
        )
        return self

    def verify_code_fds(self, code_fds):
        require(set(code_fds) == CAPABILITIES[self.domain], "INSTALLATION_CAPABILITIES")
        for name, fd in code_fds.items():
            m = os.fstat(fd)
            require(
                stat.S_ISREG(m.st_mode)
                and m.st_uid == 0
                and m.st_mode & 0o022 == 0
                and 0 < m.st_size <= 1_000_000,
                "INSTALLATION_CODE_FD",
            )
            raw = os.pread(fd, 1_000_001, 0)
            require(
                len(raw) == m.st_size
                and sha(raw) == self.record["capability_digests"][name]
                and file_identity(os.fstat(fd)) == file_identity(m),
                "INSTALLATION_CODE_CHANGED",
            )
        return self


def capability_matrix():
    def row(source, approval="NOT_APPROVED"):
        return dict(
            source=source,
            approval=approval,
            installation="NOT_DEPLOYED",
            physical="NOT_RUN",
            qualifies=False,
        )

    return {
        "scope_identity": row("IMPLEMENTED"),
        "approval_consumption": row("IMPLEMENTED"),
        "pg_fixture": row("IMPLEMENTED_WITH_PROTOCOL_BLOCK"),
        "bootstrap_image": row("NOT_IMPLEMENTED"),
        "bootstrap_candidate": row("IMPLEMENTED_SPECIFICATION_ONLY"),
        "safe_volume_disposal": row("NOT_IMPLEMENTED"),
        "target_session_guc": row("IMPLEMENTED_OFFLINE_PARSER_ONLY"),
        "resource_recovery": row("IMPLEMENTED"),
        "independent_e": row("IMPLEMENTED_REQUIRES_TRUSTED_DELEGATION"),
        "root_manager": row("IMPLEMENTED_REQUIRES_INSTALLED_PACKAGE"),
        "whole_scope_termination": row("IMPLEMENTED_KERNEL_ADAPTER_NOT_VERIFIED"),
        "artifact_publication": row("IMPLEMENTED"),
        "six_source_review": row("IMPLEMENTED_L0_L1_ONLY"),
    }


def engineering_capability_matrix():
    """Current engineering view; historical v1 capability_matrix is retained."""
    from scripts.a42364_bootstrap_builder import ENTRYPOINT
    from scripts.a42364_volume_exclusion import engineering_status

    return dict(version="a42364.engineering.v3",
                bootstrap_image="SOURCE_IMPLEMENTED_UNDEPLOYED", entrypoint=ENTRYPOINT,
                volume=engineering_status(), installation="NOT_DEPLOYED",
                physical="NOT_RUN_NOT_AUTHORIZED", active_live_gate="DENY", qualifies=False)
