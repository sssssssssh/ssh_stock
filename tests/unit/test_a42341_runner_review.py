"""AT08-18: pure 128-point mocks, deterministic rejection and exclusive artifact IO."""

import copy
import json
import os

import pytest

from scripts import a42341_calibration_review as off
from scripts import a42341_contract as c
from scripts.a42341_calibration_runner import (
    MockObserver,
    MockResources,
    MockWorkload,
    simulate,
)


@pytest.fixture(scope='module')
def good():
    expected = c.identity(run_id=os.environ.get('GITHUB_RUN_ID', 'local'),
                          attempt=int(os.environ.get('GITHUB_RUN_ATTEMPT', '1')))
    return expected, simulate(expected)


def changed(good):
    return good[0], copy.deepcopy(good[1])


def test_a42351_AT02_observer_invalid_cannot_mask_false_join_and_cleanup(good):
    expected = good[0]
    value = simulate(expected, observer=MockObserver(
        fail_at=1, failure_code='A42341_OBSERVER_INVALID'))
    partial = value['failed_point']['partial_sample']
    partial['observation']['joined'] = True
    partial['cleanup_complete'] = True
    value['cleanup_complete'] = True
    value['cleanup_failure_codes'] = []
    # A safe rejection decision is NOT enough: contradictory evidence is invalid input.
    with pytest.raises(c.Fault, match='^A42341_FAILED_POINT_INVALID$'):
        off.review(c.seal(value), expected)


@pytest.fixture(scope='module')
def a42351_joined_failure(good):
    expected, complete = good
    value = simulate(expected, observer=MockObserver(
        fail_at=1, failure_code='A42341_OBSERVER_INVALID'))
    point = value['failed_point']['partial_sample']
    point['observation'] = copy.deepcopy(complete['samples'][1]['observation'])
    # The payload fault is genuine, but the worker really ended and has a receipt.
    point['observation']['ticks'][-1]['partial'] = True
    point['resources'] = copy.deepcopy(complete['samples'][1]['resources'])
    point['cleanup_complete'] = value['cleanup_complete'] = True
    value['cleanup_failure_codes'] = []
    return expected, c.seal(value)


def test_a42351_AT10_joined_payload_failure_is_not_rejected_wholesale(a42351_joined_failure):
    expected, value = a42351_joined_failure
    original = copy.deepcopy(value)
    result = off.review(value, expected)
    assert result['collection_status'] == 'INCOMPLETE'
    assert result['first_failure_code'] == 'A42341_OBSERVER_INVALID'
    assert result['failed_point']['partial_sample']['observation']['joined'] is True
    assert result['failed_point']['partial_sample']['observation']['ticks'][-1]['partial']
    assert value == original  # No normalization/resealing/rewriting by the Reviewer.


@pytest.mark.parametrize('change', [
    'missing_end', 'three_states', 'stop_timeout', 'missing_cpu', 'missing_elapsed',
    'wrong_elapsed', 'excess_cpu', 'end_before_lookup', 'worker_start_after_tick',
    'tick_budget', 'sql_budget', 'sql_sum', 'partial_prefix', 'no_before', 'no_after',
    'interval', 'local_cleanup', 'top_cleanup', 'join_code', 'process_cpu_zero',
])
def test_a42351_AT03_AT06_joined_invalid_payload_cannot_mask_structure(
        a42351_joined_failure, change):
    expected, original = a42351_joined_failure
    value = copy.deepcopy(original)
    point = value['failed_point']['partial_sample']
    obs, resources = point['observation'], point['resources']
    if change == 'missing_end':
        obs['worker_finished_ns'] = None
    elif change == 'three_states':
        obs['lifecycle'] = ['INIT', 'RUNNING', 'STOP_REQUESTED']
    elif change == 'stop_timeout':
        obs['state'] = 'STOP_TIMEOUT'
    elif change in ('missing_cpu', 'excess_cpu'):
        resources['observer_thread_cpu_seconds'] = None if change == 'missing_cpu' else 1.0
    elif change in ('missing_elapsed', 'wrong_elapsed'):
        resources['observer_worker_elapsed_ms'] = None if change == 'missing_elapsed' else 1.0
    elif change == 'end_before_lookup':
        obs['worker_finished_ns'] = point['lookup_started_ns']
    elif change == 'worker_start_after_tick':
        obs['worker_started_ns'] += 1
        resources['observer_worker_elapsed_ms'] -= .000001
    elif change == 'tick_budget':
        obs['ticks'][-1]['wall_ms'] = 26.0
    elif change in ('sql_budget', 'sql_sum'):
        obs['ticks'][-1]['sql_wall_ms'][0] = 101.0 if change == 'sql_budget' else 1.0
    elif change == 'partial_prefix':
        obs['ticks'][0]['partial'] = True
    elif change in ('no_before', 'no_after'):
        obs['ticks'].pop(0 if change == 'no_before' else -1)
    elif change == 'interval':
        obs['ticks'][1]['started_ns'] += 1_000_000
    elif change == 'local_cleanup':
        point['cleanup_complete'] = False
    elif change == 'top_cleanup':
        value['cleanup_complete'] = False
    elif change == 'join_code':
        value['first_failure_code'] = value['failed_point']['failure_code'] = 'A42341_JOIN_TIMEOUT'
    else:
        resources['process_cpu_seconds'] = 0.0
    with pytest.raises(c.Fault, match='^A42341_(FAILED_POINT|LIFECYCLE)_INVALID$'):
        off.review(c.seal(value), expected)


@pytest.mark.parametrize('change', ['end', 'cpu', 'elapsed', 'local', 'top', 'tick_partial'])
def test_a42351_AT07_AT08_unjoined_invalid_cannot_mask_unknowns(good, change):
    expected = good[0]
    value = simulate(expected, observer=MockObserver(
        fail_at=1, failure_code='A42341_OBSERVER_INVALID'))
    point = value['failed_point']['partial_sample']
    if change == 'end':
        point['observation']['worker_finished_ns'] = point['window_finished_ns']
    elif change == 'cpu':
        point['resources']['observer_thread_cpu_seconds'] = 0.0
    elif change == 'elapsed':
        point['resources']['observer_worker_elapsed_ms'] = 0.0
    elif change == 'local':
        point['cleanup_complete'] = True
    elif change == 'top':
        value['cleanup_complete'] = True
    else:
        point['observation']['ticks'][0]['partial'] = True
    with pytest.raises(c.Fault):
        off.review(c.seal(value), expected)


@pytest.mark.parametrize('change', ['none', 'worker', 'ticks', 'lifecycle', 'cpu', 'join_code'])
def test_a42351_AT09_off_partial_semantics(good, change):
    expected = good[0]
    value = simulate(expected, resources=MockResources(rss_available=False))
    point = value['failed_point']['partial_sample']
    assert point['identity']['mode'] == 'OFF'
    if change == 'none':
        assert off.review(value, expected)['collection_status'] == 'INCOMPLETE'
        return
    if change == 'worker':
        point['observation']['worker_started_ns'] = point['window_started_ns']
    elif change == 'ticks':
        point['observation']['ticks'] = copy.deepcopy(good[1]['samples'][1]['observation']['ticks'])
    elif change == 'lifecycle':
        point['observation']['lifecycle'] = ['INIT']
    elif change == 'cpu':
        point['resources']['observer_thread_cpu_seconds'] = 0.0
    else:
        value['first_failure_code'] = value['failed_point']['failure_code'] = 'A42341_JOIN_TIMEOUT'
    with pytest.raises(c.Fault, match='^A42341_FAILED_POINT_INVALID$'):
        off.review(c.seal(value), expected)


@pytest.mark.parametrize('code', ['A42341_SQL_TIMEOUT', 'A42341_CANCELLED', 'A42341_SIGNAL'])
def test_a42351_AT11_first_error_sticky_and_cleanup_order(good, code):
    expected = good[0]
    value = simulate(expected, workload=MockWorkload(fail_at=1, failure_code=code),
                     resources=MockResources(cleanup_failure=True))
    result = off.review(value, expected)
    assert result['first_failure_code'] == code
    assert result['cleanup_failure_codes'] == ['A42341_CLEANUP_FAILED']
    assert result['failed_point']['partial_sample'] is None


def test_a42351_AT14_AT15_old_identity_schema_is_not_silently_upgraded(good):
    from scripts.a42341_calibration_runner import Bundle

    expected, original = good
    value = copy.deepcopy(original)
    # Schema-compatibility projection, NOT a rewritten historical artifact.
    value['identity']['head_sha'] = '55bd6328c3481f2b2ce767fcb843caaa8e0a2ad8'
    value['identity']['source_sha256'] = (
        '3edf9ad70bb8a0f20a3afa3078a00e5fe0fe72969a4c97aac772da12c203bdc9')
    parsed = Bundle.model_validate(value)
    assert parsed.identity.head_sha == value['identity']['head_sha']
    assert parsed.content_sha256 == value['content_sha256']  # No reseal by parser.
    with pytest.raises(c.Fault, match='^A42341_PROTOCOL_OR_SOURCE_CHANGED$'):
        off.review(parsed.model_dump(), parsed.identity)
    assert original['identity'] == expected.model_dump()


def test_AT02_AT18_full_mock_roundtrip_never_authorizes_or_proves_real_prepare(good, tmp_path):
    expected, data = good
    result = off.review(data, expected)
    assert result['calibration_decision'] == 'SIMULATED_ACCEPT'
    assert result['authorization_status'] == 'NOT_RUN_NOT_AUTHORIZED'
    assert result['overall_status'] == 'BLOCKED_NEEDS_USER_PROTOCOL_DECISION'
    assert result['prepared_evidence_status'] == 'SIMULATED_REAL_NOT_PROVEN'
    assert len(result['pairs']) == 64 and len(result['groups']) == 11
    assert result['groups']['ALL']['n'] == 64
    for name, value in c.Safety().model_dump().items():
        assert result[name] == value
    directory = tmp_path / 'bundle'
    off.write_bundle(directory, data, expected)
    assert off.review_bundle(directory, expected) == result
    assert len(c.load(directory / 'samples.json')['samples']) == 128
    assert c.load(directory / 'failure.json')['first_failure_code'] is None


@pytest.mark.parametrize('field,bad', [
    ('gc_thresholds_after', [701, 10, 10]), ('gc_enabled_after', False),
    ('lookup_wall_ms', 49.0), ('lookup_wall_ms', 0), ('lookup_wall_ms', -1),
    ('lookup_wall_ms', float('nan')), ('lookup_wall_ms', float('inf')),
    ('lookup_wall_ms', 300001.0), ('cost_scope', 'WALL_MINUS_GC'),
    ('connection_identity', 'a' * 64), ('process_identity', 'a' * 64),
])
def test_AT09_AT13_numeric_gc_timing_identity_mutations_rejected(good, field, bad):
    expected, data = changed(good)
    data['samples'][0][field] = bad
    # Nonfinite cannot be signed or serialized at all.
    if isinstance(bad, float) and not bad < float('inf'):
        with pytest.raises((c.Fault, ValueError)):
            off.review(data, expected)
    else:
        with pytest.raises(c.Fault):
            off.review(c.seal(data), expected)


@pytest.mark.parametrize('field,bad', [
    ('joined', False), ('overflow', 1), ('state', 'STOP_TIMEOUT'), ('ticks', []),
    ('schema_version', 'a4233.observer.v2'), ('planned_ticks', 128),
    ('lifecycle', ['INIT', 'RUNNING', 'RECEIPT']), ('worker_finished_ns', None),
])
def test_AT08_AT13_no_micro_lifecycle_abuse_or_unjoined_window(good, field, bad):
    expected, data = changed(good)
    data['samples'][1]['observation'][field] = bad
    with pytest.raises(c.Fault):
        off.review(c.seal(data), expected)


@pytest.mark.parametrize('change', ['before', 'after', 'partial', 'event', 'tickwall',
    'sqltimeout', 'interval', 'OFF_TICK'])
def test_AT08_AT13_tick_coverage_and_activity_fail_closed(good, change):
    expected, data = changed(good)
    obs = data['samples'][1]['observation']
    if change == 'before':
        obs['ticks'][0]['finished_ns'] = data['samples'][1]['lookup_started_ns'] + 1
    elif change == 'after':
        for t in obs['ticks'][1:]:
            t['started_ns'] = data['samples'][1]['lookup_finished_ns'] - 1
    elif change == 'partial':
        obs['ticks'][0]['partial'] = True
    elif change == 'event':
        obs['ticks'][0]['event_codes'] = ['UNKNOWN_RELATION']
    elif change == 'tickwall':
        obs['ticks'][0]['wall_ms'] = 26.0
    elif change == 'sqltimeout':
        obs['ticks'][0]['sql_wall_ms'][0] = 101.0
    elif change == 'interval':
        obs['ticks'][1]['started_ns'] += 1_000_000_000
    else:
        data['samples'][0]['observation']['ticks'] = obs['ticks']
    with pytest.raises(c.Fault):
        off.review(c.seal(data), expected)


@pytest.mark.parametrize('event', ['VACUUM_OBSERVED', 'ANALYZE_OBSERVED', 'POSSIBLE_IN_BRACKET',
    'ENVIRONMENT_ACTIVITY_ONLY', 'UNKNOWN_RELATION', 'AMBIGUOUS_EVENT', 'PID_REUSED'])
def test_AT13_every_nonabsence_event_must_fail_closed(good, event):
    expected, data = changed(good)
    data['samples'][1]['observation']['ticks'][0]['event_codes'] = [event]
    with pytest.raises(c.Fault, match='A42341_OBSERVER_INVALID'):
        off.review(c.seal(data), expected)


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'order', 'pair', 'concurrency',
    'warmup', 'warmup_key', 'sample_key', 'probe', 'probe_counter', 'budget', 'lifecycle'])
def test_AT12_AT14_exact_samples_warmup_probes_and_serial_windows(good, change):
    expected, data = changed(good)
    if change == 'missing':
        data['samples'].pop()
    elif change == 'duplicate':
        data['samples'][1] = copy.deepcopy(data['samples'][0])
    elif change == 'order':
        data['samples'][0], data['samples'][1] = data['samples'][1], data['samples'][0]
    elif change == 'pair':
        data['samples'][0]['identity']['pair'] = 1
    elif change == 'concurrency':
        data['blocks'][1]['started_ns'] = data['blocks'][0]['started_ns']
    elif change == 'warmup':
        data['warmups'] = data['warmups'][:8]
    elif change == 'warmup_key':
        data['warmups'][0]['hypothetical_batch_cache_keys'][1] = 'a' * 64
    elif change == 'sample_key':
        data['samples'][0]['batch_cache_keys'][1] = 'a' * 64
    elif change == 'probe':
        data['probes'][1]['phase'] = 'BLOCK_END'
    elif change == 'probe_counter':
        data['probes'][1]['conditions'][0]['custom_plans'] += 1
    elif change == 'budget':
        data['parent_finished_ns'] += 1_200_000_000_000
    else:
        data['lifecycle'].reverse()
    with pytest.raises(c.Fault):
        off.review(c.seal(data), expected)


def test_AT09_nested_segments_are_preserved_not_added_or_subtracted(good):
    expected, data = good
    sample = data['samples'][0]
    durations = [(s['finished_ns'] - s['started_ns']) / 1e6 for s in sample['segments'].values()]
    assert sum(durations) != sample['lookup_wall_ms']
    assert off.review(data, expected)['pairs'][0]['off_wall_ms'] == 50.0


def test_AT15_exact_inclusive_equality_and_negative_signed_preserved(good):
    assert off.inclusive([0, 1], '.95') == off.Decimal('.95')
    assert off.inclusive([0, 1, 2, 3], '.5') == off.Decimal('1.5')
    assert off.relative(100, 105)['positive'] == off.Decimal('.05')
    point = dict(block=0, variant='C0', lookup={'signed': '.1', 'absolute': '.1', 'positive': '.1'},
                 backend_cpu={'signed': '.05', 'absolute': '.05', 'positive': '.05'},
                 rss_delta_bytes=32 * 1024 ** 2)
    # A direct inclusive boundary test, separately from the complete-record validator.
    points = [dict(point, block=b, variant=v, lookup=dict(
        signed='.05', absolute='.05', positive='.05')) for b in range(4) for v in ('C0', 'C1')]
    assert off.summaries(points)[1]
    boundary = [dict(point, block=b, variant=v, lookup=dict(
        signed='0' if n < 4 else '.1', absolute='0' if n < 4 else '.1',
        positive='0' if n < 4 else '.1'))
        for b in range(4) for v in ('C0', 'C1') for n in range(8)]
    groups, accept = off.summaries(boundary)
    assert off.Decimal(groups['ALL']['lookup']['positive']['p50']) == off.Decimal('.05')
    assert off.Decimal(groups['ALL']['lookup']['positive']['p95']) == off.Decimal('.10')
    assert accept
    boundary[-1]['lookup'] = dict(signed='.100001', absolute='.100001', positive='.100001')
    assert not off.summaries(boundary)[1]
    e = good[0]
    negative = simulate(e, workload=MockWorkload(on_wall_ms=49.0))
    result = off.review(negative, e)
    assert result['calibration_decision'] == 'SIMULATED_ACCEPT'
    assert all(p['lookup']['signed'] == '-0.02' and p['lookup']['absolute'] == '0.02'
               and p['lookup']['positive'] == '0' for p in result['pairs'])


def test_AT15_slow_point_retained_and_not_votes_out_or_deleted(good):
    expected = good[0]
    data = simulate(expected, workload=MockWorkload(on_wall_ms=70.0))
    result = off.review(data, expected)
    assert result['collection_status'] == 'COMPLETE' and len(result['pairs']) == 64
    assert result['calibration_decision'] == 'SIMULATED_REJECT'
    assert result['groups']['ALL']['lookup']['positive']['maximum'] == '0.4'


def test_AT11_entire_worker_cpu_proposed_threshold_equal_and_exceed(good):
    expected, value = changed(good)
    for sample in value['samples']:
        if sample['identity']['mode'] == 'ON':
            sample['resources']['process_cpu_seconds'] = .03
            sample['resources']['observer_thread_cpu_seconds'] = .02515
    assert off.review(c.seal(value), expected)['calibration_decision'] == 'SIMULATED_ACCEPT'
    value['samples'][1]['resources']['observer_thread_cpu_seconds'] = .025151
    assert off.review(c.seal(value), expected)['calibration_decision'] == 'SIMULATED_REJECT'


@pytest.mark.parametrize('code', ['A42341_CANCELLED', 'A42341_SIGNAL', 'A42341_TIMEOUT',
                               'A42341_SQL_TIMEOUT', 'A42341_WORKLOAD_FAILED'])
def test_AT17_sticky_first_error_incomplete_point_and_cleanup(good, code):
    expected = good[0]
    value = simulate(expected, workload=MockWorkload(fail_at=3, failure_code=code),
                     resources=MockResources(cleanup_failure=True))
    result = off.review(value, expected)
    assert result['collection_status'] == 'INCOMPLETE' and result['sample_count'] == 3
    assert result['first_failure_code'] == code
    assert result['cleanup_failure_codes'] == ['A42341_CLEANUP_FAILED']
    assert result['failed_point']['identity']['position'] == 3


@pytest.mark.parametrize('code', ['A42341_JOIN_TIMEOUT', 'A42341_OBSERVER_INVALID'])
def test_AT13_AT17_unjoined_or_partial_observer_preserves_last_snapshot(good, code):
    expected = good[0]
    value = simulate(expected, observer=MockObserver(fail_at=1, failure_code=code))
    result = off.review(value, expected)
    assert result['sample_count'] == 1 and result['first_failure_code'] == code
    partial = result['failed_point']['partial_sample']
    assert partial['lookup_wall_ms'] == 51.0 and not partial['observation']['joined']
    assert partial['status'] == 'INCOMPLETE' and partial['cleanup_complete'] is False
    assert value['cleanup_complete'] is False
    assert partial['resources']['observer_thread_cpu_seconds'] is None
    assert len(partial['observation']['ticks']) == 3


@pytest.mark.parametrize('change', ['schema', 'unknown', 'digest', 'head', 'attempt', 'flags'])
def test_AT16_untrusted_bundle_metadata_and_authorization_rejected(good, change):
    expected, data = changed(good)
    if change == 'schema':
        data['schema_version'] = 'a4234.simulation.v1'
    elif change == 'unknown':
        data['SQL_PASSWORD_SECRET'] = 'SECRET_A42341_DSN'
    elif change == 'digest':
        data['content_sha256'] = 'a' * 64
    elif change in ('head', 'attempt'):
        data['identity']['head_sha' if change == 'head' else 'attempt'] = (
            'a' * 40 if change == 'head' else expected.attempt + 1)
    else:
        data['execution_enabled'] = True
    with pytest.raises(c.Fault) as error:
        off.review(data if change == 'digest' else c.seal(data), expected)
    assert 'SECRET_A42341_DSN' not in str(error.value)


@pytest.mark.parametrize('body', ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', 'broken'])
def test_AT16_bad_json_rejected(tmp_path, body):
    path = tmp_path / 'bad.json'
    path.write_text(body)
    with pytest.raises(c.Fault):
        c.load(path)


def test_AT16_AT17_symlink_oversize_exclusive_writes_and_corruption(good, tmp_path):
    expected, data = good
    directory = tmp_path / 'bundle'
    off.write_bundle(directory, data, expected)
    with pytest.raises(c.Fault):
        off.write_bundle(directory, data, expected)
    output = directory / 'review.json'
    first = output.read_bytes()
    with pytest.raises(c.Fault):
        c.write_new(output, {'replacement': True})
    assert output.read_bytes() == first
    output.write_text('{}')
    with pytest.raises(c.Fault, match='A42341_DIGEST_MISMATCH'):
        off.review_bundle(directory, expected)
    target, link = tmp_path / 'target', tmp_path / 'link'
    target.write_text('{}')
    link.symlink_to(target)
    with pytest.raises(c.Fault):
        c.load(link)
    with target.open('r+b') as stream:
        stream.truncate(16_000_001)
    with pytest.raises(c.Fault):
        c.load(target)


def test_AT17_write_failure_keeps_first_error_and_no_complete_manifest(good, tmp_path):
    expected = good[0]
    value = simulate(expected, workload=MockWorkload(fail_at=3, failure_code='A42341_SQL_TIMEOUT'))
    def broken(*args):
        raise OSError('SECRET_A42341_DSN')
    output = tmp_path / 'failed'
    with pytest.raises(c.Fault, match='A42341_ARTIFACT_WRITE_FAILED'):
        off.write_bundle(output, value, expected, writer=broken)
    failure = c.load(output / 'artifact-failure.json')
    assert failure['first_failure_code'] == 'A42341_SQL_TIMEOUT'
    assert failure['artifact_failure_code'] == 'A42341_ARTIFACT_WRITE_FAILED'
    assert 'SECRET_A42341_DSN' not in json.dumps(failure)
    assert not (output / 'manifest.json').exists()


def test_AT17_untrusted_schema_never_leaks_into_fallback_artifact(good, tmp_path):
    expected, data = changed(good)
    data['identity']['secret'] = 'SECRET_A42341_DSN'
    with pytest.raises(c.Fault):
        off.write_bundle(tmp_path / 'bad', data, expected)
    assert 'SECRET_A42341_DSN' not in (tmp_path / 'bad/artifact-failure.json').read_text()


@pytest.mark.parametrize('change', ['path', 'file_symlink', 'hash', 'unknown_file'])
def test_AT16_bundle_manifest_paths_hashes_and_hidden_files_rejected(good, tmp_path, change):
    expected, data = good
    directory = tmp_path / 'bundle'
    off.write_bundle(directory, data, expected)
    manifest = c.load(directory / 'manifest.json')
    if change == 'path':
        manifest['files']['../outside.json'] = manifest['files'].pop('review.json')
    elif change == 'hash':
        manifest['files']['review.json']['sha256'] = 'a' * 64
    elif change == 'unknown_file':
        (directory / 'extra.json').write_text('{}')
    else:
        target = tmp_path / 'target.json'
        target.write_bytes((directory / 'review.json').read_bytes())
        (directory / 'review.json').unlink()
        (directory / 'review.json').symlink_to(target)
    (directory / 'manifest.json').write_text(json.dumps(c.seal(manifest)))
    with pytest.raises(c.Fault):
        off.review_bundle(directory, expected)


def test_AT17_artifact_budget_exceeded_after_publish_removes_only_owned_link(tmp_path, monkeypatch):
    times = iter((0, 0, 3_000_000_000))
    monkeypatch.setattr(c.time, 'monotonic_ns', lambda: next(times))
    with pytest.raises(c.Fault):
        c.write_new(tmp_path / 'too-slow.json', {'value': 1})
    assert not list(tmp_path.iterdir())


def test_AT20_export_complete_and_incomplete_mock_fixtures_only_in_ci(good, tmp_path):
    expected, data = good
    directory = tmp_path
    exported = os.environ.get('A42341_ARTIFACT_ROOT')
    if exported is not None:
        assert exported == '.codex_tmp/a42341'
        directory = c.safe_path(c.ROOT / exported)
        directory.mkdir(parents=True, exist_ok=True)
    off.write_bundle(directory / 'mock-complete', data, expected)
    partial = simulate(expected,
        workload=MockWorkload(fail_at=3, failure_code='A42341_SQL_TIMEOUT'),
        resources=MockResources(cleanup_failure=True))
    off.write_bundle(directory / 'mock-incomplete', partial, expected)
    assert off.review_bundle(directory / 'mock-incomplete', expected)['sample_count'] == 3


@pytest.fixture(scope='module')
def a42342_failed(good):
    return good[0], simulate(good[0], observer=MockObserver(fail_at=1))


@pytest.mark.parametrize('change', [
    'joined', 'local_cleanup', 'status', 'duplicate_position', 'skipped_position',
    'cross_block', 'process', 'connection', 'window_inverse', 'window_future',
    'observed_past', 'observed_future', 'during_with_partial', 'post_without_partial',
    'first_error', 'join_cleanup_missing', 'unexpected_cleanup', 'duplicate_cleanup',
    'top_cleanup', 'worker_finished', 'worker_cpu', 'tick_future', 'tick_duplicate',
    'gc_future', 'segment_future', 'backend_future', 'backend_pid', 'backend_container',
    'missing_warmup', 'duplicate_warmup',
    'warmup_order', 'missing_probe', 'duplicate_probe', 'probe_order', 'probe_future',
    'probe_counter', 'missing_block', 'extra_block',
])
def test_A42342_T03_T08_T11_contradictory_failure_evidence_rejected(a42342_failed, change):
    expected, original = a42342_failed
    value = copy.deepcopy(original)
    failed = value['failed_point']
    point = failed['partial_sample']
    obs = point['observation']
    if change == 'joined':
        obs.update(joined=True, state='MOCK_JOINED',
            worker_finished_ns=point['window_finished_ns'],
            lifecycle=['INIT', 'RUNNING', 'STOP_REQUESTED', 'JOINED', 'RECEIPT'])
    elif change == 'local_cleanup':
        point['cleanup_complete'] = True
    elif change == 'status':
        point['status'] = 'COMPLETE'
    elif change in ('duplicate_position', 'skipped_position', 'cross_block'):
        position = {'duplicate_position': 0, 'skipped_position': 2, 'cross_block': 32}[change]
        failed['identity'] = c.schedule()[position]
        point['identity'] = c.schedule()[position]
    elif change in ('process', 'connection'):
        point[change + '_identity'] = 'a' * 64
    elif change == 'window_inverse':
        point['window_started_ns'] = point['window_finished_ns'] + 1
    elif change == 'window_future':
        point['window_finished_ns'] = value['parent_finished_ns'] + 1
    elif change == 'observed_past':
        failed['observed_until_ns'] = value['samples'][0]['window_started_ns']
    elif change == 'observed_future':
        failed['observed_until_ns'] = value['parent_finished_ns'] + 1
    elif change == 'during_with_partial':
        failed['phase'] = 'DURING_LOOKUP'
    elif change == 'post_without_partial':
        failed['partial_sample'] = None
    elif change == 'first_error':
        value['first_failure_code'] = 'A42341_SQL_TIMEOUT'
    elif change == 'join_cleanup_missing':
        value['cleanup_failure_codes'] = []
        value['cleanup_complete'] = True
    elif change == 'unexpected_cleanup':
        value['cleanup_failure_codes'].append('A42341_SQL_TIMEOUT')
    elif change == 'duplicate_cleanup':
        value['cleanup_failure_codes'] *= 2
    elif change == 'top_cleanup':
        value['cleanup_complete'] = True
    elif change == 'worker_finished':
        obs['worker_finished_ns'] = point['window_finished_ns']
    elif change == 'worker_cpu':
        point['resources']['observer_thread_cpu_seconds'] = .001
    elif change == 'tick_future':
        obs['ticks'][-1]['finished_ns'] = failed['observed_until_ns'] + 1
    elif change == 'tick_duplicate':
        obs['ticks'][-1] = copy.deepcopy(obs['ticks'][0])
    elif change in ('gc_future', 'segment_future'):
        target = (point['gc_events'][0] if change == 'gc_future'
                  else point['segments']['python_json'])
        target['finished_ns'] = failed['observed_until_ns'] + 1
    elif change == 'backend_future':
        point['resources']['backend_after']['observed_ns'] = failed['observed_until_ns'] + 1
    elif change == 'backend_pid':
        point['resources']['backend_after']['pid'] += 1
    elif change == 'backend_container':
        point['resources']['backend_before']['container_sha256'] = 'a' * 64
    elif change == 'missing_warmup':
        value['warmups'].pop()
    elif change == 'duplicate_warmup':
        value['warmups'][-1] = copy.deepcopy(value['warmups'][0])
    elif change == 'warmup_order':
        value['warmups'].reverse()
    elif change == 'missing_probe':
        value['probes'].pop()
    elif change == 'duplicate_probe':
        value['probes'][1] = copy.deepcopy(value['probes'][0])
    elif change == 'probe_order':
        value['probes'].reverse()
    elif change == 'probe_future':
        value['probes'][1]['started_ns'] = failed['observed_until_ns'] + 1
    elif change == 'probe_counter':
        value['probes'][0]['conditions'][0]['custom_plans'] += 1
    elif change == 'missing_block':
        value['blocks'] = []
    else:
        value['blocks'].append(copy.deepcopy(value['blocks'][0]))
    with pytest.raises(c.Fault):
        off.review(c.seal(value), expected)


@pytest.mark.parametrize('position', [0, 3, 31, 32, 33, 63, 64, 95, 96, 127])
def test_A42342_T02_T08_T10_legal_failure_prefix_at_every_block_boundary(good, position):
    expected = good[0]
    value = simulate(expected, workload=MockWorkload(fail_at=position,
        failure_code='A42341_SQL_TIMEOUT'), resources=MockResources(cleanup_failure=True))
    original = copy.deepcopy(value)
    result = off.review(value, expected)
    assert result['sample_count'] == position
    assert result['failed_point'] == original['failed_point']
    assert result['first_failure_code'] == 'A42341_SQL_TIMEOUT'
    assert result['cleanup_failure_codes'] == ['A42341_CLEANUP_FAILED']
    assert result['calibration_decision'] == 'SIMULATED_REJECT'
    assert result['prepared_evidence_status'] == 'UNDETERMINED'
    assert value == original


def test_A42342_T09_only_final_cleanup_failure_keeps_all_128_points(good, tmp_path):
    expected = good[0]
    value = simulate(expected, resources=MockResources(cleanup_failure=True))
    result = off.write_bundle(tmp_path / 'cleanup-only', value, expected)
    assert result['sample_count'] == 128 and result['failed_point'] is None
    assert result['first_failure_code'] == 'A42341_CLEANUP_FAILED'
    assert result['collection_status'] == 'INCOMPLETE'
    assert result['calibration_decision'] == 'SIMULATED_REJECT'
    assert off.review_bundle(tmp_path / 'cleanup-only', expected) == result


@pytest.mark.parametrize('change', ['missing_point', 'fake_first', 'missing_completed_block'])
def test_A42342_T09_T10_cleanup_cannot_justify_truncated_or_false_sampling_failure(good, change):
    expected = good[0]
    value = simulate(expected, resources=MockResources(cleanup_failure=True))
    if change == 'missing_point':
        value['samples'].pop()
    elif change == 'fake_first':
        value['first_failure_code'] = 'A42341_SQL_TIMEOUT'
    else:
        value['blocks'].pop()
    with pytest.raises(c.Fault):
        off.review(c.seal(value), expected)


@pytest.mark.parametrize('code', ['A42341_JOIN_TIMEOUT', 'A42341_OBSERVER_INVALID'])
def test_A42342_T11_stable_partial_snapshot_is_returned_without_rewriting(a42342_failed, code):
    expected = a42342_failed[0]
    value = simulate(expected, observer=MockObserver(fail_at=1, failure_code=code),
                     resources=MockResources(cleanup_failure=True))
    original = copy.deepcopy(value)
    result = off.review(value, expected)
    assert result['failed_point'] == value['failed_point']
    assert result['failed_point']['partial_sample']['cleanup_complete'] is False
    assert result['cleanup_failure_codes'] == ['A42341_CLEANUP_FAILED', 'A42341_JOIN_TIMEOUT']
    assert value == original


@pytest.mark.parametrize('change', ['raw_error', 'dsn'])
def test_A42342_T12_partial_unknown_fields_rejected_without_raw_text(a42342_failed, change):
    expected, original = a42342_failed
    value = copy.deepcopy(original)
    value['failed_point']['partial_sample'][change] = 'SECRET_A42342_DSN'
    with pytest.raises(c.Fault) as error:
        off.review(c.seal(value), expected)
    assert 'SECRET_A42342_DSN' not in str(error.value)
