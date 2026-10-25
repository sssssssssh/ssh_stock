"""AT16–24: closed execute routing, all-SQL budget, driver/session evidence separation."""

import pytest

from scripts import a4236_mock as m
from scripts.a4236_g1_harness_contract import FakeClock, Fault
from scripts.a4236_g1_probe import (
    ALLOWLIST_SHA,
    FakeConnection,
    Reply,
    SqlBudget,
    request,
    run_mock_requests,
)
from scripts.a4236_session_prepared import compare, sanitize_projection


def test_AT16_AT17_exact_16_includes_projection_and_never_real():
    connection = FakeConnection(FakeClock())
    requests = [request("I4")] * 6 + [request("I8")] * 6 + [request("PROJECTION")] * 4
    result = run_mock_requests(connection, requests)
    assert result["completed"] and result["mock_sql_count"] == len(connection.calls) == 16
    assert sum(c["template"] == "PROJECTION" for c in connection.calls) == 4
    assert result["real_sql_executed"] == 0 and result["capability_status"] == "PARTIAL"
    assert result["termination_status"] == "MODEL_ONLY_NOT_PROVEN"
    assert result["cached_plan_structure"] == "CACHED_PLAN_STRUCTURE_NOT_VERIFIED"


@pytest.mark.parametrize(
    "field,bad",
    [
        ("driver_sql_sha256", "f" * 64),
        ("protocol_sql_sha256", "f" * 64),
        ("parameter_count", 0),
        ("parameter_oids", (20,)),
        ("stage", "C0_C1"),
        ("template", "EXPLAIN_EXECUTE"),
        ("prepare", True),
        ("sql", "SELECT * FROM SECRET_BUSINESS_TABLE"),
    ],
)
def test_AT16_sql_bytes_oids_force_prepare_and_extra_sql_never_route(field, bad):
    conn = FakeConnection(FakeClock())
    value = request("I4").model_copy(update={field: bad})
    result = run_mock_requests(conn, [value, request("I4")])
    assert result["first_error"].startswith("A4236_") and not conn.calls
    assert result["mock_sql_count"] == 0


def test_AT16_allowlist_must_match_independent_harness():
    conn = FakeConnection(FakeClock())
    result = run_mock_requests(conn, [request("I4")], "f" * 64)
    assert result["first_error"] == "A4236_SQL_NOT_ALLOWLISTED" and not conn.calls


def test_AT17_seventeenth_refuses_before_execute_and_budget_never_refunds():
    conn = FakeConnection(FakeClock())
    budget = SqlBudget(conn.clock)
    for _ in range(16):
        conn.execute(request("PROJECTION"), budget, ALLOWLIST_SHA)
    with pytest.raises(Fault, match="SQL_BUDGET_EXCEEDED"):
        conn.execute(request("I4"), budget)
    assert len(conn.calls) == budget.count == 16 and budget.stopped
    with pytest.raises(Fault, match="PROBE_ALREADY_STOPPED"):
        conn.execute(request("I4"), budget)
    assert len(conn.calls) == 16


def test_AT17_injected_budget_cannot_raise_limit_or_approve_execution():
    conn = FakeConnection(FakeClock())
    budget = SqlBudget(conn.clock)
    budget.budget = budget.budget.model_copy(update={"max_sql": 17, "approved": True})
    with pytest.raises(Fault, match="SCHEMA_INVALID"):
        conn.execute(request("I4"), budget)
    assert not conn.calls and budget.stopped and budget.count == 0


@pytest.mark.parametrize(
    "reply",
    [
        Reply(wall_ms=101),
        Reply(rows=9),
        Reply(overhead_ms=100),
        Reply(terminable=False),
        Reply(failure_code="A4236_SQL_TIMEOUT"),
        Reply(server_timeout_ms=101),
    ],
)
def test_AT17_AT18_timeout_rows_termination_and_failures_stop_no_retry(reply):
    conn = FakeConnection(FakeClock(), replies=(reply, Reply()))
    result = run_mock_requests(conn, [request("I4")] * 2)
    assert result["first_error"].startswith("A4236_") and not result["completed"]
    assert len(conn.calls) == result["mock_sql_count"] == 1
    assert conn.calls[0]["failure_code"] == result["first_error"]
    if not reply.terminable:
        assert result["first_error"] == "A4236_TERMINATION_NOT_PROVEN"


@pytest.mark.parametrize("timeout,readonly", [(0, True), (101, True), (100, False)])
def test_AT17_server_deadline_and_read_only_required_before_sql(timeout, readonly):
    conn = FakeConnection(FakeClock(), statement_timeout_ms=timeout, read_only=readonly)
    result = run_mock_requests(conn, [request("I4")])
    assert result["first_error"] == "A4236_SERVER_TIMEOUT_UNPROVEN"
    assert not conn.calls and result["mock_sql_count"] == 0


def test_AT17_total_sql_window_includes_gaps_and_boundary_is_inclusive():
    conn = FakeConnection(FakeClock(), replies=tuple(Reply(wall_ms=100) for _ in range(16)))
    budget = SqlBudget(conn.clock)
    for _ in range(10):
        conn.execute(request("I4"), budget)
        conn.clock.advance_ms(100)
    assert conn.clock.ns - budget.started_ns == 2_000_000_000
    with pytest.raises(Fault, match="SQL_BUDGET_EXCEEDED"):
        conn.execute(request("I4"), budget)
    assert len(conn.calls) == 10


def test_AT17_exact_100ms_and_eight_rows_allowed():
    conn = FakeConnection(FakeClock(), replies=(Reply(wall_ms=100, rows=8),))
    assert run_mock_requests(conn, [request("PROJECTION")])["completed"] is True


def test_AT18_unknown_adapter_never_calls_real_execute():
    class Forbidden:
        def execute(self, *a, **kw):
            pytest.fail("no real adapter should be touched")

    with pytest.raises(Fault, match="REAL_ADAPTER_NOT_ALLOWED"):
        run_mock_requests(Forbidden(), [request("I4")])


def test_AT19_pinned_psycopg_prepare_manager_sixth_is_only_driver_model():
    from importlib.metadata import version
    from types import SimpleNamespace

    from psycopg._preparing import Prepare, PrepareManager

    assert version("psycopg") == "3.3.4"
    manager = PrepareManager()
    assert manager.prepare_threshold == 5 and manager.prepared_max == 100
    query = SimpleNamespace(query=b"SELECT $1::integer", types=(23,))
    choices = []
    for _ in range(6):
        state, name = manager.get(query)
        choices.append(state)
        manager.maybe_add_to_cache(query, state, name)
    assert choices == [Prepare.NO] * 5 + [Prepare.SHOULD]
    # No libpq send/connection/maintenance, server row or stable cached plan was inferred.


def test_AT20_AT23_good_same_session_is_not_cached_plan_or_c0_c1_proof():
    session, before, after = m.prepared()
    result = compare(before, after, session, "I4")
    assert result["prepared_capability"] == "DRIVER_MODEL_ONLY"
    assert result["server_same_session"] == "MOCK_VISIBLE"
    assert result["cached_plan_structure"] == "CACHED_PLAN_STRUCTURE_NOT_VERIFIED"
    assert not result["prepared_stable"] and result["c0_c1_status"] == "NOT_PROVEN"
    missing = after.model_copy(update={"row": None})
    assert compare(before, missing, session, "I4")["server_same_session"] == "PARTIAL"


@pytest.mark.parametrize(
    "field,bad",
    [
        ("backend_pid", 501),
        ("backend_start_sha256", "f" * 64),
        ("connection_generation", 2),
        ("connection_sha256", "f" * 64),
        ("transaction_pool", True),
        ("pool_checkout_generation", 1),
        ("prepare_threshold", 0),
        ("prepared_max", 101),
        ("driver_version", "3.3.7"),
    ],
)
def test_AT21_session_reconnect_eviction_and_pool_drift(field, bad):
    session, before, after = m.prepared()
    after = after.model_copy(update={"session": session.model_copy(update={field: bad})})
    with pytest.raises(Fault):
        compare(before, after, session, "I4")


@pytest.mark.parametrize(
    "field,bad",
    [
        ("cache_key_sha256", "f" * 64),
        ("driver_sql_sha256", "f" * 64),
        ("protocol_sql_sha256", "f" * 64),
        ("parameter_oids", (20,)),
        ("evicted", True),
        ("driver_executions", 4),
        ("projection_executions", 0),
        ("observed_ns", 500),
        ("target", "C0_C1_READY"),
    ],
)
def test_AT21_AT24_key_counter_identity_and_target_drift(field, bad):
    session, before, after = m.prepared()
    with pytest.raises(Fault):
        compare(before, after.model_copy(update={field: bad}), session, "I4")


@pytest.mark.parametrize(
    "change",
    [
        "rollback",
        "unexpected_increment",
        "mode_switch",
        "from_sql",
        "oid",
        "renamed",
        "missing",
        "projection_pollution",
    ],
)
def test_AT22_counts_and_projection_pollution_never_define_stability(change):
    session, _, first = m.prepared()
    row = first.row
    later = first.model_copy(
        update={
            "observed_ns": 3000,
            "driver_executions": 7,
            "projection_executions": 3,
            "row": row.model_copy(update={"custom_plans": 2}),
        }
    )
    updates = {
        "rollback": {"custom_plans": 0},
        "unexpected_increment": {"custom_plans": 4},
        "mode_switch": {"generic_plans": 1, "custom_plans": 1},
        "from_sql": {"from_sql": True},
        "oid": {"parameter_oids": (20,)},
        "renamed": {"identifier_sha256": "f" * 64},
    }
    if change == "missing":
        later = later.model_copy(update={"row": None})
    elif change == "projection_pollution":
        later = later.model_copy(
            update={"driver_executions": 6, "row": row.model_copy(update={"custom_plans": 2})}
        )
    else:
        later = later.model_copy(update={"row": row.model_copy(update=updates[change])})
    with pytest.raises(Fault):
        compare(first, later, session, "I4")


def test_AT20_projection_names_are_hashed_no_statement_text_or_parameters():
    rows = sanitize_projection([("PRIVATE_PREPARED_NAME", [23], False, 0, 1)])
    assert len(rows[0].identifier_sha256) == 64
    assert "PRIVATE_PREPARED_NAME" not in str(rows)
    assert "statement" not in type(rows[0]).model_fields


def test_AT22_reverse_generic_to_custom_mode_switch_is_drift_too():
    session, _, first = m.prepared()
    first = first.model_copy(
        update={"row": first.row.model_copy(update={"generic_plans": 1, "custom_plans": 0})}
    )
    later = first.model_copy(
        update={
            "observed_ns": 3000,
            "driver_executions": 7,
            "row": first.row.model_copy(update={"custom_plans": 1}),
        }
    )
    with pytest.raises(Fault, match="PLAN_MODE_DRIFT"):
        compare(first, later, session, "I4")


@pytest.mark.parametrize(
    "rows",
    [
        [("same", [23], False, 0, 1)] * 2,
        [("bad", [23], True, 0, 1)],
        [("bad", [23], False, -1, 1)],
        [("bad", [23], False, 0, 1, "SECRET_SQL")],
        [("x", [23], False, 0, 1)] * 9,
    ],
)
def test_AT20_projection_shape_and_max_rows_refuse(rows):
    with pytest.raises(Fault):
        sanitize_projection(rows)
