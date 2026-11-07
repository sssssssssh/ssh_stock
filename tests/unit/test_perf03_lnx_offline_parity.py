"""Handwritten JSON only; no ORM, pandas or true root execution."""

import copy

import pytest

from scripts import perf03_lnx_offline_contract as c


def row(receipt):
    return receipt['business_snapshot']['tables']['artificial_result']['rows'][0]


def table(receipt):
    return receipt['business_snapshot']['tables']['artificial_result']


@pytest.mark.parametrize('outcome', ['SUCCESS', 'FAILED', 'CANCELLED', 'UNKNOWN_ACK'])
def test_legal_mock_outcomes_and_explicit_identity_mapping(outcome):
    left, right = [c.mock_receipt(arm, outcome=outcome) for arm in ('OFF1', 'ON1')]
    assert row(left)['job_id'] != row(right)['job_id']
    assert c.parity(left, right)['status'] == 'MOCK_PARITY_VALIDATED'
    assert c.parity(left, right)['REAL_PG_PARITY'] == 'NOT_VERIFIED'
    if outcome == 'UNKNOWN_ACK':
        assert left['final_receipt_status'] == 'INCOMPLETE'
        with pytest.raises(c.Refused):
            c.statistics([c.mock_receipt(arm, outcome=outcome) for arm in c.ORDER])


@pytest.mark.parametrize('mutate', [
    lambda r: r['business_snapshot']['tables'].clear(),
    lambda r: r['business_snapshot']['tables'].update(extra=copy.deepcopy(table(r))),
    lambda r: table(r)['rows'].clear(),
    lambda r: table(r)['rows'].append(copy.deepcopy(row(r))),
    lambda r: table(r)['rows'].append({**row(r), 'key': 'SYNTHETIC_B'}),
    lambda r: table(r)['rows'].insert(0, {**row(r), 'key': 'SYNTHETIC_B'}),
    lambda r: row(r).pop('quantity'),
    lambda r: row(r).update(extra=1),
    lambda r: table(r)['columns']['quantity'].update(dtype='float'),
    lambda r: row(r).update(quantity=2.0),
    lambda r: row(r).update(quantity=True),
    lambda r: row(r).update(price=12.34),
    lambda r: row(r).update(price='12.34'),
    lambda r: row(r).update(price='Infinity'),
    lambda r: row(r).update(ratio=float('nan')),
    lambda r: row(r).update(ratio={'kind': 'nan'}),
    lambda r: row(r).update(optional=''),
    lambda r: row(r).update(optional=0),
    lambda r: row(r).update(day='2026-02-24'),
    lambda r: row(r).update(day='2026-02-23T00:00:00'),
    lambda r: row(r).update(at='2026-02-23T00:00:00'),
    lambda r: row(r).update(at='2026-02-23T08:00:00+08:00'),
    lambda r: row(r).update(job_id=row(r)['root_id']),
    lambda r: row(r).update(generation_id='00000000-0000-0000-0000-000000000099'),
    lambda r: row(r).update(owner_id='00000000-0000-0000-0000-000000000099'),
    lambda r: r['business_snapshot']['entities'].pop(),
    lambda r: r['business_snapshot']['entities'][1].update(root=row(r)['job_id']),
    lambda r: r['business_snapshot']['entities'][2].update(generation=row(r)['job_id']),
    lambda r: r['business_snapshot']['entities'][2].update(id=row(r)['root_id']),
    lambda r: r.update(publication_state='ABORTED'),
    lambda r: r.update(job_state='UNKNOWN_ACK', ack_state='UNKNOWN'),
    lambda r: r.pop('publication_state'),
    lambda r: r['metrics']['counts'].update(business_calls=11),
    lambda r: r['metrics']['counts'].update(business_writes=3),
    lambda r: r['metrics']['counts'].update(heartbeat_calls=2),
    lambda r: r['metrics']['counts'].update(observer_control_calls=1),
    lambda r: r['metrics']['counts'].update(total=13),
])
def test_every_business_or_identity_difference_rejected(mutate):
    left, right = c.mock_receipt('OFF1'), c.mock_receipt('ON1')
    mutate(right)
    assert c.parity(left, right)['status'] == 'MOCK_PARITY_REJECTED'


def test_owner_cannot_be_renamed_even_with_consistent_internal_graph():
    left, right = c.mock_receipt('OFF1'), c.mock_receipt('ON1')
    changed = '00000000-0000-0000-0000-000000000088'
    for node in right['business_snapshot']['entities']:
        node['owner'] = changed
        if node['kind'] == 'owner':
            node['id'] = changed
    row(right)['owner_id'] = changed
    c.validate_snapshot(right['business_snapshot'])
    assert c.parity(left, right)['status'] == 'MOCK_PARITY_REJECTED'


def test_tagged_nan_distinct_from_null_and_accepted_only_when_both_match():
    left, right = c.mock_receipt('OFF1'), c.mock_receipt('ON1')
    row(left)['ratio'] = row(right)['ratio'] = {'kind': 'nan'}
    assert c.parity(left, right)['status'] == 'MOCK_PARITY_VALIDATED'
    row(right)['ratio'] = None
    assert c.parity(left, right)['status'] == 'MOCK_PARITY_REJECTED'
