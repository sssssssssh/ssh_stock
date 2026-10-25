"""No /proc, clock or GC collection: validate mock resource scopes and report limitations."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from scripts.a4235_calibration_adapter_contract import Hash, Strict, digest
from scripts.a4235_resource_bridge import Metric
from scripts.a4236_g1_harness_contract import Counter, Fault, Positive, checked, require


class CpuPoint(Strict):
    backend_pid: Positive
    reverse_backend_pid: Positive
    mapped_proc_pid: Positive
    backend_start_sha256: Hash
    proc_start_ticks: Positive
    namespace_sha256: Hash
    pg_namespace_sha256: Hash
    container_sha256: Hash
    clock_domain_sha256: Hash
    mapping_reference_sha256: Hash
    clock_ticks: Positive
    observed_ns: Positive
    user_ticks: Counter
    system_ticks: Counter
    readable: Literal[True] = True
    evidence_kind: Literal["MOCK_ONLY"] = "MOCK_ONLY"
    source: Literal["MOCK_BACKEND_USER_SYSTEM_TICKS"] = "MOCK_BACKEND_USER_SYSTEM_TICKS"


def backend_cpu(before, after, expected, started_ns, finished_ns):
    unavailable = dict(
        availability="METRIC_UNAVAILABLE",
        mock_cpu_seconds=None,
        source="MOCK_BACKEND_USER_SYSTEM_TICKS",
        unit="seconds",
        scope="SAME_BACKEND_USER_PLUS_SYSTEM_INTERVAL",
        evidence_kind="MOCK_ONLY",
    )
    try:
        before, after, expected = [checked(CpuPoint, p) for p in (before, after, expected)]
        identity_fields = set(CpuPoint.model_fields) - {"observed_ns", "user_ticks", "system_ticks"}
        require(
            all(
                getattr(before, n) == getattr(after, n) == getattr(expected, n)
                for n in identity_fields
            )
            and before.backend_pid == before.reverse_backend_pid,
            "A4236_PROCESS_IDENTITY_DRIFT",
        )
        require(
            before.observed_ns == started_ns < finished_ns == after.observed_ns
            and after.user_ticks >= before.user_ticks
            and after.system_ticks >= before.system_ticks,
            "A4236_CPU_INTERVAL_INVALID",
        )
        ticks = after.user_ticks + after.system_ticks - before.user_ticks - before.system_ticks
        require(ticks > 0, "A4236_CPU_UNAVAILABLE")
        return dict(
            unavailable,
            mock_cpu_seconds=str(Decimal(ticks) / Decimal(before.clock_ticks)),
            reason="PHYSICAL_NOT_PROVEN",
            interval=[started_ns, finished_ns],
            identity_sha256=digest({k: getattr(before, k) for k in identity_fields}),
        )
    except Exception as error:
        code = error.code if isinstance(error, Fault) else "A4236_CPU_UNAVAILABLE"
        return dict(unavailable, reason=code)


class ResourceSet(Strict):
    metrics: Annotated[tuple[Metric, ...], Field(min_length=5, max_length=5)]
    process_started_ns: Positive
    process_finished_ns: Positive
    lifetime_started_ns: Positive
    worker_started_ns: Positive | None
    worker_finished_ns: Positive | None
    joined: bool
    identity_sha256: Hash
    gc_enabled_before: Literal[True] = True
    gc_enabled_after: Literal[True] = True
    gc_thresholds_before: tuple[Positive, Positive, Positive]
    gc_thresholds_after: tuple[Positive, Positive, Positive]


def validate_resources(value):
    value = checked(ResourceSet, value)
    start, end = value.process_started_ns, value.process_finished_ns
    require(
        value.lifetime_started_ns <= start < end
        and value.gc_thresholds_before == value.gc_thresholds_after,
        "A4236_RESOURCE_SCOPE_INVALID",
    )
    definitions = dict(
        PROCESS_CPU=("MOCK_PROCESS_TIME", "ns"),
        ENTIRE_OBSERVER_THREAD_CPU=("MOCK_THREAD_TIME", "ns"),
        WORKER_ELAPSED=("MOCK_MONOTONIC", "ns"),
        PROCESS_LIFETIME_RSS_HIGH_WATER=("MOCK_RUSAGE", "bytes"),
        NATURAL_GC_EVENT=("MOCK_GC_CALLBACK", "ns"),
    )
    require({m.scope for m in value.metrics} == set(definitions), "A4236_RESOURCE_SCOPE_INVALID")
    if value.joined:
        require(
            value.worker_started_ns is not None
            and value.worker_finished_ns is not None
            and start <= value.worker_started_ns < value.worker_finished_ns <= end,
            "A4236_WORKER_LIFECYCLE_INVALID",
        )
    else:
        require(value.worker_finished_ns is None, "A4236_WORKER_LIFECYCLE_INVALID")
    for m in value.metrics:
        require(
            (m.source, m.unit) == definitions[m.scope]
            and m.identity_sha256 == value.identity_sha256
            and m.started_ns < m.finished_ns,
            "A4236_RESOURCE_SCOPE_INVALID",
        )
        if m.scope in ("ENTIRE_OBSERVER_THREAD_CPU", "WORKER_ELAPSED"):
            if not value.joined:
                require(
                    m.value is None and m.availability == "METRIC_UNAVAILABLE",
                    "A4236_UNJOINED_CPU_UNKNOWN",
                )
                require(
                    start <= m.started_ns < m.finished_ns <= end, "A4236_RESOURCE_SCOPE_INVALID"
                )
                continue
            require(
                (m.started_ns, m.finished_ns)
                == (value.worker_started_ns, value.worker_finished_ns),
                "A4236_RESOURCE_SCOPE_INVALID",
            )
        elif m.scope == "PROCESS_LIFETIME_RSS_HIGH_WATER":
            require(
                (m.started_ns, m.finished_ns) == (value.lifetime_started_ns, end),
                "A4236_RESOURCE_SCOPE_INVALID",
            )
        elif m.scope == "PROCESS_CPU":
            require((m.started_ns, m.finished_ns) == (start, end), "A4236_RESOURCE_SCOPE_INVALID")
        else:
            require(start <= m.started_ns < m.finished_ns <= end, "A4236_RESOURCE_SCOPE_INVALID")
        require(
            (m.availability == "METRIC_UNAVAILABLE" and m.value is None)
            or (m.availability == "MOCK_ONLY" and m.value is not None and m.value > 0),
            "A4236_RESOURCE_UNAVAILABLE",
        )
        if m.value is not None and m.scope == "WORKER_ELAPSED":
            require(m.value == m.finished_ns - m.started_ns, "A4236_RESOURCE_SCOPE_INVALID")
        if m.value is not None and m.scope in ("ENTIRE_OBSERVER_THREAD_CPU", "NATURAL_GC_EVENT"):
            require(m.value <= m.finished_ns - m.started_ns, "A4236_RESOURCE_SCOPE_INVALID")
    return dict(
        evidence_kind="MOCK_ONLY",
        physical_availability="METRIC_UNAVAILABLE",
        worker_cpu_denominator="PROCESS_ELAPSED",
        gc_subtracted=False,
    )


class Environment(Strict):
    relation_oids: Annotated[tuple[Positive, ...], Field(min_length=4, max_length=4)]
    statistics_sha256: Hash
    indexes_sha256: Hash
    columns_sha256: Hash
    settings_sha256: Hash
    mvcc_sha256: Hash
    fresh_plan_sha256: Hash | None
    cached_plan_structure: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"
    maintenance: Literal["NOT_OBSERVED", "OBSERVED", "UNKNOWN"]
    evidence_kind: Literal["MOCK_ONLY"] = "MOCK_ONLY"


def environment(before, after):
    before, after = checked(Environment, before), checked(Environment, after)
    require(
        before == after
        and len(set(before.relation_oids)) == 4
        and before.maintenance == "NOT_OBSERVED",
        "A4236_ENVIRONMENT_DRIFT",
    )
    return dict(
        status="METHOD_UNVERIFIED",
        mock_descriptors_equal=True,
        absence_of_maintenance="NOT_PROVEN",
        cached_plan_structure="NOT_VERIFIED",
        mvcc_freezes_planner_statistics=False,
    )
