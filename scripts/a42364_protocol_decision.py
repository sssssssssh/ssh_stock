"""External decisions are version-bound review artifacts, not G1 run permission."""

import base64
import binascii
from dataclasses import dataclass
from typing import Literal

from scripts.a4235_calibration_adapter_contract import Hash, Strict
from scripts.a42361_contract import Positive, canonical, checked, sha
from scripts.a42362_contract import Scope
from scripts.a42363_contract import require, scope_hash

_VERIFIED = object()
ROLES = frozenset(("OWNER", "SAFETY_PLATFORM"))
KINDS = ("BOOTSTRAP_AND_BUDGET", "SAFE_VOLUME_DISPOSAL", "TARGET_SESSION_GUC")


class CandidateDecision(Strict):
    version: Literal["a42364.external-decision.v3"] = "a42364.external-decision.v3"
    kind: Literal[
        "BOOTSTRAP_AND_BUDGET", "SAFE_VOLUME_DISPOSAL", "TARGET_SESSION_GUC", "G1_L2_EXECUTION"
    ]
    choice: Literal[
        "FRESH_DYNAMIC",
        "SINGLE_USE_PREBUILT",
        "EXCLUSIVE_STORE",
        "OWNER_DIRECTORY_V4",
        "FOUR_SLOT_V3",
        "KEEP_CLOSED",
        "EXECUTION_ONCE",
    ]
    disposition: Literal["APPROVE", "REJECT", "NEED_CHANGES"]
    scope: Scope
    proposal_sha256: Hash
    installation_sha256: Hash
    image_manifest_sha256: Hash
    issued_at: Positive
    expires_at: Positive
    decision_nonce: str


class Signature(Strict):
    role: Literal["OWNER", "SAFETY_PLATFORM"]
    kid: str
    signature_b64: str


class SignedDecision(Strict):
    payload: CandidateDecision
    signatures: tuple[Signature, Signature]


def validate_candidate(
    value, scope, proposal_sha256, installation_sha256, image_manifest_sha256, now
):
    d = checked(CandidateDecision, value)
    require(
        d.scope == scope
        and d.proposal_sha256 == proposal_sha256
        and d.installation_sha256 == installation_sha256
        and d.image_manifest_sha256 == image_manifest_sha256,
        "DECISION_BINDING",
    )
    require(
        d.issued_at <= now < d.expires_at and 0 < d.expires_at - d.issued_at <= 300,
        "DECISION_EXPIRED",
    )
    import uuid

    try:
        nonce = str(uuid.UUID(d.decision_nonce))
    except (ValueError, TypeError, AttributeError):
        require(False, "DECISION_NONCE")
    require(nonce == d.decision_nonce and d.disposition == "APPROVE", "DECISION_NOT_APPROVED")
    options = dict(
        BOOTSTRAP_AND_BUDGET={"FRESH_DYNAMIC", "SINGLE_USE_PREBUILT"},
        SAFE_VOLUME_DISPOSAL={"EXCLUSIVE_STORE", "OWNER_DIRECTORY_V4"},
        TARGET_SESSION_GUC={"FOUR_SLOT_V3", "KEEP_CLOSED"},
        G1_L2_EXECUTION={"EXECUTION_ONCE"},
    )
    require(d.choice in options[d.kind], "DECISION_VERSION_OR_CHOICE")
    # Directory replacement changes the four-resource contract and is NOT this version.
    require(
        d.choice not in ("OWNER_DIRECTORY_V4", "KEEP_CLOSED"), "DECISION_SEPARATE_PROTOCOL_REQUIRED"
    )
    return d


@dataclass(frozen=True)
class VerifiedDecision:
    payload: CandidateDecision
    digest: str
    installation: object
    _seal: object

    def require(self, kind):
        require(self._seal is _VERIFIED and self.payload.kind == kind, "EXTERNAL_DECISION_REQUIRED")
        self.installation.revalidate()
        require(self.installation.now() < self.payload.expires_at, "DECISION_EXPIRED")
        return self.payload


class DecisionVerifier:
    def __init__(self, installation=None):
        self.installation = installation

    def verify(self, envelope, *, scope, proposal_sha256, image_manifest_sha256):
        from scripts.a42364_installation_verify import installed_package

        install = installed_package(self.installation)  # No caller keys or approval booleans.
        q = checked(SignedDecision, envelope)
        d = validate_candidate(
            q.payload, scope, proposal_sha256, install.digest, image_manifest_sha256, install.now()
        )
        require({s.role for s in q.signatures} == ROLES, "DECISION_INDEPENDENT_SIGNERS")
        keys = []
        for signature in q.signatures:
            key = install.signing_key(signature.role, signature.kid)
            require(key not in keys, "DECISION_INDEPENDENT_SIGNERS")
            keys.append(key)
            try:
                raw = base64.b64decode(signature.signature_b64, validate=True)
            except (binascii.Error, ValueError):
                require(False, "DECISION_SIGNATURE")
            require(len(raw) == 64, "DECISION_SIGNATURE")
            install.verifier.verify_signature(key, canonical(d.model_dump()), raw)
        install.revalidate()  # Recheck custody/revocation/expiry after crypto before ACK.
        return VerifiedDecision(d, sha(canonical(d.model_dump())), install, _VERIFIED)


class ExecutionAuthority:
    """Manager-installed capability: all decisions PLUS separate one-shot L2 authorization.

    Constructing this class does not execute SQL, install services or authorize metrics.
    A consumer must persist CLAIMED before any irreversible effect; no automatic retry.
    """

    def __init__(self, decisions, execution, scope, journal):
        require(type(execution) is VerifiedDecision, "SEPARATE_LIVE_AUTHORIZATION_REQUIRED")
        execution.require("G1_L2_EXECUTION")
        require(set(decisions) == set(KINDS), "THREE_EXTERNAL_DECISIONS_REQUIRED")
        for kind, value in decisions.items():
            require(
                type(value) is VerifiedDecision and value.payload.scope == scope, "DECISION_BINDING"
            )
            value.require(kind)
        require(execution.payload.scope == scope, "EXECUTION_SCOPE")
        self.decisions, self.execution, self.scope, self.journal = (
            decisions,
            execution,
            scope,
            journal,
        )

    def require(self, kind):
        self.execution.require("G1_L2_EXECUTION")
        self.decisions[kind].require(kind)
        return self.decisions[kind]

    def claim(self):
        key = "LIVE_" + self.execution.payload.decision_nonce.replace("-", "")
        require(self.journal.maybe_read(self.scope, key) is None, "EXECUTION_REPLAY")
        return self.journal.append(
            self.scope,
            key,
            dict(
                scope_sha256=scope_hash(self.scope),
                execution_digest=self.execution.digest,
                qualifies=False,
            ),
        )


class RegistryChannel:
    """Held Unix peer from installed A, not a caller's revocation/approved dictionary."""

    def __init__(self, channel):
        self.channel = channel

    def verify_current(self, package, role, kid, key):
        import time

        from scripts.a42364_manager import peer_uid, read_frame, send_frame

        require(
            peer_uid(self.channel) == package.document.principals["registry"],
            "REGISTRY_PEER_IDENTITY",
        )
        self.channel.settimeout(0.2)
        send_frame(
            self.channel,
            dict(
                method="candidate-key-status-v3",
                role=role,
                kid=kid,
                public_key_sha256=sha(key),
                installation_sha256=package.digest,
            ),
        )
        raw = read_frame(self.channel, time.monotonic_ns() + 200_000_000)
        require(
            type(raw) is dict
            and set(raw)
            == {
                "role",
                "kid",
                "public_key_sha256",
                "installation_sha256",
                "epoch",
                "revoked",
                "observed_at",
            },
            "REGISTRY_STATUS",
        )
        require(
            raw["role"] == role
            and raw["kid"] == kid
            and raw["public_key_sha256"] == sha(key)
            and raw["installation_sha256"] == package.digest
            and raw["epoch"] == package.document.scope.epoch
            and raw["revoked"] is False
            and type(raw["observed_at"]) is int
            and abs(package.now() - raw["observed_at"]) <= 1,
            "REGISTRY_REVOKED_OR_STALE",
        )
