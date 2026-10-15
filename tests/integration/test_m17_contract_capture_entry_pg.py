import pytest
import sqlalchemy as sa
from app.core.agent_frozen_contract_config import AgentFrozenContractConfig
from app.domain.agent.archive import AgentArchiveError
from app.domain.agent.frozen_contracts import M14_CONTRACT_VERSION, FrozenContractDraft
from app.models.agent_archive import AgentToolResultArchive, AgentTurnArchiveManifest
from app.models.agent_chat import AgentChatMessage, AgentChatTurn
from app.models.agent_frozen_contract import (
    AgentFrozenContractManifest,
    AgentFrozenResearchContract,
)
from app.repositories.agent_frozen_contract import AgentFrozenContractRepository
from app.services.agent.chat.application import AgentChatApplication
from app.services.agent.llm.contracts import LLMResponse, ToolCall
from app.services.agent.llm.fake import FakeLLMProvider
from m16_6_support import isolated_contract_database
from test_m16_2_agent_chat import _enabled_settings, _user
from test_m16_6_contract_atomic import _case_and_provider
from test_m16_6_window_end_to_end import seed_window


def test_real_chat_37_windows_refuses_before_bulk_contract_collection_and_archive_write(
    monkeypatch,
):
    with isolated_contract_database(monkeypatch) as (factory, _):
        with factory() as db:
            study_id, validation_id, _ = seed_window(db, window_count=37)
            settings = _enabled_settings()
            settings.agent_config.archive.enabled = True
            settings.agent_config.frozen_contract.enabled = True
            user = _user(db, suffix="m17-capacity")
            provider = FakeLLMProvider([LLMResponse(tool_calls=[ToolCall(
                id="windows", name="walk_forward.window_lineage",
                arguments={"study_id": str(study_id), "validation_id": str(validation_id),
                           "limit": 37},
            )])])
            service = AgentChatApplication(db, settings, provider=provider)
            chat = service.create_chat(user=user, title="Synthetic capacity acceptance")

            def refuse_bulk(*args, **kwargs):
                pytest.fail("over-budget windows must be refused before M14/M15 bulk collection")

            monkeypatch.setattr("app.services.agent.contracts.m15._rows", refuse_bulk)
            with pytest.raises(AgentArchiveError) as caught:
                service.send_message(
                    user=user, chat_id=chat.chat_id, content="Synthetic windows",
                    request_id="37-windows",
                )
            assert caught.value.code == "CONTRACT_LIMIT_EXCEEDED"
            for model in (
                AgentTurnArchiveManifest, AgentToolResultArchive,
                AgentFrozenResearchContract, AgentFrozenContractManifest,
            ):
                assert db.scalar(sa.select(sa.func.count()).select_from(model)) == 0
            turn = db.scalar(sa.select(AgentChatTurn))
            assert turn.status == "FAILED" and turn.error_code == "CONTRACT_LIMIT_EXCEEDED"
            assert db.scalar(sa.select(sa.func.count()).select_from(AgentChatMessage).where(
                AgentChatMessage.role == "ASSISTANT"
            )) == 0


def _draft(number, *, payload="gap", subject_length=0):
    return FrozenContractDraft(
        tool_call_id="m14-call", contract_kind="M14_EXACT_BUNDLE",
        subject_id=("budget-" + str(number)).ljust(subject_length, "x"), role="LIVE",
        schema_version=M14_CONTRACT_VERSION, verification_scope="FROZEN_CONTRACT_RECHECK",
        contract_json={"status": "GAP", "reason_codes": [payload]},
    )


def test_real_pg_all_contract_and_manifest_budgets_refuse_before_first_insert(monkeypatch):
    with isolated_contract_database(monkeypatch) as (factory, engine):
        with factory() as db:
            provider = _case_and_provider(db)
            settings = _enabled_settings()
            settings.agent_config.archive.enabled = True
            settings.agent_config.frozen_contract.enabled = True
            user = _user(db, suffix="m17-bytes")
            service = AgentChatApplication(db, settings, provider=provider)
            chat = service.create_chat(user=user, title="Synthetic byte budget acceptance")
            service.send_message(
                user=user, chat_id=chat.chat_id, content="Synthetic facts", request_id="baseline",
            )
            base = db.scalar(sa.select(AgentTurnArchiveManifest))
            tool = db.scalar(sa.select(AgentToolResultArchive))
            assert tool.tool_call_id == "m14-call"
            original = _frozen_hashes(db)
            cases = [
                ("single", [_draft(0), _draft(1, payload="x" * 131072)],
                 AgentFrozenContractConfig()),
                ("turn", [_draft(n, payload="x" * 120000) for n in range(9)],
                 AgentFrozenContractConfig()),
                ("manifest", [_draft(n, subject_length=160) for n in range(160)],
                 AgentFrozenContractConfig(max_contracts=200)),
            ]
            inserts = []

            def record_insert(connection, cursor, statement, parameters, context, executemany):
                if statement.lstrip().upper().startswith("INSERT") and any(
                    name in statement for name in (
                        "agent_frozen_research_contract", "agent_frozen_contract_manifest"
                    )
                ):
                    inserts.append(statement)

            sa.event.listen(engine, "before_cursor_execute", record_insert)
            try:
                for name, drafts, config in cases:
                    with pytest.raises(AgentArchiveError) as caught:
                        AgentFrozenContractRepository(db).insert_drafts(
                            base_manifest=base, drafts=drafts, config=config,
                        )
                    assert caught.value.code == "CONTRACT_LIMIT_EXCEEDED", name
                    assert inserts == [], name
                    assert _frozen_hashes(db) == original, name
                    db.commit()
            finally:
                sa.event.remove(engine, "before_cursor_execute", record_insert)
            assert _frozen_hashes(db) == original


def _frozen_hashes(db):
    return (
        tuple(db.execute(sa.select(
            AgentTurnArchiveManifest.id, AgentTurnArchiveManifest.manifest_hash,
        ).order_by(AgentTurnArchiveManifest.id))),
        tuple(db.execute(sa.select(
            AgentToolResultArchive.id, AgentToolResultArchive.payload_hash,
        ).order_by(AgentToolResultArchive.id))),
        tuple(db.execute(sa.select(
            AgentFrozenResearchContract.id, AgentFrozenResearchContract.contract_hash,
        ).order_by(AgentFrozenResearchContract.id))),
        tuple(db.execute(sa.select(
            AgentFrozenContractManifest.id, AgentFrozenContractManifest.manifest_hash,
        ).order_by(AgentFrozenContractManifest.id))),
    )
