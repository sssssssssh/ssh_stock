"""Safe complete JUnit and exact-SHA failure receipts; never a release/SQL gate."""

import argparse
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import stat
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.a42_artifacts import atomic

JUNIT_PATHS = ('.codex_tmp/v14-targeted.xml','.codex_tmp/a42331-targeted.xml',
    '.codex_tmp/m17_1_2-targeted.xml','.codex_tmp/data-publication-targeted.xml',
    '.codex_tmp/cold-start-targeted.xml','.codex_tmp/m17_1_2-full.xml')
PHASES = ('targeted','full_tests','data_queue','browser','runtime_browser')
OUTCOMES = {'success','failure','skipped','cancelled','unknown'}
ALLOWED_FULL_SUITE_SKIPS = frozenset({(
    'tests.integration.test_r1_integration_linux_mock_domain.LinuxLabTests',
    'test_linux_success_term_kill_owned_child',
    'NOT_RUN/ENV_BLOCKED: no independently approved no-network Linux lab',
)})
PROOF_VERSION = 'a42331.local-skip-proof.v1'


def require(value, code):
    if not value:
        raise RuntimeError(code)


def number(value):
    n = float(value)
    require(math.isfinite(n) and n >= 0,'A42331_JUNIT_TIME_INVALID')
    return str(n)


def safe_identifier(value, *, parameter=False):
    base = value.split('[',1)[0] if parameter else value
    safe = base if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.]{0,240}',base) else 'redacted'
    if safe != value:
        safe += '_'+hashlib.sha256(value.encode()).hexdigest()[:16]
    return safe


def _read_raw(path):
    require(path.is_file() and not path.is_symlink() and not path.is_junction()
            and path.stat().st_size <= 50_000_000, 'A42331_JUNIT_MISSING_OR_TOO_LARGE')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                 | getattr(os, 'O_BINARY', 0))
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'A42331_JUNIT_MISSING_OR_TOO_LARGE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(50_000_001)
        require(len(raw) <= 50_000_000, 'A42331_JUNIT_MISSING_OR_TOO_LARGE')
        return raw
    finally:
        os.close(fd)


def _tree(raw):
    require(len(raw) <= 50_000_000 and b'\0' not in raw,
            'A42331_JUNIT_XML_FORBIDDEN')
    require(b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper(),
            'A42331_JUNIT_XML_FORBIDDEN')
    root = ET.fromstring(raw)
    require(root.tag in ('testsuite', 'testsuites'), 'A42331_JUNIT_SCHEMA_INVALID')
    suites = [root] if root.tag == 'testsuite' else list(root)
    require(suites and all(s.tag == 'testsuite' for s in suites),
            'A42331_JUNIT_SCHEMA_INVALID')
    totals = dict(tests=0, failures=0, errors=0, skipped=0)
    cases = []
    for suite in suites:
        rows = suite.findall('testcase')
        require(len(list(suite.iter('testcase'))) == len(rows), 'A42331_JUNIT_SCHEMA_INVALID')
        observed = dict(tests=len(rows), **{k:sum(len(c.findall(tag)) for c in rows)
            for k, tag in (('failures', 'failure'), ('errors', 'error'), ('skipped', 'skipped'))})
        require(observed == {k:int(suite.attrib[k]) for k in totals},
                'A42331_JUNIT_COUNTS_MISMATCH')
        for k in totals:
            totals[k] += observed[k]
        cases.extend(rows)
    require(totals['tests'] > 0, 'A42331_JUNIT_EMPTY')
    if root.tag == 'testsuites':
        require(all(int(root.attrib[k]) == totals[k] for k in totals if k in root.attrib),
                'A42331_JUNIT_COUNTS_MISMATCH')
    return suites, cases, totals


def _raw_policy(suites, cases, counts, *, full):
    if counts['skipped'] == 0:
        return 'PASS', 0
    if not full or counts['skipped'] != 1:
        return 'REJECT', 0
    # Native unittest subreports may repeat *non-skipped* IDs. The approved
    # skipped ID itself must occur exactly once, including successful duplicates.
    skipped = [(c, node) for c in cases for node in c.findall('skipped')]
    case, node = skipped[0]
    identity = case.get('classname'), case.get('name')
    triple = (*identity, node.get('message'))
    unique = sum((c.get('classname'), c.get('name')) == identity for c in cases) == 1
    return ('PASS', 1) if unique and triple in ALLOWED_FULL_SUITE_SKIPS else ('REJECT', 0)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def _context(root):
    root = Path(root).absolute()
    require(not root.is_symlink() and not root.is_junction(), 'A42331_PROOF_PATH_INVALID')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    run = os.environ.get('GITHUB_RUN_ID', 'local')
    attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '1')
    require(re.fullmatch('[0-9a-f]{40}', head) is not None
            and head == os.environ.get('GITHUB_SHA', head), 'A42331_HEAD_MISMATCH')
    require(re.fullmatch('[A-Za-z0-9_.-]{1,80}', run) is not None
            and re.fullmatch('[0-9]{1,8}', attempt) is not None, 'A42331_PROOF_CONTEXT_INVALID')
    return dict(root_sha256=hashlib.sha256(os.fsencode(root)).hexdigest(),
                head_sha=head, run_id=run, attempt=attempt)


def _dpapi(raw, *, encrypt):
    """Current-user Windows DPAPI; private keys are never plaintext on Windows."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    function = (ctypes.windll.crypt32.CryptProtectData if encrypt
                else ctypes.windll.crypt32.CryptUnprotectData)
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    require(function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)),
            'A42331_PROOF_KEY_UNAVAILABLE')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


def _private_check(path, *, directory=False):
    require(not path.is_symlink() and not path.is_junction(), 'A42331_PROOF_PATH_INVALID')
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode),
            'A42331_PROOF_PATH_INVALID')
    if os.name == 'posix':
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0,
                'A42331_PROOF_PATH_INVALID')


def _store(context, *, create):
    # Outside the repository/artifact upload paths. Same runner user and reviewed
    # code are the trust boundary, not an experiment authorization service.
    user = str(os.getuid()) if os.name == 'posix' else 'current-user-dpapi'
    base = Path(tempfile.gettempdir())/('a42331-skip-trust-v1-'+user)
    directory = base/hashlib.sha256(_canonical(context)).hexdigest()
    for p in (base, directory):
        if create:
            p.mkdir(mode=0o700, exist_ok=True)
        _private_check(p, directory=True)
    return directory


def _key(directory, *, create):
    path = directory/'signing-key'
    if create:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
                         | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        except FileExistsError:
            pass
        else:
            try:
                raw = secrets.token_bytes(32)
                encoded = _dpapi(raw, encrypt=True) if os.name == 'nt' else raw
                require(os.write(fd, encoded) == len(encoded), 'A42331_PROOF_KEY_UNAVAILABLE')
                os.fsync(fd)
            finally:
                os.close(fd)
    _private_check(path)
    require(path.stat().st_size <= 4096, 'A42331_PROOF_KEY_UNAVAILABLE')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                 | getattr(os, 'O_BINARY', 0))
    try:
        raw = os.read(fd, 4097)
    finally:
        os.close(fd)
    key = _dpapi(raw, encrypt=False) if os.name == 'nt' else raw
    require(len(key) == 32, 'A42331_PROOF_KEY_UNAVAILABLE')
    return key


def _proof_path(directory, name):
    return directory/(hashlib.sha256(name.encode()).hexdigest()+'.json')


def _instance(path):
    value = path.stat()
    require(not path.is_symlink() and not path.is_junction()
            and stat.S_ISREG(value.st_mode), 'A42331_PROOF_SOURCE_INVALID')
    return {key:getattr(value, key) for key in
            ('st_dev', 'st_ino', 'st_ctime_ns', 'st_mtime_ns', 'st_size')}


def _issue(root, name, raw, safe, counts, decision):
    context = _context(root)
    directory = _store(context, create=True)
    key = _key(directory, create=True)
    payload = dict(version=PROOF_VERSION, context=context, source=name,
                   raw_sha256=hashlib.sha256(raw).hexdigest(),
                   safe_sha256=hashlib.sha256(safe).hexdigest(), counts=counts,
                   skip_policy_status=decision[0], approved_skip_count=decision[1],
                   safe_file=_instance(Path(root)/name))
    envelope = dict(payload=payload, mac=hmac.new(key, _canonical(payload), 'sha256').hexdigest())
    destination = _proof_path(directory, name)
    temporary = destination.with_suffix('.'+secrets.token_hex(8)+'.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
                 | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        data = _canonical(envelope)
        require(os.write(fd, data) == len(data), 'A42331_PROOF_WRITE_FAILED')
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, destination)


def _verify(root, name, raw, counts):
    try:
        context = _context(root)
        directory = _store(context, create=False)
        key = _key(directory, create=False)  # Never create a key during verification.
        path = _proof_path(directory, name)
        _private_check(path)
        require(path.stat().st_size <= 8192, 'A42331_PROOF_INVALID')
        data = json.loads(path.read_bytes())
        require(set(data) == {'payload', 'mac'}, 'A42331_PROOF_INVALID')
        payload = data['payload']
        require(hmac.compare_digest(data['mac'], hmac.new(key, _canonical(payload),
                                                        'sha256').hexdigest()),
                'A42331_PROOF_INVALID')
        require(set(payload) == {'version', 'context', 'source', 'raw_sha256', 'safe_sha256',
                                'counts', 'skip_policy_status', 'approved_skip_count', 'safe_file'},
                'A42331_PROOF_INVALID')
        require(payload['version'] == PROOF_VERSION and payload['context'] == context
                and payload['source'] == name and payload['counts'] == counts
                and payload['safe_file'] == _instance(Path(root)/name)
                and payload['safe_sha256'] == hashlib.sha256(raw).hexdigest()
                and re.fullmatch('[0-9a-f]{64}', payload['raw_sha256']) is not None,
                'A42331_PROOF_INVALID')
        decision = payload['skip_policy_status'], payload['approved_skip_count']
        require(decision in (('PASS', 1), ('REJECT', 0)) and type(decision[1]) is int,
                'A42331_PROOF_INVALID')
        return decision, True
    except Exception:
        return ('REJECT', 0), False


def _decision(path, root, raw):
    suites, cases, counts = _tree(raw)
    name = Path(path).absolute().relative_to(Path(root).absolute()).as_posix()
    require(name in JUNIT_PATHS, 'A42331_PROOF_SOURCE_INVALID')
    if counts['skipped'] and all(s.get('name') == 'a42331-safe' for s in suites):
        decision, verified = _verify(root, name, raw, counts)
        # Targeted evidence never inherits the full-suite exception.
        if name != JUNIT_PATHS[-1]:
            decision = 'REJECT', 0
        return counts, decision, True, verified
    return counts, _raw_policy(suites, cases, counts, full=name == JUNIT_PATHS[-1]), False, False


def sanitize_junit_for_pytest(path, *, root):
    """Capture raw policy before erasure; no outcome/selection/exit-code changes.

    Legacy/plain sanitizer callers do not issue an attestation. Only fixed CI
    source paths participate; a safe XML without a trusted proof stays rejected.
    """
    path, root = Path(path).absolute(), Path(root).absolute()
    try:
        name = path.relative_to(root).as_posix()
    except ValueError:
        return sanitize_junit(path)
    if name not in JUNIT_PATHS:
        return sanitize_junit(path)
    raw = _read_raw(path)
    try:
        counts, decision, safe_before, _ = _decision(path, root, raw)
    except Exception:
        # Preserve the sanitizer's fixed error codes, including corrupt XML.
        return sanitize_junit(path)
    receipt = sanitize_junit(path)
    if counts['skipped'] and not safe_before:
        try:
            _issue(root, name, raw, path.read_bytes(), counts, decision)
        except Exception:
            # No untrusted proof or altered pytest outcome. The downstream
            # collector will reject a missing/unusable attestation.
            pass
    return receipt


def sanitize_junit(path):
    path = Path(path)
    raw = _read_raw(path)
    require(b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper(),
            'A42331_JUNIT_XML_FORBIDDEN')
    try:
        _tree(raw)
        original = ET.fromstring(raw)
        require(original.tag in ('testsuites','testsuite'),'A42331_JUNIT_SCHEMA_INVALID')
        suites = [original] if original.tag == 'testsuite' else list(original)
        require(suites and all(s.tag == 'testsuite' for s in suites),
                'A42331_JUNIT_SCHEMA_INVALID')
        safe = ET.Element('testsuites')
        totals = dict(tests=0,failures=0,errors=0,skipped=0)
        for suite in suites:
            cases = suite.findall('testcase')
            observed = dict(tests=len(cases),**{k:sum(len(c.findall(tag)) for c in cases)
                for k,tag in (('failures','failure'),('errors','error'),('skipped','skipped'))})
            declared = {k:int(suite.attrib[k]) for k in totals}
            require(observed == declared,'A42331_JUNIT_COUNTS_MISMATCH')
            target = ET.SubElement(safe,'testsuite',name='a42331-safe',
                                   **{k:str(v) for k,v in observed.items()})
            for key,value in observed.items():
                totals[key] += value
            for case in cases:
                identity = case.get('classname','redacted'), case.get('name','redacted')
                approved_id = any(identity == entry[:2] for entry in ALLOWED_FULL_SUITE_SKIPS)
                if case.findall('skipped') and not approved_id:
                    # Unknown skipped IDs are untrusted input, even when they look
                    # like Python identifiers. Only canonical hashes survive a
                    # repeated export; the one public approved ID stays readable.
                    identity = tuple(value if suite.get('name') == 'a42331-safe'
                        and re.fullmatch(r'redacted_[0-9a-f]{16}', value) else
                        'redacted_'+hashlib.sha256(value.encode()).hexdigest()[:16]
                        for value in identity)
                item = ET.SubElement(target,'testcase',
                    classname=safe_identifier(identity[0]),
                    name=safe_identifier(identity[1],parameter=True),
                    time=number(case.get('time','0')))
                for tag,code in (('failure','A42331_TEST_FAILURE'),('error','A42331_TEST_ERROR'),
                                 ('skipped','A42331_TEST_SKIPPED')):
                    for _ in case.findall(tag):
                        node = ET.SubElement(item,tag,message=code,type=code)
                        node.text = code
        require(totals['tests'] > 0,'A42331_JUNIT_EMPTY')
        encoded = ET.tostring(safe,encoding='utf-8',xml_declaration=True)
        if encoded != raw:
            # Canonical safe re-exports are read-only: preserve the file-instance
            # binding. A new raw generation gets a fresh inode/time identity even
            # when redaction produces identical bytes, preventing stale PASS reuse.
            with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent,
                                             prefix=path.name+'.', suffix='.a42331.tmp',
                                             delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary,path)
        return dict(counts=totals,sha256=hashlib.sha256(encoded).hexdigest(),bytes=len(encoded))
    except BaseException:
        # ET/driver/test messages and XML attributes may contain SQL or secrets.
        raise RuntimeError('A42331_JUNIT_SANITIZATION_FAILED') from None


def collect(root, output, *, outcomes, upstream):
    root,output = Path(root),Path(output)
    value = dict(schema_version='a42331.ci-failure-evidence.v1',evidence_kind='DIAGNOSTIC_ONLY',
        head_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        run_id=os.environ.get('GITHUB_RUN_ID','local'),attempt=os.environ.get('GITHUB_RUN_ATTEMPT','1'),
        status='INCOMPLETE',evidence_complete=False,files={},full_test_counts=None,
        skip_policy_status='NOT_ASSESSED',approved_skip_count=0,
        skip_policy_version=PROOF_VERSION,full_skip_proof_source='NOT_ASSESSED',
        first_failure_code=None,capacity_ready=False,performance_eligible=False,
        production_read_authorized=False)
    try:
        require(re.fullmatch(r'[0-9a-f]{40}',value['head_sha']) is not None
                and value['head_sha'] == os.environ.get('GITHUB_SHA',value['head_sha']),
                'A42331_HEAD_MISMATCH')
        require(set(outcomes) == set(PHASES) and all(v in OUTCOMES for v in outcomes.values())
                and upstream in OUTCOMES,'A42331_STEP_STATUS_INVALID')
        value['steps'] = outcomes
        value['upstream_status'] = upstream
        policies = []
        for name in JUNIT_PATHS:
            source = root/name
            if source.exists():
                counts, decision, safe_before, verified = _decision(source, root, _read_raw(source))
                if name == JUNIT_PATHS[-1]:
                    value['full_skip_proof_source'] = (
                        'NOT_REQUIRED' if not counts['skipped'] else
                        'RAW_CURRENT_PROCESS' if not safe_before else
                        'AUTHENTICATED_PRIOR_SANITIZER' if verified else
                        'MISSING_OR_INVALID')
                policies.append(decision)
                receipt = sanitize_junit_for_pytest(source, root=root)
                output.mkdir(parents=True,exist_ok=True)
                destination = output/source.name
                destination.write_bytes(source.read_bytes())  # Source is now canonical safe XML.
                value['files'][source.name] = receipt
        required = (('full_tests','m17_1_2-full.xml'),('targeted','a42331-targeted.xml'))
        for phase,filename in required:
            if outcomes[phase] in ('success','failure'):
                require(filename in value['files'],'A42331_REQUIRED_JUNIT_MISSING')
        full = value['files'].get('m17_1_2-full.xml')
        if full:
            value['full_test_counts'] = full['counts']
        require(outcomes['full_tests'] != 'success' or full and not any(
            full['counts'][k] for k in ('failures','errors')),
            'A42331_TEST_STATUS_MISMATCH')
        value['skip_policy_status'] = 'PASS' if all(p[0] == 'PASS' for p in policies) else 'REJECT'
        value['approved_skip_count'] = sum(p[1] for p in policies) if full else 0
        if upstream == 'success':
            require(all(v == 'success' for v in outcomes.values()),
                    'A42331_REQUIRED_STAGE_NOT_RUN')
            if value['skip_policy_status'] == 'PASS':
                value['status'] = 'COMPLETE'
        else:
            value['first_failure_code'] = 'A42331_UPSTREAM_NOT_SUCCESS'
        if value['skip_policy_status'] == 'REJECT':
            value['first_failure_code'] = 'A42331_SKIP_POLICY_REJECTED'
        value['evidence_complete'] = True
    except BaseException:
        value['first_failure_code'] = 'A42331_SAFE_EVIDENCE_INCOMPLETE'
    atomic(output/'failure.json',value)  # Mandatory even when the source JUnit is missing/corrupt.
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('redact-v14','collect'))
    args = parser.parse_args()
    try:
        if args.mode == 'redact-v14':
            path = Path('.codex_tmp/v14-targeted.xml')
            if path.exists():
                sanitize_junit(path)
            return
        value = collect(Path.cwd(),Path('.codex_tmp/a42331-ci'),
            outcomes=json.loads(os.environ['A42331_STEP_OUTCOMES']),
            upstream=os.environ.get('UPSTREAM_STATUS','unknown'))
        print(json.dumps({k:value[k] for k in ('status','evidence_complete','full_test_counts',
                                              'first_failure_code','skip_policy_status',
                                              'approved_skip_count')}))
        raise SystemExit(0 if value['evidence_complete']
                         and value['skip_policy_status'] == 'PASS' else 1)
    except SystemExit:
        raise
    except BaseException:
        raise SystemExit('A42331_SAFE_EVIDENCE_FAILED') from None


if __name__ == '__main__':
    main()
