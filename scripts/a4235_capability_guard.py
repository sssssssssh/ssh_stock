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
PATCH_BASE = '55bd6328c3481f2b2ce767fcb843caaa8e0a2ad8'
OVERLAY_MANIFEST = 'docs/acceptance/a42351_reviewer_overlay_manifest.json'
OVERLAY_MANIFEST_SHA = 'ea795278e3fb84e4eebabeba737d23a92a4a0c42e6402cc828bf3801d3c9f648'
PATCH_PATHS = frozenset((
    'scripts/a42341_calibration_review.py', 'tests/unit/test_a42341_runner_review.py',
    'tests/unit/test_a4235_pg_identity.py', 'tests/unit/test_a4235_capability_review.py',
    'scripts/a42351_g1_preflight_contract.py', 'tests/unit/test_a42351_g1_preflight.py'))
STAGE_PATHS = PATCH_PATHS | frozenset((
    'scripts/a4235_capability_guard.py', OVERLAY_MANIFEST,
    *(f'docs/acceptance/a42351_{name}.md' for name in (
        'baseline_and_red', 'g1_runbook_and_trust', 'capability_decision_matrix', 'closeout'))))
NEXT_BASE = 'af08f8724e988121402988b4e8fb70c8ef5b53f2'
NEXT_MANIFEST = 'docs/acceptance/a4236_overlay_manifest.json'
NEXT_MANIFEST_SHA = 'd93bf795a59cb0a168f0e96f4382d58efcbdc2833bc43e22ebde3254a09c1156'
NEXT_SOURCES = tuple(f'scripts/a4236_{name}.py' for name in (
    'g1_harness_contract', 'grant_verifier', 'g1_probe', 'session_prepared',
    'resource_probe', 'observer_feasibility', 'evidence', 'cli', 'mock'))
NEXT_PATCH_PATHS = frozenset((*NEXT_SOURCES, *(f'tests/unit/test_a4236_{name}.py' for name in (
    'harness_grant', 'probe_prepared', 'resources_observer', 'evidence_cli', 'source_guard'))))
NEXT_STAGE_PATHS = NEXT_PATCH_PATHS | frozenset((
    'scripts/a4235_capability_guard.py', NEXT_MANIFEST,
    *(f'docs/acceptance/a4236_{name}.md' for name in (
        'baseline', 'trust_and_red', 'closeout', 'capability_matrix',
        'g1_authorization_request_TEMPLATE', 'unresolved_methods'))))
LIVE_MANIFEST_SHA = 'a88d62d980751cfe182bcffc0a450c21d57195810bdce4e24c80f43c4ff1fb64'
SERVICE_MANIFEST_SHA = '692b2ca9f3f1f95404a6ec953b557d6a6b510123a522b9f357163d3b016b1817'
CLOSEOUT_MANIFEST_SHA = '92f67e70c19eee81ef2ce19283aa9969748480cbc36921df01ebba902bc64662'
COMPLETE_MANIFEST_SHA = 'e1a594a7579ce7d79b62f828126c35f56c38df1de7f84b0b589d645e6e2c9cd7'

BUSINESS_MANIFEST_SHA = '6459e742a0604d001cac16db953486b650371990ad92ada107ea046d8dcfb52e'


def live_paths():
    from scripts.a42361_source_guard import STAGE_PATHS as paths
    from scripts.a42362_source_guard import STAGE_PATHS as service_paths
    from scripts.a42363_complete_guard import STAGE_PATHS as complete_paths
    from scripts.a42363_source_guard import STAGE_PATHS as closeout_paths
    return paths | service_paths | closeout_paths | complete_paths


def live_protected_paths():
    from scripts.a42361_source_guard import AUTHORITY, INFRA
    from scripts.a42362_source_guard import INFRA as service_infra
    from scripts.a42364_source_guard import INFRA as engineering_infra
    return (live_paths() - AUTHORITY - set(INFRA) - service_infra
            - {'infra/g1_control_plane/003_closeout.sql'} - engineering_infra)


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


def validate_next_paths(changed):
    require(set(changed) == NEXT_STAGE_PATHS, 'A4235_FROZEN_FILE_CHANGED')


def next_overlay_fingerprint(root: Path, head: str) -> str:
    """Exact af08f872 delta; legacy manifests and their patch bytes remain unchanged."""
    from scripts import a42361_source_guard as live
    # First validate the actual immutable historical commit, not a fabricated diff.
    validate_next_paths(git(root, 'diff', '--no-ext-diff', '--name-only', NEXT_BASE,
                            live.BASELINE,
                            '--', *PROTECTED).decode().splitlines())
    live_overlay = live.validate(sys.modules[__name__], root, head)
    require(path_sha(root / NEXT_MANIFEST) == NEXT_MANIFEST_SHA,
            'A4235_NEXT_OVERLAY_INVALID')
    try:
        manifest = json.loads((root / NEXT_MANIFEST).read_bytes())
        require(set(manifest) == {'schema_version', 'baseline_sha', 'stage_paths', 'patch_sha256'}
            and manifest['schema_version'] == 'a4236.next-overlay.v1'
            and manifest['baseline_sha'] == NEXT_BASE
            and manifest['stage_paths'] == sorted(NEXT_STAGE_PATHS)
            and set(manifest['patch_sha256']) == NEXT_PATCH_PATHS, 'A4235_NEXT_OVERLAY_INVALID')
        for name in NEXT_STAGE_PATHS:
            current = path_sha(root / name)
            require(current == hashlib.sha256(git(root, 'show', f'{head}:{name}')).hexdigest(),
                    'A4235_HEAD_BYTES_MISMATCH')
            if name in NEXT_PATCH_PATHS:
                original = hashlib.sha256(git(root, 'show', f'{live.BASELINE}:{name}')).hexdigest()
                require(original == manifest['patch_sha256'][name], 'A4235_NEXT_OVERLAY_INVALID')
                if name != live.OLD_TEST:
                    require(current == original, 'A4235_NEXT_OVERLAY_INVALID')
        return digest(dict(head_sha=head, manifest_sha256=NEXT_MANIFEST_SHA,
                           patch_sha256=manifest['patch_sha256'], live_overlay_sha256=live_overlay))
    except Fault:
        raise
    except Exception:
        raise Fault('A4235_NEXT_OVERLAY_INVALID') from None


def overlay_fingerprint(root: Path = ROOT) -> str:
    """Local byte/tree binding, NOT a human signature or a real-execution grant.

    The manifest pins patch bytes; the guard pins its manifest bytes. HEAD is obtained
    independently from Git (not embedded in a self-referential manifest). check_static
    additionally binds it to a caller-supplied full target and origin/master.
    """
    from scripts.business_source_contract import MANIFEST, verify

    if (root / MANIFEST).is_file():
        return verify(root)
    head = git(root, 'rev-parse', 'HEAD').decode().strip()
    require(re.fullmatch(r'[0-9a-f]{40}', head) is not None, 'A4235_FULL_SHA_REQUIRED')
    require(not git(root, 'status', '--porcelain').strip(), 'A4235_DIRTY_TREE')
    changed = set(git(root, 'diff', '--no-ext-diff', '--name-only', PATCH_BASE,
                      '--', *PROTECTED).decode().splitlines())
    require(changed == STAGE_PATHS | NEXT_STAGE_PATHS | live_protected_paths(),
        'A4235_FROZEN_FILE_CHANGED')
    require(path_sha(root / OVERLAY_MANIFEST) == OVERLAY_MANIFEST_SHA,
            'A4235_OVERLAY_MANIFEST_INVALID')
    try:
        manifest = json.loads((root / OVERLAY_MANIFEST).read_bytes())
        require(set(manifest) == {'schema_version', 'historical_baseline', 'patch_base',
                                  'patch_sha256', 'stage_paths'}
            and manifest['schema_version'] == 'a42351.reviewer-overlay.v1'
            and manifest['historical_baseline'] == BASELINE
            and manifest['patch_base'] == PATCH_BASE
            and manifest['stage_paths'] == sorted(STAGE_PATHS)
            and set(manifest['patch_sha256']) == PATCH_PATHS,
            'A4235_OVERLAY_MANIFEST_INVALID')
        next_overlay = next_overlay_fingerprint(root, head)
        for name in STAGE_PATHS:
            current = path_sha(root / name)
            committed = hashlib.sha256(git(root, 'show', f'{head}:{name}')).hexdigest()
            require(current == committed, 'A4235_HEAD_BYTES_MISMATCH')
            if name in PATCH_PATHS:
                require(current == manifest['patch_sha256'][name], 'A4235_OVERLAY_BYTES_MISMATCH')
        # Git status/diff can hide assume-unchanged files. Compare real protected bytes
        # to the committed object IDs too; no index flag can waive this invariant.
        for row in git(root, 'ls-tree', '-r', head, '--', *PROTECTED).splitlines():
            metadata, name = row.split(b'\t', 1)
            mode, kind, object_id = metadata.split()
            require(mode in {b'100644', b'100755'} and kind == b'blob',
                    'A4235_HEAD_BYTES_MISMATCH')
            path = root / name.decode()
            path_sha(path)  # Reject missing, symlink, oversized or traversing paths.
            raw = path.read_bytes()
            blob = b'blob ' + str(len(raw)).encode() + b'\0' + raw
            require(hashlib.sha1(blob).hexdigest().encode() == object_id,
                    'A4235_HEAD_BYTES_MISMATCH')
        require(head == git(root, 'rev-parse', 'HEAD').decode().strip()
            and not git(root, 'status', '--porcelain').strip(), 'A4235_DIRTY_TREE')
        return digest(dict(head_sha=head, manifest_sha256=OVERLAY_MANIFEST_SHA,
                           patch_sha256=manifest['patch_sha256'], next_overlay_sha256=next_overlay))
    except Fault:
        raise
    except Exception:
        raise Fault('A4235_OVERLAY_MANIFEST_INVALID') from None


def frozen_files(root: Path = ROOT) -> str:
    from scripts.business_source_contract import MANIFEST, verify

    if (root / MANIFEST).is_file():
        verify(root)
        return hashlib.sha256(git(root, 'ls-tree', '-r', BASELINE, '--', *PROTECTED)).hexdigest()
    entries = git(root, 'ls-tree', '-r', BASELINE, '--', *PROTECTED)
    originals = {row.split(b'\t', 1)[1].decode() for row in entries.splitlines()}
    changed = set(git(root, 'diff', '--no-ext-diff', '--name-only', BASELINE,
                      '--', *PROTECTED).decode().splitlines())
    legacy_patch = {'scripts/a42341_calibration_review.py',
                    'tests/unit/test_a42341_runner_review.py'}
    require(originals.intersection(changed) == legacy_patch
        and changed <= NEW_PATHS | STAGE_PATHS | NEXT_STAGE_PATHS | live_paths(),
            'A4235_FROZEN_FILE_CHANGED')
    overlay_fingerprint(root)
    require(path_sha(root / PACKET) == PACKET_SHA, 'A4235_PROTOCOL_CHANGED')
    return hashlib.sha256(entries).hexdigest()


def expected_identity(root: Path = ROOT, *, run_id: str = 'local', attempt: int = 1) -> Identity:
    """Independent Git/files + caller CI context; never accepts bundle's own expected object."""
    head = git(root, 'rev-parse', 'HEAD').decode().strip()
    frozen = frozen_files(root)
    source = digest(dict(sources={name: path_sha(root / name) for name in SOURCES},
                         overlay_sha256=overlay_fingerprint(root)))
    require(head == git(root, 'rev-parse', 'HEAD').decode().strip(), 'A4235_HEAD_MISMATCH')
    return Identity(head_sha=head, run_id=run_id, attempt=attempt, source_sha256=source,
                    protocol_sha256=path_sha(root / PACKET), frozen_sha256=frozen)


def check_static(target: str, root: Path = ROOT) -> dict:
    require(re.fullmatch(r'[0-9a-f]{40}', target or '') is not None,
            'A4235_FULL_SHA_REQUIRED')
    require(not any(k.startswith('PG') or k in ('DATABASE_URL', 'TEST_DATABASE_URL',)
                    or k.lower().endswith('_proxy') for k in os.environ),
            'A4235_AMBIENT_CONNECTION_REJECTED')
    # JSON schema validates full SHA before comparing; never read .env or resolve a DSN.
    identity = expected_identity(root)
    require(target == identity.head_sha == git(root, 'rev-parse', 'HEAD').decode().strip()
        == git(root, 'rev-parse', 'origin/master').decode().strip(),
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
