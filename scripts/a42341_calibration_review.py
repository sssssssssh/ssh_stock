"""Offline mock reviewer: simulated decisions never confer real execution/qualification."""

from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

from scripts.a4233_observation_contract import digest
from scripts.a42341_calibration_runner import Bundle
from scripts.a42341_contract import (
    Fault,
    Identity,
    Safety,
    file_sha,
    load,
    require,
    safe_path,
    schedule,
    seal,
    validate_identity,
    warmup_schedule,
    write_new,
)
from scripts.a42341_environment_contract import (
    backend_cpu,
    check_observer,
    compare_environment,
    environment,
)
from scripts.a42341_prepared_capability import compare, condition


def decimal(value):
    try:
        result = Decimal(str(value))
        require(result.is_finite(), 'A42341_NUMERIC_INVALID')
        return result
    except Exception:
        raise Fault('A42341_NUMERIC_INVALID') from None


def inclusive(values, p):
    values = sorted(decimal(v) for v in values)
    p = decimal(p)
    require(bool(values) and Decimal(0) <= p <= 1, 'A42341_NUMERIC_INVALID')
    h = (len(values) - 1) * p
    i = int(h.to_integral_value(rounding=ROUND_FLOOR))
    return values[i] + (h - i) * (values[min(i + 1, len(values) - 1)] - values[i])


def relative(off, on):
    off, on = decimal(off), decimal(on)
    require(off > 0 and on > 0, 'A42341_NUMERIC_INVALID')
    signed = (on - off) / off
    return dict(signed=signed, absolute=abs(signed), positive=max(signed, Decimal(0)))


def check_sample(s, expected):
    require(s.status == 'COMPLETE' and s.cleanup_complete, 'A42341_OBSERVER_INVALID')
    check_sample_evidence(s, expected)


def check_sample_evidence(s, expected):
    """Check raw evidence without changing a partial point into a complete point."""
    key = s.identity
    require(key.model_dump() == schedule()[key.position], 'A42341_SAMPLE_ORDER_INVALID')
    required = condition(expected, key.block, key.variant, 8 + (key.pair * 2 +
        int(key.mode != ('OFF' if (key.pair + key.block) % 2 == 0 else 'ON'))) * 4)
    compare(s.prepared_before, s.prepared_after, required)
    require(s.batch_cache_keys == [required.prepare_cache_key_sha256] * 4,
            'A42341_PREPARE_IDENTITY_MISMATCH')
    require(s.process_identity == required.process_identity
        and s.connection_identity == required.connection_identity,
        'A42341_PREPARE_IDENTITY_MISMATCH')
    compare_environment(s.environment_before, s.environment_after, expected)
    require(s.window_started_ns < s.lookup_started_ns < s.lookup_finished_ns < s.window_finished_ns
        and (s.lookup_finished_ns - s.lookup_started_ns) / 1e6 == s.lookup_wall_ms,
        'A42341_CLOCK_DRIFT')
    require(set(s.segments) == {'sql_execute', 'driver_buffer', 'python_json', 'natural_gc'}
        and all(s.lookup_started_ns <= v.started_ns < v.finished_ns <= s.lookup_finished_ns
                for v in s.segments.values()), 'A42341_CLOCK_DRIFT')
    require(s.gc_thresholds_before == s.gc_thresholds_after == [700, 10, 10]
        and bool(s.gc_events) and all(s.lookup_started_ns <= g.started_ns < g.finished_ns
            <= s.lookup_finished_ns for g in s.gc_events), 'A42341_ENVIRONMENT_DRIFT')
    check_observer(s.observation, key.mode, s.lookup_started_ns, s.lookup_finished_ns)
    r = s.resources
    require(r.process_elapsed_ms > 0 and r.process_cpu_seconds > 0
        and r.process_elapsed_ms == (s.window_finished_ns - s.window_started_ns) / 1e6
        and r.process_rss_peak_bytes is not None, 'A42341_METRIC_UNAVAILABLE')
    if key.mode == 'ON':
        require(r.observer_thread_cpu_seconds is not None
            and r.observer_worker_elapsed_ms is not None and r.observer_worker_elapsed_ms > 0
            and r.observer_worker_elapsed_ms == (s.observation.worker_finished_ns
                - s.observation.worker_started_ns) / 1e6
            and r.observer_thread_cpu_seconds <= r.process_cpu_seconds,
            'A42341_METRIC_UNAVAILABLE')
    else:
        require(r.observer_thread_cpu_seconds is None and r.observer_worker_elapsed_ms is None,
                'A42341_OBSERVER_INVALID')
    backend_cpu(r, required, expected)
    require(r.backend_before.observed_ns == s.window_started_ns
        and r.backend_after.observed_ns == s.window_finished_ns, 'A42341_CLOCK_DRIFT')


def distribution(values):
    return dict(samples=[str(v) for v in values], p50=str(inclusive(values, '.5')),
                p95=str(inclusive(values, '.95')), maximum=str(max(values)))


def summaries(pairs):
    groups = {'ALL': pairs}
    for variant in ('C0', 'C1'):
        groups[variant] = [p for p in pairs if p['variant'] == variant]
        for block in range(4):
            groups[f'{block}:{variant}'] = [p for p in groups[variant] if p['block'] == block]
    output, accepted = {}, True
    for name, points in groups.items():
        wall = {k: distribution([decimal(p['lookup'][k]) for p in points])
                for k in ('signed', 'absolute', 'positive')}
        cpu = {k: distribution([decimal(p['backend_cpu'][k]) for p in points])
               for k in ('signed', 'absolute', 'positive')}
        rss = [p['rss_delta_bytes'] for p in points]
        qualifies = (decimal(wall['positive']['p50']) <= Decimal('.05')
            and decimal(wall['positive']['p95']) <= Decimal('.10')
            and decimal(cpu['positive']['p50']) <= Decimal('.05')
            and max(rss) <= 32 * 1024 ** 2)
        accepted &= qualifies
        output[name] = dict(n=len(points), lookup=wall, backend_cpu=cpu,
            rss_signed_bytes=rss, rss_absolute_bytes=[abs(v) for v in rss],
            proposed_threshold_result='SIMULATED_ACCEPT' if qualifies else 'SIMULATED_REJECT')
    return output, accepted


def validate_prefix_and_timeline(data, expected):
    """Both outcomes obey the same event prefix; a lookup failure omits only its end probe."""
    keys, count, failed = schedule(), len(data.samples), data.failed_point
    if failed is not None:
        require(count < 128 and failed.identity.model_dump() == keys[count]
            and failed.failure_code == data.first_failure_code, 'A42341_FAILED_POINT_INVALID')
        started_blocks = keys[count]['block'] + 1
    else:
        require(count == 128, 'A42341_COLLECTION_INCOMPLETE')
        started_blocks = 4
    require(len(data.blocks) == started_blocks, 'A42341_BLOCK_CONCURRENCY')
    require(data.parent_started_ns < data.parent_finished_ns
        and (data.parent_finished_ns - data.parent_started_ns) / 1e6 <= 1_200_000
        and data.workflow_elapsed_ms >= (data.parent_finished_ns
            - data.parent_started_ns) / 1e6, 'A42341_BUDGET_EXCEEDED')
    for i, sample in enumerate(data.samples):
        require(sample.identity.model_dump() == keys[i], 'A42341_SAMPLE_ORDER_INVALID')
        check_sample(sample, expected)
        if i:
            require(data.samples[i - 1].window_finished_ns <= sample.window_started_ns,
                    'A42341_BLOCK_CONCURRENCY')
    for b, block in enumerate(data.blocks):
        required = condition(expected, b, 'C0')
        require(block.block == b and block.process_identity == required.process_identity
            and block.connection_identity == required.connection_identity
            and data.parent_started_ns <= block.started_ns < block.finished_ns
                <= data.parent_finished_ns
            and (block.finished_ns - block.started_ns) / 1e6 <= 300_000,
            'A42341_BLOCK_CONCURRENCY')
        if b:
            require(data.blocks[b - 1].finished_ns < block.started_ns,
                    'A42341_BLOCK_CONCURRENCY')
        require(all(block.started_ns <= s.window_started_ns < s.window_finished_ns
            <= block.finished_ns for s in data.samples if s.identity.block == b),
            'A42341_BLOCK_CONCURRENCY')

    warmups = warmup_schedule()[:started_blocks * 4]
    require(len(data.warmups) == len(warmups), 'A42341_PREPARE_IDENTITY_MISMATCH')
    for row, definition in zip(data.warmups, warmups, strict=True):
        required = condition(expected, row.block, row.variant, row.lookup_number * 4)
        required = required.model_copy(update={'warmup_lookup_count': row.lookup_number})
        require({k: getattr(row, k) for k in definition} == definition
            and row.process_identity == required.process_identity
            and row.connection_identity == required.connection_identity
            and row.hypothetical_sql_count == row.lookup_number * 4
            and row.condition_after == required
            and row.hypothetical_batch_cache_keys == [required.prepare_cache_key_sha256] * 4,
            'A42341_PREPARE_IDENTITY_MISMATCH')
    phases = [(b, phase) for b in range(started_blocks)
        for phase in range(2 if failed is not None and b == started_blocks - 1 else 3)]
    require(len(data.probes) == len(phases), 'A42341_ENVIRONMENT_DRIFT')
    for i, (probe, (b, phase)) in enumerate(zip(data.probes, phases, strict=True)):
        block = data.blocks[b]
        require(probe.block == b and probe.phase == (
            'PRE_WARMUP', 'BLOCK_START', 'BLOCK_END')[phase]
            and probe.environment == environment(expected)
            and block.started_ns <= probe.started_ns < probe.finished_ns <= block.finished_ns,
            'A42341_ENVIRONMENT_DRIFT')
        if i:
            require(data.probes[i - 1].finished_ns <= probe.started_ns,
                    'A42341_ENVIRONMENT_DRIFT')
        wanted = [condition(expected, b, v, (0, 8, 72)[phase]) for v in ('C0', 'C1')]
        if phase == 0:
            wanted = [c.model_copy(update={'warmup_lookup_count': 0}) for c in wanted]
        require(probe.conditions == wanted, 'A42341_PREPARED_STABILITY_NOT_PROVEN')
        if phase < 2:
            if len(data.samples) > b * 32:
                anchor = data.samples[b * 32].window_started_ns
            else:
                anchor = (failed.partial_sample.window_started_ns if failed.partial_sample
                          else failed.observed_until_ns)
            require(probe.finished_ns <= anchor, 'A42341_ENVIRONMENT_DRIFT')
        else:
            require(probe.started_ns >= data.samples[b * 32 + 31].window_finished_ns,
                    'A42341_ENVIRONMENT_DRIFT')


def validate_partial_observer(sample, failure_code):
    """Authenticity is independent of the claimed payload-validation failure."""
    obs, resources = sample.observation, sample.resources
    require(resources.process_cpu_seconds > 0 and resources.process_elapsed_ms > 0,
            'A42341_FAILED_POINT_INVALID')
    if sample.identity.mode == 'OFF':
        require(obs.state == 'OBSERVER_OFF' and obs.joined and not obs.ticks
            and not obs.lifecycle and obs.overflow == 0
            and obs.worker_started_ns is None and obs.worker_finished_ns is None
            and resources.observer_thread_cpu_seconds is None
            and resources.observer_worker_elapsed_ms is None
            and failure_code != 'A42341_JOIN_TIMEOUT', 'A42341_FAILED_POINT_INVALID')
        return
    require(obs.worker_started_ns is not None
        and sample.window_started_ns <= obs.worker_started_ns < sample.lookup_started_ns,
        'A42341_FAILED_POINT_INVALID')
    if obs.joined:
        require(failure_code != 'A42341_JOIN_TIMEOUT' and obs.state == 'MOCK_JOINED'
            and obs.worker_finished_ns is not None
            and sample.lookup_finished_ns < obs.worker_finished_ns <= sample.window_finished_ns
            and obs.lifecycle == ['INIT', 'RUNNING', 'STOP_REQUESTED', 'JOINED', 'RECEIPT']
            and resources.observer_thread_cpu_seconds is not None
            and resources.observer_thread_cpu_seconds <= resources.process_cpu_seconds
            and resources.observer_worker_elapsed_ms is not None
            and resources.observer_worker_elapsed_ms > 0
            and resources.observer_worker_elapsed_ms == (
                obs.worker_finished_ns - obs.worker_started_ns) / 1e6
            and len(obs.ticks) == obs.planned_ticks
            and any(t.finished_ns < sample.lookup_started_ns for t in obs.ticks)
            and any(t.started_ns > sample.lookup_finished_ns for t in obs.ticks),
            'A42341_FAILED_POINT_INVALID')
    else:
        require(failure_code in {'A42341_JOIN_TIMEOUT', 'A42341_OBSERVER_INVALID'}
            and obs.state == 'STOP_TIMEOUT' and obs.worker_finished_ns is None
            and obs.lifecycle == ['INIT', 'RUNNING', 'STOP_REQUESTED']
            and resources.observer_thread_cpu_seconds is None
            and resources.observer_worker_elapsed_ms is None
            and not sample.cleanup_complete, 'A42341_FAILED_POINT_INVALID')
    for i, tick in enumerate(obs.ticks):
        require(tick.sequence == i
            and obs.worker_started_ns <= tick.started_ns < tick.finished_ns
                <= (obs.worker_finished_ns if obs.joined else sample.window_finished_ns)
            and tick.wall_ms == (tick.finished_ns - tick.started_ns) / 1e6
            and 0 < tick.wall_ms <= 25 and all(v <= 100 for v in tick.sql_wall_ms)
            and sum(tick.sql_wall_ms) <= tick.wall_ms
            and (not tick.partial or i == len(obs.ticks) - 1),
            'A42341_FAILED_POINT_INVALID')
        if i:
            previous = obs.ticks[i - 1]
            require(previous.finished_ns <= tick.started_ns
                and 200_000_000 <= tick.started_ns - previous.started_ns <= 500_000_000,
                'A42341_FAILED_POINT_INVALID')


def validate_failed_point(data, expected):
    failed = data.failed_point
    if failed is None:
        return
    block = data.blocks[failed.identity.block]
    require(block.started_ns <= failed.observed_until_ns <= block.finished_ns,
            'A42341_FAILED_POINT_INVALID')
    if data.samples:
        require(data.samples[-1].window_finished_ns <= failed.observed_until_ns,
                'A42341_FAILED_POINT_INVALID')
    sample = failed.partial_sample
    if sample is None:
        require(failed.phase == 'DURING_LOOKUP' and failed.failure_code in {
            'A42341_CANCELLED', 'A42341_SIGNAL', 'A42341_TIMEOUT',
            'A42341_SQL_TIMEOUT', 'A42341_WORKLOAD_FAILED'}, 'A42341_FAILED_POINT_INVALID')
        return
    required = condition(expected, failed.identity.block, failed.identity.variant)
    require(failed.phase == 'POST_LOOKUP_VALIDATION' and sample.status == 'INCOMPLETE'
        and sample.identity == failed.identity
        and sample.process_identity == required.process_identity
        and sample.connection_identity == required.connection_identity
        and block.started_ns <= sample.window_started_ns < sample.lookup_started_ns
            < sample.lookup_finished_ns < sample.window_finished_ns <= block.finished_ns
        and failed.observed_until_ns == sample.window_finished_ns,
        'A42341_FAILED_POINT_INVALID')
    if data.samples:
        require(data.samples[-1].window_finished_ns <= sample.window_started_ns,
                'A42341_FAILED_POINT_INVALID')
    require(set(sample.segments) == {'sql_execute', 'driver_buffer', 'python_json', 'natural_gc'}
        and all(sample.lookup_started_ns <= s.started_ns < s.finished_ns
            <= sample.lookup_finished_ns for s in sample.segments.values())
        and all(sample.lookup_started_ns <= g.started_ns < g.finished_ns
            <= sample.lookup_finished_ns for g in sample.gc_events), 'A42341_FAILED_POINT_INVALID')
    resources = sample.resources
    require(resources.process_elapsed_ms == (sample.window_finished_ns
        - sample.window_started_ns) / 1e6, 'A42341_FAILED_POINT_INVALID')
    for endpoint, timestamp in ((resources.backend_before, sample.window_started_ns),
                                (resources.backend_after, sample.window_finished_ns)):
        require(endpoint is None or (endpoint.observed_ns == timestamp
            and endpoint.container_sha256 == expected.fixture_sha256
            and endpoint.pid == required.backend_pid
            and endpoint.backend_start == required.backend_start
            and endpoint.process_start_ticks == 10000 + failed.identity.block
            and endpoint.clock_ticks == 100),
                'A42341_FAILED_POINT_INVALID')
    validate_partial_observer(sample, failed.failure_code)
    # Reproduce the claimed validation failure against the unchanged raw point, not a
    # synthesized COMPLETE copy. Geometry/lifecycle checks above cannot be bypassed by it.
    wanted = ('A42341_OBSERVER_INVALID' if failed.failure_code == 'A42341_JOIN_TIMEOUT'
              else failed.failure_code)
    try:
        check_sample_evidence(sample, expected)
    except Fault as error:
        require(error.code == wanted, 'A42341_FAILED_POINT_INVALID')
    else:
        raise Fault('A42341_FAILED_POINT_INVALID')


def validate_cleanup_consistency(data):
    failed, codes = data.failed_point, data.cleanup_failure_codes
    expected_codes = ['A42341_CLEANUP_FAILED'] if 'A42341_CLEANUP_FAILED' in codes else []
    partial = failed.partial_sample if failed else None
    if partial is not None and not partial.observation.joined:
        expected_codes.append('A42341_JOIN_TIMEOUT')
    require(codes == expected_codes and data.cleanup_complete == (not codes),
            'A42341_LIFECYCLE_INVALID')
    if partial is not None:
        require(partial.cleanup_complete == (partial.observation.joined
            and 'A42341_CLEANUP_FAILED' not in codes), 'A42341_LIFECYCLE_INVALID')
    if data.collection_status == 'COMPLETE':
        require(failed is None and data.first_failure_code is None and not codes
            and data.cleanup_complete, 'A42341_COLLECTION_INCOMPLETE')
    elif failed is None:
        require(len(data.samples) == 128 and codes == ['A42341_CLEANUP_FAILED']
            and data.first_failure_code == 'A42341_CLEANUP_FAILED', 'A42341_FALSE_INCOMPLETE')


def review(value, expected: Identity):
    try:
        validate_identity(expected)
        require(type(value) is dict, 'A42341_SCHEMA_INVALID')
        data = Bundle.model_validate(value)
        require(data.content_sha256 == digest({k: v for k, v in value.items()
            if k != 'content_sha256'}), 'A42341_DIGEST_MISMATCH')
        require(data.identity == expected, 'A42341_IDENTITY_MISMATCH')
        require(data.lifecycle == [
            'INIT', 'MOCK_RUNNING', 'MOCK_STOPPING', 'MOCK_CLOSED', 'RECEIPT'],
                'A42341_LIFECYCLE_INVALID')
        validate_prefix_and_timeline(data, expected)
        validate_failed_point(data, expected)
        validate_cleanup_consistency(data)
        if data.collection_status == 'INCOMPLETE':
            return dict(**Safety().model_dump(), collection_status='INCOMPLETE',
                calibration_decision='SIMULATED_REJECT', prepared_evidence_status='UNDETERMINED',
                environment_stability_status='INCOMPLETE',
                first_failure_code=data.first_failure_code,
                cleanup_failure_codes=data.cleanup_failure_codes, sample_count=len(data.samples),
                failed_point=data.failed_point.model_dump() if data.failed_point else None,
                overall_status='BLOCKED_NEEDS_USER_PROTOCOL_DECISION')
        pairs = []
        cpu_qualifies = True
        for i in range(0, 128, 2):
            pair = {s.identity.mode: s for s in data.samples[i:i + 2]}
            off, on = pair['OFF'], pair['ON']
            wall = relative(off.lookup_wall_ms, on.lookup_wall_ms)
            cpu = relative(backend_cpu(off.resources, off.prepared_before, expected),
                           backend_cpu(on.resources, on.prepared_before, expected))
            thread_ratio = decimal(on.resources.observer_thread_cpu_seconds) / (
                decimal(on.resources.process_elapsed_ms) / 1000)
            cpu_qualifies &= thread_ratio <= Decimal('.05')
            pairs.append(dict(block=off.identity.block, variant=off.identity.variant,
                pair=off.identity.pair, off_position=off.identity.position,
                on_position=on.identity.position, off_wall_ms=off.lookup_wall_ms,
                on_wall_ms=on.lookup_wall_ms, lookup={k: str(v) for k, v in wall.items()},
                backend_cpu={k: str(v) for k, v in cpu.items()},
                worker_cpu_over_process_elapsed=str(thread_ratio),
                rss_delta_bytes=on.resources.process_rss_peak_bytes
                    - off.resources.process_rss_peak_bytes))
        groups, accepted = summaries(pairs)
        return dict(**Safety().model_dump(), collection_status='COMPLETE',
            calibration_decision='SIMULATED_ACCEPT' if accepted and cpu_qualifies
                else 'SIMULATED_REJECT', threshold_status='PROPOSED_THRESHOLD', pairs=pairs,
            groups=groups, sample_count=128, prepared_evidence_status='SIMULATED_REAL_NOT_PROVEN',
            environment_stability_status='SIMULATED_REAL_NOT_VERIFIED', first_failure_code=None,
            overall_status='BLOCKED_NEEDS_USER_PROTOCOL_DECISION')
    except Fault:
        raise
    except Exception:
        raise Fault('A42341_SCHEMA_INVALID') from None


def failure_receipt(value, error=None, expected=None):
    # Never copy a malformed/untrusted identity or error text to the failure artifact.
    try:
        data = Bundle.model_validate(value)
        require(expected is None or data.identity == expected, 'A42341_IDENTITY_MISMATCH')
    except Exception:
        return dict(**Safety().model_dump(), schema_version='a42341.failure.v1',
            collection_status='INCOMPLETE', identity=expected.model_dump() if expected else None,
            first_failure_code=error or 'A42341_SCHEMA_INVALID', artifact_failure_code=error,
            cleanup_failure_codes=[], cleanup_complete=False, failed_point=None)
    return dict(**Safety().model_dump(), schema_version='a42341.failure.v1',
        collection_status='INCOMPLETE' if error or value['first_failure_code'] else 'COMPLETE',
        identity=data.identity.model_dump(), first_failure_code=data.first_failure_code or error,
        artifact_failure_code=error,
        cleanup_failure_codes=value['cleanup_failure_codes'],
        cleanup_complete=value['cleanup_complete'],
        failed_point=value['failed_point'])


def write_bundle(directory, value, expected, *, writer=write_new):
    directory = safe_path(directory)
    require(not directory.exists() and directory.parent.is_dir(), 'A42341_OUTPUT_EXISTS')
    directory.mkdir()
    try:
        result = review(value, expected)
        documents = {'samples.json': value, 'review.json': result,
                     'failure.json': failure_receipt(value, expected=expected)}
        entries = {n: writer(directory / n, v) for n, v in documents.items()}
        manifest = seal(dict(**Safety().model_dump(), schema_version='a42341.manifest.v1',
            identity=expected.model_dump(), files=entries))
        writer(directory / 'manifest.json', manifest)
        return result
    except BaseException as error:
        code = error.code if isinstance(error, Fault) else 'A42341_ARTIFACT_WRITE_FAILED'
        try:
            write_new(directory / 'artifact-failure.json',
                      failure_receipt(value, code, expected))
        except BaseException:
            pass  # Disk may be broken: no manifest success; fixed code propagates.
        raise Fault(code) from None


def review_bundle(directory, expected):
    try:
        directory = safe_path(directory)
        require(directory.is_dir() and {p.name for p in directory.iterdir()} == {
            'samples.json', 'review.json', 'failure.json', 'manifest.json'},
            'A42341_BUNDLE_INCOMPLETE')
        manifest = load(directory / 'manifest.json')
        require(set(manifest) == set(Safety.model_fields) | {
            'schema_version', 'identity', 'files', 'content_sha256'}
            and manifest['schema_version'] == 'a42341.manifest.v1'
            and manifest['identity'] == expected.model_dump()
            and manifest['content_sha256'] == digest({k: v for k, v in manifest.items()
                if k != 'content_sha256'})
            and all(manifest[k] == v for k, v in Safety().model_dump().items()),
            'A42341_MANIFEST_INVALID')
        require(set(manifest['files']) == {'samples.json', 'review.json', 'failure.json'},
                'A42341_ARTIFACT_PATH_INVALID')
        for name, entry in manifest['files'].items():
            path = directory / name
            require(set(entry) == {'sha256', 'bytes'} and file_sha(path) == entry['sha256']
                and path.stat().st_size == entry['bytes'], 'A42341_DIGEST_MISMATCH')
        value = load(directory / 'samples.json')
        result = review(value, expected)
        require(load(directory / 'review.json') == result
            and load(directory / 'failure.json') == failure_receipt(value),
            'A42341_REVIEW_MISMATCH')
        return result
    except Fault:
        raise
    except Exception:
        raise Fault('A42341_BUNDLE_INVALID') from None


def main(argv=None):
    import json
    import sys

    args = sys.argv[1:] if argv is None else list(argv)
    try:
        require(len(args) == 4 and args[0] == '--directory' and args[2] == '--expected'
            and not args[1].startswith('--') and not args[3].startswith('--'),
                'A42341_EXECUTION_NOT_AUTHORIZED')
        value = review_bundle(Path(args[1]), Identity.model_validate(load(args[3])))
        accepted = value['calibration_decision'] == 'SIMULATED_ACCEPT'
        result = ('MOCK_VALID_SIMULATED_ACCEPT_NOT_AUTHORIZED' if accepted
                  else 'MOCK_VALID_NOT_QUALIFIED')
        print(json.dumps(dict(**Safety().model_dump(), result=result,
            mock_contract_validated=True,
            simulated_threshold_decision=value['calibration_decision'],
            real_performance_eligible=False), sort_keys=True))
        return 2 if accepted else 3
    except BaseException as error:
        code = error.code if isinstance(error, Fault) else 'A42341_OFFLINE_REVIEW_REJECTED'
        print(json.dumps(dict(**Safety().model_dump(), result=code,
            mock_contract_validated=False, simulated_threshold_decision=None,
            real_performance_eligible=False), sort_keys=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
