"""Closed, non-qualifying control-plane records. No runtime or configuration on import."""

import re
import sys
from typing import Annotated, Literal

from pydantic import Field

from scripts.a4235_calibration_adapter_contract import Hash, Strict
from scripts.a4236_g1_harness_contract import UUID
from scripts.a42361_contract import Binding, Limits, Positive, canonical, checked, sha
from scripts.a42361_contract import Fault as PreviousFault


class Fault(PreviousFault):
    def __init__(self, code):
        self.code = (
            code if re.fullmatch(r"A4236[12]_[A-Z0-9_]{1,80}", code or "") else "A42362_INTERNAL"
        )
        RuntimeError.__init__(self, self.code)


def require(condition, code):
    if not condition:
        raise Fault(code)


def file_identity(value):
    """Reads can advance atime; content/ownership/rename changes must still fail."""
    return tuple(
        getattr(value, k)
        for k in (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_uid",
            "st_gid",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
    )


def close_receipt(connection):
    """A close error cannot return a usable receipt or replace an earlier first fault."""
    first = sys.exception()
    try:
        connection.close()
    except BaseException:
        if first is None:
            raise Fault("A42362_CONNECTION_CLOSE_UNPROVEN") from None
        codes = list(getattr(first, "cleanup_codes", ()))
        if "A42362_CONNECTION_CLOSE_UNPROVEN" not in codes:
            codes.append("A42362_CONNECTION_CLOSE_UNPROVEN")
        first.cleanup_codes = codes


class Scope(Strict):
    token_id: UUID
    binding: Binding
    payload_sha256: Hash
    image_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    controller_uid: Positive
    namespace_sha256: Hash
    epoch: UUID
    limits: Limits = Limits()


Kind = Literal["SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER"]
Event = Literal[
    "RESERVED",
    "CREATE_ATTEMPTED",
    "OBSERVED_CREATED",
    "REMOVE_ATTEMPTED",
    "OBSERVED_ABSENT",
    "UNKNOWN",
]


class Resource(Strict):
    scope: Scope
    kind: Kind
    name: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,90}$")]


def resources(scope):
    scope = checked(Scope, scope)
    suffix = scope.binding.fixture_uuid.replace("-", "")
    base = "a42361-" + suffix
    return tuple(
        Resource(scope=scope, kind=k, name=n)
        for k, n in (
            ("SOCKET_DIR", suffix),
            ("VOLUME", base + "-data"),
            ("SECRET", base + "-owner-init"),
            ("CONTAINER", base),
        )
    )


def resource(value):
    value = checked(Resource, value)
    require(value in resources(value.scope), "A42362_RESOURCE_OUTSIDE_SCOPE")
    return value


class LedgerRequest(Strict):
    resource: Resource
    event: Event
    event_id: UUID
    observed_identity_sha256: Hash | None = None
    error_code: Annotated[str, Field(pattern=r"^A4236[12]_[A-Z0-9_]{1,80}$")] | None = None


class Lookup(Strict):
    scope: Scope


class LedgerReceipt(Strict):
    schema_version: Literal["a42362.ledger.v1"] = "a42362.ledger.v1"
    domain: Literal["CONSUMER"] = "CONSUMER"
    control_instance_sha256: Hash
    request: LedgerRequest
    sequence: Positive
    committed_at: str
    raw_receipt_sha256: Hash
    committed: Literal[True] = True


TRANSITIONS = {
    None: {"RESERVED"},
    "RESERVED": {"CREATE_ATTEMPTED", "UNKNOWN", "REMOVE_ATTEMPTED"},
    "CREATE_ATTEMPTED": {"OBSERVED_CREATED", "UNKNOWN", "REMOVE_ATTEMPTED"},
    "OBSERVED_CREATED": {"REMOVE_ATTEMPTED", "UNKNOWN"},
    "REMOVE_ATTEMPTED": {"OBSERVED_ABSENT", "UNKNOWN"},
    "UNKNOWN": {"REMOVE_ATTEMPTED"},
    "OBSERVED_ABSENT": set(),
}


def transition(previous, request):
    request = checked(LedgerRequest, request)
    resource(request.resource)
    require(request.event in TRANSITIONS.get(previous, set()), "A42362_LEDGER_TRANSITION_REJECTED")
    require(
        (request.observed_identity_sha256 is not None) == (request.event == "OBSERVED_CREATED"),
        "A42362_OBSERVATION_REQUIRED",
    )
    require(
        (request.error_code is not None) == (request.event == "UNKNOWN"),
        "A42362_FAILURE_FACT_REQUIRED",
    )
    return request


def receipt(request, sequence, committed_at, instance):
    body = dict(
        request=checked(LedgerRequest, request).model_dump(),
        sequence=sequence,
        committed_at=committed_at,
        control_instance_sha256=instance,
    )
    return LedgerReceipt(**body, raw_receipt_sha256=sha(canonical(body)))


def validate_receipt(value, expected):
    value = checked(LedgerReceipt, value)
    require(value.request == checked(LedgerRequest, expected), "A42362_RECEIPT_BINDING_MISMATCH")
    actual = receipt(
        value.request, value.sequence, value.committed_at, value.control_instance_sha256
    )
    require(actual == value, "A42362_RECEIPT_DIGEST_MISMATCH")
    return value


class State(Strict):
    implementation: Literal[
        "PARTIAL_OFFLINE_TESTED",
        "METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION",
        "SOURCE_CLOSED_PENDING_TRUST_DEPLOY",
    ] = "PARTIAL_OFFLINE_TESTED"
    g1_physical: Literal["NOT_RUN_NOT_AUTHORIZED"] = "NOT_RUN_NOT_AUTHORIZED"
    g2: Literal["PENDING"] = "PENDING"
    effective_warmups_total: Literal[8] = 8
    g3: Literal["NOT_AUTHORIZED"] = "NOT_AUTHORIZED"
    production_read_authorized: Literal[False] = False
    performance_eligible: Literal[False] = False
    capacity_ready: Literal[False] = False
    attribution_authorized: Literal[False] = False
    unique_repair_candidate: None = None


class FailureLedger:
    def __init__(self):
        self.first_error, self.last_incomplete, self.cleanup_codes = None, None, []

    def fail(self, code, *, cleanup=False):
        code = Fault(code).code
        if self.first_error is None:
            self.first_error = code
        self.last_incomplete = code
        if cleanup and code not in self.cleanup_codes:
            require(len(self.cleanup_codes) < 16, "A42362_FAILURE_LIMIT")
            self.cleanup_codes.append(code)
