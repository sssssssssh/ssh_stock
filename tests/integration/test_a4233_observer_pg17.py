"""Four empty migrated relations, restricted roles, max three ticks. No lookup/seed."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from scripts import a4233_background_observer as ob
from scripts import a4233_observation_review as off
from scripts.a4233_observation_contract import TABLES, Fault, digest, validate
from scripts.v14_test_database import isolated_v14_database, verified_test_url


@pytest.fixture
def observer_pg17(monkeypatch):
    # This is the TEST ADMIN fixture, NOT observer code. All role/schema/permission
    # setup is explicit, restricted to the newly created, dual-verified UUID target.
    url = verified_test_url()
    from app.core.config import Settings, get_settings

    with monkeypatch.context() as patch:
        patch.setitem(Settings.model_config,'env_file',None)
        get_settings.cache_clear()
        try:
            with isolated_v14_database(patch) as (_,engine):
                suffix = uuid4().hex
                names = ('a4233_ob_'+suffix,'a4233_no_stats_'+suffix)
                admin = create_engine(url,isolation_level='AUTOCOMMIT',hide_parameters=True)
                try:
                    verified_test_url()
                    with admin.connect() as db:
                        for name in names:
                            # All identifiers are harness-generated hex; synthetic password only.
                            db.execute(text(f'CREATE ROLE "{name}" LOGIN NOSUPERUSER NOCREATEDB '
                                "NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD 'synthetic'"))
                        db.execute(text(f'GRANT pg_read_all_stats TO "{names[0]}"'))
                    with engine.begin() as db:
                        assert db.scalar(text("SELECT current_setting('v14.test_instance')")) == (
                            os.environ['V14_TEST_INSTANCE'])
                        assert str(db.scalar(text(
                            'SELECT system_identifier FROM pg_control_system()'))) == (
                                os.environ['V14_TEST_SYSTEM_IDENTIFIER'])
                        assert db.scalar(text('SELECT current_database()')) == engine.url.database
                        for name in names:
                            db.execute(text('GRANT EXECUTE ON FUNCTION '
                                f'pg_catalog.pg_control_system() TO "{name}"'))
                        counts = {name:db.scalar(text(f'SELECT count(*) FROM public."{name}"'))
                                  for name in TABLES}
                        assert counts == dict.fromkeys(TABLES,0)
                    yield engine,names
                finally:
                    # Only roles and DB created by this fixture. No business cleanup.
                    verified_test_url()
                    with engine.begin() as db:
                        for name in names:
                            db.execute(text('REVOKE EXECUTE ON FUNCTION '
                                f'pg_catalog.pg_control_system() FROM "{name}"'))
                    with admin.connect() as db:
                        for name in names:
                            db.execute(text(f'DROP ROLE IF EXISTS "{name}"'))
                    admin.dispose()
        finally:
            get_settings.cache_clear()


def make_observer(engine, role, *, marker=None, system=None):
    marker = marker or os.environ['V14_TEST_INSTANCE']
    system = system or os.environ['V14_TEST_SYSTEM_IDENTIFIER']
    expected = off.source_identity(Path(__file__).resolve().parents[2],
        instance_hash=digest([marker,system]))
    target = engine.url.set(username=role,password='synthetic').render_as_string(
        hide_password=False)
    connect = ob.connection_factory(target,marker,system)
    return ob.Observer(connect,marker=marker,system_id=system,identity=expected),expected


def test_real_pg17_readonly_fields_mapping_clock_and_atomic_receipt(observer_pg17,tmp_path):
    engine,names = observer_pg17
    observer,expected = make_observer(engine,names[0])
    result = observer.run_micro()
    assert validate(result,expected).status == 'COMPLETE_CONTRACT'
    assert len(result['ticks']) == 3
    assert {r['table'] for r in result['relations'] if r['kind'] == 'TABLE'} == set(TABLES)
    assert {r['kind'] for r in result['relations']} >= {'TABLE','INDEX','TOAST','TOAST_INDEX'}
    assert all(r['n_live_tup'] == 0 for r in result['ticks'][0]['tables'])
    artifact_root = os.environ.get('A4233_ARTIFACT_ROOT')
    directory = Path(artifact_root)/'micro' if artifact_root else tmp_path/'micro'
    off.bundle(directory,result,expected)
    assert off.review_bundle(directory,expected)['status'] == 'COMPLETE_CONTRACT'


def test_real_pg17_missing_read_all_stats_fails_without_auto_grant(observer_pg17):
    engine,names = observer_pg17
    observer,expected = make_observer(engine,names[1])
    result = observer.run_micro()
    assert result['status'] == 'INCOMPLETE_OBSERVABILITY'
    assert result['first_failure_code'] == 'A4233_READ_ALL_STATS_REQUIRED'
    assert result['ticks'] == [] and result['restricted_readonly_verified'] is False
    assert validate(result,expected).capacity_ready is False
    with engine.connect() as db:
        assert db.scalar(text('SELECT pg_has_role(:role,\'pg_read_all_stats\',\'MEMBER\')'),
                         dict(role=names[1])) is False


@pytest.mark.parametrize('which',['marker','system'])
def test_real_pg17_wrong_physical_identity_no_catalog_ticks(observer_pg17,which):
    engine,names = observer_pg17
    args = dict(marker=str(uuid4())) if which == 'marker' else dict(system='1234')
    observer,expected = make_observer(engine,names[0],**args)
    result = observer.run_micro()
    assert result['first_failure_code'] == 'A4233_PHYSICAL_MISMATCH'
    assert result['ticks'] == result['relations'] == []
    assert result['physical_verified'] is False
    assert validate(result,expected).capacity_ready is False


def test_real_pg17_observer_role_has_no_business_data_or_maintenance_privileges(observer_pg17):
    engine,names = observer_pg17
    with engine.connect() as db:
        for table in TABLES:
            assert db.scalar(text("SELECT has_table_privilege(:role,:table,"
                "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,MAINTAIN')"),
                dict(role=names[0],table='public.'+table)) is False
        assert db.scalar(text("SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls "
                              'FROM pg_roles WHERE rolname=:role'),dict(role=names[0])) is False
    observer,expected = make_observer(engine,names[0])
    result = observer.run_micro()
    assert validate(result,expected).status == 'COMPLETE_CONTRACT'


def test_real_pg17_superuser_rejected_even_if_stats_visible(observer_pg17):
    engine,_ = observer_pg17
    observer,expected = make_observer(engine,engine.url.username)
    # Test admin synthetic password comes from the already verified explicit URL.
    observer.connect = ob.connection_factory(engine.url.render_as_string(hide_password=False),
        os.environ['V14_TEST_INSTANCE'],os.environ['V14_TEST_SYSTEM_IDENTIFIER'])
    result = observer.run_micro()
    assert result['first_failure_code'] == 'A4233_RESTRICTED_ROLE_REQUIRED'
    assert result['ticks'] == [] and validate(result,expected).performance_eligible is False


def test_real_pg17_readonly_connection_prevents_dml_and_has_no_long_transaction(observer_pg17):
    engine,names = observer_pg17
    observer,_ = make_observer(engine,names[0])
    with observer.connect() as db:
        observer.preflight(db)
        assert db.autocommit
        # Only the ADMIN test checks catalog flags. Observer issues no write probe.
        from psycopg.pq import TransactionStatus

        assert db.info.transaction_status == TransactionStatus.IDLE
        assert observer.restricted_readonly_verified
        assert observer.physical_verified
    assert Fault('A4233_TEST').code == 'A4233_TEST'
