"""AT25–30: resource identity, scope, missingness and observer lifecycle contracts."""

import pytest

from scripts import a4236_mock as m
from scripts.a4236_g1_harness_contract import Fault
from scripts.a4236_observer_feasibility import review_window
from scripts.a4236_resource_probe import backend_cpu, environment, validate_resources


def test_AT25_valid_reciprocal_mapping_is_still_mock_not_real_cpu():
    a, b = m.cpu()
    result = backend_cpu(a, b, a, a.observed_ns, b.observed_ns)
    assert result["mock_cpu_seconds"] == "0.01"
    assert result["availability"] == "METRIC_UNAVAILABLE"
    assert result["reason"] == "PHYSICAL_NOT_PROVEN"
    assert result["scope"] == "SAME_BACKEND_USER_PLUS_SYSTEM_INTERVAL"


@pytest.mark.parametrize(
    "field,bad",
    [
        ("backend_pid", 501),
        ("reverse_backend_pid", 501),
        ("mapped_proc_pid", 1501),
        ("backend_start_sha256", "f" * 64),
        ("proc_start_ticks", 11),
        ("namespace_sha256", "f" * 64),
        ("pg_namespace_sha256", "f" * 64),
        ("container_sha256", "f" * 64),
        ("clock_domain_sha256", "f" * 64),
        ("mapping_reference_sha256", "f" * 64),
        ("clock_ticks", 101),
        ("observed_ns", 0),
        ("user_ticks", 999),
        ("system_ticks", 99),
        ("readable", False),
        ("source", "SQL_WALL"),
        ("user_ticks", None),
    ],
)
def test_AT25_AT26_cpu_identity_reuse_mapping_time_permission_and_source(field, bad):
    a, b = m.cpu()
    result = backend_cpu(a, b.model_copy(update={field: bad}), a, a.observed_ns, b.observed_ns)
    assert result["availability"] == "METRIC_UNAVAILABLE"
    assert result["mock_cpu_seconds"] is None and result["reason"].startswith("A4236_")


def test_AT26_no_ticks_or_zero_time_denominator_is_unknown_not_zero():
    a, b = m.cpu()
    b = b.model_copy(update={"user_ticks": a.user_ticks})
    for start, end in [(a.observed_ns, b.observed_ns), (b.observed_ns, b.observed_ns)]:
        assert backend_cpu(a, b, a, start, end)["mock_cpu_seconds"] is None


def test_AT27_scopes_explicit_and_unjoined_entire_worker_unknown():
    value = m.resources()
    result = validate_resources(value)
    assert result["worker_cpu_denominator"] == "PROCESS_ELAPSED"
    assert not result["gc_subtracted"] and result["physical_availability"] == "METRIC_UNAVAILABLE"
    metrics = tuple(
        x.model_copy(update={"value": None, "availability": "METRIC_UNAVAILABLE"})
        if x.scope in ("ENTIRE_OBSERVER_THREAD_CPU", "WORKER_ELAPSED")
        else x
        for x in value.metrics
    )
    validate_resources(
        value.model_copy(update={"joined": False, "worker_finished_ns": None, "metrics": metrics})
    )
    with pytest.raises(Fault, match="UNJOINED_CPU_UNKNOWN"):
        validate_resources(value.model_copy(update={"joined": False, "worker_finished_ns": None}))


@pytest.mark.parametrize(
    "index,update",
    [
        (0, {"source": "SQL_WALL"}),
        (0, {"value": 0}),
        (0, {"availability": "METRIC_UNAVAILABLE", "value": 1}),
        (0, {"identity_sha256": "f" * 64}),
        (0, {"started_ns": 1_100_000_000}),
        (1, {"started_ns": 1_200_000_000}),
        (1, {"value": 900_000_000}),
        (2, {"value": 1}),
        (3, {"started_ns": 1_000_000_000}),
        (3, {"scope": "PER_SQL_RSS_INCREMENT"}),
        (3, {"unit": "ns"}),
        (4, {"finished_ns": 2_100_000_000}),
        (4, {"value": 11_000_000}),
    ],
)
def test_AT27_cpu_rss_gc_missingness_and_interval_mixing_refused(index, update):
    value = m.resources()
    metrics = list(value.metrics)
    metrics[index] = metrics[index].model_copy(update=update)
    with pytest.raises(Fault):
        validate_resources(value.model_copy(update={"metrics": tuple(metrics)}))


@pytest.mark.parametrize(
    "update",
    [
        {"gc_enabled_after": False},
        {"gc_thresholds_after": (701, 10, 10)},
        {"worker_finished_ns": 2_100_000_000},
        {"lifetime_started_ns": 1_500_000_000},
        {"process_finished_ns": 500_000_000},
    ],
)
def test_AT27_gc_configuration_and_lifecycle_frozen(update):
    with pytest.raises(Fault):
        validate_resources(m.resources().model_copy(update=update))


def test_AT28_equal_descriptors_are_not_independent_plan_or_maintenance_absence():
    result = environment(m.environment(), m.environment())
    assert result["status"] == "METHOD_UNVERIFIED"
    assert result["absence_of_maintenance"] == "NOT_PROVEN"
    assert result["cached_plan_structure"] == "NOT_VERIFIED"
    assert not result["mvcc_freezes_planner_statistics"]


@pytest.mark.parametrize(
    "field,bad",
    [
        ("relation_oids", (100, 100, 102, 103)),
        ("statistics_sha256", "f" * 64),
        ("indexes_sha256", "f" * 64),
        ("columns_sha256", "f" * 64),
        ("settings_sha256", "f" * 64),
        ("mvcc_sha256", "f" * 64),
        ("fresh_plan_sha256", None),
        ("maintenance", "UNKNOWN"),
        ("maintenance", "OBSERVED"),
        ("cached_plan_structure", "VERIFIED"),
    ],
)
def test_AT28_descriptor_drift_unknown_maintenance_or_plan_never_green(field, bad):
    value = m.environment()
    with pytest.raises(Fault):
        environment(value, value.model_copy(update={field: bad}))


def test_AT29_valid_three_ticks_only_proves_model_and_separates_costs():
    result = review_window(m.window())
    assert result["status"] == "MODEL_ONLY_NOT_PROVEN"
    assert result["physical_status"] == "NOT_RUN" and not result["gc_subtracted"]
    assert result["worker_cpu_denominator_ms"] == 503
    assert result["costs_separate"] == (
        "setup",
        "polling",
        "stop",
        "serialization",
        "artifact_io",
        "boundary_wait",
    )


@pytest.mark.parametrize("start,end", [(240, 249), (0, 260), (240, 502)])
def test_AT29_short_query_missing_during_before_after_is_not_padded(start, end):
    with pytest.raises(Fault):
        review_window(
            m.window().model_copy(update={"lookup_started_ms": start, "lookup_finished_ms": end})
        )


def test_AT30_join_timeout_sticky_partial_prefix_and_known_cpu_forbidden():
    value = m.window()
    ticks = value.ticks[:1] + (value.ticks[1].model_copy(update={"partial": True}),)
    failed = value.model_copy(
        update={
            "state": "STOP_TIMEOUT",
            "joined": False,
            "worker_finished_ms": None,
            "thread_cpu_ns": None,
            "worker_elapsed_ms": None,
            "cleanup_complete": False,
            "first_error": "A4236_OBSERVER_INVALID",
            "lifecycle": ("INIT", "RUNNING", "STOP_REQUESTED"),
            "ticks": ticks,
        }
    )
    result = review_window(failed)
    assert result["first_error"] == "A4236_OBSERVER_INVALID"
    assert result["cleanup_codes"] == ["A4236_JOIN_TIMEOUT"] and result["worker_cpu"] is None
    for update in [
        {"joined": True},
        {"thread_cpu_ns": 0},
        {"cleanup_complete": True},
        {"lifecycle": ("INIT", "RUNNING", "STOP_REQUESTED", "JOINED")},
    ]:
        with pytest.raises(Fault):
            review_window(failed.model_copy(update=update))


def test_AT30_legitimate_joined_but_invalid_last_payload_is_incomplete():
    value = m.window()
    value = value.model_copy(
        update={
            "first_error": "A4236_OBSERVER_INVALID",
            "ticks": value.ticks[:2] + (value.ticks[2].model_copy(update={"partial": True}),),
        }
    )
    assert review_window(value)["status"] == "INCOMPLETE"


@pytest.mark.parametrize(
    "update",
    [
        {"planned_ticks": 1},
        {"planned_ticks": 9},
        {"stop_ms": 2001},
        {"thread_cpu_ns": None},
        {"worker_elapsed_ms": None},
        {"thread_cpu_ns": 504_000_000},
        {"worker_elapsed_ms": 1},
        {"worker_finished_ms": 250},
        {"lifecycle": ("INIT", "RUNNING", "JOINED", "RECEIPT")},
        {"state": "STOP_TIMEOUT"},
        {"cleanup_complete": False},
        {"first_error": "A4236_JOIN_TIMEOUT"},
    ],
)
def test_AT30_lifecycle_stop_whole_thread_and_join_contradictions(update):
    with pytest.raises(Fault):
        review_window(m.window().model_copy(update=update))


@pytest.mark.parametrize(
    "update",
    [
        {"sequence": 9},
        {"started_ms": 251},
        {"finished_ms": 276},
        {"sql_ms": (101,)},
        {"sql_ms": (2,)},
        {"partial": True},
    ],
)
def test_AT30_tick_spacing_totalwall_sql_and_partial_prefix(update):
    value = m.window()
    ticks = list(value.ticks)
    ticks[1] = ticks[1].model_copy(update=update)
    with pytest.raises(Fault):
        review_window(value.model_copy(update={"ticks": tuple(ticks)}))


def test_AT30_off_has_no_worker_or_ticks_no_hidden_live_operations():
    off = m.window().model_copy(
        update={
            "mode": "OFF",
            "state": "OBSERVER_OFF",
            "ticks": (),
            "worker_started_ms": None,
            "worker_finished_ms": None,
            "worker_elapsed_ms": None,
            "thread_cpu_ns": None,
            "lifecycle": (),
        }
    )
    assert review_window(off)["status"] == "OFF_MODEL_ONLY"
    for update in [
        {"ticks": m.window().ticks},
        {"worker_started_ms": 0},
        {"lifecycle": ("INIT",)},
        {"thread_cpu_ns": 0},
        {"joined": False},
    ]:
        with pytest.raises(Fault):
            review_window(off.model_copy(update=update))
