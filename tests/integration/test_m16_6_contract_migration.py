import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from app.core.db import SessionLocal
from app.models.agent_archive import AgentToolResultArchive, AgentTurnArchiveManifest
from app.models.agent_chat import AgentChatToolCall, AgentChatTurn
from app.models.agent_frozen_contract import (
    AgentFrozenContractManifest,
    AgentFrozenResearchContract,
)
from sqlalchemy.exc import DBAPIError
from test_m16_4_research_reports import _cleanup, _source, _user
from test_m16_5_archive_migration import cleanup_archives


def test_0052_empty_roundtrip_owner_fks_uniqueness_and_immutability():
    config = Config("alembic.ini")
    command.downgrade(config, "0051_m16_5_evidence_archive")
    command.upgrade(config, "head")
    with SessionLocal() as db:
        assert db.scalar(sa.text("SELECT version_num FROM alembic_version")) == (
            "0053_m17_decision_paper_foundation"
        )
        owner = _user(db, "contract-migration")
        other = _user(db, "contract-other")
        owner_id, other_id = owner.id, other.id
        try:
            chat_id, assistant_id = _source(db, owner, value="0.2")
            turn = db.scalar(sa.select(AgentChatTurn).where(AgentChatTurn.session_id == chat_id))
            db.add(
                AgentChatToolCall(
                    turn_id=turn.id,
                    tool_call_id="contract-call",
                    tool_name="performance.summary",
                    args_hash="a" * 64,
                    status="READY",
                    evidence_ids_json=[],
                    duration_ms=0,
                    cache_reused=False,
                )
            )
            db.flush()
            tool = AgentToolResultArchive(
                owner_user_id=owner_id,
                chat_id=chat_id,
                turn_id=turn.id,
                tool_call_id="contract-call",
                tool_name="performance.summary",
                tool_version="1.0",
                archive_schema_version="m16.5-archive-v1",
                projector_version="m16.5-content-projector-v1",
                arguments_json={},
                input_schema_json={},
                arguments_hash="a" * 64,
                registry_schema_hash="b" * 64,
                payload_json={"records": []},
                payload_hash="c" * 64,
                payload_size_bytes=16,
                status="READY",
            )
            db.add(tool)
            manifest = AgentTurnArchiveManifest(
                owner_user_id=owner_id,
                chat_id=chat_id,
                turn_id=turn.id,
                assistant_message_id=assistant_id,
                manifest_version="m16.5-archive-v1",
                archive_status="COMPLETE",
                manifest_json={"fixture": True},
                manifest_hash="d" * 64,
                claim_digest="e" * 64,
                compiled_message_digest="f" * 64,
            )
            db.add(manifest)
            db.commit()

            contract_values = dict(
                owner_user_id=owner_id,
                chat_id=chat_id,
                turn_id=turn.id,
                tool_result_archive_id=tool.id,
                contract_kind="M14_EXACT_BUNDLE",
                subject_id=str(uuid.uuid4()),
                role="LIVE",
                schema_version="m16.6-m14-bundle-v1",
                verification_scope="FROZEN_CONTRACT_RECHECK",
                contract_json={"test": True},
                contract_hash="1" * 64,
                size_bytes=14,
            )
            contract = AgentFrozenResearchContract(**contract_values)
            db.add(contract)
            db.flush()
            child = AgentFrozenContractManifest(
                owner_user_id=owner_id,
                chat_id=chat_id,
                turn_id=turn.id,
                base_manifest_id=manifest.id,
                base_manifest_hash=manifest.manifest_hash,
                contract_ids_hash="2" * 64,
                contract_count=1,
                policy_version="m16.6-contract-manifest-v1",
                manifest_json={"test": True},
                manifest_hash="3" * 64,
            )
            db.add(child)
            db.flush()
            for statement in (
                sa.insert(AgentFrozenResearchContract).values(
                    **{**contract_values, "id": uuid.uuid4(), "owner_user_id": other_id}
                ),
                sa.insert(AgentFrozenResearchContract).values(
                    **{**contract_values, "id": uuid.uuid4()}
                ),
                sa.update(AgentFrozenResearchContract)
                .where(AgentFrozenResearchContract.id == contract.id)
                .values(contract_json={"rewritten": True}),
                sa.delete(AgentFrozenResearchContract).where(
                    AgentFrozenResearchContract.id == contract.id
                ),
                sa.update(AgentFrozenContractManifest)
                .where(AgentFrozenContractManifest.id == child.id)
                .values(contract_count=2),
                sa.delete(AgentFrozenContractManifest).where(
                    AgentFrozenContractManifest.id == child.id
                ),
            ):
                with pytest.raises(DBAPIError), db.begin_nested():
                    db.execute(statement)
                    db.flush()
            db.rollback()
        finally:
            db.rollback()
            cleanup_archives(owner_id)
            _cleanup(other_id)
