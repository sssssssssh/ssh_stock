"""Offline blocked-preparation guard. No database connection or execution approval path."""

import hashlib
import importlib.metadata
import ipaddress
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from scripts.a4233_observation_contract import Hash, Strict, digest, seal, write_new
from scripts.a4234_calibration_contract import (
    BASELINE,
    INPUT,
    MANIFEST,
    MANIFEST_SHA,
    PROTOCOL,
    PROTOCOL_SHA,
    SOURCES,
    Fault,
    Identity,
    Safety,
    file_sha,
    load,
    prepared_readiness,
    require,
)

ROOT = Path(__file__).resolve().parents[1]


class PhysicalProof(Strict):
    container_sha256: Hash
    host: str
    port: Annotated[int, Field(strict=True, ge=1, le=65535)]
    database: Annotated[str, Field(pattern=r'^v14_[0-9a-f]{32}_test$')]
    owned_nonce: Annotated[str, Field(pattern=r'^[0-9a-f]{32}$')]
    created_by_current_harness: Literal[True]
    before_ddl: Literal[True]
    pg_major: Literal[17]
    expected_marker: str
    observed_marker: str
    expected_system_id: Annotated[str, Field(pattern=r'^[0-9]{1,20}$')]
    observed_system_id: Annotated[str, Field(pattern=r'^[0-9]{1,20}$')]


class Privileges(Strict):
    superuser: Literal[False]
    can_create_role: Literal[False]
    can_create_database: Literal[False]
    can_bypass_rls: Literal[False]
    can_replication: Literal[False]
    can_dml: Literal[False]
    can_ddl: Literal[False]
    can_maintain: Literal[False]
    can_signal_other_backend: Literal[False]
    can_read_business_rows: Literal[False]
    readonly: Literal[True]
    autocommit: Literal[True]
    read_all_stats: Literal[True]
    control_system_execute: Literal[True]
    sql_timeout_ms: Literal[100]
    max_rows_per_view: Literal[128]
    sql_allowlist_sha256: Hash
    columns_allowlist_sha256: Hash


class Preflight(Safety):
    schema_version: Literal['a4234.preflight-simulation.v1'] = 'a4234.preflight-simulation.v1'
    identity: Identity
    head_sha: str
    origin_master_sha: str
    target_sha: str
    clean_tree: bool
    python_major_minor: Literal['3.12']
    dependencies_verified: Literal[True]
    physical: PhysicalProof
    privileges: Privileges
    event: Literal['SIMULATED_CONTRACT']
    profile: None = None
    token: None = None
    environment_approval: Literal['NOT_AUTHORIZED'] = 'NOT_AUTHORIZED'


def definitions(root=ROOT):
    root = Path(root)
    require(file_sha(root / PROTOCOL) == PROTOCOL_SHA, 'A4234_PROTOCOL_CHANGED')
    require(file_sha(root / MANIFEST) == MANIFEST_SHA, 'A4234_MANIFEST_CHANGED')
    manifest = load(root / MANIFEST)
    require(file_sha(root / INPUT) == manifest['input_file_sha256'], 'A4234_INPUT_CHANGED')
    keys = load(root / INPUT)
    expected = [dict(trade_date=d, ts_code=f'S{i:06d}.SZ') for d in
                ('2026-01-11', '2026-01-21') for i in range(1, 1001)]
    require(keys == expected and len(keys) == 2000 and
        hashlib.sha256(json.dumps(keys, sort_keys=True).encode()).hexdigest()
            == manifest['input_key_sha256'], 'A4234_INPUT_CHANGED')
    from scripts.business_source_contract import versioned_frozen_files

    for name, sha in versioned_frozen_files(root, manifest['source_files']).items():
        require(file_sha(root / name) == sha, 'A4234_FROZEN_SOURCE_CHANGED')
    return manifest


def source_sha(root=ROOT):
    return digest({p: file_sha(Path(root) / p) for p in SOURCES})


def audit(value, expected, root=ROOT):
    """SIMULATED typed checks only. `expected` is independent harness context.

    Even mutually matching fake physical claims cannot establish a live fixture or
    authorize execution. An otherwise valid simulation always returns BLOCKED.
    """
    from scripts.a4233_background_observer import FIELDS, SQL

    try:
        manifest = definitions(root)
        proof = Preflight.model_validate(value)
        require(proof.identity == expected, 'A4234_IDENTITY_MISMATCH')
        require(expected.protocol_sha256 == PROTOCOL_SHA, 'A4234_PROTOCOL_CHANGED')
        require(expected.fixture_sha256 == MANIFEST_SHA
            and expected.model_sha256 == manifest['model_tree_sha256']
            and expected.input_sha256 == manifest['input_key_sha256']
            and expected.dependency_sha256 == manifest['source_files']['requirements.lock']
            and expected.source_sha256 == source_sha(root), 'A4234_DEFINITION_MISMATCH')
        require(re.fullmatch(r'[0-9a-f]{40}', proof.target_sha) is not None
            and proof.head_sha == proof.origin_master_sha == proof.target_sha == expected.head_sha,
            'A4234_HEAD_MISMATCH')
        require(proof.clean_tree, 'A4234_DIRTY_TREE')
        physical = proof.physical
        require(ipaddress.ip_address(physical.host).is_loopback, 'A4234_NON_LOOPBACK')
        UUID(physical.expected_marker)
        require(physical.database == 'v14_' + physical.owned_nonce + '_test'
            and physical.container_sha256 == expected.container_sha256
            and physical.expected_marker == physical.observed_marker
            and physical.expected_system_id == physical.observed_system_id
            and expected.instance_identity_sha256 == digest(
                [physical.expected_marker, physical.expected_system_id]), 'A4234_PHYSICAL_MISMATCH')
        role = proof.privileges
        require(role.sql_allowlist_sha256 == digest(SQL)
            and role.columns_allowlist_sha256 == digest(FIELDS), 'A4234_ALLOWLIST_CHANGED')
        return dict(prepared_readiness(), scope='SIMULATED_PREFLIGHT_ONLY')
    except Fault:
        raise
    except Exception:
        raise Fault('A4234_PREFLIGHT_INVALID') from None


def git(root, *args, binary=False):
    try:
        result = subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.DEVNULL)
        return result if binary else result.decode().strip()
    except Exception:
        raise Fault('A4234_GIT_CHECK_FAILED') from None


def check_repository(root, target):
    """Local Git/file/dependency reads only; never fetches origin or reads .env."""
    root = Path(root)
    manifest = definitions(root)
    require(re.fullmatch(r'[0-9a-f]{40}', target or '') is not None, 'A4234_FULL_SHA_REQUIRED')
    require(git(root, 'rev-parse', 'HEAD') == git(root, 'rev-parse', 'origin/master') == target,
            'A4234_HEAD_MISMATCH')
    require(not git(root, 'status', '--porcelain'), 'A4234_DIRTY_TREE')
    require(sys.version_info[:2] == (3, 12), 'A4234_PYTHON_CHANGED')
    try:
        for line in (root / 'requirements.lock').read_text().splitlines():
            name, version = line.split('==')
            require(importlib.metadata.version(name.split('[')[0]) == version,
                    'A4234_DEPENDENCY_CHANGED')
    except Fault:
        raise
    except Exception:
        raise Fault('A4234_DEPENDENCY_CHANGED') from None
    for name in SOURCES:
        require(git(root, 'show', 'HEAD:' + name, binary=True) == (root / name).read_bytes(),
                'A4234_SOURCE_CHANGED')
    tree = git(root, 'ls-tree', '-r', 'HEAD', 'backend/app/models', 'migrations', 'config',
               binary=True)
    require(hashlib.sha256(tree).hexdigest() == manifest['model_tree_sha256'],
            'A4234_MODEL_CHANGED')
    paths = git(root, 'diff', '--name-only', BASELINE, '--', 'backend', 'config', 'migrations',
        'frontend', 'scripts', 'docs/acceptance/evidence',
        '.github/actions/a4-governance').splitlines()
    require(set(paths) <= set(SOURCES), 'A4234_FROZEN_SOURCE_CHANGED')
    return dict(prepared_readiness(), target_sha=target, protocol_sha256=PROTOCOL_SHA,
        source_sha256=source_sha(root), fixture_sha256=MANIFEST_SHA,
        model_sha256=manifest['model_tree_sha256'], scope='LOCAL_REPOSITORY_ONLY')


def execute(*args, **kwargs):
    # No callback/subprocess/database implementation, even with forged approvals.
    raise Fault('A4234_EXECUTION_NOT_AUTHORIZED')


def test_receipt(source, root=ROOT):
    """Safe unit counts only, not a calibration sample bundle or execution receipt."""
    from scripts.a42331_ci_evidence import sanitize_junit

    value = dict(**Safety().model_dump(), schema_version='a4234.unit-tests.v1',
        status='INCOMPLETE_CONTRACT', preparation=prepared_readiness(), counts=None,
        first_failure_code=None, physical_verified=False, calibration_run='NOT_RUN_NOT_AUTHORIZED')
    try:
        definitions(root)
        head = git(root, 'rev-parse', 'HEAD')
        run = os.environ.get('GITHUB_RUN_ID', 'local')
        attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '1')
        require(re.fullmatch(r'[0-9a-f]{40}', head) is not None
            and os.environ.get('GITHUB_SHA', head) == head
            and re.fullmatch(r'(local|[0-9]{1,24})', run) is not None
            and re.fullmatch(r'[1-9][0-9]{0,5}', attempt) is not None, 'A4234_CI_IDENTITY_INVALID')
        value.update(head_sha=head, run_id=run, attempt=int(attempt), protocol_sha256=PROTOCOL_SHA,
            source_sha256=source_sha(root), manifest_sha256=MANIFEST_SHA)
        counts = sanitize_junit(source)['counts']
        value['counts'] = counts
        if counts['tests'] > 0 and counts['failures'] == counts['errors'] == counts['skipped'] == 0:
            value['status'] = 'COMPLETE_CONTRACT'
        else:
            value['first_failure_code'] = 'A4234_UNIT_TESTS_INCOMPLETE'
    except Exception:
        value['first_failure_code'] = 'A4234_UNIT_EVIDENCE_INVALID'
    return seal(value)


def main(argv=None):
    # Deliberately no permissive parser: never echo unknown args (possibly secrets).
    args = sys.argv[1:] if argv is None else list(argv)
    try:
        if len(args) == 3 and args[:2] == ['--check', '--target-sha']:
            value = check_repository(ROOT, args[2])
            print(json.dumps(value, sort_keys=True, allow_nan=False))
            return 1  # Even a valid preparation check fails closed at the warmup blocker.
        if len(args) == 4 and args[0] == '--tests' and args[2] == '--output':
            value = test_receipt(Path(args[1]))
            write_new(Path(args[3]), value)
            return 0 if value['status'] == 'COMPLETE_CONTRACT' else 1
        raise Fault('A4234_EXECUTION_NOT_AUTHORIZED')
    except BaseException as error:
        code = error.code if isinstance(error, Fault) else 'A4234_GUARD_FAILED'
        print(json.dumps(dict(**Safety().model_dump(), status='INCOMPLETE',
                              first_failure_code=code)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
