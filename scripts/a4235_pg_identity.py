"""Typed SIMULATED fixture/least-privilege comparison, not live attestation."""

import ipaddress
from typing import Annotated, Literal

from pydantic import Field

from scripts.a4235_calibration_adapter_contract import (
    Hash,
    Identity,
    Positive,
    Strict,
    digest,
    require,
)


class Fixture(Strict):
    host: str
    port: Annotated[int, Field(strict=True, ge=1, le=65535)]
    database: Annotated[str, Field(pattern=r'^v14_[0-9a-f]{32}_test$')]
    owner_nonce: Annotated[str, Field(pattern=r'^[0-9a-f]{32}$')]
    marker: Annotated[str, Field(pattern=r'^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$')]
    system_identifier: Annotated[str, Field(pattern=r'^[1-9][0-9]{0,19}$')]
    container_digest: Hash
    pg_major: Literal[17]
    created_this_run: Literal[True]
    cleanup_chain_verified: Literal[True]
    identity: Identity
    evidence_kind: Literal['MOCK_ONLY'] = 'MOCK_ONLY'


class Privileges(Strict):
    superuser: Literal[False] = False
    root: Literal[False] = False
    create_role: Literal[False] = False
    create_database: Literal[False] = False
    bypass_rls: Literal[False] = False
    replication: Literal[False] = False
    dml: Literal[False] = False
    ddl: Literal[False] = False
    maintain: Literal[False] = False
    signal_others: Literal[False] = False
    read_business_rows: Literal[False] = False
    inherited_dangerous_roles: Literal[False] = False
    read_all_stats: Literal[False] = False
    readonly: Literal[True] = True
    statement_timeout_ms: Literal[100] = 100
    max_rows: Literal[8] = 8


class Grant(Strict):
    """A mock of a FUTURE trusted harness grant; no signing/consumption backend installed."""

    identity: Identity
    profile: Literal['a4235-capability-only-proposed-v1']
    scope: Literal['SYNTHETIC_CAPABILITY_ONLY']
    event: Literal['workflow_dispatch']
    fixture_sha256: Hash
    allowlist_sha256: Hash
    issued_at: Positive
    expires_at: Positive
    nonce: Annotated[str, Field(pattern=r'^[0-9a-f]{32}$')]
    consumed: Literal[False]
    short_sql_budget: Literal[16]
    total_budget_ms: Literal[2000]
    signature_status: Literal['MOCK_NOT_A_SIGNATURE'] = 'MOCK_NOT_A_SIGNATURE'


def compare_fixture(observed: Fixture, independent_harness: Fixture,
                    role: Privileges) -> dict:
    # Revalidate even model_copy/model_construct inputs. Matching claims still aren't proof.
    observed = Fixture.model_validate(observed.model_dump())
    independent_harness = Fixture.model_validate(independent_harness.model_dump())
    Privileges.model_validate(role.model_dump())
    require(observed.host in ('127.0.0.1', '::1')
            and ipaddress.ip_address(observed.host).is_loopback, 'A4235_NON_LOOPBACK')
    require(observed.database == f'v14_{observed.owner_nonce}_test', 'A4235_OWNER_MISMATCH')
    require(observed == independent_harness, 'A4235_PHYSICAL_IDENTITY_MISMATCH')
    return dict(status='BLOCKED_WITH_EVIDENCE', comparison='MOCK_ONLY', physical_verified=False,
                physical_identity_sha256=digest(observed.model_dump()),
                least_privilege_sha256=digest(role.model_dump()))


def validate_mock_grant(grant: Grant, independent: Grant, now: int,
                        fixture: Fixture, allowlist_sha256: str) -> dict:
    grant = Grant.model_validate(grant.model_dump())
    independent = Grant.model_validate(independent.model_dump())
    require(grant == independent and grant.identity == fixture.identity,
            'A4235_AUTHORIZATION_IDENTITY_MISMATCH')
    require(grant.fixture_sha256 == digest(fixture.model_dump())
            and grant.allowlist_sha256 == allowlist_sha256, 'A4235_AUTHORIZATION_SCOPE_MISMATCH')
    require(type(now) is int and grant.issued_at <= now < grant.expires_at
            and 0 < grant.expires_at - grant.issued_at <= 300, 'A4235_AUTHORIZATION_EXPIRED')
    return dict(capability_probe_status='NOT_RUN_NOT_AUTHORIZED',
                signature_verified=False, persistent_consumption_verified=False,
                formal_calibration_authorization='NOT_AUTHORIZED')
