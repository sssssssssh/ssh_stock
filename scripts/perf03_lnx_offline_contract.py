"""Versioned MOCK ONLY evidence; never a real experiment or application adapter."""

import copy
import hashlib
import json
import re
import statistics as arithmetic
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

SCHEMA = 'perf03-lnx.mock.v1'
KIND = 'MOCK_ONLY_DO_NOT_USE_FOR_PERFORMANCE_ACCEPTANCE'
ORDER = ('OFF1', 'ON1', 'OFF2', 'ON2', 'OFF3', 'ON3')
AUTHORIZATION = dict(real_pg_executed=False, experimental_execution_authorized=False,
                     capacity_ready=False, production_read_authorized=False)
MAX_BYTES = 65536
ROLES = ('owner', 'root', 'job', 'calc_run', 'generation')
STATES = {'COMPLETE_MOCK', 'INCOMPLETE', 'FAILED', 'TIMED_OUT', 'CRASHED',
          'CLEANUP_UNCERTAIN', 'EVIDENCE_UNAVAILABLE'}
UNCONFIRMED = 'UNCONFIRMED_REQUIRES_OWNER_CONFIRMATION'


class Refused(ValueError):
    """Fixed public failure code; never include input or raw exceptions."""


def require(condition, code='MOCK_CONTRACT_REJECTED'):
    if not condition:
        raise Refused(code)


def exact(value, keys):
    require(type(value) is dict and set(value) == set(keys))


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True, allow_nan=False).encode('ascii')
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise Refused('MOCK_JSON_REJECTED') from None


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def load(raw):
    require(type(raw) is bytes and len(raw) <= MAX_BYTES)

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result

    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: require(False))
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('MOCK_JSON_REJECTED') from None


def protocol():
    return dict(protocol_id='perf03-lnx-offline', protocol_version=1, tool_version=1,
        protocol_family='biz-perf-03-a-r1', protocol_scope='LINUX_OFFLINE_TOOL_DRAFT',
        business_seed=dict(symbols=2, history_days=420, first_calendar_date='2025-01-01',
            last_calendar_date='2026-02-24', include_closed=False, request_start='2026-02-23',
            request_end='2026-02-24', evaluate_signals=False, mode='manual',
            factor_warmup_trading_days=250, factor_lookback_calendar_days=430),
        measurement=dict(dry_run_only=True, single_pair_order=['OFF', 'ON'],
            full_order=list(ORDER), setup_seconds=180, root_seconds=180, cleanup_seconds=30,
            full_six_arm_window_seconds=2700, overhead_threshold_percent=3,
            required_complete_pairs=3, percentile_p95=None))


def validate_protocol(value):
    require(canonical(value) == canonical(protocol()))


def number(value):
    require(type(value) is str and re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?', value)
            is not None and len(value) <= 40)
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise Refused('MOCK_NUMBER_REJECTED') from None
    require(result.is_finite() and result >= 0)
    return result


def uid(value):
    try:
        require(type(value) is str and str(uuid.UUID(value)) == value)
    except (ValueError, AttributeError, TypeError):
        raise Refused('MOCK_ID_REJECTED') from None


def columns():
    return dict(key=dict(dtype='str', identity=None),
        **{role + '_id': dict(dtype='uuid', identity=role) for role in ROLES},
        quantity=dict(dtype='int', identity=None), price=dict(dtype='decimal', identity=None),
        ratio=dict(dtype='float', identity=None), day=dict(dtype='date', identity=None),
        at=dict(dtype='datetime', identity=None), optional=dict(dtype='str', identity=None))


def snapshot(index=1):
    """Small artificial fixture, explicitly unrelated to ORM table reflection."""
    ids = {role: str(uuid.UUID(int=(1 if role == 'owner' else index * 10 + i + 2)))
           for i, role in enumerate(ROLES)}
    entities = [dict(id=ids[role], kind=role, owner=ids['owner'], root=ids['root'],
                     generation=ids['generation']) for role in ROLES]
    row = dict(key='SYNTHETIC_A', **{role + '_id': ids[role] for role in ROLES},
        quantity=2, price='12.3400', ratio=1.5, day='2026-02-23',
        at='2026-02-23T00:00:00+00:00', optional=None)
    return dict(schema='perf03-lnx.artificial-business.v1', entities=entities,
                tables={'artificial_result': dict(columns=columns(), keys=['key'], rows=[row])})


def typed(value, dtype):
    if value is None:
        return
    if dtype == 'str':
        require(type(value) is str and (value == '' or
                re.fullmatch(r'SYNTHETIC_[A-Z0-9_]{1,50}', value) is not None))
    elif dtype == 'int':
        require(type(value) is int and abs(value) <= 10**12)
    elif dtype == 'float':
        # NaN is a tagged JSON value, never a nonstandard JSON numeric literal.
        require(type(value) is float or value == {'kind': 'nan'})
        if type(value) is float:
            require(Decimal(str(value)).is_finite())
    elif dtype == 'decimal':
        require(type(value) is str and len(value) <= 50)
        try:
            require(Decimal(value).is_finite())
        except InvalidOperation:
            raise Refused('MOCK_DECIMAL_REJECTED') from None
    elif dtype == 'uuid':
        uid(value)
    elif dtype in {'date', 'datetime'}:
        require(type(value) is str and len(value) <= 40)
        try:
            if dtype == 'date':
                require(date.fromisoformat(value).isoformat() == value)
            else:
                parsed = datetime.fromisoformat(value)
                require(parsed.tzinfo is not None and parsed.isoformat() == value)
        except ValueError:
            raise Refused('MOCK_DATE_REJECTED') from None
    else:
        require(False)


def validate_snapshot(value):
    exact(value, ('schema', 'entities', 'tables'))
    require(value['schema'] == 'perf03-lnx.artificial-business.v1')
    require(type(value['entities']) is list and len(value['entities']) == len(ROLES))
    by_role = {}
    for node in value['entities']:
        exact(node, ('id', 'kind', 'owner', 'root', 'generation'))
        for key in ('id', 'owner', 'root', 'generation'):
            uid(node[key])
        require(node['kind'] in ROLES and node['kind'] not in by_role)
        by_role[node['kind']] = node['id']
    require(len(set(by_role.values())) == len(ROLES))
    for node in value['entities']:
        require(all(node[k] == by_role[k] for k in ('owner', 'root', 'generation')))
    exact(value['tables'], ('artificial_result',))
    table = value['tables']['artificial_result']
    exact(table, ('columns', 'keys', 'rows'))
    require(table['columns'] == columns() and table['keys'] == ['key'])
    require(type(table['rows']) is list and len(table['rows']) <= 50)
    keys = []
    for row in table['rows']:
        exact(row, table['columns'])
        for name, spec in table['columns'].items():
            typed(row[name], spec['dtype'])
            if spec['identity']:
                require(row[name] == by_role[spec['identity']])
        require(row['key'] is not None)
        keys.append(row['key'])
    require(keys == sorted(set(keys)))
    return by_role


def normalize_snapshot(value):
    ids = validate_snapshot(value)
    result = copy.deepcopy(value)
    # Explicit schema-level mappings, NOT removing UUID columns or arbitrary IDs.
    for node in result['entities']:
        node['id'] = node['kind'] if node['kind'] != 'owner' else node['id']
        for role in ('root', 'generation'):
            node[role] = role
    result['entities'].sort(key=lambda node: node['kind'])
    for row in result['tables']['artificial_result']['rows']:
        for name, spec in columns().items():
            role = spec['identity']
            if role and role != 'owner':
                require(row[name] == ids[role])
                row[name] = role
    return result


def parity(left, right):
    try:
        validate_receipt(left)
        validate_receipt(right)
        require(left['identity'] == right['identity'])
        require(left['switch_label'] == 'OFF' and right['switch_label'] == 'ON')
        require(left['pair_index'] == right['pair_index'])
        require(left['phase'] == right['phase'] and left['cleanup_state'] == right['cleanup_state'])
        require(left['job_state'] == right['job_state']
                and left['publication_state'] == right['publication_state']
                and left['ack_state'] == right['ack_state'])
        require(canonical(normalize_snapshot(left['business_snapshot'])) ==
                canonical(normalize_snapshot(right['business_snapshot'])))
        require(left['metrics']['counts'] == right['metrics']['counts'])
        status = 'MOCK_PARITY_VALIDATED'
    except (Refused, KeyError, TypeError):
        status = 'MOCK_PARITY_REJECTED'
    return dict(status=status, REAL_PG_PARITY='NOT_VERIFIED', authorization=AUTHORIZATION.copy())


def mock_receipt(arm, wall='100', *, identity=None, outcome='SUCCESS'):
    require(type(arm) is str and arm in ORDER)
    index = ORDER.index(arm)
    states = {'SUCCESS': ('PUBLISHED', 'ACK'), 'FAILED': ('ABORTED', 'ACK'),
              'CANCELLED': ('ABORTED', 'ACK'), 'UNKNOWN_ACK': ('INCOMPLETE', 'UNKNOWN')}
    require(outcome in states)
    publication, ack = states[outcome]
    return dict(schema=SCHEMA, evidence_kind=KIND,
        identity=identity or dict(source_sha='a' * 40, source_tree_sha='b' * 40,
            mock_protocol_sha256=digest(protocol()), worktree_state='MOCK_ONLY',
            run_id='SYNTHETIC_NO_PG', dataset_sha256=digest(protocol()['business_seed']),
            configuration_sha256=digest({'all_other_flags': False})),
        protocol=protocol(), tool_version=1, execution_platform='MOCK_HOST',
        runtime_identity='SYNTHETIC_NO_PG', arm_id=arm, pair_index=index // 2 + 1,
        switch_label='OFF' if index % 2 == 0 else 'ON',
        phase='INCOMPLETE' if ack == 'UNKNOWN' else 'COMPLETE_MOCK',
        timestamps=['2000-01-01T00:00:00+00:00', '2000-01-01T00:00:01+00:00'],
        supervision=dict(phases=['SETUP', 'ROOT', 'CLEANUP'], parent_verified=False,
            child_reaped=False, deadlines_seconds=[180, 180, 30],
            mock_deadlines_seconds=[1, 1, 1], observed_elapsed_seconds='0',
            process_cleanup='NOT_ASSESSED', archive_verified=False, timeline=[]),
        child_exit_code=0, first_failure=None, failure_reason=[], cleanup_state='COMPLETE',
        final_receipt_status='INCOMPLETE' if ack == 'UNKNOWN' else 'COMPLETE_MOCK',
        business_snapshot=snapshot(index + 1), job_state=outcome,
        publication_state=publication, ack_state=ack,
        metrics=dict(synthetic=True, root_wall_ms=wall, cpu_ms='10', rss_bytes=1024,
            p95=None, counts=dict(business_calls=10, business_writes=2,
                heartbeat_calls=1, observer_control_calls=0)),
        authorization=AUTHORIZATION.copy())


def validate_receipt(value, *, supervised=False):
    template = mock_receipt('OFF1')
    exact(value, template)
    require(value['schema'] == SCHEMA and value['evidence_kind'] == KIND
            and type(value['tool_version']) is int and value['tool_version'] == 1)
    validate_protocol(value['protocol'])
    exact(value['authorization'], AUTHORIZATION)
    require(all(v is False for v in value['authorization'].values()))
    exact(value['identity'], template['identity'])
    for key in ('source_sha', 'source_tree_sha'):
        require(type(value['identity'][key]) is str and
                re.fullmatch('[a-f0-9]{40}', value['identity'][key]) is not None)
    require(value['identity']['mock_protocol_sha256'] == digest(protocol()))
    require(value['identity']['dataset_sha256'] == digest(protocol()['business_seed']))
    require(value['identity']['configuration_sha256'] ==
            digest({'all_other_flags': False}))
    require(value['identity']['worktree_state'] == 'MOCK_ONLY')
    require(type(value['identity']['run_id']) is str and re.fullmatch(
        r'SYNTHETIC_[A-Z0-9_]{1,40}', value['identity']['run_id']) is not None)
    require(value['execution_platform'] == 'MOCK_HOST'
            and value['runtime_identity'] == 'SYNTHETIC_NO_PG')
    require(type(value['arm_id']) is str and value['arm_id'] in ORDER)
    index = ORDER.index(value['arm_id'])
    require(type(value['pair_index']) is int and value['pair_index'] == index // 2 + 1
            and value['switch_label'] == ('OFF' if index % 2 == 0 else 'ON'))
    require(type(value['phase']) is str and value['phase'] in STATES
            and value['final_receipt_status'] == value['phase'])
    require(type(value['timestamps']) is list and len(value['timestamps']) == 2)
    for stamp in value['timestamps']:
        require(type(stamp) is str)
        typed(stamp, 'datetime')
    require(datetime.fromisoformat(value['timestamps'][0]) <=
            datetime.fromisoformat(value['timestamps'][1]))
    exact(value['supervision'], template['supervision'])
    supervision = value['supervision']
    require(supervision['deadlines_seconds'] == [180, 180, 30])
    require(type(supervision['phases']) is list and supervision['phases'] ==
            ['SETUP', 'ROOT', 'CLEANUP'][:len(supervision['phases'])])
    limits = supervision['mock_deadlines_seconds']
    require(type(limits) is list and len(limits) == 3 and all(
        type(x) in (int, float) and 0 < x <= 1 for x in limits))
    number(supervision['observed_elapsed_seconds'])
    timeline = supervision['timeline']
    require(type(timeline) is list and len(timeline) <= 3)
    previous = Decimal(0)
    for index, entry in enumerate(timeline):
        exact(entry, ('phase', 'began', 'deadline', 'ended', 'complete'))
        require(entry['phase'] == ('SETUP', 'ROOT', 'CLEANUP')[index]
                and type(entry['complete']) is bool)
        began, deadline, ended = (number(entry[k]) for k in ('began', 'deadline', 'ended'))
        require(previous <= began <= deadline and ended >= began)
        if entry['complete']:
            require(ended < deadline)
        previous = ended
    require(all(type(supervision[k]) is bool for k in
                ('parent_verified', 'child_reaped', 'archive_verified')))
    require(supervision['process_cleanup'] in {'NOT_ASSESSED', 'REAPED', 'UNCONFIRMED'})
    require(type(value['child_exit_code']) is int or value['child_exit_code'] is None)
    require(value['cleanup_state'] in {'COMPLETE', 'INCOMPLETE', 'NOT_ASSESSED'})
    reasons = value['failure_reason']
    require(type(reasons) is list and len(reasons) <= 10)
    for reason in reasons + ([value['first_failure']] if value['first_failure'] else []):
        require(type(reason) is str and re.fullmatch(r'MOCK_[A-Z_]{1,60}', reason) is not None)
    require((not reasons and value['first_failure'] is None) or
            (bool(reasons) and value['first_failure'] == reasons[0]))
    states = {'SUCCESS': ('PUBLISHED', 'ACK'), 'FAILED': ('ABORTED', 'ACK'),
              'CANCELLED': ('ABORTED', 'ACK'), 'UNKNOWN_ACK': ('INCOMPLETE', 'UNKNOWN')}
    require(type(value['job_state']) is str and value['job_state'] in states and
            (value['publication_state'], value['ack_state']) == states[value['job_state']])
    if value['phase'] == 'COMPLETE_MOCK':
        require(value['ack_state'] == 'ACK' and value['first_failure'] is None
                and value['child_exit_code'] == 0 and value['cleanup_state'] == 'COMPLETE'
                and supervision['phases'] == ['SETUP', 'ROOT', 'CLEANUP'])
    if supervised and value['phase'] == 'COMPLETE_MOCK':
        require(supervision['parent_verified'] and supervision['child_reaped']
                and supervision['archive_verified'] and supervision['process_cleanup'] == 'REAPED')
        require(len(timeline) == 3 and all(item['complete'] for item in timeline))
    validate_terminal(value)
    validate_snapshot(value['business_snapshot'])
    exact(value['metrics'], template['metrics'])
    metrics = value['metrics']
    require(metrics['synthetic'] is True and metrics['p95'] is None)
    for key in ('root_wall_ms', 'cpu_ms'):
        number(metrics[key])
    require(type(metrics['rss_bytes']) is int and 0 <= metrics['rss_bytes'] <= 2**40)
    exact(metrics['counts'], template['metrics']['counts'])
    require(all(type(v) is int and 0 <= v <= 10**9 for v in metrics['counts'].values()))
    require(metrics['counts']['business_writes'] <= metrics['counts']['business_calls'])
    require(len(canonical(value)) <= MAX_BYTES)


def validate_terminal(value):
    """Cross-field evidence for EACH terminal; business failure != tool failure."""
    state = value['phase']
    sup = value['supervision']
    reasons = value['failure_reason']
    code = value['child_exit_code']
    cleanup = value['cleanup_state']
    timeline = sup['timeline']
    if sup['child_reaped']:
        require(type(code) is int and sup['process_cleanup'] == 'REAPED')
    if sup['process_cleanup'] == 'UNCONFIRMED':
        require(not sup['child_reaped'])
    if sup['archive_verified']:
        require(sup['parent_verified'])
    if sup['parent_verified']:
        require(bool(timeline))
        require([item['phase'] for item in timeline if item['complete']] == sup['phases'])
        require(all(item['complete'] for item in timeline[:-1]))
    if state == 'COMPLETE_MOCK':
        if sup['parent_verified']:
            require(sup['archive_verified'] and sup['child_reaped']
                    and sup['process_cleanup'] == 'REAPED'
                    and len(timeline) == 3 and all(item['complete'] for item in timeline))
        return
    if state == 'INCOMPLETE':
        if not reasons:
            prefix = (code is None and cleanup == 'NOT_ASSESSED' and not sup['parent_verified']
                      and not sup['child_reaped'] and not sup['archive_verified']
                      and sup['process_cleanup'] == 'NOT_ASSESSED'
                      and not sup['phases'] and not timeline)
            unknown_ack = (value['job_state'] == 'UNKNOWN_ACK' and value['ack_state'] == 'UNKNOWN'
                           and code == 0 and cleanup == 'COMPLETE')
            require(prefix or unknown_ack)
        else:
            require('MOCK_PARENT_INTERRUPTED' in reasons and sup['parent_verified'])
        return
    require(bool(reasons) and value['first_failure'] is not None)
    if state == 'TIMED_OUT':
        require(sup['parent_verified'] and bool(timeline)
                and any(r in reasons for r in ('MOCK_PHASE_TIMEOUT', 'MOCK_START_TIMEOUT')))
        exceeded = any(number(t['ended']) >= number(t['deadline']) for t in timeline)
        late_exit = number(sup['observed_elapsed_seconds']) >= (
            number(timeline[-1]['deadline']) - number(timeline[0]['began']))
        require(exceeded or late_exit)
    elif state == 'CRASHED':
        require('MOCK_CHILD_EXIT' in reasons and type(code) is int and code != 0
                and (code < 0 or code in {7, 139, 3221225477})
                and sup['parent_verified'] and sup['child_reaped']
                and sup['process_cleanup'] == 'REAPED' and cleanup != 'COMPLETE')
    elif state == 'FAILED':
        allowed = {'MOCK_PHASE_ORDER', 'MOCK_PHASE_MISSING', 'MOCK_CHILD_IDENTITY',
                   'MOCK_CHILD_INCOMPLETE', 'MOCK_CHILD_EXIT', 'MOCK_EVIDENCE_INVALID',
                   'MOCK_START_TIMEOUT', 'MOCK_PHASE_TIMEOUT', 'MOCK_CLOCK_REVERSED',
                   'MOCK_JSON_REJECTED', 'MOCK_CONTRACT_REJECTED', 'MOCK_ID_REJECTED',
                   'MOCK_DATE_REJECTED', 'MOCK_DECIMAL_REJECTED', 'MOCK_NUMBER_REJECTED',
                   'MOCK_FILE_REPLACED', 'MOCK_DIRECTORY_REPLACED', 'MOCK_PARENT_REPLACED'}
        require(sup['parent_verified'] and value['first_failure'] in allowed)
        if reasons == ['MOCK_CHILD_EXIT']:
            require(type(code) is int and code != 0 and sup['child_reaped'])
    elif state == 'CLEANUP_UNCERTAIN':
        require(cleanup == 'INCOMPLETE')
        require('MOCK_CLEANUP_FAILED' in reasons or (
            'MOCK_PROCESS_UNCONFIRMED' in reasons and sup['process_cleanup'] == 'UNCONFIRMED'
            and not sup['child_reaped'] and sup['parent_verified']))
    elif state == 'EVIDENCE_UNAVAILABLE':
        require('MOCK_EVIDENCE_UNAVAILABLE' in reasons and not sup['archive_verified']
                and sup['parent_verified'])


def seal(receipt, *, confirmation_scope=None):
    validate_receipt(receipt)
    require(confirmation_scope is None or (type(confirmation_scope) is str
            and re.fullmatch('[a-f0-9]{32}', confirmation_scope) is not None))
    value = copy.deepcopy(receipt)
    return dict(schema='perf03-lnx.sealed-mock.v2', publication=UNCONFIRMED,
                confirmation_scope=confirmation_scope, receipt=value, sha256=digest(value))


def unseal(value, *, expected_sha256=None):
    """Structural/hash decoding ONLY. This does not accept a published final."""
    exact(value, ('schema', 'publication', 'confirmation_scope', 'receipt', 'sha256'))
    require(value['schema'] == 'perf03-lnx.sealed-mock.v2'
            and value['publication'] == UNCONFIRMED)
    scope = value['confirmation_scope']
    require(scope is None or (type(scope) is str and
            re.fullmatch('[a-f0-9]{32}', scope) is not None))
    validate_receipt(value['receipt'])
    require(value['sha256'] == digest(value['receipt']))
    if expected_sha256 is not None:
        require(type(expected_sha256) is str and
                re.fullmatch('[a-f0-9]{64}', expected_sha256) is not None
                and value['sha256'] == expected_sha256, 'MOCK_EXPECTED_DIGEST_MISMATCH')
    return copy.deepcopy(value['receipt'])


class MockConsumptionAuthority:
    """Owner-held, process-local acknowledgements, NEVER a signature or real authority.

    The owner creates this before supervision, keeps it outside the artifact directory,
    and receives a ticket only after all publication I/O and FD close have returned.
    A new reader cannot reconstruct confirmation from final.json or its hashes.
    This deliberately provides NO persistent/cross-process trust implementation.
    """

    def __init__(self):
        self._tickets = {}
        self._pending = {}

    def begin(self, run_id, arm):
        require(type(run_id) is str and re.fullmatch(r'SYNTHETIC_[A-Z0-9_]{1,40}', run_id)
                is not None and type(arm) is str and arm in ORDER)
        scope = uuid.uuid4().hex  # Cannot be supplied or reconstructed from a disk artifact.
        self._pending[scope] = (run_id, arm)
        return scope

    def confirm(self, sealed):
        value = unseal(sealed)
        validate_receipt(value, supervised=True)
        require(value['phase'] == 'COMPLETE_MOCK')
        scope = sealed['confirmation_scope']
        require(scope in self._pending and self._pending[scope] ==
                (value['identity']['run_id'], value['arm_id']), 'MOCK_CONFIRMATION_SCOPE')
        del self._pending[scope]
        ticket = object()
        self._tickets[ticket] = (scope, canonical(sealed))
        return ticket

    def revoke(self, ticket):
        if type(ticket) is object:
            self._tickets.pop(ticket, None)

    def revoke_scope(self, scope):
        self._pending.pop(scope, None)
        for ticket, (registered, _) in list(self._tickets.items()):
            if registered == scope:
                del self._tickets[ticket]

    def consume(self, sealed, ticket):
        require(type(ticket) is object and ticket in self._tickets, 'MOCK_CONFIRMATION_REQUIRED')
        require(self._tickets[ticket][1] == canonical(sealed), 'MOCK_CONFIRMATION_MISMATCH')
        value = unseal(sealed)
        validate_receipt(value, supervised=True)
        require(value['phase'] == 'COMPLETE_MOCK')
        return value


def consume_final(sealed, *, authority=None, confirmation=None):
    """Canonical final consumer. File existence/hash/COMPLETE payload is insufficient."""
    require(type(authority) is MockConsumptionAuthority, 'MOCK_CONFIRMATION_REQUIRED')
    return authority.consume(sealed, confirmation)


def statistics(receipts):
    require(type(receipts) is list and len(receipts) == 6)
    for index, receipt in enumerate(receipts):
        validate_receipt(receipt)
        require(receipt['arm_id'] == ORDER[index]
                and receipt['identity'] == receipts[0]['identity'])
        require(receipt['phase'] == 'COMPLETE_MOCK' and receipt['job_state'] == 'SUCCESS')
        require(canonical(normalize_snapshot(receipt['business_snapshot'])) ==
                canonical(normalize_snapshot(receipts[0]['business_snapshot'])))
    for index in (0, 2, 4):
        require(parity(receipts[index], receipts[index + 1])['status'] == 'MOCK_PARITY_VALIDATED')
    groups = {}
    for switch in ('OFF', 'ON'):
        values = [number(r['metrics']['root_wall_ms']) for r in receipts
                  if r['switch_label'] == switch]
        groups[switch] = dict(values=[str(v) for v in values], mean=str(arithmetic.mean(values)),
            median=str(arithmetic.median(values)), minimum=str(min(values)),
            maximum=str(max(values)), stddev=format(arithmetic.stdev(values).normalize(), 'f'))
    off, on = (Decimal(groups[k]['median']) for k in ('OFF', 'ON'))
    require(off > 0)
    overhead = (on / off - 1) * 100
    return dict(schema='perf03-lnx.mock-arithmetic.v1', evidence_kind=KIND,
        mock_overhead_percent=format(overhead.normalize(), 'f'),
        arithmetic_threshold_met=overhead <= 3, groups=groups, p95=None,
        raw_receipts=copy.deepcopy(receipts), REAL_MEASUREMENT=False,
        PERFORMANCE_ELIGIBILITY='NOT_CLAIMED', R1_STATUS='PARTIAL',
        authorization=AUTHORIZATION.copy())
