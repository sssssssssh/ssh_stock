"""Read local Git/static definitions only; all new live entrances deny unconditionally."""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from scripts.a4235_calibration_adapter_contract import (
    BASELINE,
    PACKET,
    PACKET_SHA,
    ROOT,
    SOURCES,
    Capability,
    Decisions,
    Fault,
    Identity,
    RealAdapter,
    Safety,
    digest,
    require,
)

PROTECTED = ('backend', 'config', 'migrations', 'frontend', '.github', 'scripts', 'tests',
             'docs/acceptance', 'requirements.lock', 'requirements-dev.txt', 'pyproject.toml')
NEW_PATHS = frozenset((*SOURCES, *(f'tests/unit/test_a4235_{name}.py' for name in (
    'pg_identity', 'measurement_contracts', 'capability_review')),
    'docs/acceptance/a42342_final_review.md', *(f'docs/acceptance/a4235_{name}.md' for name in (
        'baseline_freeze', 'protocol_decision_packet', 'capability_matrix',
        'capability_limitations', 'observation_feasibility', 'closeout'))))


def git(root: Path, *args: str) -> bytes:
    try:
        return subprocess.check_output(['git', *args], cwd=root, timeout=5,
                                       stderr=subprocess.DEVNULL)
    except Exception:
        raise Fault('A4235_GIT_UNAVAILABLE') from None


def path_sha(path: Path) -> str:
    require('..' not in path.parts and not any(p.is_symlink() for p in (path, *path.parents)),
            'A4235_PATH_INVALID')
    require(path.is_file() and path.stat().st_size <= 16_000_000, 'A4235_FILE_INVALID')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_files(root: Path = ROOT) -> str:
    entries = git(root, 'ls-tree', '-r', BASELINE, '--', *PROTECTED)
    originals = {row.split(b'\t', 1)[1].decode() for row in entries.splitlines()}
    changed = set(git(root, 'diff', '--no-ext-diff', '--name-only', BASELINE,
                      '--', *PROTECTED).decode().splitlines())
    require(not originals.intersection(changed) and changed <= NEW_PATHS,
            'A4235_FROZEN_FILE_CHANGED')
    require(path_sha(root / PACKET) == PACKET_SHA, 'A4235_PROTOCOL_CHANGED')
    return hashlib.sha256(entries).hexdigest()


def expected_identity(root: Path = ROOT, *, run_id: str = 'local', attempt: int = 1) -> Identity:
    """Independent Git/files + caller CI context; never accepts bundle's own expected object."""
    return Identity(head_sha=git(root, 'rev-parse', 'HEAD').decode().strip(),
                    run_id=run_id, attempt=attempt,
                    source_sha256=digest({name: path_sha(root / name) for name in SOURCES}),
                    protocol_sha256=path_sha(root / PACKET), frozen_sha256=frozen_files(root))


def check_static(target: str, root: Path = ROOT) -> dict:
    require(re.fullmatch(r'[0-9a-f]{40}', target or '') is not None,
            'A4235_FULL_SHA_REQUIRED')
    require(not any(k.startswith('PG') or k in ('DATABASE_URL', 'TEST_DATABASE_URL',)
                    or k.lower().endswith('_proxy') for k in os.environ),
            'A4235_AMBIENT_CONNECTION_REJECTED')
    # JSON schema validates full SHA before comparing; never read .env or resolve a DSN.
    identity = expected_identity(root)
    require(target == identity.head_sha == git(root, 'rev-parse', 'origin/master').decode().strip(),
            'A4235_HEAD_MISMATCH')
    require(not git(root, 'status', '--porcelain').strip(), 'A4235_DIRTY_TREE')
    return dict(Capability(identity=identity, evidence_kind='STATIC_ONLY').model_dump(),
                decisions=Decisions().model_dump(), scope='STATIC_ONLY')


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        require(len(args) == 3 and args[:2] == ['--check-static', '--target-sha'],
                'A4235_CAPABILITY_PROBE_NOT_AUTHORIZED')
        result = check_static(args[2])
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 2  # Valid static check is NOT authorization or performance success.
    except BaseException as error:
        code = error.code if isinstance(error, Fault) else 'A4235_STATIC_CHECK_REJECTED'
        print(json.dumps(dict(Safety().model_dump(), status='NOT_RUN_NOT_AUTHORIZED',
                              first_error=code, scope='STATIC_ONLY'), sort_keys=True))
        return 1


def probe_synthetic(*args: object, **kwargs: object) -> None:
    RealAdapter().probe_synthetic(*args, **kwargs)


if __name__ == '__main__':
    raise SystemExit(main())
