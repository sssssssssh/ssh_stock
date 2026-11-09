"""R1 offline protocol. References are never execution capabilities."""

import hashlib
import json
import math
import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Protocol

BASELINE = "b6ffb7bf8ec7d26f771d9b89923e4f7e926edbed"
VERSION = "r1.real-root.offline.v1"
SOURCE_HASHES_DIGEST = "ac0520222aa57db7aab7891e56dab97842fc0a551078d55625a69b9625b1f826"
FLAGS = {
    "factor_input_reuse_enabled": False,
    "factor_cpu_optimization_enabled": False,
    "raw_preflight_batch_enabled": False,
    "ab_merge_read_enabled": False,
    "worker_diagnostics_enabled": False,
}
BUDGET = {"setup": 180, "root": 180, "cleanup": 30, "outer": 390}
FIXTURE = {
    "seed": "tests.integration.test_business_recalc_performance.seed",
    "fixture_id": "R1_ORIGINAL_420_V1",
    "symbols": ["000001.SZ", "000002.SZ"],
    "history_days": 420,
    "include_closed": False,
    "start": "2026-02-23",
    "end": "2026-02-24",
    "evaluate_signals": False,
    "mode": "manual",
    "dirty_ranges": [],
    "warmup_trading_days": 250,
    "lookback_calendar_days": 430,
}
TRANSITIONS = {
    "WAITING_OWNER": {"REGISTERED", "PREFLIGHT_REJECTED", "REFUSED"},
    "REGISTERED": {"SPAWN_REQUESTED", "CLEANUP_REQUESTED"},
    "SPAWN_REQUESTED": {"SPAWN_CONFIRMED", "CLEANUP_REQUESTED"},
    "SPAWN_CONFIRMED": {"ROOT_STARTED", "CLEANUP_REQUESTED"},
    "ROOT_STARTED": {"ROOT_TERMINAL_OBSERVED", "CLEANUP_REQUESTED"},
    "ROOT_TERMINAL_OBSERVED": {"OUTPUT_FROZEN", "CLEANUP_REQUESTED"},
    "OUTPUT_FROZEN": {"CLEANUP_REQUESTED"},
    "CLEANUP_REQUESTED": {"CLEANUP_CONFIRMED", "CLEANUP_UNCERTAIN"},
    "CLEANUP_CONFIRMED": set(),
    "PREFLIGHT_REJECTED": set(),
    "REFUSED": set(),
    "INCOMPLETE": set(),
    "CLEANUP_UNCERTAIN": set(),
}


class Refused(ValueError):
    """Public exceptions carry only a bounded fixed code."""


def require(ok, code="R1_REFUSED"):
    if not ok:
        raise Refused(code)


def canonical(value):
    def walk(v, depth=0):
        require(depth <= 32, "R1_JSON_DEPTH")
        if type(v) is dict:
            require(all(type(k) is str for k in v), "R1_JSON_TYPE")
            for x in v.values():
                walk(x, depth + 1)
        elif type(v) is list:
            for x in v:
                walk(x, depth + 1)
        else:
            require(type(v) in (str, int, bool, float, type(None)), "R1_JSON_TYPE")
            require(type(v) is not float or math.isfinite(v), "R1_NONFINITE")
            if type(v) is str:
                v.encode("utf8", errors="strict")

    try:
        walk(value)
        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
        require(len(raw) <= 1048576, "R1_SIZE")
        return raw
    except (RecursionError, UnicodeError, OverflowError):
        raise Refused("R1_JSON_TYPE") from None


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def parse_json(raw):
    require(type(raw) is bytes and len(raw) <= 1048576, "R1_SIZE")

    def pairs(items):
        require(len({k for k, _ in items}) == len(items), "R1_DUPLICATE_KEY")
        return dict(items)

    def bad(_):
        raise Refused("R1_NONFINITE")

    try:
        value = json.loads(raw.decode("utf8"), object_pairs_hook=pairs, parse_constant=bad)
        canonical(value)
        return value
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, Refused):
            raise
        raise Refused("R1_INVALID_JSON") from None


def exact(actual, expected):
    require(type(actual) is type(expected), "R1_FIELD_TYPE")
    if type(expected) is dict:
        require(set(actual) == set(expected), "R1_FIELDS")
        for key in expected:
            exact(actual[key], expected[key])
    elif type(expected) is list:
        require(len(actual) == len(expected), "R1_FIELDS")
        for a, b in zip(actual, expected, strict=True):
            exact(a, b)
    else:
        require(actual == expected, "R1_FIELD_VALUE")


def label(value):
    require(
        type(value) is str and re.fullmatch("[a-z][a-z0-9-]{1,47}", value) is not None,
        "R1_REFERENCE",
    )
    return value


def request_template(source_hashes, *, arm="OFF1", pair="offline-pair"):
    return {
        "schema_version": VERSION,
        "target_sha": BASELINE,
        "protocol_sha256": digest({"version": VERSION, "budget": BUDGET, "fixture": FIXTURE}),
        "source_hashes": deepcopy(source_hashes),
        "r1_fixture": deepcopy(FIXTURE),
        "requested_arm": arm,
        "pair_id": pair,
        "attempt": 1,
        "owner_reservation_ref": "owner-reservation",
        "host_lease_ref": "host-lease",
        "pg_resource_ref": "pg-resource",
        "input_snapshot_ref": "input-snapshot",
        "process_domain_ref": "process-domain",
        "evidence_directory_label": "evidence-output",
        "flags": {**FLAGS, "perf_diagnostics_enabled": arm == "ON1"},
        "budget_seconds": dict(BUDGET),
        "evidence_kind": "OFFLINE_ONLY",
    }


def validate_request(value, source_hashes):
    canonical(value)
    require(digest(source_hashes) == SOURCE_HASHES_DIGEST, "R1_SOURCE_CONTRACT_DRIFT")
    require(type(value) is dict, "R1_FIELDS")
    arm = value.get("requested_arm")
    require(arm in ("OFF1", "ON1"), "R1_ARM")
    expected = request_template(source_hashes, arm=arm, pair=label(value.get("pair_id")))
    for key in (
        "owner_reservation_ref",
        "host_lease_ref",
        "pg_resource_ref",
        "input_snapshot_ref",
        "process_domain_ref",
        "evidence_directory_label",
    ):
        expected[key] = label(value.get(key))
    require(type(source_hashes) is dict and bool(source_hashes), "R1_SOURCE")
    for path, sha in source_hashes.items():
        require(type(path) is str and ".." not in path and ":" not in path, "R1_SOURCE")
        require(type(sha) is str and re.fullmatch("[0-9a-f]{64}", sha), "R1_SOURCE")
    exact(value, expected)
    return {"decision": "NO_GO", "evidence_kind": "OFFLINE_CONTRACT_TESTED"}


class OwnerAuthority(Protocol):
    """Only an injected offline interface; no durable/production implementation."""

    def reserve(self, binding: str) -> str: ...
    def confirm(self, binding: str, phase: str) -> str: ...
    def record_intent(self, binding: str) -> str: ...

    def confirm_handle(self, binding: str, handle: object, facts: dict) -> str: ...


@dataclass
class StateMachine:
    state: str = "WAITING_OWNER"
    first_error: str | None = None
    events: list = field(default_factory=list)
    last_time: float = -1

    def move(self, state, now):
        require(
            type(now) in (int, float) and math.isfinite(now) and now >= self.last_time, "R1_CLOCK"
        )
        require(state in TRANSITIONS.get(self.state, set()), "R1_TRANSITION")
        self.events.append((state, now))
        self.state, self.last_time = state, now

    def fail(self, code, now, *, uncertain=False):
        require(code in FAILURE_CODES, "R1_ERROR_CODE")
        if self.first_error is None:
            self.first_error = code
        self.state = "CLEANUP_UNCERTAIN" if uncertain else "INCOMPLETE"
        self.events.append((self.state, now))


FAILURE_CODES = frozenset(
    {
        "OWNER_UNKNOWN",
        "SPAWN_UNCERTAIN",
        "SETUP_TIMEOUT",
        "ROOT_TIMEOUT",
        "CLEANUP_TIMEOUT",
        "DOMAIN_MISMATCH",
        "ACK_UNKNOWN",
        "ROOT_INCOMPLETE",
        "OUTPUT_UNFROZEN",
        "OS_UNKNOWN",
        "CLEANUP_UNKNOWN",
        "FENCING_PENDING",
        "SYSCALL_UNCERTAIN",
        "REPLAY",
        "BUSINESS_ERROR",
    }
)


def real_execution_bridge(*_args, **_kwargs):
    """Closed before imports, IO, settings or owner calls; cannot be enabled by JSON."""
    raise Refused("R1_REAL_EXECUTION_NOT_AUTHORIZED")


def main(_argv=None):
    print("R1_REAL_EXECUTION_NOT_AUTHORIZED")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
