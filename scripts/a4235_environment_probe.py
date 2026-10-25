"""Independent statistics/plan/maintenance projections, never SQL or MVCC-based inference."""

from typing import Annotated, Literal

from pydantic import Field

from scripts.a4235_calibration_adapter_contract import Hash, Positive, Strict, require

TABLES = ('data_publication_row', 'signal_forward_eval',
          'stock_opportunity_daily', 'stock_trade_status_daily')


class Relation(Strict):
    name: Literal['data_publication_row', 'signal_forward_eval',
                  'stock_opportunity_daily', 'stock_trade_status_daily']
    oid: Positive
    statistics_sha256: Hash
    indexes_sha256: Hash
    columns_sha256: Hash


class Environment(Strict):
    relations: Annotated[list[Relation], Field(min_length=4, max_length=4)]
    instance_sha256: Hash
    schema_sha256: Hash
    data_snapshot_sha256: Hash
    mvcc_snapshot_sha256: Hash
    settings_sha256: Hash
    model_sha256: Hash
    sql_sha256: Hash
    fresh_plan_sha256: Hash
    cached_plan_sha256: None = None
    cached_plan_status: Literal['CACHED_PLAN_STRUCTURE_NOT_VERIFIED'] = (
        'CACHED_PLAN_STRUCTURE_NOT_VERIFIED')
    plan_mode: Literal['CUSTOM', 'GENERIC']
    autovacuum_certain: Literal[True]
    backend_lifecycle_sha256: Hash
    evidence_kind: Literal['MOCK_ONLY'] = 'MOCK_ONLY'


def compare(before: Environment, after: Environment,
            events: list[str]) -> dict:
    before = Environment.model_validate(before.model_dump())
    after = Environment.model_validate(after.model_dump())
    require(tuple(r.name for r in before.relations) == TABLES
            and tuple(r.name for r in after.relations) == TABLES, 'A4235_RELATION_SET_INVALID')
    require(len({r.oid for r in before.relations}) == 4, 'A4235_RELATION_SET_INVALID')
    # A NOT_OBSERVED record can never be upgraded to evidence of absence.
    require(events == ['NOT_OBSERVED'], 'A4235_BACKGROUND_ACTIVITY_UNCERTAIN')
    require(before == after, 'A4235_ENVIRONMENT_DRIFT')
    return dict(evidence_kind='MOCK_ONLY', statistics_comparison='MOCK_EQUAL',
                absence_proven=False, real_status='NOT_PROVEN',
                cached_plan_structure='CACHED_PLAN_STRUCTURE_NOT_VERIFIED')
