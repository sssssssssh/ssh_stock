"""Offline metadata/marker/hash contracts; never installs or invokes Docker/CI."""

import copy
import json
import zipfile
from pathlib import Path

import pytest
from packaging.requirements import Requirement

from scripts import business_dependency_contract as d

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / 'requirements-biz-perf-linux-py312-v1.lock'
MANIFEST = ROOT / 'docs/acceptance/biz_perf_04_d_lock.json'


def manifest():
    return json.loads(MANIFEST.read_bytes())


def test_real_closed_metadata_and_unchanged_direct_versions():
    m = manifest()
    parsed = d.validate_lock(LOCK.read_bytes(), m, (ROOT / 'requirements.lock').read_bytes())
    assert len(parsed) == 67 and len(m['direct']) == 22
    assert all(parsed[k]['version'] == v['version'] for k, v in m['direct'].items())
    assert not set(parsed) & d.TOOLS
    assert parsed['greenlet']['version'] == '3.5.6'


@pytest.mark.parametrize('name', ['greenlet', 'psycopg-binary', 'pydantic-core', 'numpy'])
def test_missing_transitive_or_direct_distribution_refused(name):
    m = manifest()
    m['distributions'].pop(name)
    with pytest.raises(ValueError):
        d.closure(m['distributions'], m['direct'])


def test_marker_environment_is_linux_not_host():
    env = d.target_environment()
    assert not Requirement('colorama; sys_platform == "win32"').marker.evaluate(env)
    assert Requirement('greenlet; platform_machine == "x86_64"').marker.evaluate(env)
    assert env['python_full_version'] == '3.12.14'
    m = manifest()
    assert 'colorama' not in m['distributions']
    # The macOS ARM cross-download omission must remain a regression.
    m['distributions'].pop('greenlet')
    with pytest.raises(ValueError):
        d.closure(m['distributions'], m['direct'])


def test_unreachable_package_and_wrong_dependency_version_are_rejected():
    m = manifest()
    m['distributions']['unexpected'] = copy.deepcopy(m['distributions']['numpy'])
    with pytest.raises(ValueError):
        d.closure(m['distributions'], m['direct'])
    m = manifest()
    m['distributions']['pydantic-core']['version'] = '0.0'
    with pytest.raises(ValueError):
        d.closure(m['distributions'], m['direct'])


@pytest.mark.parametrize('mutation', ['missing_hash', 'bad_hash', 'unpinned', 'floating', 'marker'])
def test_lock_tampering_rejected_even_when_outer_digest_recomputed(mutation):
    raw = LOCK.read_bytes()
    if mutation == 'missing_hash':
        raw = raw.replace(b' --hash=sha256:', b' # ', 1)
    elif mutation == 'bad_hash':
        raw = raw.replace(b'--hash=sha256:', b'--hash=sha256:z', 1)
    elif mutation == 'unpinned':
        raw = raw.replace(b'==', b'>=', 1)
    elif mutation == 'floating':
        raw = raw.replace(b'==1.19.1', b'==1.*', 1)
    else:
        raw = raw.replace(b' --hash=', b'; sys_platform == "win32" --hash=', 1)
    m = manifest()
    m['lock_sha256'] = d.sha(raw)
    with pytest.raises(ValueError):
        d.validate_lock(raw, m, (ROOT / 'requirements.lock').read_bytes())


@pytest.mark.parametrize('mode', ['missing', 'extra', 'version', 'duplicate'])
def test_installed_set_disagreement_refused(mode):
    m = manifest()
    items = [(k, v['version']) for k, v in m['distributions'].items()]
    if mode == 'missing':
        items.pop()
    elif mode == 'extra':
        items.append(('unapproved', '1.0'))
    elif mode == 'duplicate':
        items.append(items[0])
    else:
        items[0] = (items[0][0], '0.0')
    with pytest.raises(ValueError):
        d.validate_installed(items, m, system='Linux', machine='x86_64', python_version='3.12.14')


@pytest.mark.parametrize('system,machine,python', [('Darwin', 'arm64', '3.12.14'),
    ('Linux', 'aarch64', '3.12.14'), ('Linux', 'x86_64', '3.13.0')])
def test_wrong_runtime_never_verified(system, machine, python):
    m = manifest()
    with pytest.raises(ValueError):
        d.validate_installed([(k, v['version']) for k, v in m['distributions'].items()], m,
                             system=system, machine=machine, python_version=python)


def test_toolchain_is_separate_and_observed_not_counted_as_business():
    m = manifest()
    result = d.validate_installed([(k, v['version']) for k, v in m['distributions'].items()]
        + [('pip', '25.0.1'), ('setuptools', '80.0.0'), ('wheel', '0.45.1')], m,
        system='Linux', machine='x86_64', python_version='3.12.14')
    assert result['installed_business_count'] == 67
    assert result['toolchain'] == {'pip': '25.0.1', 'setuptools': '80.0.0', 'wheel': '0.45.1'}


def test_install_report_requires_actual_target_hash_and_complete_set():
    m = manifest()
    report = dict(version='1', environment=d.TARGET.copy(), install=[dict(
        metadata=dict(name=k, version=v['version']), download_info=dict(archive_info=dict(
            hashes=dict(sha256=v['sha256'])))) for k, v in m['distributions'].items()])
    d.validate_install_report(report, m)  # Simulated report, not a real installation receipt.
    for field in ('hash', 'platform', 'missing'):
        bad = copy.deepcopy(report)
        if field == 'hash':
            bad['install'][0]['download_info']['archive_info']['hashes']['sha256'] = '0' * 64
        elif field == 'platform':
            bad['environment']['sys_platform'] = 'darwin'
        else:
            bad['install'].pop()
        with pytest.raises(ValueError):
            d.validate_install_report(bad, m)


def test_wheel_bytes_hash_and_platform(tmp_path):
    path = tmp_path / 'synthetic-1.0-py3-none-any.whl'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('synthetic-1.0.dist-info/METADATA', 'Name: synthetic\nVersion: 1.0\n')
    records = d.wheel_records(tmp_path)
    d.validate_wheels(tmp_path, dict(distributions=records))
    with path.open('ab') as f:
        f.write(b'tamper')
    with pytest.raises(ValueError):
        d.validate_wheels(tmp_path, dict(distributions=records))
    path.rename(tmp_path / 'synthetic-1.0-cp312-cp312-win_amd64.whl')
    with pytest.raises(ValueError):
        d.wheel_records(tmp_path)
