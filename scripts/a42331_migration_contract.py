"""Owned UUID migration test boundary, independent of app Settings/SessionLocal."""

import hashlib
import json
import re
from contextlib import contextmanager
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

ARCHIVES = ('agent_tool_result_archive','agent_evidence_archive_binding',
            'agent_turn_archive_manifest')
HEAD = '0058_data_publication'


def require(value, code):
    if not value:
        raise RuntimeError(code)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def identity(connection):
    """Only identities/counts, never URL/role/row contents."""
    marker = connection.scalar(text("SELECT current_setting('v14.test_instance',true)"))
    system = str(connection.scalar(text('SELECT system_identifier FROM pg_control_system()')))
    major = int(connection.scalar(text("SELECT current_setting('server_version_num')")))//10000
    name = connection.scalar(text('SELECT current_database()'))
    schema = connection.scalar(text('SELECT current_schema()'))
    exists = connection.scalar(text("SELECT to_regclass('public.alembic_version') IS NOT NULL"))
    revision = (connection.scalar(text('SELECT version_num FROM alembic_version'))
                if exists else None)
    return dict(database=name,schema=schema,pg_major=major,
        physical_sha256=fingerprint([marker,system]),
        database_sha256=fingerprint([marker,system,name,schema]),revision=revision)


class OwnedMigration:
    def __init__(self, engine, proof, name):
        self.engine,self.proof,self.name = engine,proof,name
        self.factory = sessionmaker(bind=engine,expire_on_commit=False)
        self.evidence = []

    def verify(self, connection):
        observed = identity(connection)
        require(observed['pg_major'] == 17 and observed['schema'] == 'public'
            and observed['database'] == self.name
            and re.fullmatch(r'v14_[0-9a-f]{32}_test',self.name)
            and observed['physical_sha256'] == self.proof,'A42331_DATABASE_IDENTITY_MISMATCH')
        return observed

    def assert_same(self, session, migration_connection):
        left,right = self.verify(session),self.verify(migration_connection)
        require(left == right,'A42331_DATABASE_IDENTITY_MISMATCH')
        return left

    def migrate(self, operation, revision):
        from alembic import command
        from alembic.config import Config

        require(operation in ('upgrade','downgrade'),'A42331_MIGRATION_OPERATION_INVALID')
        with self.engine.connect() as db:
            before = self.verify(db)
            with self.factory() as session:
                compared = self.assert_same(session,db)
            self.evidence.append(dict(phase='SESSION_MIGRATION_SAME_TARGET',identity=compared))
            db.rollback()  # No external transaction from preflight may swallow DDL commits.
            config = Config('alembic.ini')
            config.attributes['connection'] = db
            try:
                getattr(command,operation)(config,revision)
                db.commit()
            except BaseException:
                db.rollback()
                self.evidence.append(dict(phase='MIGRATION_REJECTED',identity=self.verify(db)))
                raise
            self.evidence.append(dict(phase='MIGRATION_COMPLETED',before=before,
                                      identity=self.verify(db)))

    def counts(self):
        with self.engine.connect() as db:
            observed = self.verify(db)
            counts = {t:db.scalar(text(f'SELECT count(*) FROM public.{t}')) for t in ARCHIVES}
            value = dict(phase='FRESH_COMMITTED_COUNTS',identity=observed,counts=counts)
            self.evidence.append(value)
            return counts


@contextmanager
def owned_migration_database():
    """Verify independently before CREATE and DROP. No global environment patch."""
    from scripts.a42_artifacts import isolation
    from scripts.a42_receipt_contract import physical
    from scripts.v14_test_database import verified_test_url

    url = verified_test_url()
    proof = isolation()
    physical(proof)
    expected = fingerprint([proof['database_instance'],proof['physical_system_identifier']])
    name = 'v14_'+uuid4().hex+'_test'
    admin = create_engine(url,isolation_level='AUTOCOMMIT',hide_parameters=True,
        connect_args={'options':'-c statement_timeout=30000 -c lock_timeout=5000'})
    engine,owned,created = None,None,False
    try:
        with admin.connect() as db:
            require(identity(db)['physical_sha256'] == expected,'A42331_PHYSICAL_MISMATCH')
            db.execute(text(f'CREATE DATABASE "{name}"'))
            created = True
        engine = create_engine(url.set(database=name),hide_parameters=True,
            connect_args={'options':'-c statement_timeout=30000 -c lock_timeout=5000'})
        owned = OwnedMigration(engine,expected,name)
        owned.migrate('upgrade','head')
        yield owned
    finally:
        cleanup_codes = []
        if engine is not None:
            try:
                engine.dispose()
            except BaseException:
                cleanup_codes.append('A42331_ENGINE_DISPOSE_FAILED')
        try:
            if created:
                verified_test_url()
                with admin.connect() as db:
                    require(identity(db)['physical_sha256'] == expected,
                            'A42331_CLEANUP_IDENTITY_MISMATCH')
                    db.execute(text(f'DROP DATABASE "{name}"'))
        except BaseException:
            cleanup_codes.append('A42331_OWNED_DATABASE_CLEANUP_FAILED')
        finally:
            try:
                admin.dispose()
            except BaseException:
                cleanup_codes.append('A42331_ADMIN_DISPOSE_FAILED')
        if owned is not None:
            owned.evidence.append(dict(phase='OWNED_CLEANUP',cleanup_complete=not cleanup_codes,
                                       cleanup_failure_codes=cleanup_codes))
        if cleanup_codes:
            error = RuntimeError('A42331_OWNED_DATABASE_CLEANUP_FAILED')
            error.a42331_cleanup_codes = cleanup_codes
            raise error from None
