"""Blocked A4234 preparation definitions, NOT a sampler or calibration reviewer."""

import hashlib
import json
import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from scripts.a4233_observation_contract import Hash, Positive, Strict, digest

BASELINE = '5215145152ae732fdba2cc5104c022eb0bed2618'
PROTOCOL = 'docs/acceptance/v14_a4_2_3_4_calibration_protocol.md'
PROTOCOL_SHA = 'b22df81e1e439a5109dc6a92c929adbfa7ac0384f1d3a1c4bd33ec4f65677b96'
MANIFEST = 'docs/acceptance/a4234_preparation_manifest.json'
MANIFEST_SHA = '4ceb7149357ac7a91a48eda1407d0d621b7ca24f256f417e8e4e8ba35052947d'
INPUT = 'docs/acceptance/a4234_input_keys.json'
SCHEDULE_SHA = '3917cd75902cc0821b900c40d247a0d5f9bb427ae9fd7b778e53fbc6b44f858c'
WARMUP_SHA = 'ce3552ec5615884d8095f89d351ad00a7e8e54c1df270d83adcfd36a95305323'
SOURCES = ('scripts/a4234_calibration_contract.py', 'scripts/a4234_calibration_guard.py')
EXECUTION_ENABLED = False
BLOCKED = 'BLOCKED_NEEDS_SPEC_OR_CAPABILITY'
BLOCKER = 'A4234_PREPARED_WARMUP_BUDGET_INSUFFICIENT'


class Fault(RuntimeError):
    def __init__(self, code):
        self.code = code if re.fullmatch(r'A4234_[A-Z0-9_]{1,80}', code) else 'A4234_INTERNAL'
        super().__init__(self.code)


def require(value, code):
    if not value:
        raise Fault(code)


class Safety(Strict):
    evidence_kind: Literal['DIAGNOSTIC_ONLY'] = 'DIAGNOSTIC_ONLY'
    data_source: Literal['SYNTHETIC_RECEIPT_ONLY'] = 'SYNTHETIC_RECEIPT_ONLY'
    execution_enabled: Literal[False] = False
    performance_eligible: Literal[False] = False
    capacity_ready: Literal[False] = False
    production_read_authorized: Literal[False] = False
    attribution_authorized: Literal[False] = False
    unique_repair_candidate: None = None


class Identity(Strict):
    head_sha: Annotated[str, Field(pattern=r'^[0-9a-f]{40}$')]
    run_id: Annotated[str, Field(pattern=r'^(local|[0-9]{1,24})$')]
    attempt: Positive
    protocol_sha256: Hash
    source_sha256: Hash
    model_sha256: Hash
    fixture_sha256: Hash
    input_sha256: Hash
    dependency_sha256: Hash
    instance_identity_sha256: Hash
    container_sha256: Hash
    data_snapshot_sha256: Hash


class SampleIdentity(Strict):
    block: Annotated[int, Field(strict=True, ge=0, le=3)]
    variant: Literal['C0', 'C1']
    pair: Annotated[int, Field(strict=True, ge=0, le=7)]
    mode: Literal['OFF', 'ON']
    position: Annotated[int, Field(strict=True, ge=0, le=127)]


def schedule():
    """Plan only: never invokes a lookup, process, observer or connection."""
    rows = []
    for block in range(4):
        for variant in (('C0', 'C1') if block % 2 == 0 else ('C1', 'C0')):
            for pair in range(8):
                for mode in (('OFF', 'ON') if (pair + block) % 2 == 0 else ('ON', 'OFF')):
                    rows.append(dict(block=block, variant=variant, pair=pair, mode=mode,
                                     position=len(rows)))
    require(digest(rows) == SCHEDULE_SHA, 'A4234_SCHEDULE_DEFINITION_CHANGED')
    return rows


def warmup_schedule():
    """User-confirmed TOTAL eight; generates definitions, not actual warmups."""
    rows = [dict(block=b, position=p, variant=(('C0', 'C1') if b % 2 == 0 else
        ('C1', 'C0'))[p], mode='OFF') for b in range(4) for p in range(2)]
    require(digest(rows) == WARMUP_SHA, 'A4234_WARMUP_DEFINITION_CHANGED')
    return rows


def prepared_readiness():
    """Static necessary-condition proof, NOT driver/PG execution or steady-state proof.

    At threshold five, preparing requires SQL execution six. Four SQL per full lookup
    cannot prepare both templates on all four fresh connections in eight total warmups.
    Sixteen is only a lower bound for preparation, not proof of generic/custom stability.
    """
    conditions, sql_per_lookup, threshold = 4 * 2, 2000 // 500, 5
    minimum_per_condition = (threshold + 1 + sql_per_lookup - 1) // sql_per_lookup
    return dict(**Safety().model_dump(), status=BLOCKED, reason=BLOCKER,
        calibration_run='NOT_RUN_NOT_AUTHORIZED', collection_status='NOT_RUN',
        calibration_decision='NOT_AUTHORIZED', warmups_total=8, warmups_per_block=2,
        independent_process_variant_conditions=conditions, warmups_per_condition=1,
        sql_executions_per_lookup=sql_per_lookup, sql_executions_per_condition=sql_per_lookup,
        prepare_threshold=threshold, first_prepared_execution=threshold + 1,
        necessary_minimum_warmups_for_preparation=conditions * minimum_per_condition,
        minimum_is_not_steady_state_proof=True, physical_verified=False,
        backend_cpu_status='METRIC_UNAVAILABLE', recorder_implemented=False,
        calibration_reviewer_implemented=False)


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'A4234_DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    try:
        p = Path(path)
        require(p.is_file() and not p.is_symlink() and p.stat().st_size <= 16_000_000,
                'A4234_ARTIFACT_INVALID')
        def invalid(value):
            raise Fault('A4234_NONFINITE_JSON')
        return json.loads(p.read_bytes(), object_pairs_hook=pairs, parse_constant=invalid)
    except Fault:
        raise
    except Exception:
        raise Fault('A4234_ARTIFACT_INVALID') from None


def file_sha(path):
    try:
        p = Path(path)
        require(p.is_file() and not p.is_symlink(), 'A4234_FILE_INVALID')
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except Fault:
        raise
    except Exception:
        raise Fault('A4234_FILE_INVALID') from None
