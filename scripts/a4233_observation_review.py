"""Offline, bounded artifact verification. Never imports database/application code."""

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from scripts.a4233_observation_contract import (
    DRAFT,
    PROTOCOL,
    SOURCES,
    Fault,
    Identity,
    check,
    digest,
    failure_code,
    seal,
    validate,
    write_new,
)


def source_identity(root, *, instance_hash):
    """Caller already verified the independent physical target; no DB here."""
    return Identity(head_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,
        text=True).strip(),run_id=os.environ.get('GITHUB_RUN_ID','local'),
        attempt=int(os.environ.get('GITHUB_RUN_ATTEMPT','1')),
        instance_identity_sha256=instance_hash,
        source_sha256=digest({p:hashlib.sha256((root/p).read_bytes()).hexdigest()
                              for p in SOURCES}),
        protocol_sha256=hashlib.sha256((root/PROTOCOL).read_bytes()).hexdigest())


def review(value, expected):
    receipt = validate(value,expected)
    return dict(schema_version='a4233.review.v1',**expected.model_dump(),
        evidence_kind='DIAGNOSTIC_ONLY',protocol_status=DRAFT,
        data_source='SYNTHETIC_MICRO_SELFTEST',status=receipt.status,
        ticks=len(receipt.ticks),first_failure_code=receipt.first_failure_code,
        cleanup_failure_codes=receipt.cleanup_failure_codes,
        observed_event_codes=sorted({e.code for t in receipt.ticks for e in t.events}),
        absence_proven=False,causality='NOT_EVALUATED',unique_repair_candidate=None,
        performance_eligible=False,capacity_ready=False,production_read_authorized=False,
        observer_overhead_calibration='NOT_RUN_NOT_AUTHORIZED')


def load(path):
    path = Path(path)
    check(path.stat().st_size <= 8_000_000,'A4233_ARTIFACT_TOO_LARGE')
    def pairs(items):
        check(len({k for k,v in items}) == len(items),'A4233_DUPLICATE_JSON_KEY')
        return dict(items)
    try:
        return json.loads(path.read_text(),object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Fault('A4233_NONFINITE')))
    except Fault:
        raise
    except Exception:
        raise Fault('A4233_ARTIFACT_INVALID') from None


def bundle(directory, value, expected):
    """New owned directory; costs exclude lookup (none is run) and are nested wall."""
    directory = Path(directory)
    check(not directory.exists(),'A4233_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    result = review(value,expected)
    documents = {'observer-contract.json':value,
        'ticks.json':dict(**expected.model_dump(),schema_version='a4233.ticks.v1',
            evidence_kind='DIAGNOSTIC_ONLY',data_source='SYNTHETIC_MICRO_SELFTEST',
            protocol_status=DRAFT,ticks=value['ticks'],failed_tick=value.get('failed_tick')),
        'review.json':result,
        'failure.json':dict(**expected.model_dump(),schema_version='a4233.failure.v1',
            evidence_kind='DIAGNOSTIC_ONLY',protocol_status=DRAFT,
            data_source='SYNTHETIC_MICRO_SELFTEST',first_failure_code=value['first_failure_code'],
            cleanup_failure_codes=value['cleanup_failure_codes'],
            performance_eligible=False,capacity_ready=False,production_read_authorized=False)}
    records = {}
    try:
        for name,document in documents.items():
            started = time.monotonic_ns()
            encoded = (json.dumps(document,allow_nan=False,separators=(',',':'))+'\n').encode()
            serialization_ms = (time.monotonic_ns()-started)/1e6
            started = time.monotonic_ns()
            actual = write_new(directory/name,document)
            write_ms = (time.monotonic_ns()-started)/1e6
            check(hashlib.sha256(encoded).hexdigest() == actual,'A4233_WRITE_HASH_MISMATCH')
            records[name] = dict(sha256=actual,bytes=len(encoded),
                serialization_wall_ms=serialization_ms,
                atomic_write_wall_ms_including_reserialization=write_ms)
        manifest = dict(schema_version='a4233.manifest.v1',**expected.model_dump(),
            evidence_kind='DIAGNOSTIC_ONLY',protocol_status=DRAFT,
            data_source='SYNTHETIC_MICRO_SELFTEST',files=records,
            cost_scope='NESTED_WALL_NOT_CPU_OR_IO_CALIBRATION',
            performance_eligible=False,capacity_ready=False,production_read_authorized=False)
        write_new(directory/'manifest.json',seal(manifest))
    except BaseException as error:
        # Do not overwrite partial artifacts. If disk is broken, even this can fail;
        # caller/CI must fail and may only retain stdout fixed code, not claim success.
        try:
            write_new(directory/'artifact-failure.json',dict(**expected.model_dump(),
                evidence_kind='DIAGNOSTIC_ONLY',status='INCOMPLETE_OBSERVABILITY',
                first_failure_code=failure_code(error),capacity_ready=False,
                production_read_authorized=False,performance_eligible=False))
        except BaseException:
            pass
        raise Fault('A4233_ARTIFACT_WRITE_FAILED') from None
    return manifest


def review_bundle(directory, expected):
    directory = Path(directory)
    manifest = load(directory/'manifest.json')
    check(set(manifest) == set(expected.model_dump()) | {'schema_version','evidence_kind',
        'protocol_status','data_source','files','cost_scope','performance_eligible','capacity_ready',
        'production_read_authorized','content_sha256'}, 'A4233_MANIFEST_INVALID')
    check(manifest['content_sha256'] == digest({k:v for k,v in manifest.items()
        if k != 'content_sha256'}),'A4233_DIGEST_MISMATCH')
    check(all(manifest[k] == v for k,v in expected.model_dump().items()),
          'A4233_IDENTITY_MISMATCH')
    check(manifest['schema_version'] == 'a4233.manifest.v1'
          and manifest['evidence_kind'] == 'DIAGNOSTIC_ONLY'
          and manifest['protocol_status'] == DRAFT
          and manifest['data_source'] == 'SYNTHETIC_MICRO_SELFTEST'
          and manifest['cost_scope'] == 'NESTED_WALL_NOT_CPU_OR_IO_CALIBRATION'
          and all(manifest[k] is False for k in ('performance_eligible','capacity_ready',
                                                'production_read_authorized')),
          'A4233_MANIFEST_INVALID')
    check(set(manifest['files']) == {'observer-contract.json','ticks.json',
                                     'review.json','failure.json'},
          'A4233_BUNDLE_INCOMPLETE')
    for name,entry in manifest['files'].items():
        p = directory/name
        check(p.is_file() and not p.is_symlink() and p.stat().st_size <= 8_000_000
              and p.stat().st_size == entry['bytes']
              and hashlib.sha256(p.read_bytes()).hexdigest() == entry['sha256'],
              'A4233_ARTIFACT_CORRUPT')
    receipt = load(directory/'observer-contract.json')
    result = review(receipt,expected)
    check(load(directory/'review.json') == result,'A4233_REVIEW_MISMATCH')
    ticks = load(directory/'ticks.json')
    check(ticks == dict(**expected.model_dump(),schema_version='a4233.ticks.v1',
        evidence_kind='DIAGNOSTIC_ONLY',data_source='SYNTHETIC_MICRO_SELFTEST',
        protocol_status=DRAFT,ticks=receipt['ticks'],failed_tick=receipt['failed_tick']),
          'A4233_TICKS_MISMATCH')
    check(load(directory/'failure.json') == dict(**expected.model_dump(),
        schema_version='a4233.failure.v1',evidence_kind='DIAGNOSTIC_ONLY',protocol_status=DRAFT,
        data_source='SYNTHETIC_MICRO_SELFTEST',first_failure_code=receipt['first_failure_code'],
        cleanup_failure_codes=receipt['cleanup_failure_codes'],performance_eligible=False,
        capacity_ready=False,production_read_authorized=False),'A4233_FAILURE_MISMATCH')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',required=True,type=Path)
    # Explicit independent receipt identity, NOT inferred from untrusted manifest.
    for key in Identity.model_fields:
        parser.add_argument('--'+key.replace('_','-'),required=True,
                            type=int if key == 'attempt' else str)
    args = vars(parser.parse_args())
    directory = args.pop('directory')
    try:
        result = review_bundle(directory,Identity(**args))
        print(json.dumps(result,separators=(',',':')))
    except Exception:
        raise SystemExit('A4233_OFFLINE_REVIEW_REJECTED') from None


if __name__ == '__main__':
    main()
