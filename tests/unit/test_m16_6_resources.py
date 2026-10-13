import time
import uuid
from types import SimpleNamespace

import pytest
from app.core.agent_frozen_contract_config import AgentFrozenContractConfig
from app.domain.agent.archive import AgentArchiveError
from app.repositories.agent_frozen_contract import AgentFrozenContractRepository
from app.services.agent.contracts.application import AgentFrozenContractApplication
from app.services.agent.contracts.integrity import verify_contract_archive
from test_m16_6_contract_integrity import synthetic_archive


@pytest.mark.parametrize("count,size", [(101, 1), (1, 1048577)])
def test_preflight_limits_refuse_before_loading_contract_json(count, size):
    class DB:
        def scalar(self, query):
            return SimpleNamespace(contract_count=count)

        def execute(self, query):
            return SimpleNamespace(one=lambda: (count, size))

        def scalars(self, query):
            pytest.fail("large JSON rows must not be fetched")

    with pytest.raises(AgentArchiveError) as caught:
        AgentFrozenContractRepository(DB()).load_for_turn(
            owner_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            config=AgentFrozenContractConfig(),
        )
    assert caught.value.code == "CONTRACT_LIMIT_EXCEEDED"


def test_expired_shared_deadline_refuses_before_database_access():
    settings = SimpleNamespace(
        agent_config=SimpleNamespace(frozen_contract=AgentFrozenContractConfig())
    )
    with pytest.raises(AgentArchiveError) as caught:
        AgentFrozenContractApplication(None, settings).check_turn(
            owner_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            deadline=time.monotonic() - 1,
        )
    assert caught.value.status_code == 504


def test_offline_contract_check_observes_budget_callback():
    manifest, rows, base = synthetic_archive()

    def expired():
        raise AgentArchiveError("CONTRACT_VERIFY_TIMEOUT", "synthetic budget", status_code=504)

    with pytest.raises(AgentArchiveError) as caught:
        verify_contract_archive(manifest, rows, base, AgentFrozenContractConfig(), expired)
    assert caught.value.status_code == 504
