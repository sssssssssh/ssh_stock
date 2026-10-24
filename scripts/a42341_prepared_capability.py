"""Conditional prepare arithmetic and mock same-session identity; never connects."""

from typing import Annotated, Literal

from pydantic import Field

from scripts.a42341_contract import (
    Counter,
    Hash,
    Identity,
    Positive,
    Strict,
    Timestamp,
    Variant,
    definitions,
    mock_hash,
    require,
)


class PrepareCondition(Strict):
    block: Annotated[int, Field(strict=True, ge=0, le=3)]
    variant: Variant
    process_identity: Hash
    connection_identity: Hash
    backend_pid: Positive
    backend_start: Timestamp
    sql_text_sha256: Hash
    parameter_types_sha256: Hash
    prepare_cache_key_sha256: Hash
    prepare_threshold: Literal[5] = 5
    prepared_max: Literal[100] = 100
    warmup_lookup_count: Counter
    sql_exec_count: Counter
    server_prepared_observed: bool | None
    statement_name_sha256: Hash | None
    generic_plans: Counter | None
    custom_plans: Counter | None
    pool_checkout_generation: Literal[0] = 0
    evicted: Literal[False] = False
    driver_cache_observed: bool
    source: Literal['MOCK_CONTRACT_ONLY'] = 'MOCK_CONTRACT_ONLY'
    status: Literal['LOWER_BOUND_ONLY_REAL_NOT_PROVEN'] = 'LOWER_BOUND_ONLY_REAL_NOT_PROVEN'


def condition(expected: Identity, block, variant, executions=8):
    sql = definitions()['sql_template_sha256'][variant]
    connection = mock_hash('connection', expected.head_sha, block)
    types = mock_hash('PARAMETER_OIDS_MOCK_NOT_ACTUAL', [25, 2950, 25])
    return PrepareCondition(block=block, variant=variant,
        process_identity=mock_hash('process', expected.head_sha, block),
        connection_identity=connection, backend_pid=12340 + block,
        backend_start='2026-01-01T00:00:00Z', sql_text_sha256=sql, parameter_types_sha256=types,
        prepare_cache_key_sha256=mock_hash(connection, sql, types), warmup_lookup_count=2,
        sql_exec_count=executions, server_prepared_observed=executions >= 6,
        statement_name_sha256=mock_hash('statement', connection, sql) if executions >= 6 else None,
        generic_plans=0, custom_plans=max(executions - 5, 0), driver_cache_observed=True)


def necessary_condition(value: PrepareCondition):
    # No count, including eight, is ever turned into real stability proof.
    return dict(necessary_threshold_crossed=value.sql_exec_count >= 6,
        static_same_cache_key='DECLARED_MOCK_ONLY', real_proof='NOT_PROVEN',
        prepared_stable=False, effective_warmups_total=8, proposed_warmups_total=16,
        candidate_status='LOWER_BOUND_ONLY')


def compare(before: PrepareCondition, after: PrepareCondition, expected: PrepareCondition):
    identity_fields = ('block', 'variant', 'process_identity', 'connection_identity', 'backend_pid',
        'backend_start', 'sql_text_sha256', 'parameter_types_sha256', 'prepare_cache_key_sha256',
        'prepare_threshold', 'prepared_max', 'warmup_lookup_count', 'statement_name_sha256',
        'pool_checkout_generation', 'evicted')
    require(all(getattr(before, k) == getattr(after, k) == getattr(expected, k)
                for k in identity_fields), 'A42341_PREPARE_IDENTITY_MISMATCH')
    require(before.sql_exec_count == expected.sql_exec_count,
            'A42341_PREPARED_STABILITY_NOT_PROVEN')
    for item in (before, after):
        require(item.server_prepared_observed is True and item.driver_cache_observed
            and item.generic_plans is not None and item.custom_plans is not None
            and item.sql_exec_count >= 6
            and item.generic_plans == 0 and item.custom_plans == item.sql_exec_count - 5,
            'A42341_PREPARED_STABILITY_NOT_PROVEN')
    require(after.sql_exec_count - before.sql_exec_count == 4
        and after.custom_plans - before.custom_plans == 4,
        'A42341_PREPARED_STABILITY_NOT_PROVEN')
