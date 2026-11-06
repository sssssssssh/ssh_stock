"""Offline only: fake HTTP, subprocesses and temporary files, no live installation."""

import ast
import json
import subprocess
import zipfile
from pathlib import Path

import pytest
import yaml

from scripts import business_dependency_linux_install as b


def context():
    sha = 'a' * 40
    return dict(GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_REPOSITORY='sssssssssh/ssh_stock',
        GITHUB_REF='refs/heads/master', GITHUB_SHA=sha, RUNNER_ENVIRONMENT='github-hosted',
        RUNNER_OS='Linux', RUNNER_ARCH='X64'), dict(target_sha=sha,
        expected_lock_sha256='b' * 64, confirm_installation=True)


def runtime():
    return dict(implementation='cpython', python='3.12.14', releaselevel='final',
        system='Linux', machine='x86_64', bits=64, libc=['glibc', '2.39'],
        prefix='synthetic-prefix', base_prefix='synthetic-base')


@pytest.mark.parametrize('key,value', [
    ('GITHUB_EVENT_NAME', 'push'), ('GITHUB_REF', 'refs/heads/other'),
    ('GITHUB_REPOSITORY', 'other/repo'), ('GITHUB_SHA', 'c' * 40),
    ('RUNNER_ENVIRONMENT', 'self-hosted'), ('RUNNER_OS', 'Windows'), ('RUNNER_ARCH', 'ARM64'),
    ('target_sha', 'short'), ('target_sha', 'G' * 40), ('confirm_installation', False),
    ('confirm_installation', 'true'), ('expected_lock_sha256', 'z' * 64),
])
def test_identity_refuses_before_commands(key, value):
    env, inputs = context()
    b.preflight(env, inputs)
    (env if key in env else inputs)[key] = value
    with pytest.raises(b.Refused):
        b.preflight(env, inputs)


@pytest.mark.parametrize('key,value', [
    ('python', '3.12.15'), ('implementation', 'pypy'), ('releaselevel', 'candidate'),
    ('system', 'Darwin'), ('machine', 'aarch64'), ('bits', 32),
    ('libc', ['glibc', '2.27']), ('libc', ['musl', '1.2']), ('libc', ['', '']),
])
def test_exact_runtime_and_libc_required(key, value):
    value_map = runtime()
    b.check_runtime(value_map)
    value_map[key] = value
    with pytest.raises(b.Refused):
        b.check_runtime(value_map)


def record():
    return dict(version='1.0', filename='synthetic-1.0-py3-none-any.whl',
                sha256=b.sha(b'approved-wheel'))


def metadata(value=None):
    r = value or record()
    return dict(info={'version': r['version']}, urls=[dict(filename=r['filename'],
        packagetype='bdist_wheel', digests={'sha256': r['sha256']},
        url='https://files.pythonhosted.org/packages/' + r['filename'])])


@pytest.mark.parametrize('mode', ['valid', 'missing', 'duplicate', 'sdist', 'hash',
                                  'version', 'http', 'foreign', 'userinfo', 'query'])
def test_official_metadata_exact_file_and_hash(mode):
    m = metadata()
    if mode == 'missing':
        m['urls'] = []
    elif mode == 'duplicate':
        m['urls'] *= 2
    elif mode == 'sdist':
        m['urls'][0]['packagetype'] = 'sdist'
    elif mode == 'hash':
        m['urls'][0]['digests']['sha256'] = '0' * 64
    elif mode == 'version':
        m['info']['version'] = '2.0'
    elif mode == 'http':
        m['urls'][0]['url'] = 'http://files.pythonhosted.org/a.whl'
    elif mode == 'foreign':
        m['urls'][0]['url'] = 'https://evil.invalid/a.whl'
    elif mode == 'userinfo':
        m['urls'][0]['url'] = 'https://user@files.pythonhosted.org/a.whl'
    elif mode == 'query':
        m['urls'][0]['url'] += '?token=private'
    calls = []

    def get(url, host, **kwargs):
        calls.append((url, host))
        return json.dumps(m).encode()

    if mode == 'valid':
        assert b.approved_url('synthetic', record(), get=get).startswith(
            'https://files.pythonhosted.org/')
    else:
        with pytest.raises(b.Refused):
            b.approved_url('synthetic', record(), get=get)
    assert len(calls) == 1 and calls[0][1] == 'pypi.org'


@pytest.mark.parametrize('url', ['https://evil.invalid/a', 'http://pypi.org/a',
                                  'https://pypi.org:444/a'])
def test_redirect_outside_official_host_refused(url):
    with pytest.raises(b.Refused):
        b.OfficialRedirects().redirect_request(
            b.urllib.request.Request('https://pypi.org/a'), None, 302, '', {}, url)


@pytest.mark.parametrize('failure', [None, 'hash', 'network', 'extra', 'missing', 'duplicate'])
def test_new_wheelhouse_hash_and_exact_inventory(tmp_path, failure):
    directory = tmp_path / 'wheels'
    records = {'synthetic': record()}
    if failure == 'duplicate':
        records['other'] = record()

    def get(url, host, **kwargs):
        if failure == 'network':
            raise OSError('private network error')
        return json.dumps(metadata()).encode() if host == 'pypi.org' else (
            b'wrong' if failure == 'hash' else b'approved-wheel')

    if failure in ('hash', 'network', 'duplicate'):
        with pytest.raises((b.Refused, OSError)):
            b.download_wheels(directory, records, get=get)
        return
    b.download_wheels(directory, records, get=get)
    if failure == 'extra':
        (directory / 'unapproved.tar.gz').write_bytes(b'x')
    elif failure == 'missing':
        (directory / record()['filename']).unlink()
    if failure:
        with pytest.raises(b.Refused):
            b.check_wheelhouse(directory, records)
    with pytest.raises(FileExistsError):
        b.download_wheels(directory, records, get=get)


@pytest.mark.parametrize('filename', ['../escape.whl', '/tmp/escape.whl',
                                    'dir\\escape.whl', 'synthetic.tar.gz'])
def test_unapproved_wheel_paths_refused(filename):
    r = record()
    r['filename'] = filename
    with pytest.raises(b.Refused):
        b.approved_url('synthetic', r, get=lambda *a, **k: pytest.fail('no network'))


def test_install_command_keeps_resolver_hashes_and_no_index(tmp_path):
    args = b.install_args(tmp_path / 'python', tmp_path / 'wheels', tmp_path / 'report')
    assert args[1:4] == ['-m', 'pip', 'install']
    for value in ('--no-index', '--find-links', '--only-binary=:all:', '--require-hashes',
                  '--no-cache-dir', '--report', b.LOCK):
        assert value in args
    assert not set(args) & {'--no-deps', '--ignore-installed', '--trusted-host',
        '--extra-index-url', '--pre', '--upgrade', '--no-binary'}


@pytest.mark.parametrize('failure', ['exit', 'timeout'])
def test_subprocess_nonzero_or_timeout_is_fail_closed(tmp_path, monkeypatch, failure):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(args, 1, output=b'private stdout')
        return subprocess.CompletedProcess(args, 1, b'private stdout', b'private stderr')

    monkeypatch.setattr(b.subprocess, 'run', run)
    with pytest.raises(b.Refused, match='OFFLINE_INSTALL_FAILED'):
        b.command(['synthetic-command'], tmp_path, 'OFFLINE_INSTALL_FAILED', timeout=1)
    assert len(calls) == 1 and calls[0][1]['shell'] is False
    assert calls[0][1]['timeout'] == 1
    assert b'private stdout' in (tmp_path / 'commands.log').read_bytes()


def test_child_environment_has_no_business_secrets_or_pythonpath(tmp_path, monkeypatch):
    for name in ('DATABASE_URL', 'TEST_DATABASE_URL', 'TUSHARE_TOKEN', 'LLM_API_KEY',
                 'GITHUB_TOKEN', 'PIP_INDEX_URL', 'PYTHONPATH'):
        monkeypatch.setenv(name, 'secret')
    result = b.child_env(tmp_path)
    assert not set(result) & {'DATABASE_URL', 'TEST_DATABASE_URL', 'TUSHARE_TOKEN',
        'LLM_API_KEY', 'GITHUB_TOKEN', 'PIP_INDEX_URL', 'PYTHONPATH'}
    assert result['PIP_CONFIG_FILE'] == b.os.devnull


@pytest.mark.parametrize('failure', [None, 'head', 'lock', 'root', 'manifest'])
def test_source_and_lock_binding_before_install(tmp_path, monkeypatch, failure):
    env, inputs = context()
    raw_root, raw_lock = b'original-root\n', b'original-target-lock\n'
    inputs['expected_lock_sha256'] = b.sha(raw_lock)
    manifest = dict(schema='biz-perf-04-d.linux-lock.v1', root_sha256=b.sha(raw_root),
        lock_sha256=b.sha(raw_lock), direct={str(i): {} for i in range(22)},
        distributions={str(i): {} for i in range(67)})
    paths = {'requirements.lock': raw_root, b.LOCK: raw_lock,
        b.MANIFEST: json.dumps(manifest).encode(), b.CONTRACT: b'original-validator',
        b.WORKFLOW: b'approved-workflow'}
    if failure == 'lock':
        inputs['expected_lock_sha256'] = '0' * 64
    elif failure == 'root':
        paths['requirements.lock'] = b'changed-root'
    elif failure == 'manifest':
        manifest['direct'].pop('0')
        paths[b.MANIFEST] = json.dumps(manifest).encode()
    for name, raw in paths.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    monkeypatch.setattr(b, 'ROOT', tmp_path)
    calls = []

    def run(args, *a):
        calls.append(args)
        if args[:3] == ['git', 'rev-parse', 'HEAD']:
            return (('c' if failure == 'head' else 'a') * 40).encode()
        if args[1] == 'diff':
            return b''
        return b'd' * 40

    if failure:
        with pytest.raises(b.Refused):
            b.bind_source(inputs, tmp_path, run=run)
    else:
        _, hashes, blob = b.bind_source(inputs, tmp_path, run=run)
        assert hashes[b.LOCK] == inputs['expected_lock_sha256'] and blob == 'd' * 40
        assert any(a[:3] == ['git', 'diff', '--exit-code'] for a in calls)


@pytest.mark.parametrize('mutation', ['report-version', 'package-version', 'duplicate',
                                    'missing', 'hash', 'environment'])
def test_unchanged_validator_refuses_bad_complete_install_reports(mutation):
    from scripts import business_dependency_contract as contract

    m = json.loads((b.ROOT / b.MANIFEST).read_bytes())
    report = dict(version='1', environment=contract.TARGET.copy(), install=[dict(
        metadata=dict(name=k, version=v['version']), download_info=dict(archive_info=dict(
            hashes=dict(sha256=v['sha256'])))) for k, v in m['distributions'].items()])
    assert contract.validate_install_report(report, m) is True
    if mutation == 'report-version':
        report['version'] = '2'
    elif mutation == 'package-version':
        report['install'][0]['metadata']['version'] = '0.0'
    elif mutation == 'duplicate':
        report['install'].append(report['install'][0])
    elif mutation == 'missing':
        report['install'].pop()
    elif mutation == 'hash':
        report['install'][0]['download_info']['archive_info']['hashes']['sha256'] = '0' * 64
    else:
        report['environment']['python_full_version'] = '3.12.15'
    with pytest.raises(ValueError):
        contract.validate_install_report(report, m)


@pytest.mark.parametrize('system_site', ['false', 'true'])
def test_new_venv_no_system_packages(tmp_path, system_site):
    target = tmp_path / 'venv'
    calls = []

    def run(args, *a, **k):
        calls.append(args)
        target.mkdir()
        (target / 'pyvenv.cfg').write_text('include-system-site-packages = ' + system_site)
        (target / 'bin').mkdir()
        (target / 'bin/python').write_bytes(b'synthetic executable')

    if system_site == 'false':
        assert b.create_venv(target, tmp_path, run=run) == target / 'bin/python'
    else:
        with pytest.raises(b.Refused):
            b.create_venv(target, tmp_path, run=run)
    assert '--copies' in calls[0] and '--system-site-packages' not in calls[0]
    with pytest.raises(b.Refused):
        b.create_venv(target, tmp_path, run=run)


@pytest.mark.parametrize('xml', ['<testsuite><testcase/></testsuite>',
    '<testsuite><testcase><failure/></testcase></testsuite>',
    '<testsuite><testcase><error/></testcase></testsuite>',
    '<testsuite><testcase><skipped/></testcase></testsuite>',
    '<testsuite failures="1"><testcase/></testsuite>', '<testsuite/>', 'malformed'])
def test_junit_actual_cases_and_zero_failures_errors_skips(tmp_path, xml):
    path = tmp_path / 'tests.xml'
    path.write_text(xml)
    if xml == '<testsuite><testcase/></testsuite>':
        assert b.parse_junit(path)['passed'] == 1
    else:
        with pytest.raises((b.Refused, b.ET.ParseError)):
            b.parse_junit(path)
    with pytest.raises(FileNotFoundError):
        b.parse_junit(tmp_path / 'missing.xml')


def public_prefix(tmp_path):
    public = tmp_path / 'public'
    public.mkdir()
    for name in b.FILES:
        b.write_json(public / name, dict(status='NOT_VERIFIED'))
    receipt = dict(status='INCOMPLETE', transitive_lock_complete=False,
        target_installation='NOT_VERIFIED', failure_code=None)
    b.write_json(public / 'receipt.json', receipt)
    return public, receipt


@pytest.mark.parametrize('code', sorted(b.CODES))
def test_any_failure_stays_incomplete_with_no_success_fields(tmp_path, code):
    public, receipt = public_prefix(tmp_path)
    b.finish(public, receipt, code=code)
    actual = json.loads((public / 'receipt.json').read_bytes())
    assert actual['status'] == 'INCOMPLETE' and actual['transitive_lock_complete'] is False
    assert actual['target_installation'] == 'NOT_VERIFIED' and actual['failure_code'] == code
    b.validate_export(public)


@pytest.mark.parametrize('mode', ['extra', 'oversize', 'unknown-field', 'nested-secret'])
def test_export_whitelist_size_and_nested_schema(tmp_path, mode):
    public, _ = public_prefix(tmp_path)
    if mode == 'extra':
        (public / 'install-report.json').write_text('{}')
    elif mode == 'oversize':
        (public / 'tests.json').write_bytes(b' ' * (5 * 1024**2 + 1))
    elif mode == 'unknown-field':
        (public / 'tests.json').write_text('{"private_log":"private"}')
    else:
        (public / 'runtime.json').write_text('{"toolchain":{"secret":"private"}}')
    with pytest.raises(b.Refused):
        b.validate_export(public)


def test_complete_receipt_without_all_real_stage_evidence_refused(tmp_path):
    public, receipt = public_prefix(tmp_path)
    with pytest.raises(b.Refused):
        b.finish(public, receipt, complete=True)


def test_paths_refuse_traversal(tmp_path):
    with pytest.raises(b.Refused):
        b.safe_path(tmp_path / '..' / 'outside')


def test_standard_library_only_and_no_business_imports():
    tree = ast.parse(Path(b.__file__).read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(n.name.split('.')[0] in b.sys.stdlib_module_names for n in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module.split('.')[0] in b.sys.stdlib_module_names


@pytest.mark.parametrize('failure', [None, 'download', 'preinstall', 'install', 'pip-check',
    'missing-report', 'contract', 'test-command', 'junit', 'source-changed'])
def test_entire_orchestration_never_completes_after_any_stage_failure(
        tmp_path, monkeypatch, failure):
    env, inputs = context()
    env.update(RUNNER_TEMP=str(tmp_path), GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1')
    base = tmp_path / 'biz-perf-04-d/123-1'
    base.mkdir(parents=True)
    public, _ = public_prefix(base)
    real_manifest = json.loads((b.ROOT / b.MANIFEST).read_bytes())
    hashes = {k: 'b' * 64 for k in ('requirements.lock', b.LOCK, b.MANIFEST,
                                   b.CONTRACT, b.WORKFLOW)}
    binds = []

    def bind(*args):
        binds.append(1)
        actual = dict(hashes)
        if failure == 'source-changed' and len(binds) > 1:
            actual[b.LOCK] = 'c' * 64
        return real_manifest, actual, 'a' * 40

    def download(*args):
        if failure == 'download':
            raise b.Refused('APPROVED_WHEEL_UNAVAILABLE')

    calls = []

    def run(args, private, code, **kwargs):
        calls.append(args)
        if code == 'OFFLINE_INSTALL_FAILED':
            if failure == 'install':
                raise b.Refused(code)
            if failure != 'missing-report':
                (private / 'install-report.json').write_text('{}')
        elif code == 'PIP_CHECK_FAILED' and failure == 'pip-check':
            raise b.Refused(code)
        elif code == 'DEPENDENCY_CONTRACT_FAILED':
            if failure == ('contract' if '--installed' in args else 'preinstall'):
                raise b.Refused(code)
            return json.dumps(dict(installed_set_verified=failure != 'contract',
                transitive_lock_complete=True, installed_business_count=67,
                target_installation='VERIFIED', toolchain={'pip': '25.0.1'})).encode()
        elif code == 'PLATFORM_MISMATCH':
            value = runtime()
            value.update(prefix=str(private / 'venv'), base_prefix='synthetic-base')
            return json.dumps(value).encode()
        elif code == 'CONTRACT_TEST_FAILED':
            if failure == 'test-command':
                raise b.Refused(code)
            (private / 'tests.xml').write_text('<testsuite><testcase>' + (
                '<skipped/>' if failure == 'junit' else '') + '</testcase></testsuite>')
        return b''

    monkeypatch.setattr(b, 'bind_source', bind)
    monkeypatch.setattr(b, 'runtime_info', runtime)
    monkeypatch.setattr(b, 'download_wheels', download)
    monkeypatch.setattr(b, 'check_wheelhouse', lambda *args: None)
    monkeypatch.setattr(b, 'create_venv', lambda path, private: path / 'bin/python')
    monkeypatch.setattr(b, 'command', run)
    assert b.execute(env, inputs) == (0 if failure is None else 1)
    receipt = json.loads((public / 'receipt.json').read_bytes())
    assert receipt['status'] == ('COMPLETE' if failure is None else 'INCOMPLETE')
    assert receipt['transitive_lock_complete'] is (failure is None)
    if failure:
        assert json.loads((public / 'dependency-verification.json').read_bytes()).get(
            'installed_set_verified') is False
    else:
        assert receipt['workflow_blob'] == 'a' * 40
        assert json.loads((public / 'tests.json').read_bytes())['skipped'] == 0
        assert sum('-m' in a and 'pip' in a and 'install' in a for a in calls) == 1


def test_symlink_inputs_refused_without_real_os_links(tmp_path, monkeypatch):
    original = Path.is_symlink
    target = tmp_path / 'linked'
    monkeypatch.setattr(Path, 'is_symlink', lambda p: p == target or original(p))
    with pytest.raises(b.Refused):
        b.safe_path(target)


def test_exact_67_wheel_files_offline(tmp_path):
    directory = tmp_path / 'wheels'
    directory.mkdir()
    records = {}
    for i in range(67):
        raw = str(i).encode()
        name = 'synthetic' + str(i)
        filename = name + '-1.0-py3-none-any.whl'
        (directory / filename).write_bytes(raw)
        records[name] = dict(filename=filename, sha256=b.sha(raw))
    b.check_wheelhouse(directory, records)
    assert len(records) == 67


@pytest.mark.parametrize('mutation', ['metadata-name', 'metadata-version', 'two-metadata',
                                    'platform'])
def test_original_validator_rejects_wrong_wheel_metadata_and_platform(tmp_path, mutation):
    from scripts import business_dependency_contract as contract

    filename = 'synthetic-1.0-' + (
        'cp312-cp312-win_amd64.whl' if mutation == 'platform' else 'py3-none-any.whl')
    name = 'other' if mutation == 'metadata-name' else 'synthetic'
    version = '2.0' if mutation == 'metadata-version' else '1.0'
    with zipfile.ZipFile(tmp_path / filename, 'w') as archive:
        raw = 'Name: ' + name + '\nVersion: ' + version + '\n'
        archive.writestr('synthetic-1.0.dist-info/METADATA', raw)
        if mutation == 'two-metadata':
            archive.writestr('other-1.0.dist-info/METADATA', raw)
    with pytest.raises(ValueError):
        contract.wheel_records(tmp_path)


def workflow_contract(value):
    assert set(value['on']) == {'workflow_dispatch'}
    inputs = value['on']['workflow_dispatch']['inputs']
    assert set(inputs) == {'target_sha', 'expected_lock_sha256', 'confirm_installation'}
    assert all(v['required'] is True for v in inputs.values())
    assert inputs['confirm_installation']['type'] == 'boolean'
    assert inputs['confirm_installation']['default'] is False
    assert inputs['target_sha']['type'] == inputs['expected_lock_sha256']['type'] == 'string'
    assert value['permissions'] == {'contents': 'read'}
    assert value['concurrency'] == {'group': 'biz-perf-04-d-linux-install',
                                    'cancel-in-progress': False}
    assert set(value['jobs']) == {'installation'}
    job = value['jobs']['installation']
    assert job['runs-on'] == 'ubuntu-24.04' and job['timeout-minutes'] == 20
    assert not set(job) & {'environment', 'services', 'strategy', 'container'}
    steps = job['steps']
    assert len(steps) == 7 and steps[0]['id'] == 'guard'
    assert steps[1]['with'] == {'ref': '${{ inputs.target_sha }}', 'persist-credentials': False}
    assert steps[2]['id'] == 'binding' and '--bind-only' in steps[2]['run']
    assert steps[3]['with'] == {'python-version': '3.12.14', 'architecture': 'x64',
                               'check-latest': False}
    pins = {'actions/checkout': '11d5960a326750d5838078e36cf38b85af677262',
            'actions/setup-python': 'a26af69be951a213d495a4c3e4e4022e16d87065',
            'actions/upload-artifact': 'ea165f8d65b6e75b540449e92b4886f43607fa02'}
    assert {s['uses'] for s in steps if 'uses' in s} == {k+'@'+v for k, v in pins.items()}
    assert steps[-1]['if'] == steps[-2]['if'] == 'always()'
    assert steps[-1]['with']['if-no-files-found'] == 'error'
    assert steps[-1]['with']['retention-days'] == 7
    assert len(steps[-1]['with']['path'].splitlines()) == 4
    assert not any(k in json.dumps(value) for k in ('secrets.', 'continue-on-error', 'cache:'))


def test_real_workflow_contract_and_bootstrap_compile():
    value = yaml.safe_load((b.ROOT / b.WORKFLOW).read_text(encoding='utf-8'))
    workflow_contract(value)
    for step in value['jobs']['installation']['steps']:
        if "<<'PY'" in step.get('run', ''):
            code = step['run'].split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
            compile(code, '<offline-workflow>', 'exec')


@pytest.mark.parametrize('failure', [None, 'confirmation', 'branch', 'sha', 'lock'])
def test_precheckout_bootstrap_writes_only_incomplete_prefix(tmp_path, monkeypatch, failure):
    value = yaml.safe_load((b.ROOT / b.WORKFLOW).read_text(encoding='utf-8'))
    code = value['jobs']['installation']['steps'][0]['run'].split("<<'PY'\n", 1)[1]
    code = code.rsplit('\nPY', 1)[0]
    env, inputs = context()
    if failure == 'confirmation':
        inputs['confirm_installation'] = 'true'
    elif failure == 'branch':
        env['GITHUB_REF'] = 'refs/heads/other'
    elif failure == 'sha':
        inputs['target_sha'] = 'not-a-sha-secret'
    elif failure == 'lock':
        inputs['expected_lock_sha256'] = 'wrong'
    env.update(RUNNER_TEMP=str(tmp_path), GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1',
        GITHUB_ENV=str(tmp_path / 'github-env'), BIZ04_INPUTS=json.dumps(inputs))
    for key, val in env.items():
        monkeypatch.setenv(key, val)
    if failure:
        with pytest.raises(SystemExit) as error:
            exec(compile(code, '<offline-precheckout>', 'exec'), {})
        assert error.value.code == 1
    else:
        exec(compile(code, '<offline-precheckout>', 'exec'), {})
    public = tmp_path / 'biz-perf-04-d/123-1/public'
    b.validate_export(public)
    receipt = json.loads((public / 'receipt.json').read_bytes())
    assert receipt['status'] == 'INCOMPLETE' and receipt['transitive_lock_complete'] is False
    assert not (public.parent / 'private').exists()
    assert 'not-a-sha-secret' not in (public / 'receipt.json').read_text()


@pytest.mark.parametrize('failure', [False, True])
def test_prebind_checks_before_python_setup_without_installing(tmp_path, monkeypatch, failure):
    env, inputs = context()
    env.update(RUNNER_TEMP=str(tmp_path), GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1')
    base = tmp_path / 'biz-perf-04-d/123-1'
    base.mkdir(parents=True)
    public, _ = public_prefix(base)
    hashes = {p: 'b' * 64 for p in ('requirements.lock', b.LOCK, b.MANIFEST,
                                   b.CONTRACT, b.WORKFLOW)}

    def bind(*args):
        if failure:
            raise b.Refused('LOCK_SHA256_MISMATCH')
        return {}, hashes, 'a' * 40

    monkeypatch.setattr(b, 'bind_source', bind)
    monkeypatch.setattr(b, 'command', lambda *a, **k: pytest.fail('no real commands'))
    assert b.prebind(env, inputs) == (1 if failure else 0)
    receipt = json.loads((public / 'receipt.json').read_bytes())
    assert receipt['status'] == 'INCOMPLETE' and not receipt['transitive_lock_complete']
    assert not (base / 'private').exists()


def test_ninth_unknown_workflow_is_still_refused(tmp_path, monkeypatch):
    from tests.unit import test_a4_ci_governance as legacy

    target = tmp_path / '.github/workflows'
    target.mkdir(parents=True)
    for name in b.ROOT.joinpath('.github/workflows').glob('*.yml'):
        (target / name.name).write_text(name.read_text(encoding='utf-8'))
    (target / 'unapproved-ninth.yml').write_text('name: unapproved')
    monkeypatch.setattr(legacy, 'ROOT', tmp_path)
    with pytest.raises(AssertionError):
        legacy.test_inventory_covers_every_workflow_and_no_hidden_trigger_chain()


@pytest.mark.parametrize('mutation', ['trigger', 'permissions', 'environment', 'services',
    'matrix', 'timeout', 'python', 'cache', 'pin', 'concurrency', 'confirmation'])
def test_workflow_refuses_unreviewed_capabilities(mutation):
    value = yaml.safe_load((b.ROOT / b.WORKFLOW).read_text(encoding='utf-8'))
    job = value['jobs']['installation']
    if mutation == 'trigger':
        value['on']['push'] = None
    elif mutation == 'permissions':
        value['permissions']['actions'] = 'write'
    elif mutation in ('environment', 'services'):
        job[mutation] = 'unapproved'
    elif mutation == 'matrix':
        job['strategy'] = {'matrix': {'x': [1, 2]}}
    elif mutation == 'timeout':
        job['timeout-minutes'] = 21
    elif mutation == 'python':
        job['steps'][3]['with']['python-version'] = '3.12'
    elif mutation == 'cache':
        job['steps'][3]['with']['cache'] = 'pip'
    elif mutation == 'pin':
        job['steps'][1]['uses'] = 'actions/checkout@v4'
    elif mutation == 'concurrency':
        value['concurrency']['group'] = 'ssh-stock-a4-expensive'
    else:
        value['on']['workflow_dispatch']['inputs']['confirm_installation']['default'] = True
    with pytest.raises(AssertionError):
        workflow_contract(value)
