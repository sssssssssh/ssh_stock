"""Offline fixed A-D bundle integrity and privilege refusal. No execution fixtures."""

import ast
import copy
import json
import os
from pathlib import Path

import pytest

from scripts import business_evidence_bundle as e

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def bundle(tmp_path):
    for item in e.expected_entries():
        target = tmp_path / item['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / item['path']).read_bytes())
    (tmp_path / e.MANIFEST).write_bytes((ROOT / e.MANIFEST).read_bytes())
    return tmp_path


def manifest(root):
    return json.loads((root / e.MANIFEST).read_bytes())


def save_manifest(root, document):
    document['bundle_sha256'] = e.digest({k: v for k, v in document.items()
                                        if k != 'bundle_sha256'})
    (root / e.MANIFEST).write_bytes(e.canonical(document) + b'\n')


def edit(root, name, mutate):
    document = manifest(root)
    item = next(x for x in document['evidence'] if x['path'].endswith('/' + name))
    path = root / item['path']
    value = json.loads(path.read_bytes())
    mutate(value)
    path.write_bytes(e.canonical(value) + b'\n')
    item['sha256'] = e.sha(path.read_bytes())
    save_manifest(root, document)


def refused(root):
    with pytest.raises((ValueError, OSError, KeyError, TypeError)):
        e.validate(root)


def test_valid_repeated_report_is_byte_identical(bundle):
    first = e.validate(bundle)
    second = e.validate(bundle)
    assert e.canonical(first) == e.canonical(second)
    assert first['integrity'] == 'VALID'
    assert first['non_claims'] == e.NON_CLAIMS
    assert e.main(['--root', str(bundle)]) == 0
    raw = (bundle / e.REPORT).read_bytes()
    assert e.main(['--root', str(bundle)]) == 0
    assert (bundle / e.REPORT).read_bytes() == raw
    assert e.digest({k: v for k, v in manifest(bundle).items() if k != 'bundle_sha256'}) \
        == first['bundle_sha256']
    assert not {'all_stages_passed', 'performance_pass', 'capacity_pass', 'production_authorized',
                'ready_for_capacity', 'release_ready'} & set(first)


def test_original_d_bytes_and_all_source_identities(bundle):
    doc = manifest(bundle)
    assert len(doc['evidence']) == 12
    for rec in e.RECORDS[7:]:
        raw = (bundle / ('docs/acceptance/' + rec[3])).read_bytes()
        assert e.sha(raw) == rec[4]
    assert {x['source_commit_sha'] for x in doc['evidence']} == set(e.SOURCES.values())
    v = e.validate(bundle)
    assert 'HISTORICAL_SELECT_UPDATE_ATTRIBUTION_UNKNOWN' in v['stage_scope']['04-A']['excludes']
    assert 'RAW_JSONL_NOT_ARCHIVED' in v['stage_scope']['04-B']['excludes']
    assert 'CAPACITY_NOT_ASSESSED' in v['stage_scope']['04-C']['excludes']
    assert v['stage_scope']['04-D']['supports'] == 'EXACT_RUN_LINUX_INSTALLATION_ONLY'


def test_report_cannot_mutate_future_validation_policy(bundle):
    report = e.validate(bundle)
    original = e.canonical(report)
    report['non_claims'].clear()
    report['stage_scope']['04-A']['excludes'].clear()
    assert e.canonical(e.validate(bundle)) == original


@pytest.mark.parametrize('mutate', [
    lambda d: d.pop('schema'), lambda d: d.update(schema='unknown'),
    lambda d: d.update(extra=True), lambda d: d.update(performance_pass=True),
    lambda d: d.update(capacity_pass=True), lambda d: d.update(production_authorized=True),
    lambda d: d['evidence'].pop(), lambda d: d['evidence'].append(d['evidence'][0]),
    lambda d: d['evidence'].__setitem__(1, copy.deepcopy(d['evidence'][0])),
    lambda d: d['evidence'][0].pop('claim_scope'),
    lambda d: d['evidence'][0].update(unknown='value'),
    lambda d: d['evidence'][0].update(sha256='A' * 64),
    lambda d: d['evidence'][0].update(source_commit_sha='f' * 40),
    lambda d: d['evidence'][0]['claim_scope'].update(performance_pass=True),
    lambda d: d['evidence'][0]['claim_scope'].update(excludes=[]),
])
def test_manifest_tampering_even_after_rehash(bundle, mutate):
    doc = manifest(bundle)
    mutate(doc)
    save_manifest(bundle, doc)
    refused(bundle)


@pytest.mark.parametrize('path', ['/etc/passwd', '../secret', 'docs/../secret',
                                  'C:/secret', r'docs\secret', '//host/share',
                                  './docs/a', 'docs//a', 'docs/./a', '.env'])
def test_unsafe_or_unapproved_path(bundle, path):
    doc = manifest(bundle)
    doc['evidence'][0]['path'] = path
    save_manifest(bundle, doc)
    refused(bundle)


@pytest.mark.parametrize('mode', ['missing', 'bytes', 'directory', 'oversize'])
def test_missing_corrupt_nonfile_and_size(bundle, mode):
    path = bundle / manifest(bundle)['evidence'][0]['path']
    if mode == 'missing':
        path.unlink()
    elif mode == 'bytes':
        path.write_bytes(path.read_bytes() + b' ')
    elif mode == 'directory':
        path.unlink()
        path.mkdir()
    else:
        path.write_bytes(b' ' * (e.MAX_FILE_BYTES + 1))
    refused(bundle)


@pytest.mark.parametrize('raw', [b'{', b'{"x":1,"x":2}', b'{"x":NaN}',
                                b'{"x":Infinity}', b'{"x":-Infinity}', b'{"x":1e999}',
                                b'\xff', b'[' * 40 + b'0' + b']' * 40])
def test_strict_json_parser(raw):
    with pytest.raises(ValueError):
        e.parse(raw)


def test_symlink_refused_before_open(bundle):
    path = bundle / manifest(bundle)['evidence'][0]['path']
    target = bundle / 'outside.json'
    path.rename(target)
    # Windows needs Developer Mode/SeCreateSymbolicLinkPrivilege. No skip/xfail:
    # fail-closed path handling is also tested via lstat-type mock below.
    if os.name == 'nt':
        with pytest.MonkeyPatch.context() as m:
            original = Path.is_symlink
            m.setattr(Path, 'is_symlink', lambda p: p == path or original(p))
            refused(bundle)
    else:
        path.symlink_to(target)
        refused(bundle)


@pytest.mark.parametrize('name,mutate', [
    ('biz_perf_04_a_offline.json', lambda d: d.update(historical_select_update_attribution='PASS')),
    ('biz_perf_04_a_offline.json', lambda d: d.update(historical_select_update_attribution=True)),
    ('biz_perf_04_a_offline.json', lambda d: d.update(performance_runs=1)),
    ('biz_perf_04_b_generation.json', lambda d: d['runs'].pop()),
    ('biz_perf_04_b_generation.json', lambda d: d['runs'][0].update(scale='S5')),
    ('biz_perf_04_b_generation.json', lambda d: d['runs'].__setitem__(1, d['runs'][0])),
    ('biz_perf_04_b_generation.json', lambda d: d['runs'][0].update(equal=False)),
    ('biz_perf_04_b_generation.json', lambda d: d['runs'][0].update(dataset_sha256='bad')),
    ('biz_perf_04_b_generation.json', lambda d: d['runs'][0]['config'].update(expected_raw_rows=1)),
    ('biz_perf_04_b_validation.json', lambda d: d['junit'].update(failures='1')),
    ('biz_perf_04_b_validation.json', lambda d: d.update(large_generation_in_default_ci=True)),
    ('biz_perf_04_c_validation.json', lambda d: d.update(capacity_experiments=1)),
    ('biz_perf_04_c_validation.json', lambda d: d.update(worker_roots=1)),
    ('biz_perf_04_c_validation.json', lambda d: d.update(database_connections=1)),
    ('biz_perf_04_c_validation.json', lambda d: d.update(capacity='NOT_ASSESSED')),
    ('biz_perf_04_c_validation.json', lambda d: d.update(capacity=True)),
    ('biz_perf_04_c_validation.json', lambda d: d.update(performance_eligible=True)),
    ('biz_perf_04_c_validation.json', lambda d: d['tests'].update(errors='1')),
])
def test_a_b_c_semantic_escalation_refused_after_rehash(bundle, name, mutate):
    edit(bundle, name, mutate)
    refused(bundle)


@pytest.mark.parametrize('name,field,value', [
    ('receipt.json', 'run_id', '42156106472'), ('receipt.json', 'attempt', '2'),
    ('receipt.json', 'target_sha', 'f' * 40), ('receipt.json', 'exit_code', True),
    ('receipt.json', 'status', 'INCOMPLETE'),
    ('receipt.json', 'target_installation', 'NOT_VERIFIED'),
    ('receipt.json', 'transitive_lock_complete', False),
    ('receipt.json', 'failure_code', 'FAILED'),
    ('runtime.json', 'python', '3.12.15'), ('runtime.json', 'system', 'Windows'),
    ('runtime.json', 'machine', 'arm64'), ('runtime.json', 'bits', 32),
    ('runtime.json', 'libc', ['glibc', '2.27']), ('runtime.json', 'libc', ['musl', '2.39']),
    ('runtime.json', 'libc', ['glibc', 'invalid']), ('runtime.json', 'runner', 'self-hosted'),
    ('dependency-verification.json', 'actual_count', 66),
    ('dependency-verification.json', 'expected_count', 68),
    ('dependency-verification.json', 'installed_set_verified', False),
    ('tests.json', 'passed', 147), ('tests.json', 'failed', 1),
    ('tests.json', 'errors', 1), ('tests.json', 'skipped', 1),
    ('artifact-index.json', 'artifact_size', 5606),
    ('artifact-index.json', 'artifact_id', 13474492281),
    ('artifact-index.json', 'artifact_digest', 'sha256:' + 'f' * 64),
    ('artifact-index.json', 'target_sha', 'f' * 40),
    ('artifact-index.json', 'run_id', '42156106472'),
])
def test_d_identity_and_runtime_tampering_refused(bundle, name, field, value):
    edit(bundle, name, lambda d: d.update({field: value}))
    refused(bundle)


@pytest.mark.parametrize('mode', ['missing_stage', 'failed_stage', 'missing_package',
                                  'extra_package', 'version', 'hash', 'filename', 'extra_field'])
def test_d_nested_tampering(bundle, mode):
    if mode in ('missing_stage', 'failed_stage'):
        def mutate(d):
            if mode == 'missing_stage':
                d['stages'].pop('wheelhouse')
            else:
                d['stages']['wheelhouse'] = 'FAIL'
        edit(bundle, 'receipt.json', mutate)
    else:
        def mutate(d):
            if mode == 'missing_package':
                d['distributions'].pop('alembic')
            elif mode == 'extra_package':
                d['distributions']['pip'] = d['distributions']['alembic']
            else:
                d['distributions']['alembic'][mode] = 'forged'
        edit(bundle, 'dependency-verification.json', mutate)
    refused(bundle)


def test_old_offline_not_verified_is_not_installation(bundle):
    path = bundle / (e.RUN_DIR + 'receipt.json')
    path.write_bytes((ROOT / 'docs/acceptance/biz_perf_04_d_validation.json').read_bytes())
    doc = manifest(bundle)
    next(x for x in doc['evidence'] if x['path'].endswith('/receipt.json'))['sha256'] = \
        e.sha(path.read_bytes())
    save_manifest(bundle, doc)
    refused(bundle)


def test_failure_does_not_replace_valid_report(bundle, capsys):
    assert e.main(['--root', str(bundle)]) == 0
    original = (bundle / e.REPORT).read_bytes()
    edit(bundle, 'receipt.json', lambda d: d.update(status='INCOMPLETE'))
    capsys.readouterr()
    assert e.main(['--root', str(bundle)]) == 1
    assert (bundle / e.REPORT).read_bytes() == original
    assert 'INTEGRITY_VALID' not in capsys.readouterr().out


def test_atomic_replace_failure_preserves_previous(bundle, monkeypatch):
    old = b'previous-valid-report'
    (bundle / e.REPORT).write_bytes(old)

    def fail(*args):
        raise OSError('injected')

    monkeypatch.setattr(e.os, 'replace', fail)
    assert e.main(['--root', str(bundle)]) == 1
    assert (bundle / e.REPORT).read_bytes() == old
    assert not list((bundle / e.REPORT).parent.glob('.biz04-e-*'))


@pytest.mark.parametrize('relative', ['requirements.lock', 'secret.json', '../outside',
                                      'docs/acceptance/other.json'])
def test_only_fixed_report_output_is_writable(bundle, relative):
    assert e.main(['--root', str(bundle), '--report', relative]) == 1
    assert not (bundle / e.REPORT).exists()


def test_unapproved_manifest_refused_without_reading(bundle, monkeypatch):
    def fail(*args):
        pytest.fail('unapproved input was opened')

    monkeypatch.setattr(e, 'read_file', fail)
    with pytest.raises(ValueError, match='UNAPPROVED_MANIFEST'):
        e.validate(bundle, 'private.json')


def test_manifest_budget_before_parse(bundle):
    (bundle / e.MANIFEST).write_bytes(b' ' * (e.MAX_MANIFEST_BYTES + 1))
    refused(bundle)


def test_json_damage_in_evidence_is_refused_after_rehash(bundle):
    doc = manifest(bundle)
    item = doc['evidence'][0]
    raw = b'{"schema":"one","schema":"two"}'
    (bundle / item['path']).write_bytes(raw)
    item['sha256'] = e.sha(raw)
    save_manifest(bundle, doc)
    refused(bundle)


@pytest.mark.parametrize('relative', [e.MANIFEST, e.RUN_DIR + 'receipt.json'])
def test_report_cannot_overwrite_input(bundle, relative):
    before = (bundle / relative).read_bytes()
    assert e.main(['--root', str(bundle), '--report', relative]) == 1
    assert (bundle / relative).read_bytes() == before


def test_standard_library_only_and_no_business_execution():
    source = (ROOT / 'scripts/business_evidence_bundle.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    imports = {n.module.split('.')[0] if isinstance(n, ast.ImportFrom) else a.name.split('.')[0]
               for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
               for a in n.names}
    assert imports <= {'argparse', 'hashlib', 'json', 'math', 'os', 're', 'stat',
                       'tempfile', 'pathlib'}
    assert not {'backend', 'app', 'sqlalchemy', 'psycopg', 'fastapi', 'socket',
                'urllib', 'subprocess'} & imports
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id in ('eval', 'exec', '__import__') for n in ast.walk(tree))
    assert not any(isinstance(n, ast.Attribute) and n.attr in ('environ', 'getenv', 'system',
                                                              'popen', 'spawn', 'fork')
                   for n in ast.walk(tree))
    assert 'DATABASE_URL' not in source and '.env' not in source
    assert len(list((ROOT / '.github/workflows').glob('*.yml'))) == 8
