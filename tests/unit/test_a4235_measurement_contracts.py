"""AT11-24: MOCK detectors, never real SQL, CPU collection, threads or GC changes."""

import hashlib
from types import SimpleNamespace

import pytest
from psycopg._preparing import Prepare, PrepareManager

from scripts.a4235_calibration_adapter_contract import Fault, digest
from scripts.a4235_environment_probe import TABLES, Environment, Relation
from scripts.a4235_environment_probe import compare as environment_compare
from scripts.a4235_observer_bridge_contract import Tick, Window, validate_window
from scripts.a4235_prepared_probe import (
    SYNTHETIC_SQL,
    FakeCursor,
    PreparedRow,
    PreparedSnapshot,
    Session,
    compare,
    project_mock,
    validate_snapshot,
)
from scripts.a4235_resource_bridge import (
    Metric,
    ProcSnapshot,
    Resources,
    backend_delta,
    validate_resources,
)

H = 'a' * 64


@pytest.fixture
def session():
    return Session(backend_pid=1234, backend_start_sha256=H, connection_generation=1,
                   process_sha256=H, connection_sha256=H)


@pytest.fixture
def prepared(session):
    sql = hashlib.sha256(SYNTHETIC_SQL[0]).hexdigest()
    row = PreparedRow(identifier_sha256=H, sql_sha256=sql, oid_digest=digest([23]),
                      from_sql=False, generic_plans=0, custom_plans=1)
    return PreparedSnapshot(session=session, sql_sha256=sql, parameter_oids=[23],
                            cache_key_sha256=digest([H, sql, [23]]), executions=6,
                            mode='CUSTOM', row=row, projection_wall_ns=1000)


def test_AT11_exact_pinned_driver_threshold_sql_oid_and_new_manager():
    import psycopg
    assert psycopg.__version__ == '3.3.4'
    manager = PrepareManager()
    query = SimpleNamespace(query=SYNTHETIC_SQL[0], types=(23,))
    states = []
    for _ in range(8):
        state, name = manager.get(query)
        states.append(state)
        manager.maybe_add_to_cache(query, state, name)
    assert states == [Prepare.NO] * 5 + [Prepare.SHOULD, Prepare.YES, Prepare.YES]
    assert manager.prepare_threshold == 5 and manager.prepared_max == 100
    assert PrepareManager().get(query)[0] == Prepare.NO
    for different in (SimpleNamespace(query=SYNTHETIC_SQL[1], types=(23,)),
                      SimpleNamespace(query=SYNTHETIC_SQL[0], types=(20,))):
        assert manager.get(different)[0] == Prepare.NO


@pytest.mark.parametrize('executions', [0, 1, 4, 5, 6])
def test_AT11_AT15_AT16_threshold_is_only_driver_model(prepared, session, executions):
    item = prepared.model_copy(update=dict(executions=executions,
        row=prepared.row if executions == 6 else None,
        mode='CUSTOM' if executions == 6 else 'UNPREPARED'))
    assert validate_snapshot(item, session).executions == executions
    after = prepared.model_copy(update=dict(executions=7,
        row=prepared.row.model_copy(update={'custom_plans': 2})))
    result = compare(prepared, after, session)
    assert result.detector == 'DRIVER_MODEL_ONLY' and result.prepared_stable is False
    assert result.c0_c1_status == 'C0_C1_NOT_PROVEN'
    assert result.cached_plan_structure == 'CACHED_PLAN_STRUCTURE_NOT_VERIFIED'
    assert result.projection_is_zero_overhead is False


@pytest.mark.parametrize('field,bad', [
    ('backend_pid', 1235), ('backend_start_sha256', 'b' * 64),
    ('connection_generation', 2), ('process_sha256', 'b' * 64),
    ('connection_sha256', 'b' * 64), ('pool_checkout_generation', 1),
    ('transaction_pool', True), ('driver_version', '3.2.0'),
    ('prepare_threshold', 0), ('prepared_max', 0),
])
def test_AT12_AT13_session_pool_reconnect_rejected(prepared, session, field, bad):
    with pytest.raises((ValueError, Fault)):
        validate_snapshot(prepared.model_copy(update={
            'session': session.model_copy(update={field: bad})}), session)


@pytest.mark.parametrize('change', ['missing', 'evicted', 'renamed', 'reset', 'negative',
                                   'unknown', 'generic-switch', 'oid', 'sql', 'key', 'from-sql'])
def test_AT14_AT15_prepared_missing_renamed_evicted_and_counters(prepared, session, change):
    row = prepared.row.model_copy(update={'custom_plans': 2})
    after = prepared.model_copy(update={'executions': 7, 'row': row})
    updates = {
        'missing': {'row': None}, 'evicted': {'evicted': True},
        'renamed': {'row': row.model_copy(update={'identifier_sha256': 'b' * 64})},
        'reset': {'row': row.model_copy(update={'custom_plans': 0})},
        'negative': {'row': row.model_copy(update={'custom_plans': -1})},
        'unknown': {'mode': 'UNKNOWN'},
        'generic-switch': {'mode': 'GENERIC', 'row': row.model_copy(update={
            'generic_plans': 1, 'custom_plans': 1})},
        'oid': {'parameter_oids': [20]}, 'sql': {'sql_sha256': 'b' * 64},
        'key': {'cache_key_sha256': 'b' * 64},
        'from-sql': {'row': row.model_copy(update={'from_sql': True})},
    }
    with pytest.raises((ValueError, Fault)):
        compare(prepared, after.model_copy(update=updates[change]), session)


def test_AT12_AT16_only_exact_fake_cursor_no_duck_callback(prepared, session):
    assert project_mock(FakeCursor(session, (prepared.row,)), session) == (prepared.row,)
    class Injected:
        def execute(self, *args):
            pytest.fail('must not execute')
    with pytest.raises(Fault, match='REAL_CURSOR_NOT_AUTHORIZED'):
        project_mock(Injected(), session)


@pytest.fixture
def process():
    return ProcSnapshot(backend_pid=1234, mapped_proc_pid=1234, backend_start_sha256=H,
                        proc_start_ticks=100, namespace_sha256=H, container_sha256=H,
                        clock_domain_sha256=H, clock_ticks=100, observed_ns=1_000_000_000,
                        user_ticks=10, system_ticks=10, permission_verified=True,
                        bidirectional_mapping_verified=True)


@pytest.mark.parametrize('field,bad', [
    ('backend_pid', 1235), ('mapped_proc_pid', 1235), ('backend_start_sha256', 'b' * 64),
    ('proc_start_ticks', 101), ('namespace_sha256', 'b' * 64),
    ('container_sha256', 'b' * 64), ('clock_domain_sha256', 'b' * 64), ('clock_ticks', 0),
    ('permission_verified', False), ('bidirectional_mapping_verified', False),
    ('observed_ns', 1_000_000_000), ('user_ticks', 0), ('system_ticks', -1),
])
def test_AT17_AT18_cpu_reuse_clock_namespace_permission_negative(process, field, bad):
    after = process.model_copy(update={'observed_ns': 2_000_000_000, 'user_ticks': 20})
    with pytest.raises((ValueError, Fault)):
        backend_delta(process, after.model_copy(update={field: bad}), process)


def test_AT18_no_delta_is_unavailable_and_positive_is_only_mock(process):
    after = process.model_copy(update={'observed_ns': 2_000_000_000})
    with pytest.raises(Fault, match='METRIC_UNAVAILABLE'):
        backend_delta(process, after, process)
    result = backend_delta(process, after.model_copy(update={'user_ticks': 20}), process)
    assert result['mock_cpu_seconds'] == '0.1'
    assert result['real_availability'] == 'METRIC_UNAVAILABLE'
    assert result['source'] != 'SQL_WALL'


@pytest.fixture
def resources():
    mappings = [('PROCESS_CPU', 'MOCK_PROCESS_TIME', 'ns', 50),
                ('ENTIRE_OBSERVER_THREAD_CPU', 'MOCK_THREAD_TIME', 'ns', 20),
                ('WORKER_ELAPSED', 'MOCK_MONOTONIC', 'ns', 1000),
                ('PROCESS_LIFETIME_RSS_HIGH_WATER', 'MOCK_RUSAGE', 'bytes', 8192),
                ('NATURAL_GC_EVENT', 'MOCK_GC_CALLBACK', 'ns', 10)]
    return Resources(metrics=[Metric(scope=s, source=p, unit=u, started_ns=1000,
        finished_ns=2000, identity_sha256=H, availability='MOCK_ONLY', value=v)
        for s, p, u, v in mappings], gc_enabled_before=True, gc_enabled_after=True,
        gc_thresholds_before=(700, 10, 10), gc_thresholds_after=(700, 10, 10))


@pytest.mark.parametrize('change', ['valid', 'scope', 'source', 'unit', 'interval', 'unknown',
                                   'zero', 'elapsed', 'gc', 'disabled'])
def test_AT19_resource_scope_is_not_tick_sum_rss_difference_or_gc_adjustment(resources, change):
    metrics = list(resources.metrics)
    updates = {'scope': {'scope': 'ENTIRE_OBSERVER_THREAD_CPU'},
               'source': {'source': 'MOCK_THREAD_TIME'}, 'unit': {'unit': 'bytes'},
               'interval': {'finished_ns': 3000}, 'unknown': {'value': None}, 'zero': {'value': 0}}
    if change in updates:
        metrics[0] = metrics[0].model_copy(update=updates[change])
    if change == 'elapsed':
        metrics[2] = metrics[2].model_copy(update={'value': 999})
    value = resources.model_copy(update={'metrics': metrics})
    if change == 'gc':
        value = value.model_copy(update={'gc_thresholds_after': (1, 1, 1)})
    if change == 'disabled':
        value = value.model_copy(update={'gc_enabled_after': False})
    if change == 'valid':
        validate_resources(value, H, 1000, 2000)
    else:
        with pytest.raises((ValueError, Fault)):
            validate_resources(value, H, 1000, 2000)


def test_AT19_entire_thread_cpu_cannot_cover_just_tick_interval(resources):
    metrics = list(resources.metrics)
    metrics[1] = metrics[1].model_copy(update={'started_ns': 1500})
    with pytest.raises(Fault, match='METRIC_SCOPE_INVALID'):
        validate_resources(resources.model_copy(update={'metrics': metrics}), H, 1000, 2000)


@pytest.fixture
def environment():
    return Environment(relations=[Relation(name=name, oid=i + 100, statistics_sha256=H,
        indexes_sha256=H, columns_sha256=H) for i, name in enumerate(TABLES)],
        **dict.fromkeys(('instance_sha256', 'schema_sha256', 'data_snapshot_sha256',
                         'mvcc_snapshot_sha256', 'settings_sha256', 'model_sha256',
                         'sql_sha256', 'fresh_plan_sha256', 'backend_lifecycle_sha256'), H),
        plan_mode='CUSTOM', autovacuum_certain=True)


@pytest.mark.parametrize('field', ['instance_sha256', 'schema_sha256', 'data_snapshot_sha256',
                                  'settings_sha256', 'model_sha256', 'sql_sha256',
                                  'fresh_plan_sha256', 'backend_lifecycle_sha256'])
def test_AT20_each_environment_dimension_independent(environment, field):
    with pytest.raises(Fault, match='ENVIRONMENT_DRIFT'):
        environment_compare(environment, environment.model_copy(update={field: 'b' * 64}),
                            ['NOT_OBSERVED'])


@pytest.mark.parametrize('field,bad', [('oid', 999), ('statistics_sha256', 'b' * 64),
                                     ('indexes_sha256', 'b' * 64), ('columns_sha256', 'b' * 64)])
def test_AT20_mvcc_equality_does_not_mask_statistics_or_relation_drift(environment, field, bad):
    rows = list(environment.relations)
    rows[0] = rows[0].model_copy(update={field: bad})
    with pytest.raises(Fault, match='ENVIRONMENT_DRIFT'):
        environment_compare(environment, environment.model_copy(update={'relations': rows}),
                            ['NOT_OBSERVED'])


@pytest.mark.parametrize('event', ['ANALYZE_OBSERVED', 'VACUUM_OBSERVED', 'UNKNOWN_RELATION',
                                  'AMBIGUOUS_EVENT', 'POSSIBLE_IN_BRACKET', 'BACKEND_CHURN'])
def test_AT21_background_activity_and_unknown_stop(environment, event):
    with pytest.raises(Fault, match='BACKGROUND_ACTIVITY_UNCERTAIN'):
        environment_compare(environment, environment, [event])
    result = environment_compare(environment, environment, ['NOT_OBSERVED'])
    assert result['absence_proven'] is False and result['real_status'] == 'NOT_PROVEN'


@pytest.fixture
def window():
    return Window(mode='ON', identity_sha256=H, planned_ticks=3,
        lookup_started_ns=10_000_000, lookup_finished_ns=400_000_000,
        observed_until_ns=510_000_000,
        ticks=[Tick(sequence=i, started_ns=1_000_000 + i * 250_000_000,
                    finished_ns=2_000_000 + i * 250_000_000, sql_ns=[100_000], complete=True)
               for i in range(3)], state='JOINED', joined=True,
        lifecycle=['INIT', 'RUNNING', 'STOP_REQUESTED', 'JOINED', 'RECEIPT'],
        worker_started_ns=1_000_000, worker_finished_ns=505_000_000,
        worker_cpu_ns=1_000_000, stop_join_ns=1_000_000, cleanup_complete=True)


@pytest.mark.parametrize('change', ['valid', 'short-lookup', 'no-post', 'partial', 'sql-timeout',
    'tick-budget', 'poll', 'stop-timeout', 'joined-lie', 'missing-worker-end', 'missing-cpu',
    'lifecycle', 'extra-tick', 'future-tick', 'wrong-sequence', 'missing-cleanup'])
def test_AT22_AT23_AT24_long_window_state_and_bracket_fail_closed(window, change):
    value = window
    if change == 'valid':
        assert validate_window(value)['real_status'] == 'NOT_PROVEN'
        return
    updates = {'short-lookup': {'lookup_finished_ns': 20_000_000},
               'no-post': {'lookup_finished_ns': 503_000_000},
               'stop-timeout': {'stop_join_ns': 2_000_000_001},
               'joined-lie': {'state': 'STOP_TIMEOUT'},
               'missing-worker-end': {'worker_finished_ns': None},
               'missing-cpu': {'worker_cpu_ns': None}, 'lifecycle': {'lifecycle': ['INIT']},
               'extra-tick': {'planned_ticks': 2}, 'missing-cleanup': {'cleanup_complete': False}}
    if change in updates:
        value = value.model_copy(update=updates[change])
    tick_updates = {'partial': {'complete': False}, 'sql-timeout': {'sql_ns': [100_000_001]},
                    'tick-budget': {'finished_ns': 300_000_000},
                    'poll': {'started_ns': 252_000_000},
                    'future-tick': {'finished_ns': 600_000_000},
                    'wrong-sequence': {'sequence': 7}}
    if change in tick_updates:
        ticks = list(value.ticks)
        ticks[1] = ticks[1].model_copy(update=tick_updates[change])
        value = value.model_copy(update={'ticks': ticks})
    with pytest.raises((ValueError, Fault)):
        validate_window(value)


def test_AT24_stable_timeout_retains_incomplete_ticks_and_unknown_cpu(window):
    value = window.model_copy(update=dict(state='STOP_TIMEOUT', joined=False,
        lifecycle=['INIT', 'RUNNING', 'STOP_REQUESTED'], worker_finished_ns=None,
        worker_cpu_ns=None, stop_join_ns=2_000_000_000, cleanup_complete=False))
    assert validate_window(value)['status'] == 'MOCK_INCOMPLETE'
    assert len(value.ticks) == 3 and value.worker_cpu_ns is None


@pytest.mark.parametrize('change', ['overplanned', 'nonlast-partial'])
def test_AT24_timeout_snapshot_must_be_real_bounded_prefix(window, change):
    value = window.model_copy(update=dict(state='STOP_TIMEOUT', joined=False,
        lifecycle=['INIT', 'RUNNING', 'STOP_REQUESTED'], worker_finished_ns=None,
        worker_cpu_ns=None, stop_join_ns=2_000_000_000, cleanup_complete=False))
    if change == 'overplanned':
        value = value.model_copy(update={'planned_ticks': 2})
    else:
        ticks = list(value.ticks)
        ticks[0] = ticks[0].model_copy(update={'complete': False})
        value = value.model_copy(update={'ticks': ticks})
    with pytest.raises(Fault):
        validate_window(value)


def test_AT22_off_no_worker_never_claims_on_observation(window):
    off = window.model_copy(update=dict(mode='OFF', state='OBSERVER_OFF', ticks=[],
        lifecycle=[], worker_started_ns=None, worker_finished_ns=None, worker_cpu_ns=None,
        stop_join_ns=0))
    assert validate_window(off)['status'] == 'MOCK_OFF_VALID'
    with pytest.raises(Fault):
        validate_window(off.model_copy(update={'ticks': window.ticks}))
