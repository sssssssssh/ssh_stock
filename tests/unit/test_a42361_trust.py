"""Real RFC8032 crypto; all approval/RPC injections remain OFFLINE_MODEL, never grants."""

import base64
import shutil
from types import SimpleNamespace as NS

import pytest

from scripts import a42361_trust_verifier as t
from scripts.a42361_contract import Fault, GrantPayload, canonical, checked, decode, sha
from scripts.a42361_deployment import validate_deployment
from scripts.a42361_offline_cases import approval, payload

PUB = bytes.fromhex("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")
SIG = bytes.fromhex(
    "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"
)


def test_AT05_real_RFC8032_test2_nonempty_vector():
    executable = shutil.which("openssl")
    assert executable is not None  # No skip or dependency fallback.
    assert t.Ed25519Verifier(executable).verify_signature(PUB, b"\x72", SIG) is None


@pytest.mark.parametrize(
    "public,message,signature",
    [
        (PUB, b"\x73", SIG),
        (b"\0" * 32, b"\x72", SIG),
        (PUB, b"\x72", SIG[:-1] + b"\x01"),
        (PUB, b"\x72", b"short"),
    ],
)
def test_AT06_real_crypto_tamper_rejected(public, message, signature):
    with pytest.raises(Fault, match="SIGNATURE_INVALID"):
        t.Ed25519Verifier(shutil.which("openssl")).verify_signature(public, message, signature)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":2}',
        b'{"a":NaN}',
        b'{"a":1.0}',
        b'{ "a":1}',
        b'{"a":Infinity}',
        b"\xff",
        b'"\\u4e2d"',
        b"{}\n",
    ],
)
def test_AT06_strict_encoding(raw):
    with pytest.raises(Fault):
        decode(raw)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("audience", "wrong"),
        ("algorithm", "HS256"),
        ("issuer", ""),
        ("kid", "UPPER"),
        ("not_before", True),
        ("unknown", 1),
    ],
)
def test_AT06_closed_schema(field, bad):
    data = payload().model_dump()
    data[field] = bad
    with pytest.raises(Fault):
        checked(GrantPayload, data)


def test_AT07_default_has_no_key_crypto_or_rpc(monkeypatch):
    monkeypatch.setattr(
        t.subprocess, "run", lambda *a, **k: pytest.fail("crypto before installation")
    )
    with pytest.raises(Fault, match="DEPLOYMENT_NOT_CONFIGURED"):
        t.TrustVerifier().verify_signature(b"{}", payload().binding)


def trust_model(monkeypatch, *, approval_change=None, registry_change=None, key_change=None):
    """Only protocol control flow; signature callback deliberately mocked, NOT AT05."""
    p = payload()
    raw = canonical(p.model_dump())
    a = approval(p, sha(raw)).model_dump()
    if approval_change:
        a.update(approval_change)
    key = NS(
        issuer=p.issuer,
        kid=p.kid,
        public_key_hex=PUB.hex(),
        revoked=False,
        valid_from=100,
        valid_until=200,
        usage="PRODUCTION_G1",
        custody_review_sha256="6" * 64,
    )
    if key_change:
        key.__dict__.update(key_change)
    config = NS(
        image="docker.io/library/postgres@" + p.image_digest,
        expires_at=200,
        keys=(key,),
        openssl_path="not-used",
        openssl_sha256="7" * 64,
        openssl_version="not-used",
    )
    monkeypatch.setattr(t, "installed", lambda _: config)
    monkeypatch.setattr(t.time, "time", lambda: 110)
    monkeypatch.setattr(t, "checked_executable", lambda *a: "not-used")
    monkeypatch.setattr(t.Ed25519Verifier, "verify_signature", lambda *a: None)
    reg = dict(
        issuer=p.issuer,
        kid=p.kid,
        public_key_sha256=sha(PUB),
        revoked=False,
        observed_at=110,
        custody_review_sha256="6" * 64,
    )
    if registry_change:
        reg.update(registry_change)
    monkeypatch.setattr(
        t.LocalService, "call", lambda self, method, body: reg if method == "key-status" else a
    )
    envelope = canonical(
        dict(payload=base64.b64encode(raw).decode(), signature=base64.b64encode(SIG).decode())
    )
    return t.TrustVerifier(object()), envelope, p.binding


@pytest.mark.parametrize(
    "change",
    [
        {"status": "PENDING"},
        {"status": "REVOKED"},
        {"approver_sha256": ["3" * 64, "3" * 64]},
        {"issuer_subject_sha256": "3" * 64},
        {"payload_sha256": "0" * 64},
        {"audit_object_sha256": "0" * 64},
        {"expires_at": 109},
    ],
)
def test_AT08_signature_alone_cannot_approve(monkeypatch, change):
    verifier, raw, b = trust_model(monkeypatch, approval_change=change)
    with pytest.raises(Fault, match="APPROVAL_REJECTED"):
        verifier.verify_signature(raw, b)


@pytest.mark.parametrize(
    "change", [{"revoked": True}, {"kid": "rotated"}, {"observed_at": 100}, {"observed_at": True}]
)
def test_AT07_revocation_rotation_clock_fail_closed(monkeypatch, change):
    verifier, raw, b = trust_model(monkeypatch, registry_change=change)
    with pytest.raises(Fault):
        verifier.verify_signature(raw, b)


def test_AT08_offline_flow_positive_is_not_installed_authority(monkeypatch):
    verifier, raw, b = trust_model(monkeypatch)
    v = verifier.verify_signature(raw, b)
    assert v.approval.status == "APPROVED"
    from scripts.a42361_deployment import installed

    with pytest.raises(Fault):
        installed(verifier.deployment)


@pytest.mark.parametrize(
    "field", ["fixture_uuid", "nonce", "marker_sha256", "overlay_sha256", "allowlist_sha256"]
)
def test_AT09_binding_drift_before_crypto(monkeypatch, field):
    verifier, raw, b = trust_model(monkeypatch)
    data = b.model_dump()
    data[field] = (
        "92345678-1234-4234-8234-123456789012" if "uuid" in field or field == "nonce" else "0" * 64
    )
    with pytest.raises(Fault):
        verifier.verify_signature(raw, data)


def deployment_data():
    endpoints = {
        name: dict(socket_name=name, peer_uid=1001 + i)
        for i, name in enumerate(
            (
                "registry",
                "approval",
                "consumer",
                "pg_owner",
                "controller",
                "absence_auditor",
                "supervisor",
            )
        )
    }
    return dict(
        root_directory="/run/a42361-offline",
        control_database="a42361_control_offline",
        control_role="g1_consumer",
        control_socket_name="control-pg",
        control_instance_sha256="a" * 64,
        openssl_path="/not-installed/openssl",
        openssl_sha256="a" * 64,
        openssl_version="OpenSSL 3.0.0",
        python_path="/not-installed/python",
        python_sha256="a" * 64,
        podman_path="/not-installed/podman",
        podman_sha256="a" * 64,
        image="docker.io/library/postgres@sha256:" + "2" * 64,
        worker_uid=1007,
        controller_uid=1005,
        socket_gid=1008,
        keys=[
            dict(
                issuer="offline",
                kid="offline",
                public_key_hex=PUB.hex(),
                usage="TEST_ONLY",
                valid_from=100,
                valid_until=200,
                revoked=False,
                custody_review_sha256="b" * 64,
            )
        ],
        test_key_sha256=[sha(PUB)],
        deployment_review_sha256="c" * 64,
        expires_at=200,
        **endpoints,
    )


@pytest.mark.parametrize("usage", ["TEST_ONLY", "PRODUCTION_G1"])
def test_AT10_test_keys_rejected_even_if_mislabeled(usage):
    data = deployment_data()
    data["keys"][0]["usage"] = usage
    with pytest.raises(Fault, match="TEST_KEY_FORBIDDEN"):
        validate_deployment(data, 110)
