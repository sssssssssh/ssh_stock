import json
from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from app.domain.agent.chat_errors import AgentChatError
from app.domain.agent.contracts import PerformanceSummaryInput
from app.models.agent_archive import AgentTurnArchiveManifest
from app.models.agent_chat import AgentChatMessage, AgentChatTurn
from app.models.agent_frozen_contract import (
    AgentFrozenContractManifest,
    AgentFrozenResearchContract,
)
from app.repositories.agent_frozen_contract import AgentFrozenContractRepository
from app.services.agent.adapters.research import ResearchAgentAdapter
from app.services.agent.chat.application import AgentChatApplication
from app.services.agent.contracts.application import AgentFrozenContractApplication
from app.services.agent.llm.contracts import LLMResponse, ToolCall
from app.services.agent.llm.fake import FakeLLMProvider
from app.services.performance.period_application import PerformancePeriodApplicationService
from m14_4_support import seed_analytics_case
from m16_6_support import isolated_contract_database
from test_m16_2_agent_chat import _enabled_settings, _user


def _case_and_provider(db, *, benchmark_code="000300.SH"):
    dates = tuple(date(2087, 1, 2) + timedelta(days=day) for day in range(7))
    case = seed_analytics_case(db, dates, benchmark_code=benchmark_code)
    PerformancePeriodApplicationService(db).calculate_now(
        case.run_id,
        performance_id=case.performance_id,
        risk_id=case.risk_id,
        trade_id=case.trade_id,
    )
    db.commit()
    result = ResearchAgentAdapter(db).performance_summary(
        PerformanceSummaryInput(report_id=case.performance_id)
    )
    ref = result.evidence[0]
    db.rollback()
    provider = FakeLLMProvider(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="m14-call",
                        name="performance.summary",
                        arguments={"report_id": str(case.performance_id)},
                    )
                ]
            ),
            LLMResponse(
                final_text=json.dumps(
                    {
                        "answer": "verified",
                        "evidence_ids": [],
                        "warnings": [],
                        "needs_clarification": False,
                        "claims": [
                            {
                                "claim_id": "return-fact",
                                "claim_type": "FACT",
                                "text": "verified",
                                "evidence_ids": [ref.evidence_id],
                                "structured_facts": [
                                    {
                                        "path": "records.0.performance.annualized_return",
                                        "value": str(
                                            result.records[0]["performance"]["annualized_return"]
                                        ),
                                        "unit": "decimal",
                                        "trade_date": dates[-1].isoformat(),
                                        "entity": str(case.run_id),
                                        "sample_role": "LIVE",
                                    }
                                ],
                            }
                        ],
                    }
                )
            ),
        ]
    )
    return provider


@pytest.mark.parametrize("fail_insert", [False, "before", "after_manifest"])
def test_real_readonly_tool_capture_atomic_commit_replay_and_failure(monkeypatch, fail_insert):
    with isolated_contract_database(monkeypatch) as (factory, engine):
        with factory() as db:
            fake = _case_and_provider(db)
            settings = _enabled_settings()
            settings.agent_config.archive.enabled = True
            settings.agent_config.frozen_contract.enabled = True
            user = _user(db, suffix="m166-atomic")
            service = AgentChatApplication(db, settings, provider=fake)
            chat = service.create_chat(user=user, title="Synthetic M16.6 test")
            if fail_insert:
                original_insert = AgentFrozenContractRepository.insert_drafts

                def fail(repository, *args, **kwargs):
                    if fail_insert == "after_manifest":
                        original_insert(repository, *args, **kwargs)
                        for model in (AgentFrozenResearchContract, AgentFrozenContractManifest):
                            assert (
                                repository.db.scalar(sa.select(sa.func.count()).select_from(model))
                                == 1
                            )
                    raise RuntimeError("synthetic contract write failure")

                monkeypatch.setattr(
                    "app.repositories.agent_frozen_contract.AgentFrozenContractRepository"
                    ".insert_drafts",
                    fail,
                )
                with pytest.raises(AgentChatError):
                    service.send_message(
                        user=user, chat_id=chat.chat_id, content="核验收益", request_id="frozen"
                    )
            else:
                answer = service.send_message(
                    user=user, chat_id=chat.chat_id, content="核验收益", request_id="frozen"
                )
                assert answer.status == "COMPLETED"
                replay = service.send_message(
                    user=user, chat_id=chat.chat_id, content="核验收益", request_id="frozen"
                )
                assert replay.message_id == answer.message_id
                turn = db.scalar(sa.select(AgentChatTurn))
                frozen = AgentFrozenContractApplication(db, settings).check_turn(
                    owner_id=user.id, turn_id=turn.id
                )
                assert frozen.check["contract_semantics"]["status"] == "VERIFIED"
                assert frozen.check["archive_integrity"]["status"] == "VERIFIED"
                assert frozen.check["calculation_reproduced"] is False
                frozen_hash = frozen.manifest.manifest_hash
                db.rollback()
                with pytest.raises(RuntimeError, match="frozen contracts exist"):
                    with engine.begin() as connection:
                        migration = Config("alembic.ini")
                        migration.attributes["connection"] = connection
                        command.downgrade(migration, "0051_m16_5_evidence_archive")
                again = AgentFrozenContractApplication(db, settings).check_turn(
                    owner_id=user.id, turn_id=turn.id
                )
                assert again.manifest.manifest_hash == frozen_hash
            for model in (
                AgentTurnArchiveManifest,
                AgentFrozenContractManifest,
                AgentFrozenResearchContract,
            ):
                count = db.scalar(sa.select(sa.func.count()).select_from(model))
                assert count == (0 if fail_insert else 1)
            turn = db.scalar(sa.select(AgentChatTurn))
            assert turn.status == ("FAILED" if fail_insert else "COMPLETED")
            assert db.scalar(
                sa.select(sa.func.count())
                .select_from(AgentChatMessage)
                .where(AgentChatMessage.role == "ASSISTANT")
            ) == (0 if fail_insert else 1)
