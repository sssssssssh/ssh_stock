"""Independent-service contracts; only visibly MOCK atomic transitions are executable."""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Literal

from scripts.a4235_calibration_adapter_contract import Hash, Strict, digest
from scripts.a4236_g1_harness_contract import (
    Budget,
    Context,
    Fault,
    Positive,
    checked,
    require,
)


class Grant(Strict):
    schema_version: Literal["a4236.mock-grant.v1"] = "a4236.mock-grant.v1"
    context: Context
    profile: Literal["G1_SYNTHETIC_CAPABILITY_ONLY"] = "G1_SYNTHETIC_CAPABILITY_ONLY"
    token_id_sha256: Hash
    approval_record_sha256: Hash
    issuer_sha256: Hash
    key_id_sha256: Hash
    audit_object_sha256: Hash
    allowlist_sha256: Hash
    budget: Budget = Budget()
    issued_ns: Positive
    expires_ns: Positive
    revoked: Literal[False] = False
    algorithm: Literal["MOCK_NOT_CRYPTOGRAPHIC"] = "MOCK_NOT_CRYPTOGRAPHIC"
    mock_signature_sha256: Hash


class Verification(Strict):
    context: Context
    token_id_sha256: Hash
    payload_sha256: Hash
    evidence_kind: Literal["MOCK_ONLY"] = "MOCK_ONLY"
    signature_verified: Literal[False] = False
    trust_root_status: Literal["ISSUER_NOT_CONFIGURED"] = "ISSUER_NOT_CONFIGURED"


class Consumption(Strict):
    context: Context
    token_id_sha256: Hash
    payload_sha256: Hash
    state: Literal["CONSUMED"] = "CONSUMED"
    audit_sequence: Positive
    evidence_kind: Literal["MOCK_ONLY"] = "MOCK_ONLY"
    persistent_verified: Literal[False] = False
    consumer_status: Literal["PERSISTENT_CONSUMER_UNAVAILABLE"] = "PERSISTENT_CONSUMER_UNAVAILABLE"


@dataclass(frozen=True)
class FakeIssuer:
    expected: Grant

    def verify(self, value, now_ns):
        value = checked(Grant, value)
        expected = checked(Grant, self.expected)
        require(
            type(now_ns) is int
            and value == expected
            and value.issued_ns <= now_ns < value.expires_ns,
            "A4236_GRANT_REJECTED",
        )
        require(value.expires_ns - value.issued_ns <= 3_600_000_000_000, "A4236_GRANT_REJECTED")
        # Matching a separately supplied MOCK expected object is not a signature verifier.
        return Verification(
            context=value.context,
            token_id_sha256=value.token_id_sha256,
            payload_sha256=digest(value.model_dump()),
        )


@dataclass
class FakeAtomicConsumer:
    """Explicit crash/interleaving model, NEVER a persistent consumer implementation.

    Test processes share this model's compare-and-swap state. Serialized model recovery
    is a modeled durable boundary only; no file, lockfile or database is opened here.
    """

    states: dict = field(default_factory=dict)
    sequence: int = 0

    def consume(self, verification):
        v = checked(Verification, verification)
        require(
            v.token_id_sha256 not in self.states
            and not any(r["context"]["nonce"] == v.context.nonce for r in self.states.values()),
            "A4236_GRANT_ALREADY_CONSUMED",
        )
        self.sequence += 1
        result = Consumption(
            context=v.context,
            token_id_sha256=v.token_id_sha256,
            payload_sha256=v.payload_sha256,
            audit_sequence=self.sequence,
        )
        # One indivisible modeled PENDING->CONSUMED transition, before any fixture use.
        self.states[v.token_id_sha256] = result.model_dump()
        return result

    def snapshot(self):
        return deepcopy(dict(sequence=self.sequence, states=self.states))

    @classmethod
    def recover(cls, snapshot):
        require(set(snapshot) == {"states", "sequence"}, "A4236_CONSUMER_MODEL_INVALID")
        rows = {k: checked(Consumption, v) for k, v in snapshot["states"].items()}
        require(
            type(snapshot["sequence"]) is int
            and snapshot["sequence"] == len(rows)
            and all(k == v.token_id_sha256 for k, v in rows.items())
            and len({r.context.nonce for r in rows.values()}) == len(rows)
            and sorted(v.audit_sequence for v in rows.values()) == list(range(1, len(rows) + 1)),
            "A4236_CONSUMER_MODEL_INVALID",
        )
        return cls({k: v.model_dump() for k, v in rows.items()}, snapshot["sequence"])


class IndependentVerifier:
    def verify(self, *args, **kwargs):
        raise Fault("A4236_ISSUER_NOT_CONFIGURED")


class PersistentConsumer:
    def consume(self, *args, **kwargs):
        raise Fault("A4236_PERSISTENT_CONSUMER_UNAVAILABLE")
