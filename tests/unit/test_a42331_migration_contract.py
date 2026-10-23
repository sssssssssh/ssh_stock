"""No database: exercise all branches of the unchanged production downgrade guard."""

from types import SimpleNamespace

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from scripts.a42331_migration_contract import ARCHIVES, OwnedMigration


@pytest.mark.parametrize('target',ARCHIVES)
def test_unchanged_0051_guard_rejects_each_exists_branch_before_ddl(monkeypatch,target):
    module = ScriptDirectory.from_config(Config('alembic.ini')).get_revision(
        '0051_m16_5_evidence_archive').module
    queries = []
    def scalar(statement):
        table = next(t for t in ARCHIVES if t in str(statement))
        queries.append(table)
        return table == target
    monkeypatch.setattr(module,'op',SimpleNamespace(get_bind=lambda:SimpleNamespace(scalar=scalar)))
    with pytest.raises(RuntimeError,match='archive data exists'):
        module.downgrade()
    assert queries == list(ARCHIVES[:ARCHIVES.index(target)+1])


def test_identity_mismatch_is_rejected_before_config_or_ddl(monkeypatch):
    owned = OwnedMigration(None,'a'*64,'v14_'+'b'*32+'_test')
    monkeypatch.setattr('scripts.a42331_migration_contract.identity',lambda conn:dict(
        pg_major=17,schema='public',database='v14_'+'c'*32+'_test',physical_sha256='a'*64))
    with pytest.raises(RuntimeError,match='DATABASE_IDENTITY_MISMATCH'):
        owned.verify(object())


@pytest.mark.parametrize('failed',['engine','drop','admin','all'])
def test_owned_cleanup_failures_are_bounded_explicit_and_never_success(monkeypatch,failed):
    from scripts import a42331_migration_contract as c

    marker,system = '00000000-0000-0000-0000-000000000001','1234'
    proof = dict(database_instance=marker,physical_system_identifier=system,
        postgres_version='17.11',
        isolation=dict(verified=True,before_ddl=True,expected_marker=marker,observed_marker=marker,
                       expected_system_identifier=system,observed_system_identifier=system))
    monkeypatch.setattr('scripts.v14_test_database.verified_test_url',
                        lambda:SimpleNamespace(set=lambda **kw:object()))
    monkeypatch.setattr('scripts.a42_artifacts.isolation',lambda:proof)
    monkeypatch.setattr(c,'identity',lambda db:dict(physical_sha256=c.fingerprint([marker,system])))
    executed = []
    class Connection:
        def __enter__(self):
            return self
        def __exit__(self,*args):
            pass
        def execute(self,statement):
            executed.append(str(statement).split()[0])
            if str(statement).startswith('DROP') and failed in ('drop','all'):
                raise RuntimeError('secret DSN')
    class Engine:
        def __init__(self,role):
            self.role = role
        def connect(self):
            return Connection()
        def dispose(self):
            if failed in (self.role,'all'):
                raise RuntimeError('secret cleanup')
    engines = iter([Engine('admin'),Engine('engine')])
    monkeypatch.setattr(c,'create_engine',lambda *a,**kw:next(engines))
    monkeypatch.setattr(c.OwnedMigration,'migrate',lambda *a:None)
    with pytest.raises(RuntimeError,match='A42331_OWNED_DATABASE_CLEANUP_FAILED') as error:
        with c.owned_migration_database() as owned:
            assert owned.name.startswith('v14_')
    assert len(error.value.a42331_cleanup_codes) <= 3
    assert executed == ['CREATE','DROP']
    assert owned.evidence[-1]['cleanup_complete'] is False
    assert 'secret' not in str(error.value)
