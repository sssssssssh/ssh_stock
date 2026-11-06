"""04-E fixed historical evidence index. Offline integrity is not execution authority."""

import argparse
import hashlib
import json
import math
import os
import re
import stat
import tempfile
from pathlib import Path

SCHEMA = 'biz-perf-04-e.evidence-bundle.v1'
REPORT_SCHEMA = 'biz-perf-04-e.validation.v1'
MANIFEST = 'docs/acceptance/biz_perf_04_e_bundle.json'
REPORT = 'docs/acceptance/biz_perf_04_e_validation.json'
RUN = '42156106471'
TARGET = 'ab5e29df5aa230076069dd587557720c2db382dc'
RUN_DIR = 'docs/acceptance/biz_perf_04_d_runs/' + RUN + '/'
MAX_FILE_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
NON_CLAIMS = [
    'PERFORMANCE_ACCEPTANCE_NOT_CLAIMED', 'CAPACITY_ACCEPTANCE_NOT_CLAIMED',
    'PRODUCTION_READ_AUTHORIZATION_NOT_CLAIMED',
    'BUSINESS_DATABASE_EXECUTION_NOT_PERFORMED', 'WORKER_EXECUTION_NOT_PERFORMED',
]
SOURCES = {
    '04-A': '9df4cfed0d0153b09b0f4038882fa8423fe732e1',
    '04-B': 'decaaba86535575e307edd676221ec066517caf6',
    '04-C': 'c397821d45c755473bf627a40392d392bd1eab2b',
    '04-D-lock': '4fe37aee77570b3377fb5ff41b85ab9e49fbbcef',
    '04-D': TARGET,
}
# Version v1 deliberately identifies only these immutable historical records. New runs
# need a separately reviewed contract version; rehashing a forgery cannot authorize it.
RECORDS = (
    ('04-A', 'offline_contract_validation', 'biz-perf-04-a.offline.v1',
     'biz_perf_04_a_offline.json',
     '899490c051daa126753a36106b9261e173ec2fcf45a9ed091ab25fd021f1ab98'),
    ('04-A', 'historical_run_reference', 'markdown.v1', 'BIZ_PERF_04_A.md',
     '5644a2870eb40dca6cca846c2c745f4dec08bfdbb5821ea5300da618a1577c09'),
    ('04-B', 'synthetic_generation_metadata', 'biz04-b.offline-generation.v1',
     'biz_perf_04_b_generation.json',
     '2681fe0c949a15143e7d8e65b7d07760d1e53d7984d282aa68d6ce49ac820250'),
    ('04-B', 'offline_contract_validation', 'biz04-b.offline-validation.v1',
     'biz_perf_04_b_validation.json',
     '0c8bba2478427fdafa17c26ea73c10154bb6979453922acd1810b680f15e61f4'),
    ('04-C', 'offline_contract_validation', 'biz04-c.offline-validation.v1',
     'biz_perf_04_c_validation.json',
     'b8c430a0ed756295fc68e2930699a4d82ed789a102bb7b97c56885763cbd33dd'),
    ('04-C', 'source_identity_reference', 'markdown.v1', 'BIZ_PERF_04_C.md',
     'acc148ed49802e4fc4dae51295171545a70d634944043e491976f6e20dcb1669'),
    ('04-D', 'source_identity_reference', 'biz-perf-04-d.linux-lock.v1',
     'biz_perf_04_d_lock.json',
     '7229e81eb2bb7e1f50a304334b702481e02785b3a898c9e1a4c7ce90a8fb6c0c'),
    ('04-D', 'runtime_installation_receipt', 'installation-receipt.fields.v1',
     'biz_perf_04_d_runs/' + RUN + '/receipt.json',
     'c600d0468877d52c744371c7b1baaea5aa10b1f341228ec6a3b201abd6dec372'),
    ('04-D', 'runtime_installation_receipt', 'installation-runtime.fields.v1',
     'biz_perf_04_d_runs/' + RUN + '/runtime.json',
     'e2f525eab130f33b2a9e9c70e217e675d6f1a7e18d19e72ad4ef809787cf5f84'),
    ('04-D', 'runtime_installation_receipt', 'installation-dependencies.fields.v1',
     'biz_perf_04_d_runs/' + RUN + '/dependency-verification.json',
     'ecb21a5995585c5717cb78b5c86a28f3a6125f5b7841e7fdceed7d15169c5aaa'),
    ('04-D', 'runtime_installation_receipt', 'installation-tests.fields.v1',
     'biz_perf_04_d_runs/' + RUN + '/tests.json',
     '7bb8ff898888eeab9826ee811f3057c365b89816a2e81df100c5d566c4ecf908'),
)
CLAIMS = {
    '04-A': ('SQL_TERMINAL_SNAPSHOT_OFFLINE_CONTRACT',
             ['HISTORICAL_SELECT_UPDATE_ATTRIBUTION_UNKNOWN', 'HISTORICAL_ROOT_NOT_RETESTED']),
    '04-B': ('S1_S4_SYNTHETIC_METADATA_ONLY',
             ['RAW_JSONL_NOT_ARCHIVED', 'REAL_MARKET_NOT_CLAIMED', 'PG_LOAD_NOT_PERFORMED']),
    '04-C': ('INDEPENDENT_STATUS_CONTRACT_ONLY',
             ['RESOURCE_PROBE_NOT_ASSESSED', 'CAPACITY_NOT_ASSESSED',
              'PERFORMANCE_ELIGIBILITY_NOT_ASSESSED', 'PRODUCTION_READ_NOT_ASSESSED']),
    '04-D': ('EXACT_RUN_LINUX_INSTALLATION_ONLY',
             ['BUSINESS_CHAIN_NOT_VERIFIED', 'PG_WORKER_NOT_EXECUTED']),
}
STAGES = {'preflight', 'source_binding', 'runtime_and_venv', 'wheelhouse',
          'preinstall_contract', 'install_and_pip_check', 'installed_contract_and_tests'}


def require(value, code='BIZ04_E_INVALID'):
    if not value:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return sha(canonical(value))


def fields(value, expected):
    require(type(value) is dict and set(value) == set(expected))


def integer(value, expected):
    require(type(value) is int and value == expected)


def hex_value(value, length=64):
    require(type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value))


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'BIZ04_E_DUPLICATE_KEY')
        result[key] = value
    return result


def finite(value):
    value = float(value)
    require(math.isfinite(value))
    return value


def invalid_constant(value):
    raise ValueError('BIZ04_E_NONFINITE_JSON')


def parse(raw):
    require(len(raw) <= MAX_FILE_BYTES)
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                       parse_float=finite, parse_constant=invalid_constant)

    def depth(item, level=0):
        require(level <= 32, 'BIZ04_E_JSON_DEPTH')
        if type(item) is dict:
            for child in item.values():
                depth(child, level + 1)
        elif type(item) is list:
            for child in item:
                depth(child, level + 1)

    depth(value)
    return value


def safe_path(root, relative):
    require(type(relative) is str and len(relative) <= 240
            and re.fullmatch(r'[A-Za-z0-9_./-]+', relative)
            and all(part not in ('', '.', '..') for part in relative.split('/')),
            'BIZ04_E_UNSAFE_PATH')
    root = Path(root).absolute()
    require(all(not p.is_symlink() and not (hasattr(p, 'is_junction') and p.is_junction())
                for p in (root, *root.parents)), 'BIZ04_E_UNSAFE_PATH')
    path = root.joinpath(*relative.split('/'))
    require(path.is_relative_to(root), 'BIZ04_E_UNSAFE_PATH')
    for part in (path, *path.parents):
        require(not part.is_symlink()
                and not (hasattr(part, 'is_junction') and part.is_junction()),
                'BIZ04_E_UNSAFE_PATH')
    return path


def read_file(root, relative, limit=MAX_FILE_BYTES):
    path = safe_path(root, relative)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, 'BIZ04_E_FILE_TYPE_SIZE')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                 | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        require(stat.S_ISREG(opened.st_mode) and opened.st_ino == before.st_ino
                and opened.st_dev == before.st_dev and opened.st_size <= limit)
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    require(len(raw) <= limit and len(raw) == before.st_size == after.st_size
            and before.st_mtime_ns == after.st_mtime_ns)
    return raw


def entry(stage, kind, schema, name, checksum):
    source = SOURCES['04-D-lock'] if name == 'biz_perf_04_d_lock.json' else SOURCES[stage]
    return dict(stage=stage, evidence_kind=kind, schema=schema, source_commit_sha=source,
                path='docs/acceptance/' + name, sha256=checksum,
                claim_scope=dict(supports=CLAIMS[stage][0],
                                 excludes=CLAIMS[stage][1] + NON_CLAIMS))


def index_expected():
    return dict(
        schema='biz-perf-04-d.artifact-index.v1', run_id=RUN, attempt='1', target_sha=TARGET,
        event='workflow_dispatch', branch='master', status='completed', conclusion='success',
        job_id=127690531459, job_name='installation', artifact_id=13474492280,
        artifact_name='biz-perf-04-d-install-' + TARGET + '-' + RUN + '-1',
        artifact_size=5605,
        artifact_digest='sha256:735addf5df05b36eba923ac4d8cbb257c8fafceb05a069c687ffba1fa67b0a13',
        run_url='https://github.com/sssssssssh/ssh_stock/actions/runs/' + RUN,
        artifact_url='https://api.github.com/repos/sssssssssh/ssh_stock/actions/artifacts/13474492280',
        expires_at='2026-11-13T03:22:47Z',
        files={record[3].rsplit('/', 1)[-1]: record[4] for record in RECORDS[7:]})


def expected_entries():
    result = [entry(*record) for record in RECORDS]
    result.append(entry('04-D', 'runtime_installation_receipt',
                        'biz-perf-04-d.artifact-index.v1',
                        'biz_perf_04_d_runs/' + RUN + '/artifact-index.json',
                        sha(canonical(index_expected()) + b'\n')))
    return result


def check_tests(value, count, *, strings=False):
    key = 'failures' if strings else 'failed'
    for field, expected in [('tests', count), (key, 0), ('errors', 0), ('skipped', 0)]:
        if strings:
            require(type(value[field]) is str and value[field] == str(expected))
        else:
            integer(value[field], expected)


def zeroes(value, names):
    for name in names:
        integer(value[name], 0)


def semantic_check(values):
    a = values['biz_perf_04_a_offline.json']
    require(a['schema'] == 'biz-perf-04-a.offline.v1'
            and a['historical_select_update_attribution'] == 'UNKNOWN')
    zeroes(a, ('performance_runs', 'database_connections', 'workflow_dispatches'))
    b = values['biz_perf_04_b_generation.json']
    require(b['schema'] == 'biz04-b.offline-generation.v1'
            and b['workload'] == 'FILE_GENERATION_VALIDATION_ONLY')
    require(type(b['runs']) is list and len(b['runs']) == 4)
    require({r['scale'] for r in b['runs']} == {'S1', 'S2', 'S3', 'S4'})
    for run in b['runs']:
        hex_value(run['dataset_sha256'])
        require(run['equal'] is True)
        rows = {'S1': 2660, 'S2': 99750, 'S3': 500080, 'S4': 1439725}[run['scale']]
        integer(run['config']['expected_raw_rows'], rows)
        require(run['config']['scale'] == run['scale'])
        for table in ('stock_daily', 'stock_daily_basic', 'stock_adj_factor', 'stock_limit_daily'):
            integer(run['tables'][table]['rows'], rows)
    bv = values['biz_perf_04_b_validation.json']
    require(bv['schema'] == 'biz04-b.offline-validation.v1'
            and bv['large_generation_in_default_ci'] is False)
    check_tests(bv['junit'], 413, strings=True)
    zeroes(bv, ('worker_roots', 'database_connections', 'workflow_dispatches'))
    c = values['biz_perf_04_c_validation.json']
    require(c['schema'] == 'biz04-c.offline-validation.v1')
    check_tests(c['tests'], 442, strings=True)
    zeroes(c, ('worker_roots', 'database_connections', 'capacity_experiments',
               'workflow_dispatches'))
    # No invented 04-C state document or runtime observation is synthesized here.
    receipt, runtime, dependencies, tests = (values[n] for n in (
        'receipt.json', 'runtime.json', 'dependency-verification.json', 'tests.json'))
    fields(receipt, ('attempt', 'exit_code', 'failure_code', 'run_id', 'stages', 'status',
                     'target_installation', 'target_sha', 'transitive_lock_complete',
                     'workflow_blob', 'workflow_sha256'))
    require(receipt['run_id'] == RUN and receipt['attempt'] == '1'
            and receipt['target_sha'] == TARGET and receipt['status'] == 'COMPLETE'
            and receipt['failure_code'] is None and receipt['target_installation'] == 'VERIFIED'
            and receipt['transitive_lock_complete'] is True)
    integer(receipt['exit_code'], 0)
    fields(receipt['stages'], STAGES)
    require(all(v == 'PASS' for v in receipt['stages'].values()))
    fields(runtime, ('bits', 'implementation', 'libc', 'machine', 'python', 'releaselevel',
                     'runner', 'runner_arch', 'runner_os', 'system', 'toolchain'))
    require(runtime['implementation'] == 'cpython' and runtime['python'] == '3.12.14'
            and runtime['system'] == 'Linux' and runtime['machine'] == 'x86_64'
            and runtime['releaselevel'] == 'final' and runtime['runner'] == 'github-hosted'
            and runtime['runner_arch'] == 'X64' and runtime['runner_os'] == 'Linux')
    integer(runtime['bits'], 64)
    libc = runtime['libc']
    require(type(libc) is list and len(libc) == 2 and libc[0] == 'glibc'
            and type(libc[1]) is str and re.fullmatch(r'\d+\.\d+(?:\.\d+)*', libc[1]))
    require(tuple(map(int, libc[1].split('.')[:2])) >= (2, 28))
    fields(runtime['toolchain'], ('pip',))
    require(runtime['toolchain']['pip'] == '25.0.1')
    fields(dependencies, ('actual_count', 'distributions', 'expected_count', 'hashes',
                          'installed_set_verified'))
    integer(dependencies['actual_count'], 67)
    integer(dependencies['expected_count'], 67)
    require(dependencies['installed_set_verified'] is True)
    lock = values['biz_perf_04_d_lock.json']
    require(lock['schema'] == 'biz-perf-04-d.linux-lock.v1')
    records = lock['distributions']
    require(len(records) == 67 and len(lock['direct']) == 22
            and set(dependencies['distributions']) == set(records)
            and not {'pip', 'wheel', 'setuptools'} & set(records))
    for name, record in dependencies['distributions'].items():
        fields(record, ('filename', 'sha256', 'version'))
        require(record == {k: records[name][k] for k in record})
    require(dependencies['hashes']['docs/acceptance/biz_perf_04_d_lock.json']
            == next(r[4] for r in RECORDS if r[3] == 'biz_perf_04_d_lock.json'))
    require(dependencies['hashes']['requirements.lock'] == lock['root_sha256']
            and dependencies['hashes']['requirements-biz-perf-linux-py312-v1.lock']
            == lock['lock_sha256']
            and dependencies['hashes']['.github/workflows/biz-perf-04-d-linux-install.yml']
            == receipt['workflow_sha256'])
    fields(tests, ('errors', 'exit_code', 'failed', 'files', 'passed', 'skipped', 'tests'))
    check_tests(tests, 148)
    integer(tests['passed'], 148)
    integer(tests['exit_code'], 0)
    require(tests['files'] == ['tests/unit/test_biz_perf_04_d.py',
                               'tests/unit/test_biz_perf_04_d_linux_install.py'])
    require(canonical(values['artifact-index.json']) == canonical(index_expected()))


def validate(root, manifest=MANIFEST):
    require(manifest == MANIFEST, 'BIZ04_E_UNAPPROVED_MANIFEST')
    document = parse(read_file(root, manifest, MAX_MANIFEST_BYTES))
    fields(document, ('schema', 'evidence', 'bundle_sha256'))
    require(document['schema'] == SCHEMA)
    hex_value(document['bundle_sha256'])
    require(document['bundle_sha256'] == digest({k: v for k, v in document.items()
                                               if k != 'bundle_sha256'}))
    entries = document['evidence']
    require(type(entries) is list and len(entries) == 12)
    paths = []
    for item in entries:
        fields(item, ('stage', 'evidence_kind', 'schema', 'source_commit_sha', 'path',
                      'sha256', 'claim_scope'))
        hex_value(item['source_commit_sha'], 40)
        hex_value(item['sha256'])
        safe_path(root, item['path'])
        paths.append(item['path'])
    require(len(set(paths)) == len(paths))
    # Exact versioned metadata forbids privilege claims and unknown nested fields.
    expected = expected_entries()
    require(canonical([{k: v for k, v in e.items() if k != 'sha256'} for e in entries])
            == canonical([{k: v for k, v in e.items() if k != 'sha256'} for e in expected]))
    values = {}
    observed = []
    for item in entries:
        raw = read_file(root, item['path'])
        checksum = sha(raw)
        require(checksum == item['sha256'], 'BIZ04_E_FILE_DIGEST')
        if item['schema'] != 'markdown.v1':
            values[item['path'].rsplit('/', 1)[-1]] = parse(raw)
        observed.append(dict(path=item['path'], sha256=checksum))
    semantic_check(values)
    # Pin the original evidence too: editing bytes AND recomputing the index is not
    # sufficient to rewrite any historical facts or add extra schema fields.
    require(canonical(entries) == canonical(expected), 'BIZ04_E_HISTORICAL_BYTES')
    return dict(schema=REPORT_SCHEMA, integrity='VALID', bundle_sha256=document['bundle_sha256'],
                evidence=observed, non_claims=list(NON_CLAIMS),
                stage_scope={stage: dict(supports=value[0], excludes=list(value[1]))
                             for stage, value in CLAIMS.items()})


def write_report(root, relative, value, manifest=MANIFEST):
    require(relative == REPORT and relative != manifest, 'BIZ04_E_UNAPPROVED_REPORT')
    path = safe_path(root, relative)
    require(path.parent.is_dir() and (not path.exists() or path.is_file()))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.biz04-e-', delete=False) as f:
            temporary = Path(f.name)
            f.write(canonical(value) + b'\n')
            f.flush()
            os.fsync(f.fileno())
        safe_path(root, relative)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.')
    parser.add_argument('--manifest', default=MANIFEST)
    parser.add_argument('--report', default=REPORT)
    args = parser.parse_args(argv)
    try:
        result = validate(args.root, args.manifest)
        write_report(args.root, args.report, result, args.manifest)
    except (ValueError, OSError, KeyError, TypeError, RecursionError):
        print('BIZ04_E_VALIDATION_REFUSED')
        return 1
    print('BIZ04_E_INTEGRITY_VALID_NOT_EXECUTION_AUTHORITY')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
