"""Ed25519 verification, independently configured keys, live approval and revocation.

Only verification is implemented here. No issuer, signing key or formal token generator.
"""

import base64
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from scripts.a42361_contract import (
    Approval,
    Binding,
    Fault,
    GrantPayload,
    canonical,
    checked,
    decode,
    require,
    sha,
    valid_binding,
)
from scripts.a42361_deployment import LocalService, checked_executable, installed

_VERIFIED = object()


@dataclass(frozen=True)
class VerifiedGrant:
    payload: GrantPayload
    payload_sha256: str
    approval: Approval
    registry_snapshot_sha256: str
    verified_at: int
    _seal: object


def verified(value):
    require(
        type(value) is VerifiedGrant and value._seal is _VERIFIED,
        "A42361_VERIFIED_APPROVAL_REQUIRED",
    )
    require(
        value.payload_sha256 == sha(canonical(value.payload.model_dump())),
        "A42361_BINDING_MISMATCH",
    )
    return value


def unbase64(value, maximum):
    try:
        require(type(value) is str and len(value) <= maximum * 2, "A42361_ENCODING_INVALID")
        result = base64.b64decode(value, validate=True)
        require(
            base64.b64encode(result).decode("ascii") == value and len(result) <= maximum,
            "A42361_ENCODING_INVALID",
        )
        return result
    except Exception:
        raise Fault("A42361_ENCODING_INVALID") from None


class Ed25519Verifier:
    def __init__(self, executable=None, expected_version=None):
        self.executable, self.expected_version = executable, expected_version

    def verify_signature(self, public_key, message, signature):
        require(self.executable is not None, "A42361_ISSUER_NOT_CONFIGURED")
        require(
            type(public_key) is bytes
            and len(public_key) == 32
            and type(signature) is bytes
            and len(signature) == 64
            and type(message) is bytes
            and len(message) <= 65536,
            "A42361_SIGNATURE_INVALID",
        )
        try:
            clean_env = {"OPENSSL_CONF": os.devnull}
            version = subprocess.run(
                [self.executable, "version"],
                env=clean_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=0.2,
                check=False,
            )
            require(
                version.returncode == 0
                and version.stdout.startswith(b"OpenSSL 3.")
                and (
                    self.expected_version is None
                    or version.stdout.decode("ascii").strip() == self.expected_version
                ),
                "A42361_CRYPTO_RUNTIME_UNTRUSTED",
            )
            with tempfile.TemporaryDirectory(prefix="a42361-crypto-") as directory:
                files = {
                    "public.der": bytes.fromhex("302a300506032b6570032100") + public_key,
                    "payload.bin": message,
                    "signature.bin": signature,
                }
                for name, raw in files.items():
                    fd = os.open(
                        Path(directory) / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
                    )
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(raw)
                result = subprocess.run(
                    [
                        self.executable,
                        "pkeyutl",
                        "-verify",
                        "-pubin",
                        "-keyform",
                        "DER",
                        "-inkey",
                        str(Path(directory) / "public.der"),
                        "-rawin",
                        "-in",
                        str(Path(directory) / "payload.bin"),
                        "-sigfile",
                        str(Path(directory) / "signature.bin"),
                    ],
                    env=clean_env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=0.5,
                    check=False,
                )
                require(result.returncode == 0, "A42361_SIGNATURE_INVALID")
        except Fault:
            raise
        except Exception:
            raise Fault("A42361_SIGNATURE_INVALID") from None


class TrustVerifier:
    def __init__(self, deployment=None):
        self.deployment = deployment

    def verify_signature(self, envelope, expected):
        config = installed(self.deployment)  # First gate: no crypto/IPC if not installed.
        started = time.monotonic_ns()
        expected = checked(Binding, expected)
        try:
            outer = decode(envelope)
            require(
                type(outer) is dict and set(outer) == {"payload", "signature"},
                "A42361_ENVELOPE_INVALID",
            )
            raw, signature = unbase64(outer["payload"], 32768), unbase64(outer["signature"], 64)
            data = decode(raw)
            payload = checked(GrantPayload, data)
            valid_binding(payload.binding, expected)
            require(
                payload.image_digest == config.image.rsplit("@", 1)[-1], "A42361_BINDING_MISMATCH"
            )
            now = int(time.time())
            require(
                0 < payload.issued_at <= payload.not_before <= now < payload.expires_at
                and payload.expires_at - payload.issued_at <= 300
                and config.expires_at > now,
                "A42361_GRANT_EXPIRED",
            )
            keys = [k for k in config.keys if k.issuer == payload.issuer and k.kid == payload.kid]
            require(len(keys) == 1, "A42361_ISSUER_NOT_CONFIGURED")
            key = keys[0]
            require(
                not key.revoked
                and key.valid_from <= now < key.valid_until
                and key.usage == "PRODUCTION_G1",
                "A42361_KEY_REVOKED",
            )
            registry = LocalService(self.deployment, "registry").call(
                "key-status",
                dict(
                    issuer=key.issuer,
                    kid=key.kid,
                    public_key_sha256=sha(bytes.fromhex(key.public_key_hex)),
                ),
            )
            require(
                type(registry) is dict
                and set(registry)
                == {
                    "issuer",
                    "kid",
                    "public_key_sha256",
                    "revoked",
                    "observed_at",
                    "custody_review_sha256",
                }
                and registry
                == dict(
                    issuer=key.issuer,
                    kid=key.kid,
                    public_key_sha256=sha(bytes.fromhex(key.public_key_hex)),
                    revoked=False,
                    observed_at=registry.get("observed_at"),
                    custody_review_sha256=key.custody_review_sha256,
                )
                and type(registry.get("observed_at")) is int
                and abs(int(time.time()) - registry["observed_at"]) <= 1,
                "A42361_REGISTRY_UNTRUSTED",
            )
            binary = checked_executable(config.openssl_path, config.openssl_sha256)
            Ed25519Verifier(binary, config.openssl_version).verify_signature(
                bytes.fromhex(key.public_key_hex), raw, signature
            )
            approval = checked(
                Approval,
                LocalService(self.deployment, "approval").call(
                    "approval", dict(approval_id=payload.approval_id)
                ),
            )
            require(
                approval.approval_id == payload.approval_id
                and approval.payload_sha256 == sha(raw)
                and approval.binding == expected
                and approval.limits == payload.limits
                and approval.status == "APPROVED"
                and approval.audit_object_sha256 == payload.audit_object_sha256
                and len(set(approval.approver_sha256)) == 2
                and approval.issuer_subject_sha256 not in approval.approver_sha256
                and abs(now - approval.observed_at) <= 1
                and now < approval.expires_at,
                "A42361_APPROVAL_REJECTED",
            )
            require(
                0 <= time.monotonic_ns() - started <= 1_000_000_000
                and abs(int(time.time()) - now) <= 1,
                "A42361_TRUSTED_CLOCK_UNAVAILABLE",
            )
            return VerifiedGrant(
                payload, sha(raw), approval, sha(canonical(registry)), now, _VERIFIED
            )
        except Fault:
            raise
        except Exception:
            raise Fault("A42361_GRANT_REJECTED") from None
