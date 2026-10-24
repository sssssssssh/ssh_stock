"""New proposal/source checks only; never implements either human execution approval gate."""

import importlib.metadata
import json
import os
import re
import sys
from pathlib import Path

from scripts.a4233_observation_contract import seal
from scripts.a4234_calibration_guard import git
from scripts.a42341_contract import (
    BASELINE,
    ROOT,
    SOURCES,
    Fault,
    Safety,
    definitions,
    identity,
    require,
    safe_path,
    write_new,
)


def blocked():
    return dict(**Safety().model_dump(), status='BLOCKED_NEEDS_USER_PROTOCOL_DECISION',
        effective_warmups_total=8, proposed_warmups_total=16,
        proposal_status='USER_APPROVAL_PENDING',
        prepared_evidence_status='PREPARED_STABILITY_NOT_PROVEN',
        backend_cpu_status='METRIC_UNAVAILABLE', environment_status='ENVIRONMENT_NOT_VERIFIED',
        protocol_gate='NOT_APPROVED', real_execution_gate='NOT_APPROVED')


def check_repository(root, target):
    definitions(root)
    require(re.fullmatch(r'[0-9a-f]{40}', target or '') is not None, 'A42341_FULL_SHA_REQUIRED')
    require(git(root, 'rev-parse', 'HEAD') == git(root, 'rev-parse', 'origin/master') == target,
            'A42341_PROTOCOL_OR_SOURCE_CHANGED')
    require(not git(root, 'status', '--porcelain'), 'A42341_DIRTY_TREE')
    require(sys.version_info[:2] == (3, 12), 'A42341_DEPENDENCY_CHANGED')
    try:
        for line in (Path(root) / 'requirements.lock').read_text().splitlines():
            name, version = line.split('==')
            require(importlib.metadata.version(name.split('[')[0]) == version,
                    'A42341_DEPENDENCY_CHANGED')
    except Exception:
        raise Fault('A42341_DEPENDENCY_CHANGED') from None
    for name in SOURCES:
        require(git(root, 'show', 'HEAD:' + name, binary=True) == (Path(root) / name).read_bytes(),
                'A42341_PROTOCOL_OR_SOURCE_CHANGED')
    changed = git(root, 'diff', '--name-only', BASELINE, '--', 'scripts', 'backend', 'config',
        'migrations', 'frontend', 'docs/acceptance/evidence', '.github/actions').splitlines()
    require(set(changed) <= set(SOURCES), 'A42341_FROZEN_FILE_CHANGED')
    model = git(root, 'ls-tree', '-r', 'HEAD', 'backend/app/models', 'migrations', 'config',
                binary=True)
    import hashlib

    require(hashlib.sha256(model).hexdigest() == definitions(root)['model_tree_sha256'],
            'A42341_PROTOCOL_OR_SOURCE_CHANGED')
    return dict(blocked(), identity=identity(root).model_dump())


def execute(*args, **kwargs):
    raise Fault('A42341_EXECUTION_NOT_AUTHORIZED')


def unit_receipt(source, root=ROOT):
    from scripts.a42331_ci_evidence import sanitize_junit

    value = dict(blocked(), schema_version='a42341.tests.v1', unit_status='INCOMPLETE_CONTRACT',
        toolchain_status='INCOMPLETE', counts=None, first_failure_code=None)
    try:
        run = os.environ.get('GITHUB_RUN_ID', 'local')
        attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '1')
        require(re.fullmatch(r'[1-9][0-9]{0,5}', attempt) is not None, 'A42341_CI_IDENTITY_INVALID')
        expected = identity(root, run_id=run, attempt=int(attempt))
        require(os.environ.get('GITHUB_SHA', expected.head_sha) == expected.head_sha,
                'A42341_CI_IDENTITY_INVALID')
        value['identity'] = expected.model_dump()
        counts = sanitize_junit(source)['counts']
        value['counts'] = counts
        if counts['tests'] > 0 and counts['failures'] == counts['errors'] == counts['skipped'] == 0:
            value.update(unit_status='COMPLETE_CONTRACT',
                toolchain_status='TOOLCHAIN_CONTRACT_READY_FOR_REVIEW')
        else:
            value['first_failure_code'] = 'A42341_UNIT_TESTS_INCOMPLETE'
    except BaseException:
        value['first_failure_code'] = 'A42341_UNIT_EVIDENCE_INVALID'
    return seal(value)


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    try:
        if len(args) == 3 and args[:2] == ['--check', '--target-sha']:
            print(json.dumps(check_repository(ROOT, args[2]), sort_keys=True))
            return 1
        if len(args) == 4 and args[0] == '--tests' and args[2] == '--output':
            value = unit_receipt(Path(args[1]))
            path = safe_path(args[3])
            require(path.parent == ROOT / '.codex_tmp/a42341' and path.name == 'tests.json',
                    'A42341_ARTIFACT_PATH_INVALID')
            path.parent.mkdir(parents=True, exist_ok=True)
            write_new(path, value)
            return 0 if value['unit_status'] == 'COMPLETE_CONTRACT' else 1
        raise Fault('A42341_EXECUTION_NOT_AUTHORIZED')
    except BaseException as error:
        code = error.code if isinstance(error, Fault) else 'A42341_GUARD_FAILED'
        print(json.dumps(dict(blocked(), first_failure_code=code)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
