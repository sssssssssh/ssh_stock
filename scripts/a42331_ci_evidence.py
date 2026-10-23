"""Safe complete JUnit and exact-SHA failure receipts; never a release/SQL gate."""

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.a42_artifacts import atomic

JUNIT_PATHS = ('.codex_tmp/v14-targeted.xml','.codex_tmp/a42331-targeted.xml',
    '.codex_tmp/m17_1_2-targeted.xml','.codex_tmp/data-publication-targeted.xml',
    '.codex_tmp/cold-start-targeted.xml','.codex_tmp/m17_1_2-full.xml')
PHASES = ('targeted','full_tests','data_queue','browser','runtime_browser')
OUTCOMES = {'success','failure','skipped','cancelled','unknown'}


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


def sanitize_junit(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 50_000_000,
            'A42331_JUNIT_MISSING_OR_TOO_LARGE')
    raw = path.read_bytes()
    require(b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper(),
            'A42331_JUNIT_XML_FORBIDDEN')
    try:
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
                item = ET.SubElement(target,'testcase',
                    classname=safe_identifier(case.get('classname','redacted')),
                    name=safe_identifier(case.get('name','redacted'),parameter=True),
                    time=number(case.get('time','0')))
                for tag,code in (('failure','A42331_TEST_FAILURE'),('error','A42331_TEST_ERROR'),
                                 ('skipped','A42331_TEST_SKIPPED')):
                    for _ in case.findall(tag):
                        node = ET.SubElement(item,tag,message=code,type=code)
                        node.text = code
        require(totals['tests'] > 0,'A42331_JUNIT_EMPTY')
        encoded = ET.tostring(safe,encoding='utf-8',xml_declaration=True)
        temporary = path.with_suffix(path.suffix+'.a42331.tmp')
        with temporary.open('wb') as stream:
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
        for name in JUNIT_PATHS:
            source = root/name
            if source.exists():
                receipt = sanitize_junit(source)
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
            full['counts'][k] for k in ('failures','errors','skipped')),
            'A42331_TEST_STATUS_MISMATCH')
        if upstream == 'success':
            require(all(v == 'success' for v in outcomes.values()),
                    'A42331_REQUIRED_STAGE_NOT_RUN')
            value['status'] = 'COMPLETE'
        else:
            value['first_failure_code'] = 'A42331_UPSTREAM_NOT_SUCCESS'
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
                                              'first_failure_code')}))
        raise SystemExit(0 if value['evidence_complete'] else 1)
    except SystemExit:
        raise
    except BaseException:
        raise SystemExit('A42331_SAFE_EVIDENCE_FAILED') from None


if __name__ == '__main__':
    main()
