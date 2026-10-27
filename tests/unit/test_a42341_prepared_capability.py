"""AT01-07: conditional arithmetic, frozen v2 and no real prepare/connection."""

from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest
from psycopg._preparing import Prepare, PrepareManager

from scripts import a42341_contract as c
from scripts.a4233_observation_contract import digest
from scripts.a4234_calibration_contract import prepared_readiness, warmup_schedule
from scripts.a4234_calibration_guard import execute
from scripts.a42341_prepared_capability import compare, condition, necessary_condition

ROOT = Path(__file__).resolve().parents[2]


def test_AT01_frozen_old_files_and_old_execute_and_eight_warmups():
    import hashlib

    from scripts.business_source_contract import historical_bytes, verify

    manifest = c.definitions()
    assert len(warmup_schedule()) == 8 and prepared_readiness()['warmups_total'] == 8
    assert prepared_readiness()['status'] == 'BLOCKED_NEEDS_SPEC_OR_CAPABILITY'
    for name, sha in manifest['frozen_files'].items():
        assert hashlib.sha256(historical_bytes(name)).hexdigest() == sha
    with pytest.raises(RuntimeError, match='A4234_EXECUTION_NOT_AUTHORIZED'):
        execute(token='forged', approved=True)

    assert len(verify()) == 64


def test_AT02_AT03_fixed_order_warmup_lower_bound_and_real_not_proven():
    expected = c.identity()
    rows = c.schedule()
    assert len(rows) == 128 and len({(r['block'], r['variant'], r['pair']) for r in rows}) == 64
    assert digest(rows) == c.definitions()['schedule_sha256']
    warm = c.warmup_schedule()
    assert len(warm) == 16
    assert Counter((w['block'], w['variant']) for w in warm) == {
        (b, v): 2 for b in range(4) for v in ('C0', 'C1')}
    for count in (4, 8, 72):
        result = necessary_condition(condition(expected, 0, 'C0', count))
        assert result['necessary_threshold_crossed'] is (count >= 6)
        assert result['real_proof'] == 'NOT_PROVEN' and result['prepared_stable'] is False
    assert len({condition(expected, b, 'C0').connection_identity for b in range(4)}) == 4


def test_AT03_pinned_pure_prepare_manager_same_sql_type_and_new_connection_counts():
    query = SimpleNamespace(query=b'A42341_MOCK_CACHE_KEY', types=(25, 2950))
    managers = [PrepareManager(), PrepareManager()]
    assert all(m.prepare_threshold == 5 and m.prepared_max == 100 for m in managers)
    states = []
    for _ in range(8):
        state, name = managers[0].get(query)
        states.append(state)
        managers[0].maybe_add_to_cache(query, state, name)
    assert states == [Prepare.NO] * 5 + [Prepare.SHOULD, Prepare.YES, Prepare.YES]
    assert managers[1].get(query)[0] == Prepare.NO
    assert managers[0].get(SimpleNamespace(query=query.query, types=(25, 25)))[0] == Prepare.NO


@pytest.mark.parametrize('field,bad', [
    ('connection_identity', 'a' * 64), ('process_identity', 'a' * 64),
    ('backend_pid', 54321), ('backend_start', '2026-01-02T00:00:00Z'),
    ('sql_text_sha256', 'a' * 64), ('parameter_types_sha256', 'a' * 64),
    ('prepare_cache_key_sha256', 'a' * 64), ('statement_name_sha256', 'a' * 64),
    ('pool_checkout_generation', 1), ('evicted', True), ('prepare_threshold', 0),
    ('prepared_max', 1), ('sql_exec_count', 0), ('custom_plans', 0),
    ('generic_plans', 1), ('server_prepared_observed', None), ('driver_cache_observed', False),
])
def test_AT04_AT05_prepare_identity_eviction_checkout_counters_are_never_stability(field, bad):
    expected = c.identity()
    before = condition(expected, 0, 'C0')
    after = condition(expected, 0, 'C0', 12)
    compare(before, after, before)
    with pytest.raises((c.Fault, ValueError)):
        compare(before.model_copy(update={field: bad}), after, before)


def test_AT04_eight_only_counts_do_not_supply_server_or_statement_proof():
    before = condition(c.identity(), 0, 'C1')
    with pytest.raises(c.Fault, match='A42341_PREPARED_STABILITY_NOT_PROVEN'):
        compare(before.model_copy(update={'server_prepared_observed': False}),
                condition(c.identity(), 0, 'C1', 12), before)
