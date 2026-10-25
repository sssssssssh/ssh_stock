"""Offline G1 design contracts only. No network, database, thread or real probe API."""

from typing import Annotated, Literal

from pydantic import Field

from scripts.a4235_calibration_adapter_contract import (
    Fault,
    Hash,
    Identity,
    Safety,
    Strict,
    require,
)

UUID = Annotated[str, Field(pattern=(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'))]
CAPABILITIES = ('FIXTURE_IDENTITY', 'ROLE_PRIVILEGE', 'PREPARED_SAME_SESSION',
                'CACHED_PLAN_STRUCTURE', 'BACKEND_CPU', 'LONG_WINDOW', 'CLEANUP_AUDIT')
ALLOWLIST = ('synthetic_constant_v1', 'minimal_prepared_projection_v1')


class FixtureDesign(Strict):
    fixture_uuid: UUID
    nonce: UUID
    marker_sha256: Hash
    host: Literal['127.0.0.1', '::1', 'UNIX']
    socket_directory: str | None = None
    database: str
    owner: str
    pg_major: Literal[17] = 17
    disposable: Literal[True] = True
    existing_database: Literal[False] = False
    public_port_mapping: Literal[False] = False
    # Design claims are not observed system/container identities.
    system_identifier_status: Literal['NOT_PROVEN'] = 'NOT_PROVEN'
    container_namespace_status: Literal['NOT_PROVEN'] = 'NOT_PROVEN'
    image_digest_status: Literal['NOT_PROVEN'] = 'NOT_PROVEN'
    independent_harness_status: Literal['NOT_PROVEN'] = 'NOT_PROVEN'


class RoleDesign(Strict):
    read_only: Literal[True] = True
    superuser: Literal[False] = False
    createdb: Literal[False] = False
    createrole: Literal[False] = False
    bypassrls: Literal[False] = False
    replication: Literal[False] = False
    maintain: Literal[False] = False
    writes: Literal[False] = False
    business_read: Literal[False] = False
    pg_read_all_stats: Literal[False] = False
    visibility: Literal['NOT_PROVEN'] = 'NOT_PROVEN'


class ProposedBudget(Strict):
    max_sql: Literal[16] = 16
    total_ms: Literal[2000] = 2000
    per_sql_ms: Literal[100] = 100
    max_rows: Literal[8] = 8
    real_sql_executed: Literal[0] = 0
    effective_warmups: Literal[8] = 8
    approved: Literal[False] = False


class FutureGrantDesign(Strict):
    identity: Identity
    issuer: Literal['HUMAN_REVIEW_REQUIRED'] = 'HUMAN_REVIEW_REQUIRED'
    issued_at: Annotated[int, Field(strict=True, ge=0)]
    expires_at: Annotated[int, Field(strict=True, gt=0)]
    nonce: UUID
    scope: Literal['SYNTHETIC_CAPABILITY_ONLY'] = 'SYNTHETIC_CAPABILITY_ONLY'
    profile: Literal['G1_PROPOSED_NOT_APPROVED'] = 'G1_PROPOSED_NOT_APPROVED'
    allowlist: tuple[Literal['synthetic_constant_v1'],
                     Literal['minimal_prepared_projection_v1']] = ALLOWLIST
    signature_verifier: Literal['NOT_IMPLEMENTED'] = 'NOT_IMPLEMENTED'
    persistent_consumption: Literal['NOT_IMPLEMENTED'] = 'NOT_IMPLEMENTED'
    consumed: Literal[False] = False


class PreflightDesign(Safety):
    identity: Identity
    fixture: FixtureDesign
    role: RoleDesign = RoleDesign()
    budget: ProposedBudget = ProposedBudget()
    grant_design: FutureGrantDesign
    cached_plan_structure: Literal['CACHED_PLAN_STRUCTURE_NOT_VERIFIED'] = (
        'CACHED_PLAN_STRUCTURE_NOT_VERIFIED')
    c0_c1: Literal['NOT_PROVEN'] = 'NOT_PROVEN'
    backend_cpu_seconds: None = None
    cleanup_status: Literal['NOT_RUN_NOT_PROVEN'] = 'NOT_RUN_NOT_PROVEN'


def review_design(value: object, expected: Identity, *, now: int) -> dict:
    """Validate a proposed design. Even identical claims cannot establish physical proof."""
    try:
        design = PreflightDesign.model_validate(value)
        fixture, grant = design.fixture, design.grant_design
        require(design.identity == expected == grant.identity, 'A4235_G1_IDENTITY_MISMATCH')
        require(type(now) is int and grant.issued_at <= now < grant.expires_at
            and grant.expires_at - grant.issued_at <= 3600, 'A4235_G1_GRANT_DESIGN_INVALID')
        require(grant.nonce == fixture.nonce and fixture.nonce != fixture.fixture_uuid,
                'A4235_G1_NONCE_INVALID')
        suffix = fixture.fixture_uuid.replace('-', '')
        require(fixture.database == f'a42351_{suffix}'
            and fixture.owner == f'a42351_ro_{suffix}', 'A4235_G1_FIXTURE_DESIGN_INVALID')
        require((fixture.host == 'UNIX'
            and fixture.socket_directory == f'/run/postgresql/a42351/{fixture.fixture_uuid}')
            or (fixture.host != 'UNIX' and fixture.socket_directory is None),
            'A4235_G1_LOCAL_ENDPOINT_INVALID')
        return dict(**Safety().model_dump(), status='G1_PREFLIGHT_READY_FOR_REVIEW',
            identity=expected.model_dump(), physical_status='NOT_RUN_NOT_AUTHORIZED',
            real_sql_executed=0, cleanup_status='NOT_RUN_NOT_PROVEN',
            capabilities={name: dict(execution='NOT_RUN', proof='NOT_PROVEN')
                          for name in CAPABILITIES})
    except Fault:
        raise
    except Exception:
        raise Fault('A4235_G1_DESIGN_INVALID') from None


class TickDesign(Strict):
    started_ms: Annotated[int, Field(strict=True, ge=0)]
    wall_ms: Annotated[int, Field(strict=True, gt=0, le=25)]
    sql_ms: Annotated[int, Field(strict=True, ge=0, le=100)]
    partial: Literal[False] = False


class WindowDesign(Strict):
    lookup_started_ms: Annotated[int, Field(strict=True, ge=0)]
    lookup_finished_ms: Annotated[int, Field(strict=True, gt=0)]
    ticks: Annotated[list[TickDesign], Field(min_length=2, max_length=8)]
    stop_join_ms: Annotated[int, Field(strict=True, ge=0, le=2000)]


def review_mock_window(value: object) -> dict:
    try:
        window = WindowDesign.model_validate(value)
        start, end = window.lookup_started_ms, window.lookup_finished_ms
        require(start < end and all(t.sql_ms <= t.wall_ms for t in window.ticks),
                'A4235_G1_WINDOW_INVALID')
        require(all(b.started_ms - a.started_ms == 250
            for a, b in zip(window.ticks, window.ticks[1:], strict=False)),
            'A4235_G1_WINDOW_INVALID')
        require(any(t.started_ms + t.wall_ms < start for t in window.ticks)
            and any(start <= t.started_ms and t.started_ms + t.wall_ms <= end
                    for t in window.ticks)
            and any(t.started_ms > end for t in window.ticks), 'A4235_G1_BRACKET_UNCOVERED')
        return dict(**Safety().model_dump(), status='MODEL_ONLY_NOT_PROVEN')
    except Fault:
        raise
    except Exception:
        raise Fault('A4235_G1_WINDOW_INVALID') from None


def main(argv=None) -> int:
    # No live flags, ambient token, ordinary push or dispatch can create authority.
    import json

    print(json.dumps(dict(**Safety().model_dump(), first_error=
        'A4235_CAPABILITY_PROBE_NOT_AUTHORIZED', real_sql_executed=0), sort_keys=True))
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
