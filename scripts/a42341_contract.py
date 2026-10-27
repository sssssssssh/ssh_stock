"""A42341 mock-only identity, frozen definitions and bounded exclusive artifact IO."""

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field

from scripts.a4233_observation_contract import Counter, Hash, Positive, Strict, digest, seal
from scripts.a4234_calibration_contract import SampleIdentity, schedule
from scripts.a4234_calibration_guard import git

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'f5c0fe4d08f37c01714a3085d49f30da4bc4f1d4'
PROPOSAL = 'docs/acceptance/v14_a4_2_3_4_calibration_protocol_v3_proposal.md'
PROPOSAL_SHA = '065b529f759308c49630c5ce390864a7589b51fcb1be645ca420ed3575692220'
MANIFEST = 'docs/acceptance/a42341_preparation_manifest.json'
MANIFEST_SHA = '4cca8088909821371f99d8cd9dba450d2fa6ada4c6dbc462ccd8ec64498a163e'
SOURCES = tuple('scripts/a42341_' + n + '.py' for n in ('contract', 'prepared_capability',
    'calibration_runner', 'environment_contract', 'calibration_review', 'calibration_guard'))
Variant = Literal['C0', 'C1']
Milliseconds = Annotated[float, Field(ge=0, le=300_000)]
Seconds = Annotated[float, Field(ge=0, le=300)]
Timestamp = Annotated[str, Field(pattern=r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')]
Failure = Literal['A42341_CANCELLED', 'A42341_SIGNAL', 'A42341_TIMEOUT',
    'A42341_SQL_TIMEOUT', 'A42341_WORKLOAD_FAILED', 'A42341_CLEANUP_FAILED',
    'A42341_JOIN_TIMEOUT', 'A42341_BRACKET_UNCOVERED', 'A42341_OBSERVER_INVALID',
    'A42341_METRIC_UNAVAILABLE', 'A42341_ENVIRONMENT_DRIFT', 'A42341_PREPARE_IDENTITY_MISMATCH',
    'A42341_PREPARED_STABILITY_NOT_PROVEN', 'A42341_CLOCK_DRIFT', 'A42341_INTERNAL',
    'A42341_ARTIFACT_WRITE_FAILED']


class Fault(RuntimeError):
    def __init__(self, code):
        self.code = code if re.fullmatch(r'A42341_[A-Z0-9_]{1,80}', code) else 'A42341_INTERNAL'
        super().__init__(self.code)


def require(value, code):
    if not value:
        raise Fault(code)


def mock_hash(*values):
    return digest(['MOCK_CONTRACT_ONLY', *values])


class Safety(Strict):
    evidence_kind: Literal['MOCK_CONTRACT_ONLY'] = 'MOCK_CONTRACT_ONLY'
    data_source: Literal['PURE_IN_MEMORY_MOCK'] = 'PURE_IN_MEMORY_MOCK'
    execution_enabled: Literal[False] = False
    performance_eligible: Literal[False] = False
    capacity_ready: Literal[False] = False
    production_read_authorized: Literal[False] = False
    attribution_authorized: Literal[False] = False
    unique_repair_candidate: None = None
    absence_proven: Literal[False] = False
    causality: Literal['NOT_EVALUATED'] = 'NOT_EVALUATED'
    authorization_status: Literal['NOT_RUN_NOT_AUTHORIZED'] = 'NOT_RUN_NOT_AUTHORIZED'


class Identity(Strict):
    head_sha: Annotated[str, Field(pattern=r'^[0-9a-f]{40}$')]
    run_id: Annotated[str, Field(pattern=r'^(local|[0-9]{1,24})$')]
    attempt: Positive
    protocol_sha256: Hash
    manifest_sha256: Hash
    source_sha256: Hash
    old_source_sha256: Hash
    model_sha256: Hash
    input_sha256: Hash
    dependency_sha256: Hash
    fixture_sha256: Hash
    data_snapshot_sha256: Hash


def safe_path(path):
    path = Path(path).absolute()
    require('..' not in Path(path).parts, 'A42341_ARTIFACT_PATH_INVALID')
    require(not any(p.is_symlink() for p in (path, *path.parents)),
            'A42341_ARTIFACT_PATH_INVALID')
    return path


def file_sha(path):
    path = safe_path(path)
    require(path.is_file() and path.stat().st_size <= 16_000_000, 'A42341_FILE_INVALID')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    try:
        path = safe_path(path)
        require(path.is_file() and path.stat().st_size <= 16_000_000, 'A42341_ARTIFACT_INVALID')
        def pairs(items):
            require(len({k for k, _ in items}) == len(items), 'A42341_DUPLICATE_JSON_KEY')
            return dict(items)
        def nonfinite(value):
            raise Fault('A42341_NONFINITE_JSON')
        return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=nonfinite)
    except Fault:
        raise
    except Exception:
        raise Fault('A42341_ARTIFACT_INVALID') from None


def definitions(root=ROOT):
    root = Path(root)
    require(file_sha(root / PROPOSAL) == PROPOSAL_SHA, 'A42341_PROTOCOL_OR_SOURCE_CHANGED')
    require(file_sha(root / MANIFEST) == MANIFEST_SHA, 'A42341_PROTOCOL_OR_SOURCE_CHANGED')
    value = load(root / MANIFEST)
    from scripts.business_source_contract import versioned_frozen_files

    for name, sha in versioned_frozen_files(root, value['frozen_files']).items():
        require(file_sha(root / name) == sha, 'A42341_FROZEN_FILE_CHANGED')
    return value


def source_sha(root=ROOT):
    return digest({p: file_sha(Path(root) / p) for p in SOURCES})


def identity(root=ROOT, *, run_id='local', attempt=1):
    from scripts.a4234_calibration_guard import source_sha as old_source_sha

    value = definitions(root)
    return Identity(head_sha=git(root, 'rev-parse', 'HEAD'), run_id=run_id, attempt=attempt,
        protocol_sha256=PROPOSAL_SHA, manifest_sha256=MANIFEST_SHA, source_sha256=source_sha(root),
        old_source_sha256=old_source_sha(root), model_sha256=value['model_tree_sha256'],
        input_sha256=value['input_key_sha256'],
        dependency_sha256=value['frozen_files']['requirements.lock'],
        fixture_sha256=mock_hash('PG17_FIXTURE_NOT_CREATED'),
        data_snapshot_sha256=mock_hash('DATA_NOT_CREATED', 4233))


def validate_identity(expected, root=ROOT):
    require(type(expected) is Identity, 'A42341_IDENTITY_INVALID')
    actual = identity(root, run_id=expected.run_id, attempt=expected.attempt)
    require(expected == actual, 'A42341_PROTOCOL_OR_SOURCE_CHANGED')


def warmup_schedule():
    rows = [dict(block=b, position=p, variant=(('C0', 'C1') if b % 2 == 0 else
        ('C1', 'C0'))[p % 2], mode='OFF', lookup_number=p // 2 + 1)
        for b in range(4) for p in range(4)]
    require(digest(rows) == definitions()['candidate_warmup_sha256'], 'A42341_SCHEDULE_CHANGED')
    return rows


def write_new(path, value):
    """Publish using an exclusive hard link, not a check-then-overwriting replace."""
    parent_fd, temporary, published = None, None, False
    started = time.monotonic_ns()
    try:
        path = safe_path(path)
        require(path.parent.is_dir(), 'A42341_ARTIFACT_PATH_INVALID')
        raw = (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
               + '\n').encode()
        require(len(raw) <= 16_000_000, 'A42341_ARTIFACT_TOO_LARGE')
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        temporary = '.a42341-' + uuid4().hex
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent_fd)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        require(time.monotonic_ns() - started <= 2_000_000_000, 'A42341_ARTIFACT_WRITE_FAILED')
        os.link(temporary, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd,
                follow_symlinks=False)
        published = True
        os.fsync(parent_fd)
        require(time.monotonic_ns() - started <= 2_000_000_000, 'A42341_ARTIFACT_WRITE_FAILED')
        return dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    except Exception:
        if published:
            try:
                # Only our just-linked inode, never an existing/replaced user's artifact.
                a = os.stat(temporary, dir_fd=parent_fd, follow_symlinks=False)
                b = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
                if (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino):
                    os.unlink(path.name, dir_fd=parent_fd)
            except OSError:
                pass  # Caller also emits an independent incomplete receipt when possible.
        raise Fault('A42341_ARTIFACT_WRITE_FAILED') from None
    finally:
        if parent_fd is not None:
            cleanup_failed = False
            if temporary is not None:
                try:
                    os.unlink(temporary, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
                except OSError:
                    cleanup_failed = True
            try:
                os.close(parent_fd)
            except OSError:
                cleanup_failed = True
            if cleanup_failed:
                raise Fault('A42341_ARTIFACT_WRITE_FAILED') from None


__all__ = ['Counter', 'Hash', 'Positive', 'Strict', 'SampleIdentity', 'schedule', 'seal']
