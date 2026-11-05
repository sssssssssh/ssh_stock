"""Versioned Linux wheel closure and lock contract; no application/DB imports."""

import argparse
import hashlib
import json
import platform
import re
import zipfile
from email.parser import BytesParser
from importlib import metadata
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

SCHEMA = 'biz-perf-04-d.linux-lock.v1'
TARGET = dict(sys_platform='linux', platform_system='Linux', platform_machine='x86_64',
              os_name='posix', implementation_name='cpython',
              platform_python_implementation='CPython', python_version='3.12',
              python_full_version='3.12.14', implementation_version='3.12.14')
PLATFORMS = [f'manylinux_2_{i}_x86_64' for i in range(5, 29)] + [
    'manylinux1_x86_64', 'manylinux2010_x86_64', 'manylinux2014_x86_64']
TOOLS = {'pip', 'setuptools', 'wheel'}


def require(value):
    if not value:
        raise ValueError('BIZ04_DEPENDENCY_CONTRACT_INVALID')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def target_environment():
    # Override every platform/Python variable; never inherit macOS marker values.
    return {**default_environment(), **TARGET, 'platform_release': '', 'platform_version': ''}


def target_tags():
    return set(cpython_tags((3, 12), abis=['cp312'], platforms=PLATFORMS)) | set(
        compatible_tags((3, 12), interpreter='cp312', platforms=PLATFORMS))


def exact(requirement):
    require(requirement.url is None and len(requirement.specifier) == 1)
    spec = next(iter(requirement.specifier))
    require(spec.operator == '==' and '*' not in spec.version)
    return spec.version


def roots(text):
    result = {}
    for line in text.splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            r = Requirement(line)
            require(r.marker is None)
            name = canonicalize_name(r.name)
            require(name not in result)
            result[name] = dict(version=exact(r), extras=sorted(r.extras))
    require(bool(result))
    return result


def wheel_records(directory):
    records = {}
    for path in sorted(Path(directory).glob('*.whl')):
        name, version, _, tags = parse_wheel_filename(path.name)
        require(bool(tags & target_tags()) and name not in records and not path.is_symlink())
        with zipfile.ZipFile(path) as z:
            files = [n for n in z.namelist() if n.endswith('.dist-info/METADATA')]
            require(len(files) == 1)
            raw = z.read(files[0])
            m = BytesParser().parsebytes(raw)
        require(canonicalize_name(m['Name']) == name and Version(m['Version']) == version)
        records[name] = dict(version=str(version), filename=path.name,
            sha256=sha(path.read_bytes()), metadata_sha256=sha(raw),
            requires_python=m.get('Requires-Python'), requires_dist=m.get_all('Requires-Dist', []))
    require(bool(records))
    return records


def closure(records, direct):
    extras = {k: set(v['extras']) for k, v in direct.items()}
    require(all(k in records and records[k]['version'] == v['version']
                for k, v in direct.items()))
    pending = list(direct)
    while pending:
        name = pending.pop()
        rec = records[name]
        if rec['requires_python']:
            from packaging.specifiers import SpecifierSet

            require(SpecifierSet(rec['requires_python']).contains('3.12.14', prereleases=True))
        for raw in rec['requires_dist']:
            r = Requirement(raw)
            require(r.url is None)
            require(r.marker is None or not re.search(
                r'\b(platform_release|platform_version)\b', str(r.marker)))
            if r.marker and not any(r.marker.evaluate({**target_environment(), 'extra': e})
                                    for e in extras[name] | {''}):
                continue
            dep = canonicalize_name(r.name)
            require(dep in records and r.specifier.contains(records[dep]['version'],
                                                            prereleases=True))
            unseen = dep not in extras
            old = extras.get(dep, set())
            new = old | set(r.extras)
            if unseen or new != old:
                extras[dep] = new
                pending.append(dep)
    require(set(extras) == set(records))
    return extras


def lock_bytes(records, direct):
    extras = closure(records, direct)
    lines = ['# ' + SCHEMA, '# Linux x86_64 glibc>=2.28 CPython 3.12.14; wheel-only',
             '# Generated from historical constrained wheel METADATA; roots unchanged.']
    for name, rec in sorted(records.items()):
        suffix = '[' + ','.join(sorted(extras[name])) + ']' if extras[name] else ''
        lines.append(f'{name}{suffix}=={rec["version"]} --hash=sha256:{rec["sha256"]}')
    return ('\n'.join(lines) + '\n').encode()


def parse_lock(data):
    text = data.decode().replace('\\\n', ' ')
    records = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        parts = line.split(' --hash=sha256:')
        require(len(parts) == 2 and re.fullmatch('[0-9a-f]{64}', parts[1]))
        r = Requirement(parts[0])
        require(r.marker is None)  # This is a resolved single-target lock, no dormant entries.
        name = canonicalize_name(r.name)
        require(name not in records)
        records[name] = dict(version=exact(r), extras=sorted(r.extras), sha256=parts[1])
    require(bool(records))
    return records


def validate_lock(lock, manifest, root_bytes):
    require(manifest['schema'] == SCHEMA and manifest['target'] == TARGET)
    require(manifest['root_sha256'] == sha(root_bytes) and manifest['lock_sha256'] == sha(lock))
    direct = roots(root_bytes.decode())
    require(manifest['direct'] == direct)
    records = manifest['distributions']
    extras = closure(records, direct)
    parsed = parse_lock(lock)
    require(set(parsed) == set(records))
    for name, value in parsed.items():
        require(value == dict(version=records[name]['version'], extras=sorted(extras[name]),
                              sha256=records[name]['sha256']))
    require(lock == lock_bytes(records, direct))
    return parsed


def validate_wheels(directory, manifest):
    require(wheel_records(directory) == manifest['distributions'])


def validate_installed(installed, manifest, *, system, machine, python_version):
    require((system, machine, python_version) == ('Linux', 'x86_64', '3.12.14'))
    values = {}
    for name, version in installed:
        key = canonicalize_name(name)
        require(key not in values)
        values[key] = version
    expected = {k: v['version'] for k, v in manifest['distributions'].items()}
    business = {k: v for k, v in values.items() if k not in TOOLS or k in expected}
    require(business == expected)
    return dict(schema=SCHEMA, installed_set_verified=True,
                installed_business_count=len(business),
                toolchain={k: v for k, v in values.items() if k in TOOLS and k not in expected})


def validate_install_report(report, manifest):
    require(report.get('version') == '1')
    require(all(report.get('environment', {}).get(k) == v for k, v in TARGET.items()))
    found = {}
    for entry in report.get('install', []):
        name = canonicalize_name(entry['metadata']['name'])
        require(name not in found and name in manifest['distributions'])
        expected = manifest['distributions'][name]
        require(entry['metadata']['version'] == expected['version'])
        require(entry['download_info']['archive_info']['hashes']['sha256'] == expected['sha256'])
        found[name] = entry['metadata']['version']
    require(set(found) == set(manifest['distributions']))
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheelhouse', type=Path)
    parser.add_argument('--root', type=Path, default=Path('requirements.lock'))
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--generate', action='store_true')
    parser.add_argument('--installed', action='store_true')
    parser.add_argument('--pip-report', type=Path)
    args = parser.parse_args()
    root = args.root.read_bytes()
    if args.generate:
        require(not args.lock.exists() and not args.manifest.exists())
        records = wheel_records(args.wheelhouse)
        direct = roots(root.decode())
        lock = lock_bytes(records, direct)
        m = dict(schema=SCHEMA, target=TARGET, root_sha256=sha(root), lock_sha256=sha(lock),
                 direct=direct, distributions=records, generation=dict(
                     python=platform.python_version(),
                     packaging=__import__('packaging').__version__, pip=metadata.version('pip'),
                     host_system=platform.system(), host_machine=platform.machine()))
        args.lock.write_bytes(lock)
        args.manifest.write_text(json.dumps(m, indent=2, sort_keys=True) + '\n')
    m = json.loads(args.manifest.read_bytes())
    validate_lock(args.lock.read_bytes(), m, root)
    validate_wheels(args.wheelhouse, m)
    result = dict(schema=SCHEMA, wheel_closure_verified=True,
                  transitive_lock_complete=False, target_installation='NOT_VERIFIED')
    if args.installed:
        require(args.pip_report is not None)
        report_verified = validate_install_report(json.loads(args.pip_report.read_bytes()), m)
        from importlib.metadata import distributions

        result = validate_installed([(d.metadata['Name'], d.version) for d in distributions()], m,
            system=platform.system(), machine=platform.machine(),
            python_version=platform.python_version())
        result['transitive_lock_complete'] = report_verified and result['installed_set_verified']
        result['target_installation'] = 'VERIFIED'
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
