"""Export counts/fixed identifiers only; never archive arbitrary pytest failure text."""

import argparse
from pathlib import Path
from xml.etree import ElementTree

from scripts.a42_artifacts import atomic, failure, header, isolation


def receipt(source):
    output = dict(**header('a4232-light-contracts'),status='INCOMPLETE',
        evidence_kind='DIAGNOSTIC_ONLY',capacity_ready=False,performance_eligible=False)
    try:
        if not source.is_file() or source.stat().st_size > 50_000_000:
            raise ValueError('A4232_TEST_RECEIPT_MISSING')
        suites = list(ElementTree.fromstring(source.read_bytes()).iter('testsuite'))
        counts = {key:sum(int(s.attrib[key]) for s in suites)
                  for key in ('tests','failures','errors','skipped')}
        output['counts'] = counts
        if counts['tests'] > 0 and counts['failures'] == counts['errors'] == counts['skipped'] == 0:
            output['status'] = 'COMPLETE'
    except BaseException as error:
        output.update(failure(error))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    output = receipt(args.source)
    try:
        output.update(isolation())
    except BaseException as error:
        output.update(status='INCOMPLETE',**failure(error))
    atomic(args.output,output)
    raise SystemExit(0 if output['status'] == 'COMPLETE' else 1)


if __name__ == '__main__':
    main()
