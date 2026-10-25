"""A4235 offline-only contracts. No DB/worker adapter or calibration entry point."""

import hashlib
import json
import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

BASELINE = '7681b57b68aa2f402e1bac2dc59ade606700f759'
ROOT = Path(__file__).resolve().parents[1]
PACKET = 'docs/acceptance/a4235_protocol_decision_packet.md'
PACKET_SHA = '84b572e71d1bc92ad58da105a8333d57e3d42b2d32db1102c234e63bbcea5c87'
Hash = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Sha = Annotated[str, Field(pattern=r'^[0-9a-f]{40}$')]
Positive = Annotated[int, Field(strict=True, gt=0)]
Counter = Annotated[int, Field(strict=True, ge=0)]
Code = Annotated[str, Field(pattern=r'^A4235_[A-Z0-9_]{1,70}$')]
Status = Literal['CAPABILITY_READY_FOR_HUMAN_REVIEW', 'CAPABILITY_PARTIAL',
                 'BLOCKED_WITH_EVIDENCE', 'NOT_RUN_NOT_AUTHORIZED']
SOURCES = tuple('scripts/a4235_' + name + '.py' for name in (
    'calibration_adapter_contract', 'pg_identity', 'capability_guard', 'prepared_probe',
    'resource_bridge', 'environment_probe', 'observer_bridge_contract', 'capability_review'))


class Fault(RuntimeError):
    def __init__(self, code: str):
        self.code = code if re.fullmatch(r'A4235_[A-Z0-9_]{1,70}', code) else 'A4235_INTERNAL'
        super().__init__(self.code)


def require(condition: object, code: str) -> None:
    if not condition:
        raise Fault(code)


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False,
                             revalidate_instances='always', frozen=True)


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


class Safety(Strict):
    execution_enabled: Literal[False] = False
    performance_eligible: Literal[False] = False
    capacity_ready: Literal[False] = False
    production_read_authorized: Literal[False] = False
    attribution_authorized: Literal[False] = False
    unique_repair_candidate: None = None
    capability_probe_status: Literal['NOT_RUN_NOT_AUTHORIZED'] = 'NOT_RUN_NOT_AUTHORIZED'
    protocol_decision_status: Literal['PENDING'] = 'PENDING'
    formal_calibration_authorization: Literal['NOT_AUTHORIZED'] = 'NOT_AUTHORIZED'


class Identity(Strict):
    head_sha: Sha
    run_id: Annotated[str, Field(pattern=r'^(local|[1-9][0-9]{0,23})$')]
    attempt: Annotated[int, Field(strict=True, ge=1, le=999999)]
    source_sha256: Hash
    protocol_sha256: Hash
    frozen_sha256: Hash


class Decisions(Safety):
    selected: Literal['C'] = 'C'
    effective_warmups_total: Literal[8] = 8
    candidate_a: Literal['PROPOSED_NOT_APPROVED'] = 'PROPOSED_NOT_APPROVED'
    candidate_b: Literal['RESEARCH_ONLY_NOT_APPROVED'] = 'RESEARCH_ONLY_NOT_APPROVED'
    candidate_c: Literal['BLOCKED'] = 'BLOCKED'
    candidate_fixed_budgets: tuple[Literal[16], Literal[32]] = (16, 32)
    automatic_escalation: Literal[False] = False
    retry_allowed: Literal[False] = False
    prepared_stable: Literal[False] = False


class Capability(Safety):
    schema_version: Literal['a4235.capability.v1'] = 'a4235.capability.v1'
    identity: Identity
    evidence_kind: Literal['STATIC_ONLY', 'MOCK_ONLY']
    status: Status = 'BLOCKED_WITH_EVIDENCE'
    implementation_status: Literal['CAPABILITY_IMPLEMENTED_NOT_YET_PROVEN'] = (
        'CAPABILITY_IMPLEMENTED_NOT_YET_PROVEN')
    physical_identity_sha256: Hash | None = None
    least_privilege_sha256: Hash | None = None
    prepared: Literal['DRIVER_MODEL_ONLY', 'C0_C1_NOT_PROVEN'] = 'C0_C1_NOT_PROVEN'
    backend_cpu: Literal['METRIC_UNAVAILABLE'] = 'METRIC_UNAVAILABLE'
    cached_plan_structure: Literal['NOT_VERIFIED'] = 'NOT_VERIFIED'


class Limitations(Strict):
    schema_version: Literal['a4235.limitations.v1'] = 'a4235.limitations.v1'
    identity: Identity
    codes: Annotated[list[Code], Field(min_length=1, max_length=32)]


class Failure(Strict):
    schema_version: Literal['a4235.failure.v1'] = 'a4235.failure.v1'
    identity: Identity
    first_error: Code | None
    cleanup_codes: Annotated[list[Code], Field(max_length=4)]
    cleanup_omitted: Counter = 0
    cleanup_complete: bool
    last_snapshot_sha256: Hash | None = None


class FileProof(Strict):
    sha256: Hash
    bytes: Annotated[int, Field(strict=True, ge=1, le=1_000_000)]


class Manifest(Strict):
    schema_version: Literal['a4235.manifest.v1'] = 'a4235.manifest.v1'
    identity: Identity
    capability: FileProof
    limitations: FileProof
    failure: FileProof


class RealAdapter:
    """No callbacks, DSN, DB imports, subprocesses or 128-point execution method."""

    def probe_synthetic(self, *args: object, **kwargs: object) -> None:
        raise Fault('A4235_CAPABILITY_PROBE_NOT_AUTHORIZED')


def record_failure(identity: Identity, first: str | None, cleanup: list[str],
                   snapshot_sha256: str | None = None) -> Failure:
    # Bounded stable safe codes, never stringify an arbitrary exception or payload.
    codes = list(dict.fromkeys(Fault(code).code for code in cleanup))
    first = first or (codes[0] if codes else None)
    return Failure(identity=identity, first_error=Fault(first).code if first else None,
                   cleanup_codes=codes[:4], cleanup_omitted=max(len(codes) - 4, 0),
                   cleanup_complete=not codes, last_snapshot_sha256=snapshot_sha256)
