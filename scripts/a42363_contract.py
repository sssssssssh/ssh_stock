"""A42363 closed envelopes. Importing this module grants no capabilities."""

import re
from typing import Literal

from scripts.a4235_calibration_adapter_contract import Hash, Strict
from scripts.a42361_contract import Fault as PreviousFault
from scripts.a42361_contract import Positive, canonical, checked, decode, sha
from scripts.a42362_contract import Lookup, Scope

DOMAINS = (
    "registry",
    "approval",
    "consumer",
    "pg_owner",
    "controller",
    "supervisor",
    "absence_auditor",
)


class Fault(PreviousFault):
    def __init__(self, code):
        self.code = (
            code if re.fullmatch(r"A42363_[A-Z0-9_]{1,80}", code or "") else "A42363_INTERNAL"
        )
        RuntimeError.__init__(self, self.code)


def require(value, code):
    if not value:
        raise Fault("A42363_" + code)


def scope_hash(scope):
    return sha(canonical(checked(Scope, scope).model_dump()))


class Receipt(Strict):
    schema_version: Literal["a42363.receipt.v1"] = "a42363.receipt.v1"
    domain: Literal[
        "registry",
        "approval",
        "consumer",
        "pg_owner",
        "controller",
        "supervisor",
        "absence_auditor",
    ]
    scope_sha256: Hash
    epoch: str
    event: str
    sequence: Positive
    record: dict
    digest: Hash
    committed: Literal[True] = True
    qualifies: Literal[False] = False


def receipt(domain, scope, event, sequence, record):
    scope = checked(Scope, scope)
    record = decode(canonical(record))  # Same JSON types before/after a real JSONB/IPC round trip.
    body = dict(
        domain=domain,
        scope_sha256=scope_hash(scope),
        epoch=scope.epoch,
        event=event,
        sequence=sequence,
        record=record,
    )
    return Receipt(**body, digest=sha(canonical(body)))


def verify_receipt(raw, domain, scope, event=None):
    r = checked(Receipt, raw)
    require(r == receipt(domain, scope, r.event, r.sequence, r.record), "RECEIPT_BINDING")
    require(event is None or r.event == event, "RECEIPT_EVENT")
    return r


class State(Strict):
    source_status: Literal["PARTIAL_SOURCE_BLOCKED", "SOURCE_IMPLEMENTED_EXCEPT_METHOD_BLOCKED"] = (
        "PARTIAL_SOURCE_BLOCKED"
    )
    offline_level: Literal["L0_L1_ONLY"] = "L0_L1_ONLY"
    method_decision: Literal["METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION"] = (
        "METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION"
    )
    trust_deployment: Literal["NOT_CONFIGURED"] = "NOT_CONFIGURED"
    g1_physical: Literal["NOT_RUN_NOT_AUTHORIZED"] = "NOT_RUN_NOT_AUTHORIZED"
    real_probe_sql_executed: Literal[0] = 0
    effective_warmups_total: Literal[8] = 8
    g2: Literal["PENDING"] = "PENDING"
    g3: Literal["NOT_AUTHORIZED"] = "NOT_AUTHORIZED"
    production_read_authorized: Literal[False] = False
    performance_eligible: Literal[False] = False
    capacity_ready: Literal[False] = False
    attribution_authorized: Literal[False] = False
    unique_repair_candidate: None = None


def lookup(body):
    return checked(Lookup, body).scope


def session_method():
    # No runtime flag, env override, mock approval or seventeenth query.
    raise Fault("A42363_METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION")
