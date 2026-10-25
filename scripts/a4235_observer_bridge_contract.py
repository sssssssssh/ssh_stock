"""Mock long-window v3 contract, not an adapter to the existing three-tick observer."""

from typing import Annotated, Literal

from pydantic import Field

from scripts.a4235_calibration_adapter_contract import (
    Counter,
    Hash,
    Positive,
    Strict,
    require,
)


class Tick(Strict):
    sequence: Counter
    started_ns: Positive
    finished_ns: Positive
    sql_ns: Annotated[list[Positive], Field(min_length=1, max_length=5)]
    complete: bool


class Window(Strict):
    schema_version: Literal['a4235.mock-long-window.v3'] = 'a4235.mock-long-window.v3'
    evidence_kind: Literal['MOCK_ONLY'] = 'MOCK_ONLY'
    mode: Literal['OFF', 'ON']
    identity_sha256: Hash
    planned_ticks: Annotated[int, Field(strict=True, ge=2, le=8)]
    poll_ms: Literal[250] = 250
    lookup_started_ns: Positive
    lookup_finished_ns: Positive
    observed_until_ns: Positive
    ticks: Annotated[list[Tick], Field(max_length=8)]
    state: Literal['OBSERVER_OFF', 'JOINED', 'STOP_TIMEOUT']
    joined: bool
    lifecycle: Annotated[list[Literal['INIT', 'RUNNING', 'STOP_REQUESTED', 'JOINED', 'RECEIPT']],
                         Field(max_length=5)]
    worker_started_ns: Positive | None
    worker_finished_ns: Positive | None
    worker_cpu_ns: Positive | None
    stop_join_ns: Counter
    cleanup_complete: bool


def validate_window(value: Window) -> dict:
    value = Window.model_validate(value.model_dump())
    require(value.lookup_started_ns < value.lookup_finished_ns <= value.observed_until_ns,
            'A4235_CLOCK_INVALID')
    if value.mode == 'OFF':
        require(value.state == 'OBSERVER_OFF' and value.joined and not value.ticks
                and not value.lifecycle and value.worker_started_ns is None
                and value.worker_finished_ns is None and value.worker_cpu_ns is None
                and value.stop_join_ns == 0 and value.cleanup_complete,
                'A4235_OBSERVER_STATE_INVALID')
        return dict(status='MOCK_OFF_VALID', real_status='NOT_PROVEN')
    require(value.worker_started_ns is not None
            and value.worker_started_ns <= value.lookup_started_ns,
            'A4235_OBSERVER_STATE_INVALID')
    require(len(value.ticks) <= value.planned_ticks
            and all(t.complete for t in value.ticks[:-1]), 'A4235_TICK_INCOMPLETE')
    for i, tick in enumerate(value.ticks):
        require(tick.sequence == i and value.worker_started_ns <= tick.started_ns
                < tick.finished_ns <= value.observed_until_ns
                and tick.finished_ns - tick.started_ns <= 25_000_000
                and max(tick.sql_ns) <= 100_000_000
                and sum(tick.sql_ns) <= tick.finished_ns - tick.started_ns,
                'A4235_TICK_INVALID')
        if i:
            require(tick.started_ns - value.ticks[i - 1].started_ns == 250_000_000,
                    'A4235_POLL_DRIFT')
    if value.state == 'STOP_TIMEOUT':
        require(not value.joined and not value.cleanup_complete
                and value.worker_finished_ns is None and value.worker_cpu_ns is None
                and value.lifecycle == ['INIT', 'RUNNING', 'STOP_REQUESTED']
                and value.stop_join_ns == 2_000_000_000, 'A4235_OBSERVER_STATE_INVALID')
        return dict(status='MOCK_INCOMPLETE', real_status='NOT_PROVEN',
                    first_error='A4235_JOIN_TIMEOUT')
    require(value.state == 'JOINED' and value.joined and value.cleanup_complete
            and value.worker_finished_ns is not None and value.worker_cpu_ns is not None
            and value.lifecycle == ['INIT', 'RUNNING', 'STOP_REQUESTED', 'JOINED', 'RECEIPT']
            and value.lookup_finished_ns < value.worker_finished_ns <= value.observed_until_ns
            and value.worker_cpu_ns <= value.worker_finished_ns - value.worker_started_ns
            and value.stop_join_ns <= 2_000_000_000, 'A4235_OBSERVER_STATE_INVALID')
    require(len(value.ticks) == value.planned_ticks and all(t.complete for t in value.ticks),
            'A4235_TICK_INCOMPLETE')
    require(value.ticks[0].finished_ns <= value.lookup_started_ns
            and value.ticks[-1].started_ns >= value.lookup_finished_ns
            and value.ticks[-1].finished_ns <= value.worker_finished_ns
            and any(value.lookup_started_ns <= t.started_ns
                    < t.finished_ns <= value.lookup_finished_ns for t in value.ticks),
            'A4235_BRACKET_UNCOVERED')
    return dict(status='MOCK_LONG_WINDOW_VALID', real_status='NOT_PROVEN')
