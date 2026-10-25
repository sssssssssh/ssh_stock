"""Exclusive failure-first export and independent, non-qualifying receipt review.

No bundle is its own trust anchor. An offline-valid bundle is NEVER a G1 success.
"""

import os
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from scripts.a4235_calibration_adapter_contract import Hash, Strict
from scripts.a42361_contract import (
    Binding,
    Capability,
    Fault,
    canonical,
    checked,
    decode,
    require,
    sha,
)
from scripts.a42361_deployment import LocalService, installed


class Evidence(Strict):
    schema_version: Literal["a42361.evidence.v1"] = "a42361.evidence.v1"
    binding: Binding
    evidence_kind: Literal["OFFLINE_CONTRACT_ONLY", "UNATTESTED_RECEIPT_REFERENCES"]
    payload_sha256: Hash
    references: dict[str, Hash]
    worker_sha256: Hash | None
    first_error: str | None
    cleanup_codes: tuple[str, ...]
    last_incomplete: str | None
    capabilities: Capability = Capability()


@dataclass
class FailureLedger:
    first_error: str | None = None
    cleanup_codes: list[str] = field(default_factory=list)
    last_incomplete: str | None = None

    def fail(self, code, *, cleanup=False):
        code = Fault(code).code
        if self.first_error is None:
            self.first_error = code
        self.last_incomplete = code
        if cleanup and code not in self.cleanup_codes:
            require(len(self.cleanup_codes) < 16, "A42361_CLEANUP_ERRORS_EXCEEDED")
            self.cleanup_codes.append(code)


def validate_evidence(value):
    value = checked(Evidence, value)
    require(
        set(value.references)
        <= {"approval", "consumer", "pg_owner", "controller", "supervisor", "absence_auditor"},
        "A42361_RECEIPT_DOMAIN_INVALID",
    )
    require(
        len(value.cleanup_codes) <= 16
        and len(set(value.cleanup_codes)) == len(value.cleanup_codes),
        "A42361_FAILURE_LEDGER_INVALID",
    )
    for code in (value.first_error, value.last_incomplete, *value.cleanup_codes):
        require(code is None or Fault(code).code == code, "A42361_FAILURE_LEDGER_INVALID")
    require(
        not value.cleanup_codes
        or value.first_error is not None
        and value.last_incomplete is not None,
        "A42361_FAILURE_LEDGER_INVALID",
    )
    return value


def _directory(path):
    require(type(path) is Path or isinstance(path, Path), "A42361_UNSAFE_OUTPUT")
    require(
        path.is_absolute()
        and ".." not in path.parts
        and not any(p.is_symlink() for p in (path, *path.parents)),
        "A42361_UNSAFE_OUTPUT",
    )


def write_bundle(path, evidence):
    """No overwrite. Bounded bytes; .incomplete remains until manifest+directory fsync.

    This function's elapsed guard is not a physical fsync kill guarantee. Its installed
    caller MUST run in the external artifact supervisor; absent deployment stays blocked.
    """
    path = Path(path)
    _directory(path)
    value = validate_evidence(evidence)
    raw = canonical(value.model_dump())
    started = time.monotonic_ns()
    fd = None
    try:
        os.mkdir(path, 0o700)
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        meta = os.fstat(fd)
        require(
            meta.st_uid == os.getuid() and stat.S_IMODE(meta.st_mode) == 0o700,
            "A42361_UNSAFE_OUTPUT",
        )

        def write(name, data):
            target = os.open(
                name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=fd
            )
            with os.fdopen(target, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            require(0 <= time.monotonic_ns() - started <= 2_000_000_000, "A42361_ARTIFACT_TIMEOUT")

        write(".incomplete", b"A42361_INCOMPLETE\n")
        write("evidence.json", raw)
        write(
            "manifest.json",
            canonical(
                dict(
                    schema_version="a42361.manifest.v1",
                    files={"evidence.json": dict(bytes=len(raw), sha256=sha(raw))},
                )
            ),
        )
        os.fsync(fd)
        require(path.stat() == os.fstat(fd), "A42361_UNSAFE_OUTPUT")
        os.unlink(".incomplete", dir_fd=fd)
        os.fsync(fd)
        require(time.monotonic_ns() - started <= 2_000_000_000, "A42361_ARTIFACT_TIMEOUT")
    except BaseException:
        # Even a late fsync failure must NOT leave a complete-looking directory.
        if fd is not None:
            try:
                marker = os.open(
                    ".incomplete",
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=fd,
                )
                os.close(marker)
            except OSError:
                pass
        raise Fault("A42361_ARTIFACT_INCOMPLETE") from None
    finally:
        if fd is not None:
            os.close(fd)


def read_bundle(path):
    path = Path(path)
    _directory(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            meta = os.fstat(fd)
            require(
                meta.st_uid == os.getuid() and stat.S_IMODE(meta.st_mode) == 0o700,
                "A42361_UNSAFE_OUTPUT",
            )
            require(
                set(os.listdir(fd)) == {"manifest.json", "evidence.json"},
                "A42361_ARTIFACT_INCOMPLETE",
            )

            def read(name):
                f = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    before = os.fstat(f)
                    require(
                        stat.S_ISREG(before.st_mode)
                        and before.st_uid == os.getuid()
                        and stat.S_IMODE(before.st_mode) == 0o600
                        and before.st_nlink == 1
                        and 0 < before.st_size <= 65536,
                        "A42361_UNSAFE_OUTPUT",
                    )
                    raw = os.read(f, 65537)
                    require(os.fstat(f) == before, "A42361_ARTIFACT_CHANGED")
                    return raw
                finally:
                    os.close(f)

            raw = read("evidence.json")
            require(
                decode(read("manifest.json"))
                == dict(
                    schema_version="a42361.manifest.v1",
                    files={"evidence.json": dict(bytes=len(raw), sha256=sha(raw))},
                ),
                "A42361_MANIFEST_INVALID",
            )
            value = validate_evidence(decode(raw))
            require(path.stat() == os.fstat(fd), "A42361_ARTIFACT_CHANGED")
            return value
        finally:
            os.close(fd)
    except Fault:
        raise
    except Exception:
        raise Fault("A42361_ARTIFACT_INCOMPLETE") from None


class Reviewer:
    def __init__(self, deployment=None):
        self.deployment = deployment

    def review(self, path, expected):
        value = read_bundle(path)
        require(value.binding == expected, "A42361_BINDING_MISMATCH")
        result = dict(
            status="OFFLINE_CONTRACT_VALID",
            exit_code=2,
            qualifies=False,
            physical_capabilities="NOT_PROVEN",
            **Capability().model_dump(),
        )
        if self.deployment is None:
            return result
        installed(self.deployment)
        from scripts.a42361_source_guard import independent_binding

        fresh = independent_binding(
            expected.identity.run_id,
            expected.identity.attempt,
            expected.fixture_uuid,
            expected.nonce,
            expected.marker_sha256,
        )
        require(fresh == expected, "A42361_SOURCE_DRIFT")
        require(
            value.evidence_kind == "UNATTESTED_RECEIPT_REFERENCES"
            and set(value.references)
            == {"approval", "consumer", "pg_owner", "controller", "supervisor", "absence_auditor"},
            "A42361_RECEIPTS_UNTRUSTED",
        )
        for domain, digest in value.references.items():
            receipt = LocalService(self.deployment, domain).call(
                "receipt", dict(payload_sha256=value.payload_sha256, receipt_sha256=digest)
            )
            require(
                type(receipt) is dict
                and set(receipt)
                == {
                    "domain",
                    "binding",
                    "payload_sha256",
                    "receipt_sha256",
                    "raw_receipt_sha256",
                    "status",
                }
                and receipt["domain"] == domain
                and receipt["binding"] == expected.model_dump()
                and receipt["payload_sha256"] == value.payload_sha256
                and receipt["receipt_sha256"] == digest == receipt["raw_receipt_sha256"]
                and receipt["status"] == "COMMITTED_VERIFIED",
                "A42361_RECEIPTS_UNTRUSTED",
            )
        # A new physical qualification reviewer is NOT installed by a repository push.
        return dict(result, status="RECEIPTS_MATCH_PENDING_INDEPENDENT_G1_REVIEW")
