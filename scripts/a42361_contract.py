"""G1 control-plane data only. A parsed payload or Git digest is never authority."""

import hashlib
import json
import re
from typing import Annotated, Literal

from pydantic import Field

from scripts.a4235_calibration_adapter_contract import Hash, Identity, Safety, Strict
from scripts.a4236_g1_harness_contract import UUID
from scripts.a4236_g1_probe import ALLOWLIST_SHA

BASELINE = "6d54841522bc013ad21a52bc45d75218de2d9ce6"
Positive = Annotated[int, Field(strict=True, gt=0)]
Count = Annotated[int, Field(strict=True, ge=0)]
Name = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,62}$")]


class Fault(RuntimeError):
    def __init__(self, code):
        self.code = (
            code if re.fullmatch(r"A42361_[A-Z0-9_]{1,70}", code or "") else "A42361_INTERNAL"
        )
        super().__init__(self.code)


def require(condition, code):
    if not condition:
        raise Fault(code)


def canonical(value):
    """Protocol v1 permits only integer/string/bool/null/array/object JSON, never floats."""

    def visit(v):
        require(
            type(v) in (dict, list, tuple, int, str, bool, type(None)), "A42361_ENCODING_INVALID"
        )
        if type(v) is dict:
            require(all(type(k) is str and k.isascii() for k in v), "A42361_ENCODING_INVALID")
            for x in v.values():
                visit(x)
        if type(v) in (tuple, list):
            for x in v:
                visit(x)
        if type(v) is str:
            require(v.isascii(), "A42361_ENCODING_INVALID")

    try:
        visit(value)
        result = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
        require(0 < len(result) <= 65536, "A42361_INPUT_TOO_LARGE")
        return result
    except Fault:
        raise
    except Exception:
        raise Fault("A42361_ENCODING_INVALID") from None


def decode(raw):
    try:
        require(type(raw) is bytes and 0 < len(raw) <= 65536, "A42361_INPUT_TOO_LARGE")

        def pairs(items):
            require(len({k for k, _ in items}) == len(items), "A42361_DUPLICATE_KEY")
            return dict(items)

        def reject(_):
            raise Fault("A42361_ENCODING_INVALID")

        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=pairs,
            parse_float=reject,
            parse_constant=reject,
        )
        require(canonical(value) == raw, "A42361_NONCANONICAL")
        return value
    except Fault:
        raise
    except Exception:
        raise Fault("A42361_ENCODING_INVALID") from None


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def checked(model, value):
    from scripts.a4236_g1_harness_contract import checked as old_checked

    try:
        if isinstance(value, Strict):
            value = old_checked(model, value).model_dump()
        result = model.model_validate_json(canonical(value))

        def unchanged(before, after):
            if type(before) is dict:
                require(type(after) is dict, "A42361_SCHEMA_INVALID")
                for key, item in before.items():
                    unchanged(item, after[key])
            elif type(before) in (list, tuple):
                require(
                    type(after) in (list, tuple) and len(before) == len(after),
                    "A42361_SCHEMA_INVALID",
                )
                for a, b in zip(before, after, strict=True):
                    unchanged(a, b)
            else:
                require(type(before) is type(after) and before == after, "A42361_SCHEMA_INVALID")

        unchanged(value, result.model_dump())
        return result
    except Exception:
        raise Fault("A42361_SCHEMA_INVALID") from None


class Limits(Strict):
    max_sql: Literal[16] = 16
    per_sql_ms: Literal[100] = 100
    sql_window_ms: Literal[2000] = 2000
    max_rows: Literal[8] = 8
    authorization_ms: Literal[1000] = 1000
    initialization_ms: Literal[2000] = 2000
    initialization_max_sql: Literal[8] = 8
    initialization_max_commands: Literal[12] = 12
    termination_ms: Literal[2000] = 2000
    cleanup_ms: Literal[2000] = 2000
    artifact_ms: Literal[2000] = 2000
    cpu_millicores: Literal[1000] = 1000
    rss_mib: Literal[512] = 512
    pids: Literal[32] = 32


class Binding(Strict):
    identity: Identity
    overlay_sha256: Hash
    allowlist_sha256: Hash = ALLOWLIST_SHA
    fixture_uuid: UUID
    nonce: UUID
    marker_sha256: Hash
    profile: Literal["G1_SYNTHETIC_CAPABILITY_ONLY"] = "G1_SYNTHETIC_CAPABILITY_ONLY"
    scope: Literal["G1_SYNTHETIC_CAPABILITY_ONLY"] = "G1_SYNTHETIC_CAPABILITY_ONLY"


class GrantPayload(Strict):
    schema_version: Literal["a42361.grant.v1"] = "a42361.grant.v1"
    binding: Binding
    audience: Literal["a42361-independent-control-plane"] = "a42361-independent-control-plane"
    issuer: Name
    kid: Name
    algorithm: Literal["Ed25519"] = "Ed25519"
    token_id: UUID
    approval_id: UUID
    audit_object_sha256: Hash
    image_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    limits: Limits = Limits()
    issued_at: Positive
    not_before: Positive
    expires_at: Positive


class Approval(Strict):
    schema_version: Literal["a42361.approval.v1"] = "a42361.approval.v1"
    approval_id: UUID
    payload_sha256: Hash
    binding: Binding
    limits: Limits
    status: Literal["APPROVED", "PENDING", "REVOKED", "DENIED"]
    approver_sha256: tuple[Hash, Hash]
    issuer_subject_sha256: Hash
    audit_object_sha256: Hash
    observed_at: Positive
    expires_at: Positive


class Receipt(Strict):
    schema_version: Literal["a42361.service-receipt.v1"] = "a42361.service-receipt.v1"
    receipt_id: UUID
    domain: Literal[
        "APPROVAL", "CONSUMER", "PG_OWNER", "CONTROLLER", "ABSENCE_AUDITOR", "SUPERVISOR"
    ]
    event: Literal[
        "APPROVED",
        "CONSUMED",
        "CREATED",
        "PROBE_FINISHED",
        "DESTROY_REQUESTED",
        "DESTROYED",
        "ABSENT",
        "TERMINATED",
    ]
    binding: Binding
    payload_sha256: Hash
    subject_sha256: Hash
    observed_ns: Positive
    body: dict
    evidence_kind: Literal["SERVICE_RECEIPT"] = "SERVICE_RECEIPT"


class Capability(Safety):
    implementation_status: Literal[
        "PARTIAL_OFFLINE_TESTED", "G1_LIVE_CHAIN_CODE_READY_PENDING_TRUST_DEPLOY"
    ] = "PARTIAL_OFFLINE_TESTED"
    g1_physical: Literal["G1_PHYSICAL_NOT_RUN"] = "G1_PHYSICAL_NOT_RUN"
    real_sql_executed: Literal[0] = 0
    g2: Literal["G2_PENDING"] = "G2_PENDING"
    warmups_total: Literal[8] = 8
    g3: Literal["G3_NOT_AUTHORIZED"] = "G3_NOT_AUTHORIZED"
    physical_tests: Literal["TRUSTED_INTEGRATION_NOT_RUN"] = "TRUSTED_INTEGRATION_NOT_RUN"


def valid_binding(value, expected):
    value, expected = checked(Binding, value), checked(Binding, expected)
    require(
        value == expected
        and value.allowlist_sha256 == ALLOWLIST_SHA
        and value.nonce != value.fixture_uuid,
        "A42361_BINDING_MISMATCH",
    )
    return value
