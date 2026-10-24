"""Pure data mocks, not a driver: no database, process, thread, workload or GC API."""

from typing import Annotated, Literal

from pydantic import Field

from scripts.a42341_contract import (
    Counter,
    Failure,
    Fault,
    Hash,
    Identity,
    Milliseconds,
    Positive,
    Safety,
    SampleIdentity,
    Strict,
    Variant,
    require,
    schedule,
    seal,
    validate_identity,
    warmup_schedule,
)
from scripts.a42341_environment_contract import (
    BackendPoint,
    Environment,
    GCEvent,
    Observation,
    Resources,
    Tick,
    environment,
)
from scripts.a42341_prepared_capability import PrepareCondition, condition


class MockWorkload(Strict):
    off_wall_ms: Annotated[float, Field(gt=0, le=300_000)] = 50.0
    on_wall_ms: Annotated[float, Field(gt=0, le=300_000)] = 51.0
    fail_at: Annotated[int, Field(strict=True, ge=0, le=127)] | None = None
    failure_code: Literal['A42341_WORKLOAD_FAILED', 'A42341_CANCELLED', 'A42341_SIGNAL',
                          'A42341_TIMEOUT', 'A42341_SQL_TIMEOUT'] = 'A42341_WORKLOAD_FAILED'


class MockObserver(Strict):
    planned_ticks: Literal[3] = 3
    fail_at: Annotated[int, Field(strict=True, ge=0, le=127)] | None = None
    failure_code: Literal['A42341_JOIN_TIMEOUT', 'A42341_OBSERVER_INVALID'] = 'A42341_JOIN_TIMEOUT'
    source: Literal['MOCK_CONTRACT_ONLY'] = 'MOCK_CONTRACT_ONLY'


class MockClock(Strict):
    window_ms: Literal[503] = 503
    block_stride_ms: Literal[20000] = 20000


class MockResources(Strict):
    backend_available: bool = True
    rss_available: bool = True
    cleanup_failure: bool = False


class Segment(Strict):
    started_ns: Counter
    finished_ns: Positive


class Sample(Strict):
    identity: SampleIdentity
    process_identity: Hash
    connection_identity: Hash
    window_started_ns: Positive
    window_finished_ns: Positive
    lookup_started_ns: Positive
    lookup_finished_ns: Positive
    lookup_wall_ms: Annotated[float, Field(gt=0, le=300_000)]
    segments: dict[Literal['sql_execute', 'driver_buffer', 'python_json', 'natural_gc'], Segment]
    cost_scope: Literal['NESTED_NOT_ADDITIVE_NOT_SUBTRACTED']
    setup_wall_ms: Milliseconds
    observer_wait_wall_ms: Milliseconds
    serialization_wall_ms: Milliseconds
    write_wall_ms: Milliseconds
    gc_enabled_before: Literal[True]
    gc_enabled_after: Literal[True]
    gc_thresholds_before: Annotated[list[Counter], Field(min_length=3, max_length=3)]
    gc_thresholds_after: Annotated[list[Counter], Field(min_length=3, max_length=3)]
    gc_events: Annotated[list[GCEvent], Field(max_length=256)]
    environment_before: Environment
    environment_after: Environment
    prepared_before: PrepareCondition
    prepared_after: PrepareCondition
    keys: Literal[2000] = 2000
    batch_size: Literal[500] = 500
    batch_cache_keys: Annotated[list[Hash], Field(min_length=4, max_length=4)]
    resources: Resources
    observation: Observation
    status: Literal['COMPLETE', 'INCOMPLETE'] = 'COMPLETE'
    cleanup_complete: bool = True
    source: Literal['MOCK_CONTRACT_ONLY'] = 'MOCK_CONTRACT_ONLY'


class Warmup(Strict):
    block: Annotated[int, Field(strict=True, ge=0, le=3)]
    position: Annotated[int, Field(strict=True, ge=0, le=3)]
    variant: Variant
    mode: Literal['OFF']
    lookup_number: Literal[1, 2]
    process_identity: Hash
    connection_identity: Hash
    hypothetical_sql_count: Literal[4, 8]
    condition_after: PrepareCondition
    hypothetical_batch_cache_keys: Annotated[list[Hash], Field(min_length=4, max_length=4)]
    source: Literal['MOCK_CONTRACT_ONLY'] = 'MOCK_CONTRACT_ONLY'


class Probe(Strict):
    block: Annotated[int, Field(strict=True, ge=0, le=3)]
    phase: Literal['PRE_WARMUP', 'BLOCK_START', 'BLOCK_END']
    started_ns: Positive
    finished_ns: Positive
    environment: Environment
    conditions: Annotated[list[PrepareCondition], Field(min_length=2, max_length=2)]
    source: Literal['MOCK_CONTRACT_ONLY'] = 'MOCK_CONTRACT_ONLY'


class Block(Strict):
    block: Annotated[int, Field(strict=True, ge=0, le=3)]
    process_identity: Hash
    connection_identity: Hash
    started_ns: Positive
    finished_ns: Positive
    status: Literal['MOCK_SERIAL_BLOCK'] = 'MOCK_SERIAL_BLOCK'


class FailedPoint(Strict):
    identity: SampleIdentity
    observed_until_ns: Positive
    failure_code: Failure
    phase: Literal['DURING_LOOKUP', 'POST_LOOKUP_VALIDATION']
    partial_sample: Sample | None


class Bundle(Safety):
    schema_version: Literal['a42341.mock.v1'] = 'a42341.mock.v1'
    identity: Identity
    collection_status: Literal['COMPLETE', 'INCOMPLETE']
    samples: Annotated[list[Sample], Field(max_length=128)]
    warmups: Annotated[list[Warmup], Field(max_length=16)]
    probes: Annotated[list[Probe], Field(max_length=12)]
    blocks: Annotated[list[Block], Field(max_length=4)]
    parent_started_ns: Positive
    parent_finished_ns: Positive
    workflow_elapsed_ms: Annotated[float, Field(gt=0, le=1_800_000)]
    first_failure_code: Failure | None
    cleanup_failure_codes: Annotated[list[Failure], Field(max_length=4)]
    cleanup_complete: bool
    failed_point: FailedPoint | None
    lifecycle: Annotated[list[Literal['INIT', 'MOCK_RUNNING', 'MOCK_STOPPING',
        'MOCK_CLOSED', 'RECEIPT']], Field(min_length=5, max_length=5)]
    content_sha256: Hash


def probe(expected, block, phase, time_ns, executions):
    conditions = [condition(expected, block, v, executions) for v in ('C0', 'C1')]
    if executions == 0:
        conditions = [c.model_copy(update={'warmup_lookup_count': 0}) for c in conditions]
    return Probe(block=block, phase=phase, started_ns=time_ns, finished_ns=time_ns + 1_000_000,
        environment=environment(expected), conditions=conditions)


def mock_sample(expected, position, start_ns, workload, resources):
    key = SampleIdentity(**schedule()[position])
    before = condition(expected, key.block, key.variant, 8 + (key.pair * 2 +
        int(key.mode != ('OFF' if (key.pair + key.block) % 2 == 0 else 'ON'))) * 4)
    after = before.model_copy(update={'sql_exec_count': before.sql_exec_count + 4,
                                    'custom_plans': before.custom_plans + 4})
    wall = workload.off_wall_ms if key.mode == 'OFF' else workload.on_wall_ms
    lookup_start, lookup_end = start_ns + 2_000_000, start_ns + 2_000_000 + round(wall * 1e6)
    ticks = [Tick(sequence=i, started_ns=start_ns + i * 250_000_000,
        finished_ns=start_ns + i * 250_000_000 + 1_000_000, wall_ms=1.0,
        sql_wall_ms=[0.1] * 5, event_codes=['NOT_OBSERVED'], partial=False) for i in range(3)]
    on = key.mode == 'ON'
    obs = Observation(state='MOCK_JOINED' if on else 'OBSERVER_OFF', ticks=ticks if on else [],
        overflow=0, joined=True, stop_wall_ms=1.0,
        worker_started_ns=start_ns if on else None,
        worker_finished_ns=start_ns + 503_000_000 if on else None,
        lifecycle=['INIT', 'RUNNING', 'STOP_REQUESTED', 'JOINED', 'RECEIPT'] if on else [])
    backend = BackendPoint(container_sha256=expected.fixture_sha256, pid=before.backend_pid,
        backend_start=before.backend_start, process_start_ticks=10000 + key.block,
        clock_ticks=100, observed_ns=start_ns, user_system_cpu_seconds=10.0)
    end_backend = backend.model_copy(update={
        'user_system_cpu_seconds': 10.0051 if on else 10.005,
        'observed_ns': start_ns + 503_000_000})
    metrics = Resources(process_cpu_seconds=0.021 if on else 0.02, process_elapsed_ms=503.0,
        process_rss_peak_bytes=((104 if on else 96) * 1024 ** 2)
            if resources.rss_available else None,
        observer_thread_cpu_seconds=0.001 if on else None,
        observer_worker_elapsed_ms=503.0 if on else None,
        backend_before=backend if resources.backend_available else None,
        backend_after=end_backend if resources.backend_available else None,
        backend_status='MOCK_AVAILABLE' if resources.backend_available else 'NOT_AVAILABLE',
        cpu_scope='ENTIRE_WORKER_THREAD_OVER_PROCESS_ELAPSED',
        rss_scope='PROCESS_LIFETIME_HIGH_WATER',
        backend_scope='SAME_BACKEND_USER_PLUS_SYSTEM_INTERVAL')
    env = environment(expected)
    segments = {name: Segment(started_ns=lookup_start + round(a * wall * 1e6),
                             finished_ns=lookup_start + round(b * wall * 1e6))
        for name, a, b in (('sql_execute', 0, .6), ('driver_buffer', .6, .7),
                          ('python_json', .7, .99), ('natural_gc', .8, .82))}
    return Sample(identity=key, process_identity=before.process_identity,
        connection_identity=before.connection_identity, window_started_ns=start_ns,
        window_finished_ns=start_ns + 503_000_000, lookup_started_ns=lookup_start,
        lookup_finished_ns=lookup_end, lookup_wall_ms=wall, segments=segments,
        cost_scope='NESTED_NOT_ADDITIVE_NOT_SUBTRACTED', setup_wall_ms=2.0,
        observer_wait_wall_ms=max(500.0 - wall, 0.0), serialization_wall_ms=0.5, write_wall_ms=0.5,
        gc_enabled_before=True, gc_enabled_after=True,
        gc_thresholds_before=[700, 10, 10], gc_thresholds_after=[700, 10, 10],
        gc_events=[GCEvent(started_ns=segments['natural_gc'].started_ns,
                          finished_ns=segments['natural_gc'].finished_ns, generation=0,
                          collected=1, uncollectable=0)],
        environment_before=env, environment_after=env, prepared_before=before, prepared_after=after,
        batch_cache_keys=[before.prepare_cache_key_sha256] * 4,
        resources=metrics, observation=obs)


def simulate(expected, *, workload=None, observer=None, clock=None, resources=None):
    """Only exact built-in data-only mocks; NEVER calls injected arbitrary callbacks."""
    from scripts.a42341_calibration_review import check_sample

    validate_identity(expected)
    mocks = []
    try:
        for value, model in ((workload, MockWorkload), (observer, MockObserver),
                             (clock, MockClock), (resources, MockResources)):
            require(value is None or type(value) is model, 'A42341_REAL_ADAPTER_FORBIDDEN')
            mocks.append(model() if value is None else
                         model.model_validate(value.model_dump(warnings='error')))
    except Fault:
        raise
    except Exception:
        raise Fault('A42341_MOCK_CONFIG_INVALID') from None
    workload, observer, clock, resources = mocks
    require(observer.fail_at is None or schedule()[observer.fail_at]['mode'] == 'ON',
            'A42341_OBSERVER_INVALID')
    samples, warmups, probes, blocks = [], [], [], []
    first, failed = None, None
    for b in range(4):
        base = 1_000_000 + b * clock.block_stride_ms * 1_000_000
        probes.append(probe(expected, b, 'PRE_WARMUP', base, 0))
        for row in (w for w in warmup_schedule() if w['block'] == b):
            c = condition(expected, b, row['variant'])
            after = condition(expected, b, row['variant'], row['lookup_number'] * 4)
            after = after.model_copy(update={'warmup_lookup_count': row['lookup_number']})
            warmups.append(Warmup(**row, process_identity=c.process_identity,
                connection_identity=c.connection_identity,
                hypothetical_sql_count=row['lookup_number'] * 4, condition_after=after,
                hypothetical_batch_cache_keys=[c.prepare_cache_key_sha256] * 4))
        probes.append(probe(expected, b, 'BLOCK_START', base + 5_000_000, 8))
        finish = base + 6_000_000
        for offset in range(32):
            position, start = b * 32 + offset, base + 6_000_000 + offset * 503_000_000
            point = None
            try:
                if workload.fail_at == position:
                    raise Fault(workload.failure_code)
                point = mock_sample(expected, position, start, workload, resources)
                if observer.fail_at == position:
                    fields = dict(joined=False, state='STOP_TIMEOUT', worker_finished_ns=None,
                                  lifecycle=['INIT', 'RUNNING', 'STOP_REQUESTED'])
                    if observer.failure_code == 'A42341_OBSERVER_INVALID':
                        ticks = list(point.observation.ticks)
                        ticks[-1] = ticks[-1].model_copy(update={'partial': True})
                        fields['ticks'] = ticks
                    point = point.model_copy(update={
                        'observation': point.observation.model_copy(update=fields),
                        'resources': point.resources.model_copy(update={
                            'observer_thread_cpu_seconds': None,
                            'observer_worker_elapsed_ms': None})})
                    raise Fault(observer.failure_code)
                check_sample(point, expected)
                samples.append(point)
                finish = point.window_finished_ns
            except Exception as error:
                code = error.code if isinstance(error, Fault) else 'A42341_INTERNAL'
                # Unknown/schema diagnostics never become arbitrary exception output.
                if code not in Failure.__args__:
                    code = 'A42341_INTERNAL'
                first = first or code
                if point is not None:
                    point = point.model_copy(update={'status': 'INCOMPLETE',
                        'cleanup_complete': point.observation.joined
                            and not resources.cleanup_failure})
                failed = FailedPoint(identity=SampleIdentity(**schedule()[position]),
                    observed_until_ns=point.window_finished_ns if point else start + 1_000_000,
                    failure_code=first,
                    phase='POST_LOOKUP_VALIDATION' if point else 'DURING_LOOKUP',
                    partial_sample=point)
                finish = failed.observed_until_ns
                break
        c = condition(expected, b, 'C0')
        blocks.append(Block(block=b, process_identity=c.process_identity,
            connection_identity=c.connection_identity, started_ns=base,
            finished_ns=finish + 1_000_000))
        if first:
            break
        probes.append(probe(expected, b, 'BLOCK_END', finish, 72))
    cleanup = ['A42341_CLEANUP_FAILED'] if resources.cleanup_failure else []
    if failed and failed.partial_sample and not failed.partial_sample.observation.joined:
        cleanup.append('A42341_JOIN_TIMEOUT')
    if cleanup:
        first = first or cleanup[0]
    value = dict(**Safety().model_dump(), schema_version='a42341.mock.v1',
        identity=expected.model_dump(), collection_status='INCOMPLETE' if first else 'COMPLETE',
        samples=[p.model_dump() for p in samples], warmups=[w.model_dump() for w in warmups],
        probes=[p.model_dump() for p in probes], blocks=[b.model_dump() for b in blocks],
        parent_started_ns=1, parent_finished_ns=blocks[-1].finished_ns + 1,
        workflow_elapsed_ms=(blocks[-1].finished_ns + 1) / 1e6,
        first_failure_code=first, cleanup_failure_codes=cleanup, cleanup_complete=not cleanup,
        failed_point=failed.model_dump() if failed else None,
        lifecycle=['INIT', 'MOCK_RUNNING', 'MOCK_STOPPING', 'MOCK_CLOSED', 'RECEIPT'])
    return Bundle.model_validate(seal(value)).model_dump()


def main(argv=None):
    # Not even --mock is a CLI permission; mocks are invoked by contract tests only.
    raise Fault('A42341_EXECUTION_NOT_AUTHORIZED')


if __name__ == '__main__':
    raise SystemExit('A42341_EXECUTION_NOT_AUTHORIZED')
