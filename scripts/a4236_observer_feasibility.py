"""Pure long-window feasibility. No observer threads, sleeps or SQL are started."""

from typing import Annotated, Literal

from pydantic import Field

from scripts.a4235_calibration_adapter_contract import Strict
from scripts.a4236_g1_harness_contract import Counter, checked, require


class Tick(Strict):
    sequence: Counter
    started_ms: Counter
    finished_ms: Counter
    sql_ms: Annotated[tuple[Counter, ...], Field(max_length=5)]
    partial: bool = False


class Window(Strict):
    mode: Literal["ON", "OFF"]
    planned_ticks: Annotated[int, Field(strict=True, ge=2, le=8)]
    ticks: Annotated[tuple[Tick, ...], Field(max_length=8)]
    worker_started_ms: Counter | None
    worker_finished_ms: Counter | None
    thread_cpu_ns: Counter | None
    worker_elapsed_ms: Counter | None
    process_elapsed_ms: Counter
    lookup_started_ms: Counter
    lookup_finished_ms: Counter
    state: Literal["OBSERVER_OFF", "MOCK_JOINED", "STOP_TIMEOUT"]
    lifecycle: tuple[str, ...]
    joined: bool
    stop_ms: Counter
    cleanup_complete: bool
    first_error: Literal["A4236_JOIN_TIMEOUT", "A4236_OBSERVER_INVALID"] | None = None
    evidence_kind: Literal["MOCK_ONLY"] = "MOCK_ONLY"


def review_window(value):
    value = checked(Window, value)
    require(
        0 <= value.lookup_started_ms < value.lookup_finished_ms <= value.process_elapsed_ms
        and value.process_elapsed_ms > 0
        and value.stop_ms <= 2000,
        "A4236_OBSERVER_CONTRADICTION",
    )
    if value.mode == "OFF":
        require(
            value.state == "OBSERVER_OFF"
            and value.joined
            and not value.ticks
            and not value.lifecycle
            and value.worker_started_ms is None
            and value.worker_finished_ms is None
            and value.thread_cpu_ns is None
            and value.worker_elapsed_ms is None
            and value.first_error is None
            and value.cleanup_complete,
            "A4236_OBSERVER_CONTRADICTION",
        )
        return dict(status="OFF_MODEL_ONLY", physical_status="NOT_RUN")
    require(
        value.worker_started_ms is not None and value.worker_started_ms < value.lookup_started_ms,
        "A4236_OBSERVER_CONTRADICTION",
    )
    if value.joined:
        require(
            value.state == "MOCK_JOINED"
            and value.worker_finished_ms is not None
            and value.lookup_finished_ms < value.worker_finished_ms <= value.process_elapsed_ms
            and value.lifecycle == ("INIT", "RUNNING", "STOP_REQUESTED", "JOINED", "RECEIPT")
            and value.thread_cpu_ns is not None
            and value.worker_elapsed_ms is not None
            and value.worker_elapsed_ms == value.worker_finished_ms - value.worker_started_ms
            and value.thread_cpu_ns <= value.worker_elapsed_ms * 1_000_000
            and len(value.ticks) == value.planned_ticks
            and value.cleanup_complete
            and value.first_error != "A4236_JOIN_TIMEOUT",
            "A4236_OBSERVER_CONTRADICTION",
        )
    else:
        require(
            value.state == "STOP_TIMEOUT"
            and value.worker_finished_ms is None
            and value.lifecycle == ("INIT", "RUNNING", "STOP_REQUESTED")
            and value.thread_cpu_ns is None
            and value.worker_elapsed_ms is None
            and not value.cleanup_complete
            and value.first_error in ("A4236_JOIN_TIMEOUT", "A4236_OBSERVER_INVALID")
            and len(value.ticks) <= value.planned_ticks,
            "A4236_OBSERVER_CONTRADICTION",
        )
    for i, tick in enumerate(value.ticks):
        require(
            tick.sequence == i
            and value.worker_started_ms
            <= tick.started_ms
            < tick.finished_ms
            <= (value.worker_finished_ms if value.joined else value.process_elapsed_ms)
            and tick.finished_ms - tick.started_ms <= 25
            and all(t <= 100 for t in tick.sql_ms)
            and sum(tick.sql_ms) <= tick.finished_ms - tick.started_ms
            and (not tick.partial or i == len(value.ticks) - 1),
            "A4236_OBSERVER_CONTRADICTION",
        )
        if i:
            require(
                tick.started_ms - value.ticks[i - 1].started_ms == 250,
                "A4236_OBSERVER_CONTRADICTION",
            )
    if not value.joined:
        return dict(
            status="INCOMPLETE",
            first_error=value.first_error,
            cleanup_codes=["A4236_JOIN_TIMEOUT"],
            worker_cpu=None,
            physical_status="NOT_RUN",
        )
    require(
        any(t.finished_ms < value.lookup_started_ms for t in value.ticks)
        and any(
            value.lookup_started_ms <= t.started_ms and t.finished_ms <= value.lookup_finished_ms
            for t in value.ticks
        )
        and any(t.started_ms > value.lookup_finished_ms for t in value.ticks),
        "A4236_BRACKET_UNCOVERED",
    )
    if any(t.partial for t in value.ticks):
        require(value.first_error == "A4236_OBSERVER_INVALID", "A4236_OBSERVER_CONTRADICTION")
        return dict(status="INCOMPLETE", first_error=value.first_error, physical_status="NOT_RUN")
    require(value.first_error is None, "A4236_OBSERVER_CONTRADICTION")
    return dict(
        status="MODEL_ONLY_NOT_PROVEN",
        physical_status="NOT_RUN",
        whole_worker_cpu_ns=value.thread_cpu_ns,
        worker_cpu_denominator_ms=value.process_elapsed_ms,
        costs_separate=(
            "setup",
            "polling",
            "stop",
            "serialization",
            "artifact_io",
            "boundary_wait",
        ),
        gc_subtracted=False,
    )
