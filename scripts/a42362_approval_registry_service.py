"""A-domain external-signature imports and fresh immutable registry/approval reads."""

import base64
import os
import time
from typing import Annotated, Literal

from pydantic import Field

from scripts.a4235_calibration_adapter_contract import Hash, Strict
from scripts.a42361_contract import Approval, canonical, checked, decode, sha
from scripts.a42362_contract import Fault, require


class ImportRequest(Strict):
    kind: Literal["APPROVAL", "KEY_STATUS", "REVOCATION"]
    record_hex: Annotated[str, Field(pattern=r"^(?:[0-9a-f]{2})+$", max_length=50000)]
    signature_base64: Annotated[str, Field(max_length=128)]


class KeyLookup(Strict):
    issuer: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,62}$")]
    kid: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,62}$")]
    public_key_sha256: Hash


class ApprovalLookup(Strict):
    approval_id: Annotated[str, Field(pattern=r"^[0-9a-f-]{36}$")]


class ReceiptLookup(Strict):
    receipt_sha256: Hash


class KeyStatus(KeyLookup):
    revoked: bool
    custody_review_sha256: Hash
    revision: Annotated[int, Field(strict=True, gt=0)]
    expires_at: Annotated[int, Field(strict=True, gt=0)]


class Revocation(Strict):
    approval_id: Annotated[str, Field(pattern=r"^[0-9a-f-]{36}$")]
    payload_sha256: Hash
    reason_sha256: Hash
    revision: Annotated[int, Field(strict=True, gt=0)]
    expires_at: Annotated[int, Field(strict=True, gt=0)]


class ApprovalRegistryService:
    """Does not issue or sign grants. Only independently signed admin facts are imported."""

    def __init__(self, installation=None, repository=None):
        self.installation, self.repository = installation, repository

    def dispatch(self, peer_uid, method, body):
        from scripts.a42362_service_host import installation

        config = installation(self.installation)
        require(
            config.domain in ("registry", "approval") and os.getuid() == config.uid,
            "A42362_SERVICE_IDENTITY_MISMATCH",
        )
        read_uids = config.read_uids
        if method == "import":
            require(peer_uid == config.operator_uid, "A42362_PEER_REJECTED")
            return self.import_record(body)
        require(peer_uid in read_uids, "A42362_PEER_REJECTED")
        require(self.repository is not None, "A42362_APPROVAL_SERVICE_NOT_CONFIGURED")
        if config.domain == "registry" and method == "key-status":
            q = checked(KeyLookup, body)
            row = self.repository.read(
                "SELECT canonical_record FROM g1_control.registry_events "
                "WHERE issuer=%s AND kid=%s AND key_sha256=%s ORDER BY revision DESC LIMIT 1",
                (q.issuer, q.kid, q.public_key_sha256),
            )
            require(row is not None, "A42362_UNKNOWN_KEY")
            value = checked(KeyStatus, row[0])
            require(value.expires_at > int(time.time()), "A42362_REGISTRY_EXPIRED")
            return dict(
                **q.model_dump(),
                revoked=value.revoked,
                observed_at=int(time.time()),
                custody_review_sha256=value.custody_review_sha256,
            )
        if config.domain == "approval" and method == "approval":
            q = checked(ApprovalLookup, body)
            row = self.repository.read(
                "SELECT canonical_record,EXISTS(SELECT 1 FROM g1_control.approval_revocations r "
                "WHERE r.approval_id=a.approval_id) FROM g1_control.approval_records a "
                "WHERE a.approval_id=%s::uuid",
                (q.approval_id,),
            )
            require(row is not None, "A42362_APPROVAL_NOT_FOUND")
            approval = checked(Approval, row[0]).model_dump()
            approval.update(observed_at=int(time.time()))
            if row[1]:
                approval["status"] = "REVOKED"
            return approval
        if method == "receipt":
            q = checked(ReceiptLookup, body)
            row = self.repository.read(
                "SELECT canonical_record FROM g1_control.external_imports WHERE receipt_sha256=%s",
                (q.receipt_sha256,),
            )
            require(row is not None, "A42362_APPROVAL_RECEIPT_MISSING")
            return row[0]
        raise Fault("A42362_METHOD_REJECTED")

    def import_record(self, body):
        from scripts.a42362_service_host import installation

        config = installation(self.installation)
        q = checked(ImportRequest, body)
        require(
            config.attestation_public_key_hex is not None and self.repository is not None,
            "A42362_APPROVAL_SERVICE_NOT_CONFIGURED",
        )
        from scripts.a42361_deployment import checked_executable
        from scripts.a42361_trust_verifier import Ed25519Verifier

        raw = bytes.fromhex(q.record_hex)
        record = decode(raw)
        value = checked(
            {"APPROVAL": Approval, "KEY_STATUS": KeyStatus, "REVOCATION": Revocation}[q.kind],
            record,
        )
        signature = base64.b64decode(q.signature_base64, validate=True)
        require(
            len(signature) == 64 and base64.b64encode(signature).decode() == q.signature_base64,
            "A42362_SIGNATURE_REJECTED",
        )
        # Domain-separation prevents signing an unrelated grant as an admin import.
        executable = checked_executable(config.openssl_path, config.openssl_sha256)
        Ed25519Verifier(executable, config.openssl_version).verify_signature(
            bytes.fromhex(config.attestation_public_key_hex),
            canonical(dict(kind=q.kind, record=record, purpose="EXTERNAL_ADMIN_IMPORT_ONLY")),
            signature,
        )
        require(value.expires_at > int(time.time()), "A42362_APPROVAL_EXPIRED")
        if q.kind == "APPROVAL":
            require(
                value.status == "APPROVED"
                and len(set(value.approver_sha256)) == 2
                and value.issuer_subject_sha256 not in value.approver_sha256,
                "A42362_TWO_INDEPENDENT_APPROVERS_REQUIRED",
            )
        digest = sha(canonical(q.model_dump()))
        # The fixed SQL function takes locks shared with B before append; no self approval.
        self.repository.write_import(q.kind, value.model_dump(), digest)
        fresh = self.repository.read(
            "SELECT canonical_record FROM g1_control.external_imports WHERE receipt_sha256=%s",
            (digest,),
        )
        require(
            fresh is not None and fresh[0] == value.model_dump(),
            "A42362_IMPORT_COMMIT_UNKNOWN_NO_RETRY",
        )
        return dict(receipt_sha256=digest, committed=True, execution_authorized=False)
