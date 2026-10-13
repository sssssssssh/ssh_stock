from collections.abc import Sequence

from sqlalchemy import Text, cast, func, select
from sqlalchemy.orm import Session

from app.core.agent_frozen_contract_config import AgentFrozenContractConfig
from app.domain.agent.archive import archive_error
from app.domain.agent.frozen_contracts import CONTRACT_MANIFEST_VERSION, FrozenContractDraft
from app.models.agent_archive import AgentToolResultArchive, AgentTurnArchiveManifest
from app.models.agent_frozen_contract import (
    AgentFrozenContractManifest,
    AgentFrozenResearchContract,
)
from app.services.agent.contracts.canonical import (
    contract_hash,
    contract_json,
    contract_storage_size,
)


class AgentFrozenContractRepository:
    def __init__(self, db: Session):
        self.db = db

    def load_for_turn(self, *, owner_id, turn_id, config, check_budget=lambda: None):
        check_budget()
        manifest = self.db.scalar(
            select(AgentFrozenContractManifest).where(
                AgentFrozenContractManifest.owner_user_id == owner_id,
                AgentFrozenContractManifest.turn_id == turn_id,
            )
        )
        count, size = self.db.execute(
            select(
                func.count(),
                func.coalesce(
                    func.sum(
                        func.octet_length(cast(AgentFrozenResearchContract.contract_json, Text))
                    ),
                    0,
                ),
            ).where(
                AgentFrozenResearchContract.owner_user_id == owner_id,
                AgentFrozenResearchContract.turn_id == turn_id,
            )
        ).one()
        check_budget()
        if count > config.max_contracts or size > config.max_turn_bytes:
            raise archive_error("CONTRACT_LIMIT_EXCEEDED")
        if manifest is None:
            if count:
                raise archive_error("CONTRACT_MANIFEST_MISSING")
            return None, []
        if count != manifest.contract_count:
            raise archive_error("CONTRACT_SET_MISMATCH")
        rows = list(
            self.db.scalars(
                select(AgentFrozenResearchContract)
                .where(
                    AgentFrozenResearchContract.owner_user_id == owner_id,
                    AgentFrozenResearchContract.turn_id == turn_id,
                )
                .limit(config.max_contracts + 1)
            )
        )
        check_budget()
        return manifest, rows

    def insert_drafts(
        self,
        *,
        base_manifest: AgentTurnArchiveManifest,
        drafts: Sequence[FrozenContractDraft],
        config: AgentFrozenContractConfig,
    ) -> AgentFrozenContractManifest | None:
        if not drafts:
            return None
        if len(drafts) > config.max_contracts:
            raise archive_error("CONTRACT_LIMIT_EXCEEDED")
        tools = {
            row.tool_call_id: row
            for row in self.db.scalars(
                select(AgentToolResultArchive).where(
                    AgentToolResultArchive.owner_user_id == base_manifest.owner_user_id,
                    AgentToolResultArchive.turn_id == base_manifest.turn_id,
                )
            )
        }
        rows = []
        keys = set()
        total_bytes = 0
        for draft in drafts:
            tool = tools.get(draft.tool_call_id)
            if tool is None or tool.status != "READY":
                raise archive_error("CONTRACT_TOOL_BINDING_MISMATCH")
            expected_tools = {
                "M14_EXACT_BUNDLE": {"performance.summary", "walk_forward.window_lineage"},
                "M15_WINDOW_LINEAGE": {"walk_forward.window_lineage"},
                "M15_STUDY_AGGREGATE": {"walk_forward.summary"},
            }[draft.contract_kind]
            if tool.tool_name not in expected_tools:
                raise archive_error("CONTRACT_TOOL_BINDING_MISMATCH")
            key = (tool.id, draft.contract_kind, draft.subject_id, draft.role)
            if key in keys:
                raise archive_error("CONTRACT_DUPLICATE_SOURCE")
            keys.add(key)
            body = contract_json(draft.contract_json)
            size = contract_storage_size(body)
            if size > config.max_contract_bytes:
                raise archive_error("CONTRACT_LIMIT_EXCEEDED")
            total_bytes += size
            row = AgentFrozenResearchContract(
                owner_user_id=base_manifest.owner_user_id,
                chat_id=base_manifest.chat_id,
                turn_id=base_manifest.turn_id,
                tool_result_archive_id=tool.id,
                contract_kind=draft.contract_kind,
                subject_id=draft.subject_id,
                role=draft.role,
                schema_version=draft.schema_version,
                verification_scope=draft.verification_scope,
                contract_json=body,
                contract_hash=contract_hash(body),
                size_bytes=size,
            )
            self.db.add(row)
            self.db.flush()
            rows.append((draft.tool_call_id, row))
        refs = [
            {
                "id": str(row.id),
                "tool_call_id": call_id,
                "tool_result_archive_id": str(row.tool_result_archive_id),
                "contract_kind": row.contract_kind,
                "subject_id": row.subject_id,
                "role": row.role,
                "schema_version": row.schema_version,
                "contract_hash": row.contract_hash,
            }
            for call_id, row in sorted(
                rows,
                key=lambda item: (item[0], item[1].contract_kind, item[1].subject_id, item[1].role),
            )
        ]
        for ref, (_, row) in zip(
            refs,
            sorted(
                rows,
                key=lambda item: (item[0], item[1].contract_kind, item[1].subject_id, item[1].role),
            ),
            strict=True,
        ):
            if row.contract_kind != "M15_WINDOW_LINEAGE":
                continue
            dependencies = []
            for endpoint in row.contract_json["m14_contract_refs"]:
                matches = [
                    candidate
                    for candidate in refs
                    if (
                        candidate["tool_result_archive_id"] == ref["tool_result_archive_id"]
                        and candidate["contract_kind"] == "M14_EXACT_BUNDLE"
                        and candidate["subject_id"] == endpoint["subject_id"]
                        and candidate["role"] == endpoint["role"]
                        and candidate["contract_hash"] == endpoint["contract_hash"]
                    )
                ]
                if len(matches) != 1:
                    raise archive_error("CONTRACT_DEPENDENCY_MISMATCH")
                dependencies.append(
                    {key: matches[0][key] for key in ("id", "role", "contract_hash")}
                )
            ref["dependencies"] = dependencies
        ids_hash = contract_hash(refs)
        body = contract_json(
            {
                "policy_version": CONTRACT_MANIFEST_VERSION,
                "base_manifest_id": str(base_manifest.id),
                "base_manifest_hash": base_manifest.manifest_hash,
                "owner_user_id": str(base_manifest.owner_user_id),
                "chat_id": str(base_manifest.chat_id),
                "turn_id": str(base_manifest.turn_id),
                "contract_count": len(refs),
                "contract_ids_hash": ids_hash,
                "contracts": refs,
            }
        )
        total_bytes += contract_storage_size(body)
        if total_bytes > config.max_turn_bytes or contract_storage_size(body) > 65536:
            raise archive_error("CONTRACT_LIMIT_EXCEEDED")
        manifest = AgentFrozenContractManifest(
            owner_user_id=base_manifest.owner_user_id,
            chat_id=base_manifest.chat_id,
            turn_id=base_manifest.turn_id,
            base_manifest_id=base_manifest.id,
            base_manifest_hash=base_manifest.manifest_hash,
            contract_ids_hash=ids_hash,
            contract_count=len(refs),
            policy_version=CONTRACT_MANIFEST_VERSION,
            manifest_json=body,
            manifest_hash=contract_hash(body),
        )
        self.db.add(manifest)
        self.db.flush()
        return manifest
