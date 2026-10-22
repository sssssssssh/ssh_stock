"""Tiny PG17 contracts only; distinct module name avoids pytest import collisions."""

from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from scripts import publication_lookup_diagnostic_a422 as lab
from scripts.a4232_plan_probe import assert_plans, capture_queries, plan_snapshot
from scripts.a4232_stability_contract import (
    CONTROL,
    TABLES,
    assert_stable,
    owned,
    stabilize,
    statistics_snapshot,
)
from scripts.publication_tail_stability_a4232 import bound_owned_engine
from scripts.v14_test_database import isolated_v14_database, verified_test_url


@pytest.fixture
def tiny_stability_database(monkeypatch):
    verified_test_url()  # Explicit physical target before Settings/application imports.
    from app.core.config import Settings, get_settings

    with monkeypatch.context() as patch:
        patch.setitem(Settings.model_config,'env_file',None)
        get_settings.cache_clear()
        try:
            _,c,candidate = lab.setup_runtime()
            with isolated_v14_database(patch) as (factory,engine):
                bound_owned_engine(engine)
                days = [date(2026,1,2)+timedelta(days=i) for i in range(20)]
                c.seed(factory,4,days)
                with candidate(factory,engine,start=days[0],end=days[-1]) as (db,job):
                    ws = db.info['publication_workspace']
                    for model in c.MODELS[:8]:
                        ws.upsert(model,[c.payload(model,job.id,days[0],1,15)],
                                  c.KEYS[model.__tablename__])
                    db.commit()
                    with factory() as probe:
                        probe.connection(execution_options={'isolation_level':'AUTOCOMMIT'})
                        probe.execute(text("SET statement_timeout='300s'"))
                        yield db,probe,engine,c,ws
        except DBAPIError as error:
            # Also protect the existing full pytest/JUnit job, which does not
            # use the dedicated job's no-trace options/plugin.
            sanitized = RuntimeError('A4232_PG17_DRIVER_FAILURE')
            sanitized.a4232_driver_type = type(error.orig).__name__
            sanitized.a4232_sqlstate = getattr(error.orig,'sqlstate',None)
            raise sanitized from None
        finally:
            get_settings.cache_clear()


def test_actual_pg17_catalog_digests_and_fresh_cached_plans_are_stable(tiny_stability_database):
    db,probe,engine,c,ws = tiny_stability_database
    state = stabilize(db,engine.url.database,lambda:statistics_snapshot(probe))
    assert state['status'] == 'STABLE'
    assert_stable(state['identity'],statistics_snapshot(probe))
    model = next(m for m in c.MODELS if m.__tablename__ == CONTROL)
    inputs = [dict(r) for r in db.execute(text('SELECT trade_date,ts_code FROM public.'
        'stock_trade_status_daily ORDER BY trade_date,ts_code')).mappings()]
    queries = capture_queries(ws,model,inputs)
    golden = None
    # Four 500-size calls per workload in the real diagnostic; emulate the same
    # fixed 16 statement executions per variant without measuring any latency.
    for _ in range(16):
        for variant in ('C0','C1'):
            result = lab.lookup(ws,model,inputs,variant)
            golden = result if golden is None else golden
            assert result == golden
    before = plan_snapshot(db,probe,queries)
    after = plan_snapshot(db,probe,queries)
    assert_plans(before,after)
    assert {p['cached_mode'] for p in before['variants'].values()} <= {'generic','custom'}
    assert all(p['generic_plans']+p['custom_plans'] > 0 for p in before['variants'].values())
    assert_stable(state['identity'],statistics_snapshot(probe))


def test_fresh_catalog_observer_detects_manual_analyze_even_with_same_rows(tiny_stability_database):
    db,probe,engine,_,_ = tiny_stability_database
    owned(db,engine.url.database)
    for table in TABLES:
        db.execute(text(f'ANALYZE public."{table}"'))
    db.execute(text('SELECT pg_stat_force_next_flush()'))
    db.commit()
    before = statistics_snapshot(probe)
    owned(db,engine.url.database)
    db.execute(text('ANALYZE public.stock_trade_status_daily'))
    db.execute(text('SELECT pg_stat_force_next_flush()'))
    db.commit()
    after = statistics_snapshot(probe)
    with pytest.raises(ValueError,match='ENVIRONMENT_DRIFT'):
        assert_stable(before,after)


def test_wrong_database_cannot_change_table_options_or_global_autovacuum(tiny_stability_database):
    db,probe,_,_,_ = tiny_stability_database
    before = probe.scalar(text('SHOW autovacuum'))
    with pytest.raises(ValueError,match='NOT_NEW_OWNED_DATABASE'):
        stabilize(db,'business',lambda:statistics_snapshot(probe))
    assert probe.scalar(text('SHOW autovacuum')) == before
    assert not probe.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_class WHERE "
        "'autovacuum_enabled=false'=ANY(coalesce(reloptions,ARRAY[]::text[])))"))


def test_conditional_table_control_is_limited_to_new_synthetic_relations(tiny_stability_database):
    db,probe,engine,_,_ = tiny_stability_database
    before = probe.scalar(text('SHOW autovacuum'))
    calls = 0
    def observed():
        nonlocal calls
        calls += 1
        if calls == 2:
            # Real tiny-fixture statistics fault, NOT a performance experiment.
            owned(db,engine.url.database)
            db.execute(text('ANALYZE public.stock_trade_status_daily'))
            db.execute(text('SELECT pg_stat_force_next_flush()'))
            db.commit()
        return statistics_snapshot(probe)
    state = stabilize(db,engine.url.database,observed)
    assert len(state['attempts']) == 2 and state['attempts'][0]['valid'] is False
    assert state['environment_kind'] == 'CONTROLLED_SYNTHETIC_TABLE_AUTOVACUUM_OFF'
    assert all('autovacuum_enabled=false' in r['reloptions']
               for r in state['identity']['relations'])
    assert probe.scalar(text('SHOW autovacuum')) == before
    timeout = probe.scalar(text("SELECT setting::int FROM pg_settings "
                                "WHERE name='statement_timeout'"))
    assert timeout == 300000
