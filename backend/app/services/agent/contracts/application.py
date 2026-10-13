import time

from sqlalchemy import text

from app.domain.agent.archive import archive_error
from app.repositories.agent_frozen_contract import AgentFrozenContractRepository
from app.services.agent.archive.application import AgentArchiveApplication
from app.services.agent.archive.recheck import recheck_archive
from app.services.agent.contracts.integrity import missing_contracts, verify_contract_archive


class AgentFrozenContractApplication:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings
        self.config = settings.agent_config.frozen_contract
        self.repo = AgentFrozenContractRepository(db)

    def check_turn(
        self, *, owner_id, turn_id, expected_reference=None, deadline=None, base_bundle=None
    ):
        self._deadline = deadline or time.monotonic() + self.config.verify_timeout_seconds
        self._check_budget()
        if self.db.get_bind().dialect.name == "postgresql":
            timeout_ms = min(
                self.settings.agent_config.statement_timeout_ms,
                max(1, int((self._deadline - time.monotonic()) * 1000)),
            )
            self.db.execute(
                text("SELECT set_config('statement_timeout', :timeout, true)"),
                {
                    "timeout": f"{timeout_ms}ms",
                },
            )
        manifest, rows = self.repo.load_for_turn(
            owner_id=owner_id, turn_id=turn_id, config=self.config, check_budget=self._check_budget
        )
        if manifest is None:
            if expected_reference is not None:
                raise archive_error("REPORT_CONTRACT_BINDING_MISMATCH")
            return missing_contracts()
        if expected_reference is not None and (
            str(manifest.id) != str(expected_reference["manifest_id"])
            or manifest.manifest_hash != expected_reference["manifest_hash"]
            or manifest.policy_version != expected_reference["policy_version"]
        ):
            raise archive_error("REPORT_CONTRACT_BINDING_MISMATCH")
        archive = AgentArchiveApplication(self.db, self.settings)
        archive._deadline = self._deadline
        base = base_bundle if base_bundle is not None else archive.load_bundle(owner_id, turn_id)
        if base is None:
            raise archive_error("CONTRACT_BASE_ARCHIVE_MISSING")
        facts = recheck_archive(
            base,
            config=archive.config,
            started_at=self._deadline - archive.config.verify_timeout_seconds,
        )
        if (
            facts["integrity"]["status"] == "MISMATCH"
            or facts["fact_recheck"]["status"] == "MISMATCH"
        ):
            raise archive_error("CONTRACT_FROZEN_FACT_MISMATCH")
        self._check_budget()
        result = verify_contract_archive(manifest, rows, base, self.config, self._check_budget)
        result.check["archive_integrity"] = facts["integrity"]
        result.check["frozen_fact_recheck"] = {
            "status": facts["fact_recheck"]["status"],
            "policy_version": facts["fact_recheck"].get("policy_version"),
        }
        self._check_budget()
        return result

    def _check_budget(self):
        if time.monotonic() >= self._deadline:
            raise archive_error("CONTRACT_VERIFY_TIMEOUT", status_code=504)
