"""A4233 low-cost test counts/proof only; no raw JUnit or driver error export."""

import argparse
from pathlib import Path

from scripts.a42_artifacts import isolation
from scripts.a42_receipt_contract import physical
from scripts.a4232_test_receipt import receipt as test_counts
from scripts.a4233_observation_contract import DRAFT, digest, seal, write_new
from scripts.a4233_observation_review import source_identity


def receipt(source):
    root = Path(__file__).resolve().parents[1]
    result = dict(schema_version='a4233.tests.v1',evidence_kind='DIAGNOSTIC_ONLY',
        data_source='SYNTHETIC_MICRO_SELFTEST',protocol_status=DRAFT,
        status='INCOMPLETE_OBSERVABILITY',physical_verified=False,
        first_failure_code=None,capacity_ready=False,performance_eligible=False,
        production_read_authorized=False,unique_repair_candidate=None)
    instance_hash = digest(None)
    try:
        proof = isolation()
        physical(proof)
        instance_hash = digest([proof['database_instance'],proof['physical_system_identifier']])
        result['physical_verified'] = True
        counts = test_counts(source)
        result['counts'] = counts.get('counts')
        if counts['status'] == 'COMPLETE':
            result['status'] = 'COMPLETE_CONTRACT'
        else:
            result['first_failure_code'] = 'A4233_TESTS_INCOMPLETE'
    except BaseException:
        result['first_failure_code'] = 'A4233_TEST_PROOF_INCOMPLETE'
    result.update(source_identity(root,instance_hash=instance_hash).model_dump())
    return seal(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    value = receipt(args.source)
    write_new(args.output,value)
    raise SystemExit(0 if value['status'] == 'COMPLETE_CONTRACT' else 1)


if __name__ == '__main__':
    main()
