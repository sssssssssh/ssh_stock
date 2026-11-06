"""Manual Linux dependency installation only; standard-library orchestration."""

import argparse
import hashlib
import json
import os
import platform
import re
import struct
import subprocess
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = 'requirements-biz-perf-linux-py312-v1.lock'
MANIFEST = 'docs/acceptance/biz_perf_04_d_lock.json'
CONTRACT = 'scripts/business_dependency_contract.py'
WORKFLOW = '.github/workflows/biz-perf-04-d-linux-install.yml'
FILES = ('receipt.json', 'runtime.json', 'dependency-verification.json', 'tests.json')
TESTS = ('tests/unit/test_biz_perf_04_d.py',
         'tests/unit/test_biz_perf_04_d_linux_install.py')
CODES = frozenset(('INVALID_DISPATCH_CONTEXT', 'TARGET_SHA_MISMATCH',
    'LOCK_SHA256_MISMATCH', 'MANIFEST_BINDING_INVALID', 'PYTHON_TARGET_UNAVAILABLE',
    'PLATFORM_MISMATCH', 'APPROVED_WHEEL_UNAVAILABLE', 'WHEEL_HASH_MISMATCH',
    'WHEELHOUSE_CONTENT_MISMATCH', 'OFFLINE_INSTALL_FAILED', 'PIP_CHECK_FAILED',
    'DEPENDENCY_CONTRACT_FAILED', 'CONTRACT_TEST_FAILED', 'ARTIFACT_EVIDENCE_INVALID',
    'UNEXPECTED_INTERNAL_ERROR'))


class Refused(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_path(path):
    path = Path(path).absolute()
    require('..' not in path.parts and all(not p.is_symlink()
        and not (hasattr(p, 'is_junction') and p.is_junction())
        for p in (path, *path.parents)), 'ARTIFACT_EVIDENCE_INVALID')
    return path


def write_json(path, value):
    path = safe_path(path)
    raw = json.dumps(value, sort_keys=True, allow_nan=False).encode()
    require(len(raw) <= 5 * 1024**2, 'ARTIFACT_EVIDENCE_INVALID')
    temporary = path.with_suffix('.pending')
    with temporary.open('xb') as stream:
        stream.write(raw + b'\n')
    temporary.replace(path)


def preflight(env, inputs):
    require(env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
        and env.get('GITHUB_REPOSITORY') == 'sssssssssh/ssh_stock'
        and env.get('GITHUB_REF') == 'refs/heads/master'
        and set(inputs) == {'target_sha', 'expected_lock_sha256', 'confirm_installation'}
        and inputs['confirm_installation'] is True, 'INVALID_DISPATCH_CONTEXT')
    require(isinstance(inputs['target_sha'], str)
        and re.fullmatch('[0-9a-f]{40}', inputs['target_sha'])
        and inputs['target_sha'] == env.get('GITHUB_SHA'), 'TARGET_SHA_MISMATCH')
    require(isinstance(inputs['expected_lock_sha256'], str)
        and re.fullmatch('[0-9a-f]{64}', inputs['expected_lock_sha256']),
        'LOCK_SHA256_MISMATCH')
    require(env.get('RUNNER_ENVIRONMENT') == 'github-hosted'
        and env.get('RUNNER_OS') == 'Linux' and env.get('RUNNER_ARCH') == 'X64',
        'PLATFORM_MISMATCH')


def runtime_info():
    return dict(implementation=sys.implementation.name, python=platform.python_version(),
        releaselevel=sys.version_info.releaselevel, system=platform.system(),
        machine=platform.machine(), bits=struct.calcsize('P') * 8,
        libc=list(platform.libc_ver()), prefix=sys.prefix, base_prefix=sys.base_prefix)


def check_runtime(value):
    require(value['implementation'] == 'cpython' and value['python'] == '3.12.14'
        and value['releaselevel'] == 'final', 'PYTHON_TARGET_UNAVAILABLE')
    libc = value['libc']
    require(value['system'] == 'Linux' and value['machine'] == 'x86_64'
        and value['bits'] == 64 and isinstance(libc, list) and len(libc) == 2
        and libc[0] == 'glibc' and re.fullmatch(r'\d+\.\d+(?:\.\d+)*', libc[1])
        and tuple(int(x) for x in libc[1].split('.')[:2]) >= (2, 28), 'PLATFORM_MISMATCH')


def child_env(directory, *, pythonpath=None):
    # No inherited credentials, pip configuration, backend path, proxy or DB URL.
    result = {k: os.environ[k] for k in ('PATH', 'SYSTEMROOT') if k in os.environ}
    result.update(HOME=str(directory), TMPDIR=str(directory), LANG='C.UTF-8',
        PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK='1',
        PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    if pythonpath:
        result['PYTHONPATH'] = str(pythonpath)
    return result


def command(args, directory, code, *, timeout=180, pythonpath=None):
    try:
        result = subprocess.run(args, shell=False, cwd=ROOT, capture_output=True,
            timeout=timeout, env=child_env(directory, pythonpath=pythonpath), check=False)
        with safe_path(directory / 'commands.log').open('ab') as stream:
            stream.write(result.stdout + b'\n' + result.stderr + b'\n')
        require(result.returncode == 0, code)
        return result.stdout
    except subprocess.TimeoutExpired as error:
        with safe_path(directory / 'commands.log').open('ab') as stream:
            stream.write((error.stdout or b'') + b'\n' + (error.stderr or b''))
        raise Refused(code) from None


def bind_source(inputs, directory, *, run=command):
    head = run(['git', 'rev-parse', 'HEAD'], directory, 'TARGET_SHA_MISMATCH').decode().strip()
    require(head == inputs['target_sha'], 'TARGET_SHA_MISMATCH')
    paths = ('requirements.lock', LOCK, MANIFEST, CONTRACT, WORKFLOW)
    run(['git', 'diff', '--exit-code', 'HEAD', '--', *paths,
         'scripts/business_dependency_linux_install.py', *TESTS], directory,
        'TARGET_SHA_MISMATCH')
    hashes = {p: sha(safe_path(ROOT / p).read_bytes()) for p in paths}
    require(hashes[LOCK] == inputs['expected_lock_sha256'], 'LOCK_SHA256_MISMATCH')
    manifest = json.loads((ROOT / MANIFEST).read_bytes())
    require(manifest['schema'] == 'biz-perf-04-d.linux-lock.v1'
        and manifest['root_sha256'] == hashes['requirements.lock']
        and manifest['lock_sha256'] == hashes[LOCK]
        and len(manifest['distributions']) == 67 and len(manifest['direct']) == 22,
        'MANIFEST_BINDING_INVALID')
    blob = run(['git', 'rev-parse', 'HEAD:' + WORKFLOW], directory,
               'TARGET_SHA_MISMATCH').decode().strip()
    require(re.fullmatch('[0-9a-f]{40}', blob), 'TARGET_SHA_MISMATCH')
    return manifest, hashes, blob


def check_url(url, host):
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == 'https' and parsed.hostname == host
        and parsed.port in (None, 443) and parsed.username is None
        and parsed.password is None and not parsed.query and not parsed.fragment,
        'APPROVED_WHEEL_UNAVAILABLE')


class OfficialRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        check_url(newurl, urllib.parse.urlsplit(request.full_url).hostname)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def fetch(url, host, *, limit=150 * 1024**2):
    check_url(url, host)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), OfficialRedirects())
    try:
        with opener.open(urllib.request.Request(url, headers={'User-Agent': 'biz04-install'}),
                         timeout=45) as response:
            check_url(response.url, host)
            raw = response.read(limit + 1)
    except (urllib.error.URLError, OSError):
        raise Refused('APPROVED_WHEEL_UNAVAILABLE') from None
    require(len(raw) <= limit, 'APPROVED_WHEEL_UNAVAILABLE')
    return raw


def approved_url(name, record, *, get=fetch):
    require(re.fullmatch('[a-z0-9][a-z0-9-]*', name)
        and re.fullmatch('[A-Za-z0-9_.+!-]+', record['version']), 'MANIFEST_BINDING_INVALID')
    filename = record['filename']
    require(Path(filename).name == filename and '/' not in filename and '\\' not in filename
        and filename.endswith('.whl'), 'WHEELHOUSE_CONTENT_MISMATCH')
    url = 'https://pypi.org/pypi/' + name + '/' + record['version'] + '/json'
    value = json.loads(get(url, 'pypi.org', limit=10 * 1024**2))
    require(value['info']['version'] == record['version'], 'APPROVED_WHEEL_UNAVAILABLE')
    matches = [f for f in value['urls'] if f['filename'] == filename]
    require(len(matches) == 1 and matches[0]['packagetype'] == 'bdist_wheel',
            'APPROVED_WHEEL_UNAVAILABLE')
    require(matches[0]['digests']['sha256'] == record['sha256'], 'WHEEL_HASH_MISMATCH')
    check_url(matches[0]['url'], 'files.pythonhosted.org')
    return matches[0]['url']


def check_wheelhouse(directory, records):
    safe_path(directory)
    paths = list(directory.iterdir())
    require(len(paths) == len(records) and {p.name for p in paths} == {
        r['filename'] for r in records.values()}, 'WHEELHOUSE_CONTENT_MISMATCH')
    for record in records.values():
        path = safe_path(directory / record['filename'])
        require(path.is_file() and sha(path.read_bytes()) == record['sha256'],
                'WHEEL_HASH_MISMATCH')


def download_wheels(directory, records, *, get=fetch):
    safe_path(directory).mkdir(exist_ok=False)
    require(len({r['filename'] for r in records.values()}) == len(records),
            'WHEELHOUSE_CONTENT_MISMATCH')
    for name, record in sorted(records.items()):
        url = approved_url(name, record, get=get)
        raw = get(url, 'files.pythonhosted.org')
        require(sha(raw) == record['sha256'], 'WHEEL_HASH_MISMATCH')
        with safe_path(directory / record['filename']).open('xb') as stream:
            stream.write(raw)
    check_wheelhouse(directory, records)


def contract_args(python, wheelhouse, *, report=None):
    args = [str(python), '-m', 'scripts.business_dependency_contract', str(wheelhouse),
        '--root', 'requirements.lock', '--lock', LOCK, '--manifest', MANIFEST]
    return args + (['--installed', '--pip-report', str(report)] if report else [])


def create_venv(path, private, *, run=command):
    require(not safe_path(path).exists(), 'ARTIFACT_EVIDENCE_INVALID')
    run([sys.executable, '-m', 'venv', '--copies', str(path)], private,
        'PYTHON_TARGET_UNAVAILABLE')
    config = safe_path(path / 'pyvenv.cfg').read_text()
    settings = dict(line.lower().strip().split(' = ', 1) for line in config.splitlines()
                    if ' = ' in line)
    require(settings.get('include-system-site-packages') == 'false', 'PLATFORM_MISMATCH')
    python = safe_path(path / 'bin/python')
    # --copies keeps the executable inside the private directory, without symlinks.
    return python


def install_args(python, wheelhouse, report):
    return [str(python), '-m', 'pip', 'install', '--no-index', '--find-links', str(wheelhouse),
        '--only-binary=:all:', '--require-hashes', '--no-cache-dir', '--report', str(report),
        '-r', LOCK]


def parse_junit(path):
    root = ET.fromstring(safe_path(path).read_bytes())
    cases = list(root.iter('testcase'))
    require(root.tag in ('testsuites', 'testsuite') and bool(cases), 'CONTRACT_TEST_FAILED')
    require(all(int(n.attrib.get(k, '0')) == 0 for n in root.iter()
        if n.tag in ('testsuites', 'testsuite') for k in ('failures', 'errors', 'skipped')),
        'CONTRACT_TEST_FAILED')
    failed = sum(c.find('failure') is not None for c in cases)
    errors = sum(c.find('error') is not None for c in cases)
    skipped = sum(c.find('skipped') is not None for c in cases)
    require(not (failed or errors or skipped) and not list(root.iter('error')),
            'CONTRACT_TEST_FAILED')
    return dict(tests=len(cases), passed=len(cases), failed=0, errors=0, skipped=0, exit_code=0)


def validate_export(public):
    safe_path(public)
    require({p.name for p in public.iterdir()} == set(FILES), 'ARTIFACT_EVIDENCE_INVALID')
    total = 0
    for name in FILES:
        path = safe_path(public / name)
        require(path.is_file(), 'ARTIFACT_EVIDENCE_INVALID')
        total += path.stat().st_size
        require(total <= 5 * 1024**2, 'ARTIFACT_EVIDENCE_INVALID')
        value = json.loads(path.read_bytes())
        allowed = {
            'receipt.json': {'status', 'transitive_lock_complete', 'target_installation',
                'failure_code', 'target_sha', 'run_id', 'attempt', 'workflow_blob',
                'workflow_sha256', 'stages', 'exit_code'},
            'runtime.json': {'status', 'implementation', 'python', 'releaselevel', 'system',
                'machine', 'bits', 'libc', 'runner', 'runner_os', 'runner_arch', 'toolchain'},
            'dependency-verification.json': {'status', 'hashes', 'expected_count', 'actual_count',
                'installed_set_verified', 'distributions'},
            'tests.json': {'status', 'files', 'tests', 'passed', 'failed', 'errors',
                'skipped', 'exit_code'},
        }
        require(isinstance(value, dict) and set(value) <= allowed[name],
                'ARTIFACT_EVIDENCE_INVALID')
        for key, item in value.items():
            if key == 'status':
                valid = item in ('COMPLETE', 'INCOMPLETE', 'NOT_VERIFIED')
            elif key == 'target_installation':
                valid = item in ('VERIFIED', 'NOT_VERIFIED')
            elif key == 'failure_code':
                valid = item is None or item in CODES
            elif key in ('target_sha', 'workflow_blob', 'workflow_sha256'):
                valid = isinstance(item, str) and re.fullmatch(
                    '[0-9a-f]{64}' if key == 'workflow_sha256' else '[0-9a-f]{40}', item)
            elif key in ('run_id', 'attempt'):
                valid = isinstance(item, str) and re.fullmatch('[1-9][0-9]*', item)
            elif key in ('transitive_lock_complete', 'installed_set_verified'):
                valid = type(item) is bool
            elif key in ('expected_count', 'actual_count', 'tests', 'passed', 'failed',
                         'errors', 'skipped', 'exit_code', 'bits'):
                valid = item is None or (type(item) is int and item >= 0)
            elif key == 'stages':
                valid = isinstance(item, dict) and set(item) <= {
                    'preflight', 'source_binding', 'wheelhouse', 'preinstall_contract',
                    'runtime_and_venv', 'install_and_pip_check', 'installed_contract_and_tests'}
                valid = valid and all(v == 'PASS' for v in item.values())
            elif key == 'hashes':
                valid = isinstance(item, dict) and set(item) == {
                    'requirements.lock', LOCK, MANIFEST, CONTRACT, WORKFLOW}
                valid = valid and all(isinstance(v, str) and re.fullmatch('[0-9a-f]{64}', v)
                                      for v in item.values())
            elif key == 'distributions':
                valid = isinstance(item, dict) and len(item) == 67
                valid = valid and all(re.fullmatch('[a-z0-9-]+', k) and isinstance(v, dict)
                    and set(v) == {'version', 'filename', 'sha256'}
                    and re.fullmatch('[A-Za-z0-9_.+!-]+', v['version'])
                    and re.fullmatch('[A-Za-z0-9_.+!-]+\\.whl', v['filename'])
                    and re.fullmatch('[0-9a-f]{64}', v['sha256']) for k, v in item.items())
            elif key == 'toolchain':
                valid = isinstance(item, dict) and set(item) <= {'pip', 'setuptools', 'wheel'}
                valid = valid and all(isinstance(v, str)
                    and re.fullmatch('[A-Za-z0-9_.+!-]+', v) for v in item.values())
            elif key == 'files':
                valid = item == list(TESTS)
            elif key == 'libc':
                valid = isinstance(item, list) and len(item) == 2 and item[0] == 'glibc'
                valid = valid and bool(re.fullmatch(r'\d+\.\d+(?:\.\d+)*', item[1]))
            else:
                expected = dict(implementation='cpython', python='3.12.14', releaselevel='final',
                    system='Linux', machine='x86_64', runner='github-hosted', runner_os='Linux',
                    runner_arch='X64')
                valid = key in expected and item == expected[key]
            require(valid, 'ARTIFACT_EVIDENCE_INVALID')
        raw = path.read_text()
        require(not any(s in raw for s in ('://', 'password=', 'Token ', 'Traceback',
            str(public.parent), '\\u0000')), 'ARTIFACT_EVIDENCE_INVALID')
    receipt = json.loads((public / 'receipt.json').read_bytes())
    if receipt.get('status') == 'COMPLETE':
        dependency = json.loads((public / 'dependency-verification.json').read_bytes())
        tests = json.loads((public / 'tests.json').read_bytes())
        runtime = json.loads((public / 'runtime.json').read_bytes())
        require(receipt.get('transitive_lock_complete') is True
            and {'target_sha', 'run_id', 'attempt', 'workflow_blob', 'workflow_sha256'}
                <= set(receipt)
            and receipt.get('target_installation') == 'VERIFIED'
            and receipt.get('failure_code') is None and receipt.get('exit_code') == 0
            and set(receipt.get('stages', {})) == {'preflight', 'source_binding', 'wheelhouse',
                'preinstall_contract', 'runtime_and_venv', 'install_and_pip_check',
                'installed_contract_and_tests'}
            and dependency.get('installed_set_verified') is True
            and dependency.get('expected_count') == dependency.get('actual_count') == 67
            and len(dependency.get('distributions', {})) == 67
            and tests.get('files') == list(TESTS) and tests.get('tests', 0) > 0
            and tests.get('passed') == tests.get('tests')
            and all(tests.get(k) == 0 for k in ('failed', 'errors', 'skipped', 'exit_code')),
            'ARTIFACT_EVIDENCE_INVALID')
        check_runtime(runtime)


def finish(public, receipt, *, complete=False, code=None):
    receipt.update(status='COMPLETE' if complete else 'INCOMPLETE',
        transitive_lock_complete=complete, target_installation='VERIFIED' if complete
        else 'NOT_VERIFIED', failure_code=code, exit_code=0 if complete else 1)
    if not complete:
        write_json(public / 'dependency-verification.json', dict(status='INCOMPLETE',
            expected_count=67, actual_count=None, installed_set_verified=False))
    write_json(public / 'receipt.json', receipt)
    validate_export(public)


def execute(env, inputs):
    preflight(env, inputs)
    require(all(re.fullmatch('[1-9][0-9]*', env.get(k, '')) for k in (
        'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')), 'INVALID_DISPATCH_CONTEXT')
    base = safe_path(Path(env['RUNNER_TEMP']) / 'biz-perf-04-d' /
        (env['GITHUB_RUN_ID'] + '-' + env['GITHUB_RUN_ATTEMPT']))
    public = safe_path(base / 'public')
    receipt = json.loads((public / 'receipt.json').read_bytes())
    receipt.update(target_sha=inputs['target_sha'], run_id=env['GITHUB_RUN_ID'],
                   attempt=env['GITHUB_RUN_ATTEMPT'])
    private = safe_path(base / 'private')
    require(base.is_relative_to(safe_path(env['RUNNER_TEMP'])) and public.is_dir()
        and not private.exists(), 'ARTIFACT_EVIDENCE_INVALID')
    private.mkdir()
    receipt['stages'] = {'preflight': 'PASS'}

    def passed(stage):
        receipt['stages'][stage] = 'PASS'
        write_json(public / 'receipt.json', receipt)

    try:
        manifest, hashes, blob = bind_source(inputs, private)
        receipt.update(workflow_blob=blob, workflow_sha256=hashes[WORKFLOW])
        passed('source_binding')
        check_runtime(runtime_info())
        runtime = {k: v for k, v in runtime_info().items() if k not in ('prefix', 'base_prefix')}
        runtime.update(runner='github-hosted', runner_os=env['RUNNER_OS'],
                       runner_arch=env['RUNNER_ARCH'])
        write_json(public / 'runtime.json', runtime)
        wheels = private / 'wheels'
        download_wheels(wheels, manifest['distributions'])
        passed('wheelhouse')
        # Bootstrap the unchanged validator from the approved pure Python packaging wheel.
        packaging_wheel = wheels / manifest['distributions']['packaging']['filename']
        command(contract_args(sys.executable, wheels), private, 'DEPENDENCY_CONTRACT_FAILED',
                pythonpath=packaging_wheel)
        passed('preinstall_contract')
        venv = private / 'venv'
        python = create_venv(venv, private)
        probe = ('import json; from scripts.business_dependency_linux_install import runtime_info; '
                 'print(json.dumps(runtime_info()))')
        value = json.loads(command([str(python), '-c', probe], private, 'PLATFORM_MISMATCH'))
        check_runtime(value)
        require(Path(value['prefix']).resolve() == venv.resolve()
            and value['prefix'] != value['base_prefix'], 'PLATFORM_MISMATCH')
        passed('runtime_and_venv')
        report = private / 'install-report.json'
        command(install_args(python, wheels, report), private,
                'OFFLINE_INSTALL_FAILED', timeout=300)
        command([str(python), '-m', 'pip', 'check'], private, 'PIP_CHECK_FAILED')
        passed('install_and_pip_check')
        require(safe_path(report).is_file(), 'OFFLINE_INSTALL_FAILED')
        verified = json.loads(command(contract_args(python, wheels, report=report), private,
                                      'DEPENDENCY_CONTRACT_FAILED'))
        require(verified.get('installed_set_verified') is True
            and verified.get('transitive_lock_complete') is True
            and verified.get('installed_business_count') == 67
            and verified.get('target_installation') == 'VERIFIED', 'DEPENDENCY_CONTRACT_FAILED')
        runtime['toolchain'] = verified['toolchain']
        write_json(public / 'runtime.json', runtime)
        write_json(public / 'dependency-verification.json', dict(hashes=hashes,
            expected_count=67, actual_count=67, installed_set_verified=True,
            distributions={k: {f: r[f] for f in ('version', 'filename', 'sha256')}
                           for k, r in manifest['distributions'].items()}))
        junit = private / 'tests.xml'
        command([str(python), '-m', 'pytest', '-q', '--tb=no', '--show-capture=no', '-rN',
            *TESTS, '--junitxml=' + str(junit)], private, 'CONTRACT_TEST_FAILED', timeout=300)
        tests = parse_junit(junit)
        tests['files'] = list(TESTS)
        write_json(public / 'tests.json', tests)
        passed('installed_contract_and_tests')
        # Revalidate sources and files after tests; test success cannot authorize a changed lock.
        require(bind_source(inputs, private)[1] == hashes, 'MANIFEST_BINDING_INVALID')
        check_wheelhouse(wheels, manifest['distributions'])
        validate_export(public)
        finish(public, receipt, complete=True)
        return 0
    except Exception as error:
        safe_path(private / 'failure.log').write_text(traceback.format_exc(), encoding='utf-8')
        code = str(error) if isinstance(error, Refused) and str(error) in CODES else (
            'UNEXPECTED_INTERNAL_ERROR')
        finish(public, receipt, code=code)
        return 1


def prebind(env, inputs):
    preflight(env, inputs)
    require(all(re.fullmatch('[1-9][0-9]*', env.get(k, '')) for k in (
        'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')), 'INVALID_DISPATCH_CONTEXT')
    base = safe_path(Path(env['RUNNER_TEMP']) / 'biz-perf-04-d' /
        (env['GITHUB_RUN_ID'] + '-' + env['GITHUB_RUN_ATTEMPT']))
    directory = safe_path(base / 'binding')
    directory.mkdir(exist_ok=False)
    public = safe_path(base / 'public')
    receipt = json.loads((public / 'receipt.json').read_bytes())
    receipt.update(target_sha=inputs['target_sha'], run_id=env['GITHUB_RUN_ID'],
                   attempt=env['GITHUB_RUN_ATTEMPT'])
    try:
        _, hashes, blob = bind_source(inputs, directory)
        receipt.update(workflow_blob=blob, workflow_sha256=hashes[WORKFLOW])
        receipt.setdefault('stages', {})['source_binding'] = 'PASS'
        write_json(public / 'receipt.json', receipt)
        write_json(public / 'dependency-verification.json', dict(status='NOT_VERIFIED',
            hashes=hashes, expected_count=67, actual_count=None, installed_set_verified=False))
        validate_export(public)
        return 0
    except Exception as error:
        safe_path(directory / 'failure.log').write_text(traceback.format_exc(), encoding='utf-8')
        code = str(error) if isinstance(error, Refused) and str(error) in CODES else (
            'UNEXPECTED_INTERNAL_ERROR')
        finish(public, receipt, code=code)
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind-only', action='store_true')
    args = parser.parse_args()
    try:
        run = prebind if args.bind_only else execute
        result = run(os.environ, json.loads(os.environ['BIZ04_INPUTS']))
    except Exception:
        # The pre-checkout prefix remains INCOMPLETE; never emit exception text.
        result = 1
    raise SystemExit(result)


if __name__ == '__main__':
    main()
