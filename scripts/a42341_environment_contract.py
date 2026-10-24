"""Bounded mock resources/environment; no DB, clock, process or GC collection."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from scripts.a42341_contract import (
    Counter,
    Hash,
    Identity,
    Milliseconds,
    Positive,
    Seconds,
    Strict,
    Timestamp,
    Variant,
    definitions,
    mock_hash,
    require,
)

TABLES = ('data_publication_row', 'signal_forward_eval',
          'stock_opportunity_daily', 'stock_trade_status_daily')


class Environment(Strict):
    data_sha256: Hash
    model_sha256: Hash
    index_sha256: Hash
    statistics: dict[Literal['data_publication_row', 'signal_forward_eval',
        'stock_opportunity_daily', 'stock_trade_status_daily'], Hash]
    sql_templates: dict[Variant, Hash]
    fresh_plans: dict[Variant, Hash]
    cached_plans: dict[Variant, Hash]
    cached_mode: Literal['CUSTOM_ONLY'] = 'CUSTOM_ONLY'
    clock_domain_sha256: Hash
    backend_container_sha256: Hash
    source: Literal['MOCK_CONTRACT_ONLY'] = 'MOCK_CONTRACT_ONLY'


def environment(expected: Identity):
    return Environment(data_sha256=expected.data_snapshot_sha256,
        model_sha256=expected.model_sha256, index_sha256=mock_hash('index'),
        statistics={t: mock_hash('statistics', t) for t in TABLES},
        sql_templates=definitions()['sql_template_sha256'],
        fresh_plans={v: mock_hash('fresh', v) for v in ('C0', 'C1')},
        cached_plans={v: mock_hash('cached', v) for v in ('C0', 'C1')},
        clock_domain_sha256=mock_hash('monotonic_mock_clock'),
        backend_container_sha256=expected.fixture_sha256)


class BackendPoint(Strict):
    container_sha256: Hash
    pid: Positive
    backend_start: Timestamp
    process_start_ticks: Positive
    clock_ticks: Positive
    observed_ns: Positive
    user_system_cpu_seconds: Seconds
    source: Literal['MOCK_USER_PLUS_SYSTEM'] = 'MOCK_USER_PLUS_SYSTEM'


class Resources(Strict):
    process_cpu_seconds: Seconds
    process_elapsed_ms: Milliseconds
    process_rss_peak_bytes: Positive | None
    observer_thread_cpu_seconds: Seconds | None
    observer_worker_elapsed_ms: Milliseconds | None
    backend_before: BackendPoint | None
    backend_after: BackendPoint | None
    backend_status: Literal['MOCK_AVAILABLE', 'NOT_AVAILABLE']
    cpu_scope: Literal['ENTIRE_WORKER_THREAD_OVER_PROCESS_ELAPSED']
    rss_scope: Literal['PROCESS_LIFETIME_HIGH_WATER']
    backend_scope: Literal['SAME_BACKEND_USER_PLUS_SYSTEM_INTERVAL']


class Tick(Strict):
    sequence: Counter
    started_ns: Counter
    finished_ns: Positive
    wall_ms: Milliseconds
    sql_wall_ms: Annotated[list[Milliseconds], Field(min_length=5, max_length=5)]
    event_codes: Annotated[list[Literal['NOT_OBSERVED', 'VACUUM_OBSERVED', 'ANALYZE_OBSERVED',
        'POSSIBLE_IN_BRACKET', 'ENVIRONMENT_ACTIVITY_ONLY', 'UNKNOWN_RELATION',
        'AMBIGUOUS_EVENT', 'PID_REUSED']], Field(min_length=1, max_length=8)]
    partial: bool


class Observation(Strict):
    schema_version: Literal['a42341.mock-window.v1'] = 'a42341.mock-window.v1'
    state: Literal['OBSERVER_OFF', 'MOCK_JOINED', 'STOP_TIMEOUT']
    planned_ticks: Literal[3] = 3
    ticks: Annotated[list[Tick], Field(max_length=3)]
    overflow: Counter
    joined: bool
    worker_started_ns: Counter | None
    worker_finished_ns: Positive | None
    lifecycle: Annotated[list[Literal['INIT', 'RUNNING', 'STOP_REQUESTED', 'JOINED', 'RECEIPT']],
                         Field(max_length=5)]
    stop_wall_ms: Annotated[float, Field(ge=0, le=2000)]
    source: Literal['MOCK_CONTRACT_ONLY'] = 'MOCK_CONTRACT_ONLY'


class GCEvent(Strict):
    started_ns: Counter
    finished_ns: Positive
    generation: Annotated[int, Field(strict=True, ge=0, le=2)]
    collected: Counter
    uncollectable: Counter
    label: Literal['MOCK_NATURAL_GC_EVENT'] = 'MOCK_NATURAL_GC_EVENT'


def compare_environment(before, after, expected):
    require(before == after == environment(expected), 'A42341_ENVIRONMENT_DRIFT')
    require(set(before.statistics) == set(TABLES), 'A42341_ENVIRONMENT_DRIFT')


def backend_cpu(resources: Resources, prepared, expected):
    before, after = resources.backend_before, resources.backend_after
    require(resources.backend_status == 'MOCK_AVAILABLE' and before is not None
        and after is not None, 'A42341_METRIC_UNAVAILABLE')
    for name in ('container_sha256', 'pid', 'backend_start', 'process_start_ticks', 'clock_ticks'):
        require(getattr(before, name) == getattr(after, name), 'A42341_ENVIRONMENT_DRIFT')
    require(before.container_sha256 == expected.fixture_sha256
        and before.pid == prepared.backend_pid and before.backend_start == prepared.backend_start
        and before.process_start_ticks == 10000 + prepared.block and before.clock_ticks == 100,
        'A42341_ENVIRONMENT_DRIFT')
    require(before.observed_ns < after.observed_ns
        and (after.observed_ns - before.observed_ns) / 1e6 == resources.process_elapsed_ms,
        'A42341_CLOCK_DRIFT')
    value = (Decimal(str(after.user_system_cpu_seconds))
             - Decimal(str(before.user_system_cpu_seconds)))
    require(value > 0, 'A42341_METRIC_UNAVAILABLE')
    return value


def check_observer(value: Observation, mode, started, finished):
    if mode == 'OFF':
        require(value.state == 'OBSERVER_OFF' and not value.ticks and value.overflow == 0
            and value.joined and value.worker_started_ns is None
            and value.worker_finished_ns is None and not value.lifecycle, 'A42341_OBSERVER_INVALID')
        return
    require(value.state == 'MOCK_JOINED' and value.joined and value.overflow == 0
        and len(value.ticks) == 3
        and value.lifecycle == ['INIT', 'RUNNING', 'STOP_REQUESTED', 'JOINED', 'RECEIPT']
        and value.worker_started_ns is not None and value.worker_finished_ns is not None
        and value.worker_started_ns < started < finished < value.worker_finished_ns,
        'A42341_OBSERVER_INVALID')
    for i, tick in enumerate(value.ticks):
        require(tick.sequence == i and not tick.partial and tick.event_codes == ['NOT_OBSERVED']
            and tick.finished_ns > tick.started_ns
            and tick.wall_ms == (tick.finished_ns - tick.started_ns) / 1e6
            and tick.wall_ms <= 25 and all(v <= 100 for v in tick.sql_wall_ms)
            and sum(tick.sql_wall_ms) <= tick.wall_ms, 'A42341_OBSERVER_INVALID')
        if i:
            require(200_000_000 <= tick.started_ns - value.ticks[i - 1].started_ns
                    <= 500_000_000, 'A42341_CLOCK_DRIFT')
    require(any(t.finished_ns < started for t in value.ticks)
        and any(t.started_ns > finished for t in value.ticks), 'A42341_BRACKET_UNCOVERED')
