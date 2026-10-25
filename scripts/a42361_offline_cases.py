"""TEST_ONLY inert data; no signer, installed seal, database or resource operations."""

from scripts.a4235_calibration_adapter_contract import Identity
from scripts.a42361_contract import Approval, Binding, GrantPayload


def real_components():
    from scripts.a42361_fixture_controller import FixtureController
    from scripts.a42361_one_shot_store import PostgresConsumer
    from scripts.a42361_trust_verifier import TrustVerifier
    from scripts.a42361_watchdog import Watchdog

    return (TrustVerifier, PostgresConsumer, FixtureController, Watchdog)


def binding():
    return Binding(
        identity=Identity(
            head_sha="a" * 40,
            run_id="local",
            attempt=1,
            source_sha256="b" * 64,
            protocol_sha256="c" * 64,
            frozen_sha256="d" * 64,
        ),
        overlay_sha256="e" * 64,
        fixture_uuid="12345678-1234-4234-8234-123456789012",
        nonce="22345678-1234-4234-8234-123456789012",
        marker_sha256="f" * 64,
    )


def payload():
    return GrantPayload(
        binding=binding(),
        issuer="offline-issuer",
        kid="offline-key",
        token_id="32345678-1234-4234-8234-123456789012",
        approval_id="42345678-1234-4234-8234-123456789012",
        audit_object_sha256="1" * 64,
        image_digest="sha256:" + "2" * 64,
        issued_at=100,
        not_before=100,
        expires_at=200,
    )


def approval(p, payload_sha):
    return Approval(
        approval_id=p.approval_id,
        payload_sha256=payload_sha,
        binding=p.binding,
        limits=p.limits,
        status="APPROVED",
        approver_sha256=("3" * 64, "4" * 64),
        issuer_subject_sha256="5" * 64,
        audit_object_sha256=p.audit_object_sha256,
        observed_at=110,
        expires_at=200,
    )
