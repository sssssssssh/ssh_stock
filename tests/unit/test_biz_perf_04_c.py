"""Pure offline state/evidence contracts. No resource probe or dataset generation."""

import copy

import pytest

from scripts import business_capacity_contract as c


def initial():
    return c.initial('a' * 40, 'b' * 64)


def dataset(outcome=True):
    return dict(validator_version='biz-perf-04-b.generator.v1', outcome=outcome,
                manifest_sha256='c' * 64)


def denial():
    return dict(policy_version=c.VERSION, decision='DENIED', approval_reference_sha256='d' * 64)


def test_unassessed_is_neither_failure_nor_success():
    value = initial()
    assert all(s == {'value': 'NOT_ASSESSED', 'evidence': None}
               for s in value['states'].values())
    c.validate(value)


@pytest.mark.parametrize('field,payload,expected', [
    ('runner_resources_ready', c.RESOURCE_LIMITS, True),
    ('runner_resources_ready', {**c.RESOURCE_LIMITS, 'cpu_count': 0}, False),
    ('dataset_contract_ready', dataset(), True),
    ('dataset_contract_ready', dataset(False), False),
    ('performance_eligible', denial(), False), ('production_read_authorized', denial(), False),
])
def test_independent_observations(field, payload, expected):
    before = initial()
    after = c.transition(before, field, payload)
    assert after['states'][field]['value'] is expected
    assert all(after['states'][k] == before['states'][k] for k in c.FIELDS if k != field)
    assert before == initial()
    c.validate_transition(before, after)


def test_resource_and_dataset_success_never_grant_capacity_or_authority():
    first = c.transition(initial(), 'runner_resources_ready', c.RESOURCE_LIMITS)
    second = c.transition(first, 'dataset_contract_ready', dataset())
    for field in c.FIELDS[2:]:
        assert second['states'][field]['value'] == c.NOT_ASSESSED
    with pytest.raises(ValueError):
        c.transition(second, 'diagnostic_capacity_assessed', {'outcome': True})
    with pytest.raises(ValueError):
        c.transition(second, 'dataset_contract_ready', dataset())


@pytest.mark.parametrize('mutation', [
    lambda d: d['states'].pop('dataset_contract_ready'),
    lambda d: d['states'].update(unknown={'value': False, 'evidence': None}),
    lambda d: d['states']['runner_resources_ready'].update(value=False),
    lambda d: d['states']['performance_eligible'].update(value=True),
    lambda d: d['states']['production_read_authorized'].update(value=True),
    lambda d: d['states']['diagnostic_capacity_assessed'].update(value=True),
    lambda d: d.update(schema_version='unknown'),
    lambda d: d.update(commit_sha='bad'), lambda d: d.update(dataset_sha256='bad'),
    lambda d: d.update(revision=True), lambda d: d.update(capacity_ready=True),
])
def test_missing_invalid_and_privilege_states_refused(mutation):
    doc = initial()
    mutation(doc)
    with pytest.raises(ValueError):
        c.validate(doc)


@pytest.mark.parametrize('key,value', [('sha256', '0' * 64), ('commit_sha', 'e' * 40),
                                     ('dataset_sha256', 'e' * 64), ('field', 'other')])
def test_wrong_evidence_identity_refused(key, value):
    doc = c.transition(initial(), 'dataset_contract_ready', dataset())
    doc['states']['dataset_contract_ready']['evidence'][key] = value
    with pytest.raises(ValueError):
        c.validate(doc)


@pytest.mark.parametrize('payload', [dict(cpu_count=True, available_memory_bytes=1,
    free_disk_bytes=1), {}, dict(c.RESOURCE_LIMITS, extra=1)])
def test_incomplete_or_wrong_resource_evidence_refused(payload):
    with pytest.raises(ValueError):
        c.transition(initial(), 'runner_resources_ready', payload)


def test_false_and_not_assessed_cannot_be_reset_or_changed():
    before = c.transition(initial(), 'dataset_contract_ready', dataset(False))
    after = copy.deepcopy(before)
    after['states']['dataset_contract_ready'] = initial()['states']['dataset_contract_ready']
    with pytest.raises(ValueError):
        c.validate_transition(before, after)
    next_doc = c.transition(before, 'runner_resources_ready', c.RESOURCE_LIMITS)
    next_doc['previous_sha256'] = '0' * 64
    with pytest.raises(ValueError):
        c.validate_transition(before, next_doc)


@pytest.mark.parametrize('field', ['performance_eligible', 'production_read_authorized'])
def test_policy_allow_is_never_supported(field):
    with pytest.raises(ValueError):
        c.transition(initial(), field, {**denial(), 'decision': 'ALLOWED'})
