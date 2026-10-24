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
from scripts.a42341_environment_contract import backend_cpu, check_observer, compare_environment
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
    key = s.identity
    require(s.status == 'COMPLETE' and s.cleanup_complete, 'A42341_OBSERVER_INVALID')
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
        for i, s in enumerate(data.samples):
            require(s.identity.model_dump() == schedule()[i], 'A42341_SAMPLE_ORDER_INVALID')
            check_sample(s, expected)
            if i:
                require(data.samples[i - 1].window_finished_ns <= s.window_started_ns,
                        'A42341_BLOCK_CONCURRENCY')
        require(data.parent_started_ns < data.parent_finished_ns
            and (data.parent_finished_ns - data.parent_started_ns) / 1e6 <= 1_200_000
            and data.workflow_elapsed_ms >= (data.parent_finished_ns
                - data.parent_started_ns) / 1e6, 'A42341_BUDGET_EXCEEDED')
        for b, block in enumerate(data.blocks):
            c = condition(expected, b, 'C0')
            require(block.block == b and block.process_identity == c.process_identity
                and block.connection_identity == c.connection_identity
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
        if data.collection_status == 'INCOMPLETE':
            require(data.cleanup_complete == (not data.cleanup_failure_codes),
                    'A42341_LIFECYCLE_INVALID')
            require(data.first_failure_code is not None and
                (data.failed_point is not None or bool(data.cleanup_failure_codes)),
                'A42341_FALSE_INCOMPLETE')
            if data.failed_point is not None:
                require(len(data.samples) < 128 and data.failed_point.identity.model_dump()
                    == schedule()[len(data.samples)]
                    and data.failed_point.failure_code == data.first_failure_code,
                    'A42341_FAILED_POINT_INVALID')
                partial = data.failed_point.partial_sample
                require(partial is None or partial.identity == data.failed_point.identity,
                        'A42341_FAILED_POINT_INVALID')
            return dict(**Safety().model_dump(), collection_status='INCOMPLETE',
                calibration_decision='SIMULATED_REJECT', prepared_evidence_status='UNDETERMINED',
                environment_stability_status='INCOMPLETE',
                first_failure_code=data.first_failure_code,
                cleanup_failure_codes=data.cleanup_failure_codes, sample_count=len(data.samples),
                failed_point=data.failed_point.model_dump() if data.failed_point else None,
                overall_status='BLOCKED_NEEDS_USER_PROTOCOL_DECISION')
        require(len(data.samples) == 128 and len(data.blocks) == 4 and len(data.warmups) == 16
            and len(data.probes) == 12 and data.failed_point is None
            and data.first_failure_code is None and not data.cleanup_failure_codes
            and data.cleanup_complete, 'A42341_COLLECTION_INCOMPLETE')
        for row, definition in zip(data.warmups, warmup_schedule(), strict=True):
            c = condition(expected, row.block, row.variant, row.lookup_number * 4)
            c = c.model_copy(update={'warmup_lookup_count': row.lookup_number})
            require({k: getattr(row, k) for k in definition} == definition
                and row.process_identity == c.process_identity
                and row.connection_identity == c.connection_identity
                and row.hypothetical_sql_count == row.lookup_number * 4
                and row.condition_after == c
                and row.hypothetical_batch_cache_keys == [c.prepare_cache_key_sha256] * 4,
                'A42341_PREPARE_IDENTITY_MISMATCH')
        for i, probe in enumerate(data.probes):
            b, phase = divmod(i, 3)
            executions = (0, 8, 72)[phase]
            require(probe.block == b and probe.phase == (
                'PRE_WARMUP', 'BLOCK_START', 'BLOCK_END')[phase]
                and probe.environment == data.samples[b * 32].environment_before
                and probe.finished_ns > probe.started_ns
                and data.blocks[b].started_ns <= probe.started_ns < probe.finished_ns
                    <= data.blocks[b].finished_ns, 'A42341_ENVIRONMENT_DRIFT')
            wanted = [condition(expected, b, v, executions) for v in ('C0', 'C1')]
            if phase == 0:
                wanted = [c.model_copy(update={'warmup_lookup_count': 0}) for c in wanted]
            require(probe.conditions == wanted, 'A42341_PREPARED_STABILITY_NOT_PROVEN')
            if phase < 2:
                require(probe.finished_ns <= data.samples[b * 32].window_started_ns,
                        'A42341_ENVIRONMENT_DRIFT')
            else:
                require(probe.started_ns >= data.samples[b * 32 + 31].window_finished_ns,
                        'A42341_ENVIRONMENT_DRIFT')
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
    import sys

    args = sys.argv[1:] if argv is None else list(argv)
    try:
        require(len(args) == 4 and args[0] == '--directory' and args[2] == '--expected',
                'A42341_EXECUTION_NOT_AUTHORIZED')
        value = review_bundle(Path(args[1]), Identity.model_validate(load(args[3])))
        return 0 if value['calibration_decision'] == 'SIMULATED_ACCEPT' else 1
    except BaseException as error:
        print(error.code if isinstance(error, Fault) else 'A42341_OFFLINE_REVIEW_REJECTED')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
