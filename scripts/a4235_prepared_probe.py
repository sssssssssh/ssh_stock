"""Pure fake-cursor detector. Synthetic SQL cannot prove C0/C1 cached plans."""

import hashlib
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field

from scripts.a4235_calibration_adapter_contract import (
    Counter,
    Hash,
    Positive,
    Strict,
    digest,
    require,
)

SYNTHETIC_SQL = (b'SELECT $1::integer', b'SELECT $1::bigint + 1')
PROJECTION_SQL = (
    'SELECT name, parameter_types::oid[], from_sql, generic_plans, custom_plans '
    'FROM pg_prepared_statements ORDER BY name LIMIT 8')
ALLOWLIST_SHA = digest([*[s.decode() for s in SYNTHETIC_SQL], PROJECTION_SQL])


class Session(Strict):
    backend_pid: Positive
    backend_start_sha256: Hash
    connection_generation: Positive
    process_sha256: Hash
    connection_sha256: Hash
    pool_checkout_generation: Literal[0] = 0
    transaction_pool: Literal[False] = False
    driver_version: Literal['3.3.4'] = '3.3.4'
    prepare_threshold: Literal[5] = 5
    prepared_max: Literal[100] = 100


class PreparedRow(Strict):
    identifier_sha256: Hash
    sql_sha256: Hash
    oid_digest: Hash
    from_sql: Literal[False]
    generic_plans: Counter
    custom_plans: Counter


class PreparedSnapshot(Strict):
    session: Session
    sql_sha256: Hash
    parameter_oids: Annotated[list[Positive], Field(min_length=1, max_length=8)]
    cache_key_sha256: Hash
    executions: Counter
    mode: Literal['UNPREPARED', 'CUSTOM', 'GENERIC', 'UNKNOWN']
    row: PreparedRow | None
    evicted: Literal[False] = False
    phase: Literal['UNTIMED_PRESET'] = 'UNTIMED_PRESET'
    projection_wall_ns: Positive
    evidence_kind: Literal['MOCK_ONLY'] = 'MOCK_ONLY'


class PreparedCapability(Strict):
    schema_version: Literal['a4235.prepared.v1'] = 'a4235.prepared.v1'
    evidence_kind: Literal['MOCK_ONLY'] = 'MOCK_ONLY'
    scope: Literal['SYNTHETIC_SQL_ONLY'] = 'SYNTHETIC_SQL_ONLY'
    detector: Literal['DRIVER_MODEL_ONLY'] = 'DRIVER_MODEL_ONLY'
    real_status: Literal['REAL_NOT_PROVEN'] = 'REAL_NOT_PROVEN'
    c0_c1_status: Literal['C0_C1_NOT_PROVEN'] = 'C0_C1_NOT_PROVEN'
    cached_plan_structure: Literal['CACHED_PLAN_STRUCTURE_NOT_VERIFIED'] = (
        'CACHED_PLAN_STRUCTURE_NOT_VERIFIED')
    prepared_stable: Literal[False] = False
    projection_is_zero_overhead: Literal[False] = False
    snapshot_sha256: Hash


@dataclass(frozen=True)
class FakeCursor:
    session: Session
    rows: tuple[PreparedRow, ...]


def project_mock(cursor: FakeCursor, expected: Session) -> tuple[PreparedRow, ...]:
    require(type(cursor) is FakeCursor, 'A4235_REAL_CURSOR_NOT_AUTHORIZED')
    require(cursor.session == expected and len(cursor.rows) <= 8, 'A4235_SESSION_CHANGED')
    rows = tuple(PreparedRow.model_validate(r.model_dump()) for r in cursor.rows)
    require(len({r.identifier_sha256 for r in rows}) == len(rows), 'A4235_PREPARED_ROW_INVALID')
    return rows


def validate_snapshot(value: PreparedSnapshot, expected: Session) -> PreparedSnapshot:
    value = PreparedSnapshot.model_validate(value.model_dump())
    Session.model_validate(expected.model_dump())
    require(value.session == expected, 'A4235_SESSION_CHANGED')
    require(value.sql_sha256 in {hashlib.sha256(s).hexdigest() for s in SYNTHETIC_SQL},
            'A4235_NON_SYNTHETIC_SQL')
    require(value.cache_key_sha256 == digest([expected.connection_sha256,
            value.sql_sha256, value.parameter_oids]), 'A4235_CACHE_KEY_MISMATCH')
    if value.executions < 6:
        require(value.row is None and value.mode == 'UNPREPARED', 'A4235_PREPARE_COUNT_INVALID')
    else:
        row = value.row
        require(row is not None and value.mode in ('CUSTOM', 'GENERIC'),
                'A4235_PREPARED_NOT_VISIBLE')
        require(row.sql_sha256 == value.sql_sha256
                and row.oid_digest == digest(value.parameter_oids)
                and row.generic_plans + row.custom_plans == value.executions - 5,
                'A4235_PREPARE_COUNT_INVALID')
        require((value.mode == 'CUSTOM' and row.generic_plans == 0 and row.custom_plans > 0)
                or (value.mode == 'GENERIC' and row.generic_plans > 0),
                'A4235_PLAN_MODE_INVALID')
    return value


def compare(before: PreparedSnapshot, after: PreparedSnapshot,
            expected: Session) -> PreparedCapability:
    before = validate_snapshot(before, expected)
    after = validate_snapshot(after, expected)
    require(before.sql_sha256 == after.sql_sha256
            and before.parameter_oids == after.parameter_oids
            and before.cache_key_sha256 == after.cache_key_sha256,
            'A4235_CACHE_KEY_MISMATCH')
    require(before.row is not None and after.row is not None
            and before.row.identifier_sha256 == after.row.identifier_sha256
            and before.mode == after.mode and after.executions > before.executions,
            'A4235_PREPARED_CONTINUITY_LOST')
    require(after.row.generic_plans >= before.row.generic_plans
            and after.row.custom_plans >= before.row.custom_plans,
            'A4235_PREPARE_COUNTER_RESET')
    return PreparedCapability(snapshot_sha256=digest([before.model_dump(), after.model_dump()]))
