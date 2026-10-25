"""Mock-only same-lifecycle resource bridge. Never reads /proc or deploys helpers."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from scripts.a4235_calibration_adapter_contract import (
    Counter,
    Hash,
    Positive,
    Strict,
    require,
)


class ProcSnapshot(Strict):
    backend_pid: Positive
    mapped_proc_pid: Positive
    backend_start_sha256: Hash
    proc_start_ticks: Positive
    namespace_sha256: Hash
    container_sha256: Hash
    clock_domain_sha256: Hash
    clock_ticks: Positive
    observed_ns: Positive
    user_ticks: Counter
    system_ticks: Counter
    permission_verified: Literal[True]
    bidirectional_mapping_verified: Literal[True]
    evidence_kind: Literal['MOCK_ONLY'] = 'MOCK_ONLY'


def backend_delta(before: ProcSnapshot, after: ProcSnapshot,
                  expected: ProcSnapshot) -> dict:
    points = [ProcSnapshot.model_validate(p.model_dump()) for p in (before, after, expected)]
    before, after, expected = points
    fields = ('backend_pid', 'mapped_proc_pid', 'backend_start_sha256', 'proc_start_ticks',
              'namespace_sha256', 'container_sha256', 'clock_domain_sha256', 'clock_ticks')
    require(all(getattr(before, k) == getattr(after, k) == getattr(expected, k) for k in fields),
            'A4235_PROCESS_IDENTITY_DRIFT')
    require(before.backend_pid == before.mapped_proc_pid, 'A4235_NAMESPACE_MAPPING_UNPROVEN')
    require(after.observed_ns > before.observed_ns
            and after.user_ticks >= before.user_ticks
            and after.system_ticks >= before.system_ticks, 'A4235_RESOURCE_INTERVAL_INVALID')
    ticks = after.user_ticks + after.system_ticks - before.user_ticks - before.system_ticks
    require(ticks > 0, 'A4235_METRIC_UNAVAILABLE')
    cpu = Decimal(ticks) / Decimal(before.clock_ticks)
    elapsed = Decimal(after.observed_ns - before.observed_ns) / Decimal(1_000_000_000)
    return dict(evidence_kind='MOCK_ONLY', scope='SAME_BACKEND_USER_PLUS_SYSTEM_INTERVAL',
                source='MOCK_PROC_USER_SYSTEM_TICKS', unit='seconds',
                interval=[before.observed_ns, after.observed_ns],
                mock_cpu_seconds=str(cpu), mock_cpu_over_elapsed=str(cpu / elapsed),
                real_availability='METRIC_UNAVAILABLE')


class Metric(Strict):
    scope: Literal['PROCESS_CPU', 'ENTIRE_OBSERVER_THREAD_CPU', 'WORKER_ELAPSED',
                   'PROCESS_LIFETIME_RSS_HIGH_WATER', 'NATURAL_GC_EVENT']
    source: Literal['MOCK_PROCESS_TIME', 'MOCK_THREAD_TIME', 'MOCK_MONOTONIC',
                    'MOCK_RUSAGE', 'MOCK_GC_CALLBACK']
    unit: Literal['ns', 'bytes']
    started_ns: Positive
    finished_ns: Positive
    identity_sha256: Hash
    availability: Literal['MOCK_ONLY', 'METRIC_UNAVAILABLE']
    value: Counter | None


class Resources(Strict):
    metrics: Annotated[list[Metric], Field(min_length=5, max_length=5)]
    gc_enabled_before: Literal[True]
    gc_enabled_after: Literal[True]
    gc_thresholds_before: tuple[Positive, Positive, Positive]
    gc_thresholds_after: tuple[Positive, Positive, Positive]


def validate_resources(value: Resources, identity_sha256: str,
                       started_ns: int, finished_ns: int) -> None:
    value = Resources.model_validate(value.model_dump())
    expected = dict(PROCESS_CPU=('MOCK_PROCESS_TIME', 'ns'),
                    ENTIRE_OBSERVER_THREAD_CPU=('MOCK_THREAD_TIME', 'ns'),
                    WORKER_ELAPSED=('MOCK_MONOTONIC', 'ns'),
                    PROCESS_LIFETIME_RSS_HIGH_WATER=('MOCK_RUSAGE', 'bytes'),
                    NATURAL_GC_EVENT=('MOCK_GC_CALLBACK', 'ns'))
    require({m.scope for m in value.metrics} == set(expected), 'A4235_METRIC_SCOPE_INVALID')
    require(value.gc_thresholds_before == value.gc_thresholds_after, 'A4235_GC_CHANGED')
    for metric in value.metrics:
        require((metric.source, metric.unit) == expected[metric.scope]
                and metric.identity_sha256 == identity_sha256
                and started_ns <= metric.started_ns < metric.finished_ns <= finished_ns,
                'A4235_METRIC_SCOPE_INVALID')
        require((metric.availability == 'METRIC_UNAVAILABLE' and metric.value is None)
                or (metric.availability == 'MOCK_ONLY' and metric.value is not None
                    and metric.value > 0), 'A4235_METRIC_UNAVAILABLE')
        if metric.scope != 'NATURAL_GC_EVENT':
            require(metric.started_ns == started_ns and metric.finished_ns == finished_ns,
                    'A4235_METRIC_SCOPE_INVALID')
        if metric.scope in ('ENTIRE_OBSERVER_THREAD_CPU', 'NATURAL_GC_EVENT') \
                and metric.value is not None:
            require(metric.value <= metric.finished_ns - metric.started_ns,
                    'A4235_METRIC_SCOPE_INVALID')
        if metric.value is not None and metric.scope == 'WORKER_ELAPSED':
            require(metric.value == metric.finished_ns - metric.started_ns,
                    'A4235_METRIC_SCOPE_INVALID')
