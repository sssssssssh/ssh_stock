"""04-C offline status contract. No execution authority or runtime integration."""

import copy
import hashlib
import json
import re

VERSION = 'biz-perf-04-c.status.v1'
NOT_ASSESSED = 'NOT_ASSESSED'
FIELDS = ('runner_resources_ready', 'dataset_contract_ready', 'diagnostic_capacity_assessed',
          'performance_eligible', 'production_read_authorized')
RESOURCE_LIMITS = {'cpu_count': 4, 'available_memory_bytes': 8 * 1024**3,
                   'free_disk_bytes': 8 * 1024**3}


def require(value):
    if not value:
        raise ValueError('BIZ04_STATUS_CONTRACT_INVALID')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def hex_value(value, length):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value)


def initial(commit_sha, dataset_sha256):
    document = dict(schema_version=VERSION, commit_sha=commit_sha,
                    dataset_sha256=dataset_sha256, revision=0,
                    previous_sha256=None, states={k: dict(value=NOT_ASSESSED, evidence=None)
                                                  for k in FIELDS})
    validate(document)
    return document


def observation_value(field, evidence, document):
    require(isinstance(evidence, dict) and set(evidence) == {
        'schema_version', 'field', 'commit_sha', 'dataset_sha256', 'payload', 'sha256'})
    require(evidence['schema_version'] == VERSION and evidence['field'] == field
            and evidence['commit_sha'] == document['commit_sha']
            and evidence['dataset_sha256'] == document['dataset_sha256'])
    require(evidence['sha256'] == digest({k: v for k, v in evidence.items() if k != 'sha256'}))
    payload = evidence['payload']
    require(isinstance(payload, dict))
    if field == 'runner_resources_ready':
        require(set(payload) == set(RESOURCE_LIMITS))
        require(all(type(v) is int and v >= 0 for v in payload.values()))
        return all(payload[k] >= minimum for k, minimum in RESOURCE_LIMITS.items())
    if field == 'dataset_contract_ready':
        require(set(payload) == {'validator_version', 'outcome', 'manifest_sha256'})
        require(payload['validator_version'] == 'biz-perf-04-b.generator.v1'
                and type(payload['outcome']) is bool
                and hex_value(payload['manifest_sha256'], 64))
        return payload['outcome']
    # No capacity experiment is authorized in this version. No positive privilege exists.
    require(field in ('performance_eligible', 'production_read_authorized'))
    require(set(payload) == {'policy_version', 'decision', 'approval_reference_sha256'})
    require(payload['policy_version'] == VERSION and payload['decision'] == 'DENIED'
            and hex_value(payload['approval_reference_sha256'], 64))
    return False


def validate(document):
    require(isinstance(document, dict) and set(document) == {
        'schema_version', 'commit_sha', 'dataset_sha256', 'revision', 'previous_sha256', 'states'})
    require(document['schema_version'] == VERSION and hex_value(document['commit_sha'], 40)
            and hex_value(document['dataset_sha256'], 64))
    require(type(document['revision']) is int and 0 <= document['revision'] <= len(FIELDS))
    require((document['revision'] == 0 and document['previous_sha256'] is None)
            or (document['revision'] > 0 and hex_value(document['previous_sha256'], 64)))
    require(isinstance(document['states'], dict) and set(document['states']) == set(FIELDS))
    assessed = 0
    for field, state in document['states'].items():
        require(isinstance(state, dict) and set(state) == {'value', 'evidence'})
        value = state['value']
        if type(value) is str and value == NOT_ASSESSED:
            require(state['evidence'] is None)
        else:
            require(type(value) is bool)
            expected = observation_value(field, state['evidence'], document)
            require(value is expected)
            assessed += 1
    require(assessed == document['revision'])


def transition(previous, field, payload):
    """Append one assessment; cannot erase or overwrite any prior assessment."""
    validate(previous)
    require(field in FIELDS and previous['states'][field]['value'] == NOT_ASSESSED)
    result = copy.deepcopy(previous)
    evidence = dict(schema_version=VERSION, field=field, commit_sha=previous['commit_sha'],
                    dataset_sha256=previous['dataset_sha256'], payload=copy.deepcopy(payload))
    evidence['sha256'] = digest(evidence)
    value = observation_value(field, evidence, previous)
    result['states'][field] = dict(value=value, evidence=evidence)
    result['revision'] += 1
    result['previous_sha256'] = digest(previous)
    validate_transition(previous, result)
    return result


def validate_transition(previous, current):
    validate(previous)
    validate(current)
    require(all(previous[k] == current[k] for k in
                ('schema_version', 'commit_sha', 'dataset_sha256')))
    require(current['revision'] == previous['revision'] + 1
            and current['previous_sha256'] == digest(previous))
    changes = [k for k in FIELDS if previous['states'][k] != current['states'][k]]
    require(len(changes) == 1)
    field = changes[0]
    require(previous['states'][field]['value'] == NOT_ASSESSED
            and type(current['states'][field]['value']) is bool)
