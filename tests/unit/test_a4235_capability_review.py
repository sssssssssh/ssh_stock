"""AT24-30: safe bounded offline evidence; no artifact can authorize calibration."""

import hashlib
import json
import os
import subprocess
import sys

import pytest

from scripts import a4235_capability_guard as guard
from scripts import a4235_capability_review as reviewer
from scripts.a4235_calibration_adapter_contract import (
    ROOT,
    SOURCES,
    Capability,
    Fault,
    Limitations,
    record_failure,
)


@pytest.fixture(scope='module')
def expected():
    return guard.expected_identity()


@pytest.fixture
def bundle(tmp_path, expected):
    path = tmp_path / 'evidence'
    capability = Capability(identity=expected, evidence_kind='MOCK_ONLY')
    limits = Limitations(identity=expected, codes=list(reviewer.LIMITS))
    failure = record_failure(expected, 'A4235_CAPABILITY_PROBE_NOT_AUTHORIZED', [], 'a' * 64)
    reviewer.write_bundle(path, capability, limits, failure)
    return path


def cli(path, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GITHUB_')}
    env.update(PYTHONPATH=str(ROOT), DATABASE_URL='postgresql://SECRET_DO_NOT_PRINT@127.0.0.1:1/no')
    result = subprocess.run([sys.executable, '-m', 'scripts.a4235_capability_review',
                             '--directory', str(path), *args], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=20)
    assert not result.stderr and 'SECRET_DO_NOT_PRINT' not in result.stdout
    assert str(path) not in result.stdout and len(result.stdout) < 5000
    value = json.loads(result.stdout)
    assert value['execution_enabled'] is value['performance_eligible'] is False
    assert value['formal_calibration_authorization'] == 'NOT_AUTHORIZED'
    return result.returncode, value


def rewrite(path, filename, transform):
    value = reviewer.decode((path / filename).read_bytes())
    raw = reviewer.encode(transform(value))
    (path / filename).write_bytes(raw)
    manifest = json.loads((path / 'manifest.json').read_bytes())
    manifest[filename[:-5]] = dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    (path / 'manifest.json').write_bytes(reviewer.encode(manifest))


def test_AT24_AT26_mock_valid_cli_is_nonzero_and_no_physical_claim(bundle, expected):
    result = reviewer.review_bundle(bundle, expected)
    assert result['offline_contract_validated'] is True
    assert result['status'] == 'BLOCKED_WITH_EVIDENCE'
    assert result['backend_cpu'] == 'METRIC_UNAVAILABLE'
    assert result['capability_probe_status'] == 'NOT_RUN_NOT_AUTHORIZED'
    code, result = cli(bundle)
    assert code == 3 and result['result'] == 'CAPABILITY_VALID_NOT_AUTHORIZED'


@pytest.mark.parametrize('change', ['sha', 'run', 'attempt', 'source', 'protocol', 'ready',
                                   'live-kind', 'flag', 'extra-field', 'limits', 'cleanup'])
def test_AT25_AT26_rehashed_forgery_rejected(bundle, expected, change):
    if change in ('sha', 'run', 'attempt', 'source', 'protocol'):
        key, value = {'sha': ('head_sha', 'f' * 40), 'run': ('run_id', '9999'),
                      'attempt': ('attempt', 2), 'source': ('source_sha256', 'f' * 64),
                      'protocol': ('protocol_sha256', 'f' * 64)}[change]
        rewrite(bundle, 'capability.json', lambda x: x | {'identity': x['identity'] | {key: value}})
    elif change == 'limits':
        rewrite(bundle, 'limitations.json', lambda x: x | {'codes': []})
    elif change == 'cleanup':
        rewrite(bundle, 'failure.json', lambda x: x | {'cleanup_codes': ['A4235_JOIN_TIMEOUT']})
    else:
        update = {'ready': {'status': 'CAPABILITY_READY_FOR_HUMAN_REVIEW'},
                  'live-kind': {'evidence_kind': 'REAL'}, 'flag': {'performance_eligible': True},
                  'extra-field': {'dsn': 'SECRET_DO_NOT_PRINT'}}[change]
        rewrite(bundle, 'capability.json', lambda x: x | update)
    with pytest.raises(Fault):
        reviewer.review_bundle(bundle, expected)
    assert cli(bundle)[0] == 1


@pytest.mark.parametrize('change', ['missing', 'extra', 'symlink-file', 'symlink-dir',
                                   'traversal', 'fifo', 'oversized', 'hash', 'duplicate',
                                   'nan', 'inf', 'bad-json', 'manifest-extra'])
def test_AT25_unsafe_files_and_json_fail_closed(bundle, expected, change, tmp_path):
    path = bundle
    target = bundle / 'capability.json'
    if change == 'missing':
        target.unlink()
    elif change == 'extra':
        (bundle / 'unexpected.json').write_text('{}')
    elif change == 'symlink-file':
        target.unlink()
        target.symlink_to(tmp_path / 'missing')
    elif change == 'symlink-dir':
        path = tmp_path / 'link'
        path.symlink_to(bundle, target_is_directory=True)
    elif change == 'traversal':
        path = bundle / '..' / 'evidence'
    elif change == 'fifo':
        target.unlink()
        os.mkfifo(target)
    elif change == 'manifest-extra':
        target = bundle / 'manifest.json'
        target.write_bytes(reviewer.encode(json.loads(target.read_bytes()) | {'unsafe': True}))
    else:
        raw = {'oversized': b' ' * 1_000_001, 'hash': b'{}',
               'duplicate': b'{"x":1,"x":2}', 'nan': b'{"x":NaN}', 'inf': b'{"x":Infinity}',
               'bad-json': b'{'}[change]
        target.write_bytes(raw)
    with pytest.raises(Fault):
        reviewer.review_bundle(path, expected)
    assert cli(path)[0] == 1


@pytest.mark.parametrize('field,bad', [('head_sha', 'f' * 40), ('source_sha256', 'f' * 64),
                                     ('protocol_sha256', 'f' * 64), ('frozen_sha256', 'f' * 64)])
def test_AT25_expected_cannot_be_self_reported(bundle, expected, field, bad):
    with pytest.raises(Fault, match='UNTRUSTED_EXPECTED'):
        reviewer.review_bundle(bundle, expected.model_copy(update={field: bad}))


@pytest.mark.parametrize('flag', ['--execute', '--approve', '--force', '--token', '--repeat',
                                '--budget', '--probe-synthetic', '--run'])
def test_AT27_reviewer_unknown_flags_never_activate_live(bundle, flag):
    code, value = cli(bundle, flag, 'SECRET_DO_NOT_PRINT')
    assert code == 1 and value['first_error'] == 'A4235_CAPABILITY_PROBE_NOT_AUTHORIZED'


def test_AT24_atomic_new_bundle_and_sticky_cleanup(bundle, expected, tmp_path):
    cap = Capability(identity=expected, evidence_kind='MOCK_ONLY')
    limits = Limitations(identity=expected, codes=list(reviewer.LIMITS))
    first = 'A4235_READ_FAILED'
    cleanup = [f'A4235_CLEANUP_{i}' for i in range(7)]
    failure = record_failure(expected, first, cleanup, 'b' * 64)
    assert failure.first_error == first and failure.cleanup_omitted == 3
    assert failure.last_snapshot_sha256 == 'b' * 64 and not failure.cleanup_complete
    path = tmp_path / 'failed'
    reviewer.write_bundle(path, cap, limits, failure)
    assert reviewer.review_bundle(path, expected)['status'] == 'BLOCKED_WITH_EVIDENCE'
    original = {p.name: p.read_bytes() for p in bundle.iterdir()}
    with pytest.raises(Fault, match='ARTIFACT_WRITE_FAILED'):
        reviewer.write_bundle(bundle, cap, limits, failure)
    assert original == {p.name: p.read_bytes() for p in bundle.iterdir()}


def test_AT24_timeout_preserves_failure_and_cannot_be_reviewed(tmp_path, expected, monkeypatch):
    path = tmp_path / 'partial'
    counter = iter([0, 1, 2, 2_000_000_001])
    monkeypatch.setattr(reviewer.time, 'monotonic_ns', lambda: next(counter))
    with pytest.raises(Fault, match='WRITE_TIMEOUT'):
        reviewer.write_bundle(path, Capability(identity=expected, evidence_kind='MOCK_ONLY'),
            Limitations(identity=expected, codes=list(reviewer.LIMITS)),
            record_failure(expected, 'A4235_ORIGINAL_ERROR', [], 'b' * 64))
    assert json.loads((path / 'failure.json').read_bytes())['first_error'] == 'A4235_ORIGINAL_ERROR'
    assert not (path / 'manifest.json').exists()
    with pytest.raises(Fault, match='ARTIFACT_SET_INVALID'):
        reviewer.review_bundle(path, expected)


def test_AT24_late_timeout_cannot_leave_acceptable_bundle(tmp_path, expected, monkeypatch):
    path = tmp_path / 'late-timeout'
    counter = iter([0, 1, 2, 3, 4, 2_000_000_001])
    monkeypatch.setattr(reviewer.time, 'monotonic_ns', lambda: next(counter))
    with pytest.raises(Fault, match='WRITE_TIMEOUT'):
        reviewer.write_bundle(path, Capability(identity=expected, evidence_kind='MOCK_ONLY'),
            Limitations(identity=expected, codes=list(reviewer.LIMITS)),
            record_failure(expected, 'A4235_ORIGINAL_ERROR', [], 'b' * 64))
    with pytest.raises(Fault):
        reviewer.review_bundle(path, expected)


def test_AT24_cleanup_only_still_records_first_failure(expected):
    result = record_failure(expected, None, ['A4235_CLOSE_FAILED'])
    assert result.first_error == 'A4235_CLOSE_FAILED' and not result.cleanup_complete


def test_AT24_manifest_fsync_failure_is_unacceptable(tmp_path, expected, monkeypatch):
    path = tmp_path / 'fsync-failed'
    real_fsync = reviewer.os.fsync
    calls = 0

    def fail_manifest_fsync(fd):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OSError('SECRET_DO_NOT_PRINT')
        return real_fsync(fd)

    monkeypatch.setattr(reviewer.os, 'fsync', fail_manifest_fsync)
    with pytest.raises(Fault, match='A4235_ARTIFACT_WRITE_FAILED') as error:
        reviewer.write_bundle(path, Capability(identity=expected, evidence_kind='MOCK_ONLY'),
            Limitations(identity=expected, codes=list(reviewer.LIMITS)),
            record_failure(expected, 'A4235_ORIGINAL_ERROR', [], 'b' * 64))
    assert 'SECRET_DO_NOT_PRINT' not in str(error.value)
    assert json.loads((path / 'failure.json').read_bytes())['first_error'] == 'A4235_ORIGINAL_ERROR'
    with pytest.raises(Fault):
        reviewer.review_bundle(path, expected)


def test_AT10_AT28_source_boundary_no_network_no_real_collection():
    import ast
    forbidden = {'socket', 'requests', 'httpx', 'psycopg', 'sqlalchemy', 'gc', 'threading',
                 'multiprocessing', 'dotenv', 'app', 'ctypes'}
    for name in SOURCES:
        tree = ast.parse((ROOT / name).read_bytes())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not {n.name.split('.')[0] for n in node.names} & forbidden
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or '').split('.')[0] not in forbidden
    assert 'failure.json' in reviewer.NAMES


def test_AT05_frozen_path_change_is_rejected_without_touching_original(monkeypatch):
    original_git = guard.git
    def fake_git(root, *args):
        if args[0] == 'diff':
            return b'scripts/a42341_calibration_review.py\n'
        return original_git(root, *args)
    monkeypatch.setattr(guard, 'git', fake_git)
    with pytest.raises(Fault, match='FROZEN_FILE_CHANGED'):
        guard.frozen_files()


def test_AT10_new_production_file_also_breaks_freeze(monkeypatch):
    original_git = guard.git
    def fake_git(root, *args):
        if args[0] == 'diff':
            return b'backend/app/new_production_file.py\n'
        return original_git(root, *args)
    monkeypatch.setattr(guard, 'git', fake_git)
    with pytest.raises(Fault, match='FROZEN_FILE_CHANGED'):
        guard.frozen_files()
