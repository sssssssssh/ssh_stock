"""Bounded offline bundles with independent Git identity. CLI NEVER exits zero."""

import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path

from scripts.a4235_calibration_adapter_contract import (
    Capability,
    Failure,
    Fault,
    FileProof,
    Identity,
    Limitations,
    Manifest,
    Safety,
    require,
)
from scripts.a4235_capability_guard import expected_identity

NAMES = frozenset(('capability.json', 'limitations.json', 'failure.json', 'manifest.json'))
LIMITS = ['A4235_CAPABILITY_PROBE_NOT_AUTHORIZED', 'A4235_C0_C1_NOT_PROVEN',
          'A4235_CACHED_PLAN_STRUCTURE_NOT_VERIFIED', 'A4235_METRIC_UNAVAILABLE',
          'A4235_LONG_WINDOW_NOT_PROVEN', 'A4235_PROTOCOL_DECISION_PENDING']


def open_directory(path: Path) -> int:
    require('..' not in path.parts, 'A4235_PATH_INVALID')
    path = path.absolute()
    fd = None
    try:
        fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in path.parts[1:]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = following
        return fd
    except BaseException:
        if fd is not None:
            os.close(fd)
        raise Fault('A4235_PATH_INVALID') from None


def encode(value: object) -> bytes:
    try:
        raw = (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
               + '\n').encode()
        require(len(raw) <= 1_000_000, 'A4235_ARTIFACT_TOO_LARGE')
        return raw
    except Fault:
        raise
    except Exception:
        raise Fault('A4235_ARTIFACT_INVALID') from None


def decode(raw: bytes) -> object:
    def pairs(items: list) -> dict:
        require(len({k for k, _ in items}) == len(items), 'A4235_DUPLICATE_JSON_KEY')
        return dict(items)

    def constant(value: str) -> None:
        raise Fault('A4235_NONFINITE_JSON')

    try:
        require(0 < len(raw) <= 1_000_000, 'A4235_ARTIFACT_TOO_LARGE')
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except Fault:
        raise
    except Exception:
        raise Fault('A4235_ARTIFACT_INVALID') from None


def proof(raw: bytes) -> FileProof:
    return FileProof(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def validate(capability: Capability, limits: Limitations, failure: Failure,
             expected: Identity) -> None:
    capability = Capability.model_validate(capability.model_dump())
    limits = Limitations.model_validate(limits.model_dump())
    failure = Failure.model_validate(failure.model_dump())
    require(capability.identity == limits.identity == failure.identity == expected,
            'A4235_IDENTITY_MISMATCH')
    # No live source/attestation implementation exists this phase; no input can claim READY.
    require(capability.status in ('BLOCKED_WITH_EVIDENCE', 'CAPABILITY_PARTIAL',
                                  'NOT_RUN_NOT_AUTHORIZED'), 'A4235_UNPROVEN_READY_REJECTED')
    require(limits.codes == LIMITS, 'A4235_LIMITATIONS_MISSING')
    require(failure.cleanup_complete == (not failure.cleanup_codes and not failure.cleanup_omitted)
            and len(set(failure.cleanup_codes)) == len(failure.cleanup_codes),
            'A4235_CLEANUP_CONTRADICTION')
    require(not failure.cleanup_omitted or len(failure.cleanup_codes) == 4,
            'A4235_CLEANUP_CONTRADICTION')
    require(not failure.cleanup_codes or failure.first_error is not None,
            'A4235_FIRST_ERROR_MISSING')
    if capability.evidence_kind == 'STATIC_ONLY':
        require(capability.physical_identity_sha256 is None
                and capability.least_privilege_sha256 is None
                and failure.last_snapshot_sha256 is None, 'A4235_STATIC_PHYSICAL_CLAIM')
    else:
        require((capability.physical_identity_sha256 is None)
                == (capability.least_privilege_sha256 is None), 'A4235_PRIVILEGE_CHAIN_MISSING')


def write_bundle(path: Path, capability: Capability, limits: Limitations,
                 failure: Failure) -> None:
    validate(capability, limits, failure, capability.identity)
    require('..' not in path.parts, 'A4235_PATH_INVALID')
    parent = open_directory(path.absolute().parent)
    fd = None
    manifest_inode = None
    started = time.monotonic_ns()
    try:
        # Exclusive directory publication; existing or partial output can never be overwritten.
        os.mkdir(path.name, mode=0o700, dir_fd=parent)
        fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        payload = {'capability.json': encode(capability.model_dump()),
                   'limitations.json': encode(limits.model_dump()),
                   'failure.json': encode(failure.model_dump())}
        manifest = Manifest(identity=capability.identity,
                            **{k[:-5]: proof(raw) for k, raw in payload.items()})
        payload['manifest.json'] = encode(manifest.model_dump())
        # Failure receipt first, manifest last; incomplete writes remain visibly incomplete.
        for name in ('failure.json', 'capability.json', 'limitations.json', 'manifest.json'):
            require(time.monotonic_ns() - started <= 2_000_000_000, 'A4235_WRITE_TIMEOUT')
            out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                          0o600, dir_fd=fd)
            if name == 'manifest.json':
                meta = os.fstat(out)
                manifest_inode = (meta.st_dev, meta.st_ino)
            with os.fdopen(out, 'wb') as stream:
                stream.write(payload[name])
                stream.flush()
                os.fsync(stream.fileno())
        os.fsync(fd)
        os.fsync(parent)
        require(time.monotonic_ns() - started <= 2_000_000_000, 'A4235_WRITE_TIMEOUT')
    except BaseException as error:
        if manifest_inode is not None:
            try:
                meta = os.stat('manifest.json', dir_fd=fd, follow_symlinks=False)
                require((meta.st_dev, meta.st_ino) == manifest_inode,
                        'A4235_ARTIFACT_CLEANUP_FAILED')
                os.unlink('manifest.json', dir_fd=fd)
                os.fsync(fd)
            except BaseException:
                raise Fault('A4235_ARTIFACT_CLEANUP_FAILED') from None
        raise Fault(error.code if isinstance(error, Fault)
                    else 'A4235_ARTIFACT_WRITE_FAILED') from None
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def review_bundle(path: Path, expected: Identity) -> dict:
    fd = None
    try:
        expected = Identity.model_validate(expected.model_dump())
        require(expected == expected_identity(run_id=expected.run_id, attempt=expected.attempt),
                'A4235_UNTRUSTED_EXPECTED')
        fd = open_directory(path)
        require(set(os.listdir(fd)) == NAMES, 'A4235_ARTIFACT_SET_INVALID')
        raw = {}
        for name in sorted(NAMES):
            file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(file_fd, 'rb') as stream:
                meta = os.fstat(stream.fileno())
                require(stat.S_ISREG(meta.st_mode) and 0 < meta.st_size <= 1_000_000,
                        'A4235_ARTIFACT_TOO_LARGE')
                raw[name] = stream.read(1_000_001)
                require(len(raw[name]) <= 1_000_000, 'A4235_ARTIFACT_TOO_LARGE')
        data = {name: decode(value) for name, value in raw.items()}
        manifest = Manifest.model_validate(data['manifest.json'])
        require(manifest.identity == expected, 'A4235_IDENTITY_MISMATCH')
        for name in ('capability', 'limitations', 'failure'):
            require(getattr(manifest, name) == proof(raw[name + '.json']),
                    'A4235_ARTIFACT_HASH_MISMATCH')
        capability = Capability.model_validate(data['capability.json'])
        limits = Limitations.model_validate(data['limitations.json'])
        failure = Failure.model_validate(data['failure.json'])
        validate(capability, limits, failure, expected)
        return dict(capability.model_dump(), offline_contract_validated=True,
                    result='CAPABILITY_VALID_NOT_AUTHORIZED')
    except Fault:
        raise
    except Exception:
        raise Fault('A4235_ARTIFACT_INVALID') from None
    finally:
        if fd is not None:
            os.close(fd)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        require(len(args) == 2 and args[0] == '--directory' and not args[1].startswith('--'),
                'A4235_CAPABILITY_PROBE_NOT_AUTHORIZED')
        # Git and CI context, not an expected.json supplied by the bundle.
        expected = expected_identity(run_id=os.environ.get('GITHUB_RUN_ID', 'local'),
                                     attempt=int(os.environ.get('GITHUB_RUN_ATTEMPT', '1')))
        print(json.dumps(review_bundle(Path(args[1]), expected), sort_keys=True, allow_nan=False))
        return 3
    except BaseException as error:
        code = error.code if isinstance(error, Fault) else 'A4235_OFFLINE_REVIEW_REJECTED'
        print(json.dumps(dict(Safety().model_dump(), status='NOT_RUN_NOT_AUTHORIZED',
                              first_error=code), sort_keys=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
