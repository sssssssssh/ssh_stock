import uuid
from copy import deepcopy

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from app.core.db import SessionLocal
from app.models.agent_archive import (
    AgentEvidenceArchiveBinding,
    AgentToolResultArchive,
    AgentTurnArchiveManifest,
)
from app.models.agent_chat import AgentChatToolCall, AgentChatTurn
from sqlalchemy.exc import DBAPIError
from test_m16_4_research_reports import _cleanup, _source, _user


def cleanup_archives(owner_id):
    with SessionLocal() as db:
        for model in (
            AgentTurnArchiveManifest,
            AgentEvidenceArchiveBinding,
            AgentToolResultArchive,
        ):
            db.execute(sa.delete(model).where(model.owner_user_id == owner_id))
        db.commit()
    _cleanup(owner_id)


def test_0051_empty_upgrade_downgrade_and_real_archive_owner_constraints():
    config = Config("alembic.ini")
    command.downgrade(config, "0049_m16_2_1_hash_name")
    command.upgrade(config, "head")
    with SessionLocal() as db:
        assert (
            db.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0057_data_queue"
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
            with pytest.raises(RuntimeError, match="archive data exists"):
                command.downgrade(config, "0050_m16_4_reports")
            assert (
                db.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == "0057_data_queue"
            )
        finally:
            db.rollback()
            cleanup_archives(owner_id)
            _cleanup(other_id)
