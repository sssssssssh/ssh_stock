"""Root-owned read-only installation package. Plans do not install or approve G1."""

import os
import re
import stat
import time
from dataclasses import dataclass
from typing import Literal

from scripts.a4235_calibration_adapter_contract import Hash, Strict
from scripts.a42361_contract import Positive, checked, decode, sha
from scripts.a42362_contract import Scope, file_identity
from scripts.a42363_contract import DOMAINS, require

_INSTALLED = object()
PRINCIPALS = (*DOMAINS, "worker", "runtime")


class InstallDocument(Strict):
    version: str
    service_domain: Literal["root_manager", "absence_auditor"]
    scope: Scope
    principals: dict[str, Positive]
    binary_sha256: dict[str, Hash]
    code_archive_sha256: Hash
    image_manifest_sha256: Hash
    custody_review_sha256: Hash
    public_keys: dict[str, dict[str, str]]
    revoked_kids: tuple[str, ...]
    openssl_version: str
    expires_at: Positive


def installation_layout():
    return dict(
        manager_uid=0,
        distinct_nonroot_principals=PRINCIPALS,
        fixed_prefix="/opt/space-g1",
        auto_start_g1=False,
        reserved_fds=dict(installation=3, source_archive=4, listener=5),
        deployment="NOT_DEPLOYED",
        physical="NOT_RUN_NOT_AUTHORIZED",
    )


def validate_document(document, now):
    if type(document) is dict and document.get("version") == "a42366.installation.v5":
        from scripts.a42366_installation import validate_domain_document

        return validate_domain_document(document, now)
    d = checked(InstallDocument, document)
    require(
        d.version == "a42364.installation.v3" and d.expires_at > now, "INSTALL_VERSION_OR_EXPIRY"
    )
    require(
        set(d.principals) == set(PRINCIPALS)
        and len(set(d.principals.values())) == 9
        and d.principals["controller"] == d.scope.controller_uid,
        "INSTALL_DISTINCT_UIDS",
    )
    require(
        set(d.binary_sha256) == {"python", "worker", "podman", "collector", "openssl"},
        "INSTALL_BINARIES",
    )
    require(set(d.public_keys) == {"OWNER", "SAFETY_PLATFORM"}, "INSTALL_SIGNERS")
    public = []
    for group in d.public_keys.values():
        require(group and len(group) <= 8, "INSTALL_KEYS")
        for kid, value in group.items():
            require(
                re.fullmatch(r"[A-Za-z0-9_-]{1,40}", kid) is not None
                and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
                "INSTALL_KEYS",
            )
            raw = bytes.fromhex(value)
            # Public RFC8032 fixture keys are never formal trust roots.
            require(
                value
                not in (
                    "0" * 64,
                    "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
                    "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
                ),
                "INSTALL_TEST_KEY",
            )
            public.append(raw)
    require(len(public) == len(set(public)), "INSTALL_SIGNER_INDEPENDENCE")
    return d


def read_root_document(fd, expected_digest):
    import fcntl

    m = os.fstat(fd)
    require(
        stat.S_ISREG(m.st_mode)
        and m.st_uid == 0
        and m.st_nlink == 1
        and m.st_mode & 0o277 == 0
        and 0 < m.st_size <= 65536
        and fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY,
        "INSTALL_ROOT_FD",
    )
    raw = os.pread(fd, 65537, 0)
    require(
        len(raw) == m.st_size
        and sha(raw) == expected_digest
        and file_identity(os.fstat(fd)) == file_identity(m),
        "INSTALL_DOCUMENT_CHANGED",
    )
    return raw, file_identity(m)


@dataclass(frozen=True)
class InstalledPackage:
    fd: int
    digest: str
    document: InstallDocument
    metadata: tuple
    verifier: object
    registry: object
    _seal: object

    @classmethod
    def read(cls, fd, expected_digest, registry=None):
        raw, metadata = read_root_document(fd, expected_digest)
        d = validate_document(decode(raw), int(time.time()))
        from scripts.a42361_deployment import checked_executable
        from scripts.a42361_trust_verifier import Ed25519Verifier

        require(d.openssl_version.startswith("OpenSSL 3."), "INSTALL_PINNED_CRYPTO_REQUIRED")
        binary = checked_executable("/usr/bin/openssl", d.binary_sha256["openssl"])
        verifier = Ed25519Verifier(binary, d.openssl_version)
        return cls(fd, expected_digest, d, metadata, verifier, registry, _INSTALLED)

    def now(self):
        return int(time.time())

    def revalidate(self):
        raw, metadata = read_root_document(self.fd, self.digest)
        require(
            metadata == self.metadata
            and validate_document(decode(raw), self.now()) == self.document,
            "INSTALL_DOCUMENT_CHANGED",
        )
        validate_document(self.document, self.now())
        from scripts.a42361_deployment import checked_executable

        checked_executable("/usr/bin/openssl", self.document.binary_sha256["openssl"])
        return self

    def signing_key(self, role, kid):
        self.revalidate()
        require(kid not in self.document.revoked_kids, "INSTALL_KEY_REVOKED")
        require(
            role in self.document.public_keys and kid in self.document.public_keys[role],
            "INSTALL_KEY_UNKNOWN",
        )
        key = bytes.fromhex(self.document.public_keys[role][kid])
        from scripts.a42364_protocol_decision import RegistryChannel

        require(type(self.registry) is RegistryChannel, "INDEPENDENT_REGISTRY_REQUIRED")
        self.registry.verify_current(self, role, kid, key)
        return key

    def verify_binary(self, name, fd):
        require(name in self.document.binary_sha256, "INSTALL_BINARY_UNKNOWN")
        m = os.fstat(fd)
        require(
            stat.S_ISREG(m.st_mode)
            and m.st_uid == 0
            and m.st_nlink == 1
            and not m.st_mode & 0o022
            and 0 < m.st_size <= 64_000_000,
            "INSTALL_BINARY_FD",
        )
        import hashlib

        digest = hashlib.sha256()
        offset = 0
        while offset < m.st_size:
            raw = os.pread(fd, min(65536, m.st_size - offset), offset)
            require(raw, "INSTALL_BINARY_CHANGED")
            digest.update(raw)
            offset += len(raw)
        require(
            digest.hexdigest() == self.document.binary_sha256[name]
            and file_identity(os.fstat(fd)) == file_identity(m),
            "INSTALL_BINARY_CHANGED",
        )
        return fd


def installed_package(value):
    require(
        type(value) is InstalledPackage and value._seal is _INSTALLED, "INSTALLED_PACKAGE_REQUIRED"
    )
    return value.revalidate()


class InstallationPackage:
    """Exact-file stage writer. Never enables/starts systemd, allocates UIDs or runs G1.

    The admin must first supply a reviewed root-owned package and fixed parent FD.
    Failure leaves .incomplete and existing files intact; no recursive rollback/remove.
    """

    def __init__(self, files):
        allowed = {
            "root_manager.service",
            "worker.service",
            "read_only_auditor.service",
            "source.zip",
            "entry.py",
            "installation.json",
        }
        require(
            set(files) == allowed
            and all(type(v) is bytes and len(v) <= 16_000_000 for v in files.values()),
            "INSTALL_PACKAGE_FILES",
        )
        self.files = dict(files)

    def plan(self):
        return dict(
            files={
                n: dict(sha256=sha(v), mode="0400" if n == "installation.json" else "0444")
                for n, v in self.files.items()
            },
            auto_start_g1=False,
            qualifies=False,
        )

    def stage(self, parent_fd, package):
        p = installed_package(package)
        require(os.getuid() == 0, "ROOT_INSTALLER_REQUIRED")
        m = os.fstat(parent_fd)
        require(
            stat.S_ISDIR(m.st_mode)
            and m.st_uid == 0
            and m.st_mode & 0o022 == 0
            and os.readlink("/proc/self/fd/" + str(parent_fd)) == "/opt/space-g1",
            "INSTALL_TARGET",
        )
        require(
            sha(self.files["source.zip"]) == p.document.code_archive_sha256
            and sha(self.files["installation.json"]) == p.digest,
            "INSTALL_PACKAGE_DIGEST",
        )
        marker = os.open(
            ".incomplete",
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent_fd,
        )
        os.fsync(marker)
        os.close(marker)
        os.fsync(parent_fd)
        for name, raw in self.files.items():
            p.revalidate()
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o400 if name == "installation.json" else 0o444,
                dir_fd=parent_fd,
            )
            try:
                view = memoryview(raw)
                while view:
                    n = os.write(fd, view)
                    require(n > 0, "INSTALL_SHORT_WRITE")
                    view = view[n:]
                os.fsync(fd)
            finally:
                os.close(fd)
        os.fsync(parent_fd)
        os.unlink(".incomplete", dir_fd=parent_fd)
        os.fsync(parent_fd)
        return dict(status="FILES_STAGED_SERVICES_NOT_STARTED", qualifies=False)


def document_schema():
    return InstallDocument.model_json_schema()
