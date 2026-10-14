import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum


class PaperError(RuntimeError):
    def __init__(self, code: str, *, status_code: int = 409):
        self.code = code
        self.status_code = status_code
        super().__init__(code)


class AccountStatus(StrEnum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"


class ProposalStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class DecisionAction(StrEnum):
    WATCH = "WATCH"
    PROPOSE_BUY = "PROPOSE_BUY"
    PROPOSE_REDUCE = "PROPOSE_REDUCE"
    PROPOSE_EXIT = "PROPOSE_EXIT"


class OrderStatus(StrEnum):
    ORDER_PENDING = "ORDER_PENDING"
    FILLED = "FILLED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


ACCOUNT_TRANSITIONS = {
    "CREATED": frozenset({"ACTIVE", "PAUSED", "CLOSED"}),
    "ACTIVE": frozenset({"PAUSED", "CLOSED"}),
    "PAUSED": frozenset({"ACTIVE", "CLOSED"}),
    "CLOSED": frozenset(),
}
PROPOSAL_TRANSITIONS = {
    "DRAFT": frozenset({"PENDING_REVIEW", "EXPIRED"}),
    "PENDING_REVIEW": frozenset({"APPROVED", "REJECTED", "EXPIRED"}),
    "APPROVED": frozenset(),
    "REJECTED": frozenset(),
    "EXPIRED": frozenset(),
}
ORDER_TRANSITIONS = {
    "ORDER_PENDING": frozenset({"FILLED", "SKIPPED", "CANCELLED", "EXPIRED"}),
    "FILLED": frozenset(),
    "SKIPPED": frozenset(),
    "CANCELLED": frozenset(),
    "EXPIRED": frozenset(),
}


def require_transition(kind: str, before: str, after: str) -> None:
    transitions = {
        "account": ACCOUNT_TRANSITIONS,
        "proposal": PROPOSAL_TRANSITIONS,
        "order": ORDER_TRANSITIONS,
    }
    if after not in transitions.get(kind, {}).get(before, ()):
        raise PaperError("PAPER_INVALID_STATE_TRANSITION")


def canonical_json(value: object) -> str:
    """M17-only canonical form; historical M13-M16 hashes are not reinterpreted."""

    def normalize(item):
        if isinstance(item, Decimal):
            if not item.is_finite():
                raise PaperError("PAPER_INVALID_NUMBER", status_code=422)
            fixed = format(item, "f")
            return "0" if item == 0 else fixed.rstrip("0").rstrip(".") if "." in fixed else fixed
        if isinstance(item, float):
            raise PaperError("PAPER_FLOAT_NOT_ALLOWED", status_code=422)
        if isinstance(item, datetime):
            if item.utcoffset() is None:
                raise PaperError("PAPER_TIMEZONE_REQUIRED", status_code=422)
            return item.astimezone(UTC).isoformat()
        if isinstance(item, date):
            return item.isoformat()
        if isinstance(item, uuid.UUID):
            return str(item)
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise PaperError("PAPER_INVALID_SNAPSHOT", status_code=422)
            return {key: normalize(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        if item is None or isinstance(item, (str, int, bool)):
            return item
        raise PaperError("PAPER_INVALID_SNAPSHOT", status_code=422)

    return json.dumps(normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_id(owner_id: uuid.UUID, kind: str, business_key: str) -> uuid.UUID:
    return uuid.uuid5(owner_id, canonical_json(["m17-id-v1", kind, business_key]))


def checked_snapshot(value: dict, *, limit_bytes: int = 131072) -> tuple[dict, str]:
    if not isinstance(value.get("schema_version"), str) or not value["schema_version"]:
        raise PaperError("PAPER_SCHEMA_VERSION_REQUIRED", status_code=422)
    encoded = canonical_json(value)
    if len(encoded.encode("utf-8")) > limit_bytes:
        raise PaperError("PAPER_SNAPSHOT_TOO_LARGE", status_code=422)
    return json.loads(encoded), hashlib.sha256(encoded.encode("utf-8")).hexdigest()
