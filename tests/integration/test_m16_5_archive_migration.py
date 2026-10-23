import uuid
from copy import deepcopy

import pytest
import sqlalchemy as sa
from app.core.db import SessionLocal
from app.models.agent_archive import (
    AgentEvidenceArchiveBinding,
    AgentToolResultArchive,
    AgentTurnArchiveManifest,
)
from app.models.agent_chat import AgentChatToolCall, AgentChatTurn
from sqlalchemy.exc import DBAPIError
from test_m16_4_research_reports import _cleanup, _source, _user


def cleanup_archives(owner_id, session_factory=None):
    factory = session_factory or SessionLocal
    with factory() as db:
        for model in (
            AgentTurnArchiveManifest,
            AgentEvidenceArchiveBinding,
            AgentToolResultArchive,
        ):
            db.execute(sa.delete(model).where(model.owner_user_id == owner_id))
        db.commit()
    _cleanup(owner_id, session_factory=factory)


def test_empty_archive_roundtrip_restores_head(archive_migration_database):
    owned = archive_migration_database
    assert owned.counts() == dict.fromkeys(
        ('agent_tool_result_archive','agent_evidence_archive_binding','agent_turn_archive_manifest'),0)
    owned.migrate('downgrade','0050_m16_4_reports')
    owned.migrate('upgrade','head')
    with owned.engine.connect() as db:
        assert owned.verify(db)['revision'] == '0058_data_publication'


@pytest.mark.parametrize('kind',['tool','binding_with_parent','manifest'])
def test_each_valid_archive_presence_refuses_downgrade_without_data_loss(
    archive_migration_database,kind,
):
    owned = archive_migration_database
    with owned.factory() as db:
        user = _user(db,'guard-'+kind)
        chat_id,message_id = _source(db,user,value='0.1')
        turn = db.scalar(sa.select(AgentChatTurn).where(AgentChatTurn.session_id == chat_id))
        if kind != 'manifest':
            db.add(AgentChatToolCall(turn_id=turn.id,tool_call_id='guard-call',
                tool_name='market.snapshot',args_hash='a'*64,status='READY',
                evidence_ids_json=['guard-evidence'],duration_ms=0,cache_reused=False))
            db.flush()
            tool = AgentToolResultArchive(owner_user_id=user.id,chat_id=chat_id,turn_id=turn.id,
                tool_call_id='guard-call',tool_name='market.snapshot',tool_version='1.0',
                archive_schema_version='m16.5-archive-v1',projector_version='m16.5-content-projector-v1',
                arguments_json={},input_schema_json={},arguments_hash='a'*64,
                registry_schema_hash='b'*64,payload_json={'fixture':True},payload_hash='c'*64,
                payload_size_bytes=17,status='READY')
            db.add(tool)
            db.flush()
            if kind == 'binding_with_parent':
                db.add(AgentEvidenceArchiveBinding(owner_user_id=user.id,chat_id=chat_id,
                    turn_id=turn.id,tool_result_archive_id=tool.id,evidence_id='guard-evidence',
                    ref_json={},ref_hash='a'*64,source_projection_json={},
                    source_projection_hash='b'*64,projection_version='m16.5-content-projector-v1',
                    record_path='records.0'))
        else:
            db.add(AgentTurnArchiveManifest(owner_user_id=user.id,chat_id=chat_id,turn_id=turn.id,
                assistant_message_id=message_id,manifest_version='m16.5-archive-v1',
                archive_status='COMPLETE',manifest_json={'fixture':True},manifest_hash='a'*64,
                claim_digest='b'*64,compiled_message_digest='c'*64))
        db.commit()
    counts = owned.counts()  # New connection: committed data, before any migration DDL.
    assert counts == dict(agent_tool_result_archive=0 if kind == 'manifest' else 1,
        agent_evidence_archive_binding=int(kind == 'binding_with_parent'),
        agent_turn_archive_manifest=int(kind == 'manifest'))
    with pytest.raises(RuntimeError,match='archive data exists'):
        owned.migrate('downgrade','0050_m16_4_reports')
    assert owned.counts() == counts
    with owned.engine.connect() as db:
        assert owned.verify(db)['revision'] == '0058_data_publication'


def test_different_uuid_database_fails_closed_before_any_migration(archive_migration_database):
    from scripts.a42331_migration_contract import owned_migration_database

    left = archive_migration_database
    with owned_migration_database() as right, left.factory() as session:
        with right.engine.connect() as connection:
            with pytest.raises(RuntimeError,match='DATABASE_IDENTITY_MISMATCH'):
                left.assert_same(session,connection)
        assert right.counts() == dict.fromkeys(
            ('agent_tool_result_archive','agent_evidence_archive_binding',
             'agent_turn_archive_manifest'),0)


@pytest.mark.parametrize('import_late',[False,True])
def test_import_order_and_settings_cache_never_redirect_explicit_migration(
    archive_migration_database,import_late,
):
    import os
    import subprocess
    import sys

    from scripts.a42331_migration_contract import owned_migration_database

    left = archive_migration_database
    with owned_migration_database() as right:
        code = '''
import os,sys
sys.path.insert(0,'backend')
from sqlalchemy import create_engine
from scripts.v14_test_database import verified_test_url
verified_test_url()
from app.core.config import Settings,get_settings
Settings.model_config['env_file']=None
get_settings.cache_clear()
from app.core.db import SessionLocal
from scripts.a42331_migration_contract import OwnedMigration
os.environ['DATABASE_URL']=os.environ['A42331_OTHER_URL']
get_settings.cache_clear()
assert get_settings().database_url==os.environ['A42331_OTHER_URL']
engine=create_engine(os.environ['A42331_TARGET_URL'],hide_parameters=True)
owned=OwnedMigration(engine,os.environ['A42331_PHYSICAL_HASH'],os.environ['A42331_TARGET_NAME'])
with SessionLocal() as session,engine.connect() as connection:
    try:
        owned.assert_same(session,connection)
    except RuntimeError as error:
        assert str(error)=='A42331_DATABASE_IDENTITY_MISMATCH'
        assert os.environ['A42331_IMPORT_LATE']=='True'
    else:
        assert os.environ['A42331_IMPORT_LATE']=='False'
owned.migrate('upgrade','head')
engine.dispose()
print('A42331_EXPLICIT_CONNECTION_PRESERVED')
'''
        a = left.engine.url.render_as_string(hide_password=False)
        b = right.engine.url.render_as_string(hide_password=False)
        env = dict(os.environ,DATABASE_URL=b if import_late else a,
            A42331_OTHER_URL=a if import_late else b,A42331_TARGET_URL=a,
            A42331_PHYSICAL_HASH=left.proof,A42331_TARGET_NAME=left.name,
            A42331_IMPORT_LATE=str(import_late))
        result = subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,
                                text=True,timeout=30)
        assert result.returncode == 0, 'A42331_IMPORT_ORDER_CHILD_FAILED'
        assert result.stdout.strip() == 'A42331_EXPLICIT_CONNECTION_PRESERVED'


def test_0051_empty_upgrade_downgrade_and_real_archive_owner_constraints(
    archive_migration_database,
):
    owned = archive_migration_database
    owned.migrate('downgrade', '0049_m16_2_1_hash_name')
    owned.migrate('upgrade', 'head')
    with owned.factory() as db:
        assert (
            db.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0058_data_publication"
        )
        owner = _user(db, "archive-migration")
        other = _user(db, "archive-other")
        owner_id, other_id = owner.id, other.id
        try:
            chat_id, message_id = _source(db, owner, value="0.1")
            turn = db.scalar(sa.select(AgentChatTurn).where(AgentChatTurn.session_id == chat_id))
            db.add(
                AgentChatToolCall(
                    turn_id=turn.id,
                    tool_call_id="migration-call",
                    tool_name="market.snapshot",
                    args_hash="a" * 64,
                    status="READY",
                    evidence_ids_json=["test-evidence"],
                    duration_ms=0,
                    cache_reused=False,
                )
            )
            db.commit()
            values = dict(
                owner_user_id=owner_id,
                chat_id=chat_id,
                turn_id=turn.id,
                tool_call_id="migration-call",
                tool_name="market.snapshot",
                tool_version="1.0",
                archive_schema_version="m16.5-archive-v1",
                projector_version="m16.5-content-projector-v1",
                arguments_json={},
                input_schema_json={},
                arguments_hash="a" * 64,
                registry_schema_hash="b" * 64,
                payload_json={"fixture": True},
                payload_hash="c" * 64,
                payload_size_bytes=17,
                status="READY",
            )
            with pytest.raises(DBAPIError):
                db.execute(
                    sa.insert(AgentToolResultArchive).values(
                        **{**values, "owner_user_id": other_id}
                    )
                )
                db.commit()
            db.rollback()
            row = AgentToolResultArchive(**values)
            db.add(row)
            db.commit()
            for changes in (
                {"tool_call_id": "missing-audit"},
                {"payload_hash": "bad"},
                {"payload_size_bytes": 65537},
            ):
                with pytest.raises(DBAPIError):
                    db.execute(sa.insert(AgentToolResultArchive).values(**{**values, **changes}))
                    db.commit()
                db.rollback()
            binding_values = dict(
                owner_user_id=owner_id,
                chat_id=chat_id,
                turn_id=turn.id,
                tool_result_archive_id=row.id,
                evidence_id="test-evidence",
                ref_json={},
                ref_hash="a" * 64,
                source_projection_json={},
                source_projection_hash="b" * 64,
                projection_version="m16.5-content-projector-v1",
                record_path="records.0",
            )
            with pytest.raises(DBAPIError):
                db.execute(
                    sa.insert(AgentEvidenceArchiveBinding).values(
                        **{**binding_values, "tool_result_archive_id": uuid.uuid4()}
                    )
                )
                db.commit()
            db.rollback()
            binding = AgentEvidenceArchiveBinding(**binding_values)
            db.add(binding)
            manifest = AgentTurnArchiveManifest(
                owner_user_id=owner_id,
                chat_id=chat_id,
                turn_id=turn.id,
                assistant_message_id=message_id,
                manifest_version="m16.5-archive-v1",
                archive_status="COMPLETE",
                manifest_json={"fixture": True},
                manifest_hash="a" * 64,
                claim_digest="b" * 64,
                compiled_message_digest="c" * 64,
            )
            db.add(manifest)
            db.commit()
            frozen = deepcopy(row.payload_json)
            for model, row_id, change in (
                (AgentToolResultArchive, row.id, {"payload_json": {}}),
                (AgentEvidenceArchiveBinding, binding.id, {"ref_json": {"rewrite": True}}),
                (AgentTurnArchiveManifest, manifest.id, {"manifest_json": {}}),
            ):
                with pytest.raises(DBAPIError):
                    db.execute(sa.update(model).where(model.id == row_id).values(**change))
                    db.commit()
                db.rollback()
            db.refresh(row)
            assert row.payload_json == frozen
            # 0052 downgrade runs DDL before 0051 checks for existing archives.
            # Release this session's read locks so the downgrade can reach that guard.
            db.rollback()
            assert owned.counts() == {
                'agent_tool_result_archive':1,'agent_evidence_archive_binding':1,
                'agent_turn_archive_manifest':1}
            with pytest.raises(RuntimeError, match="archive data exists"):
                owned.migrate('downgrade', '0050_m16_4_reports')
            assert (
                db.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == "0058_data_publication"
            )
        finally:
            db.rollback()
            cleanup_archives(owner_id, session_factory=owned.factory)
            _cleanup(other_id, session_factory=owned.factory)
