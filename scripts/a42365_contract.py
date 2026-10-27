"""Runtime v4 envelopes. Import, L1 receipts and source checks confer no live rights."""

import os
import re
from dataclasses import dataclass
from typing import Literal

from scripts.a4235_calibration_adapter_contract import Hash, Strict
from scripts.a42361_contract import canonical, checked, decode, sha
from scripts.a42362_contract import Scope, file_identity
from scripts.a42363_contract import DOMAINS, Fault, require, scope_hash

VERSION = "a42365.runtime.v4"
GATES = ("BOOTSTRAP_AND_BUDGET", "SAFE_VOLUME_DISPOSAL", "TARGET_SESSION_GUC", "G1_L2_EXECUTION")
SERVICE_DOMAINS = (*DOMAINS, "root_manager", "writer_broker")
NO_ACTIONS = dict(g1_sql=0, podman=0, initdb=0, cgroup=0, installed_services=0)


class Envelope(Strict):
    version: Literal["a42365.runtime.v4"] = VERSION
    scope: Scope
    source_archive_sha256: Hash
    budget_plan_sha256: Hash
    domain: Literal[*SERVICE_DOMAINS]
    method: str
    body: dict


class RuntimeReceipt(Strict):
    version: Literal["a42365.runtime.v4"] = VERSION
    domain: Literal[*SERVICE_DOMAINS]
    scope_sha256: Hash
    epoch: str
    event: str
    sequence: int
    record: dict
    digest: Hash
    committed: Literal[True] = True
    qualifies: Literal[False] = False


def runtime_receipt(domain, scope, event, sequence, record):
    require(type(sequence) is int and sequence > 0, "RUNTIME_RECEIPT_SEQUENCE")
    body = dict(
        domain=domain,
        scope_sha256=scope_hash(scope),
        epoch=scope.epoch,
        event=event,
        sequence=sequence,
        record=decode(canonical(record)),
    )
    return RuntimeReceipt(**body, digest=sha(canonical(body)))


def message(scope, source, budget, domain, method, body):
    require(re.fullmatch(r"[a-z][a-z0-9-]{0,39}", method) is not None, "RUNTIME_METHOD")
    return Envelope(
        scope=scope,
        source_archive_sha256=source,
        budget_plan_sha256=budget,
        domain=domain,
        method=method,
        body=body,
    )


def verify_envelope(value, scope, source, budget, domain, methods):
    q = checked(Envelope, value)
    require(
        q.scope == scope
        and q.source_archive_sha256 == source
        and q.budget_plan_sha256 == budget
        and q.domain == domain,
        "RUNTIME_SCOPE_DRIFT",
    )
    require(q.method in methods, "RUNTIME_METHOD")
    require(
        not {"class", "factory", "shell", "argv", "dsn", "root", "approved"}.intersection(q.body),
        "RUNTIME_INJECTED_CAPABILITY",
    )
    return q


def safe_code(error):
    value = getattr(error, "code", "A42363_RUNTIME_ACK_UNKNOWN")
    return (
        value
        if re.fullmatch(r"A4236[1-5]_[A-Z0-9_]{1,80}", value)
        else "A42363_RUNTIME_ACK_UNKNOWN"
    )


@dataclass(frozen=True)
class HeldFile:
    fd: int
    identity: tuple
    digest: str

    @classmethod
    def read(cls, fd, expected, *, owner=None, maximum=65536):
        import fcntl
        import stat

        m = os.fstat(fd)
        require(
            stat.S_ISREG(m.st_mode)
            and m.st_nlink == 1
            and not m.st_mode & 0o022
            and 0 < m.st_size <= maximum
            and (owner is None or m.st_uid == owner)
            and fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY,
            "RUNTIME_HELD_FILE",
        )
        raw = os.pread(fd, maximum + 1, 0)
        require(
            len(raw) == m.st_size
            and sha(raw) == expected
            and file_identity(m) == file_identity(os.fstat(fd)),
            "RUNTIME_FILE_CHANGED",
        )
        return cls(fd, file_identity(m), expected)

    def revalidate(self):
        require(
            file_identity(os.fstat(self.fd)) == self.identity
            and sha(os.pread(self.fd, self.identity[6] + 1, 0)) == self.digest,
            "RUNTIME_FILE_CHANGED",
        )
        return self


def nonqualifying(scope, status, **fields):
    return dict(
        version=VERSION,
        scope_sha256=scope_hash(scope),
        epoch=scope.epoch,
        status=status,
        qualifies=False,
        physical="NOT_RUN_NOT_AUTHORIZED",
        **fields,
    )


__all__ = [
    "VERSION",
    "GATES",
    "SERVICE_DOMAINS",
    "NO_ACTIONS",
    "Envelope",
    "Fault",
    "HeldFile",
    "canonical",
    "checked",
    "decode",
    "sha",
    "require",
    "scope_hash",
    "message",
    "verify_envelope",
    "safe_code",
    "nonqualifying",
]
