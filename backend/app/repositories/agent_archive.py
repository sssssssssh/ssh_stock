import uuid
from typing import Any

from sqlalchemy import Text, cast, func, select
from sqlalchemy.orm import Session

from app.domain.agent.archive import ARCHIVE_VERSION, ArchiveDraft, archive_error
from app.models.agent_archive import (
    AgentEvidenceArchiveBinding,
    AgentToolResultArchive,
    AgentTurnArchiveManifest,
)
from app.models.agent_chat import AgentChatToolCall
from app.services.agent.archive.canonical import archive_hash, archive_storage_size


def compiled_message_digest(content: str, metadata: dict[str, Any]) -> str:
    return archive_hash({"content": content, "metadata": metadata})


class AgentArchiveRepository:
    def __init__(self, db: Session):
        self.db = db

    def insert_draft(
        self, *, owner_id, chat_id, turn_id, assistant, draft: ArchiveDraft, max_turn_bytes: int
    ):
        if draft.claim_digest != archive_hash(assistant.metadata_json["verified_claims"]):
            raise archive_error("ARCHIVE_CLAIM_DIGEST_MISMATCH")
        audits = {
            row.tool_call_id: row
            for row in self.db.scalars(
                select(AgentChatToolCall).where(AgentChatToolCall.turn_id == turn_id)
            )
        }
        tool_rows = {}
        for item in draft.tools:
            audit = audits.get(item.tool_call_id)
            if (
                audit is None
                or (audit.args_hash, audit.tool_name, audit.status)
                != (item.arguments_hash, item.tool_name, "READY")
                or set(audit.evidence_ids_json)
                != {ref["evidence_id"] for ref in item.payload_json["evidence"]}
            ):
                raise archive_error("ARCHIVE_AUDIT_MISMATCH")
            if bool(item.cache_origin_call_id) != audit.cache_reused or (
                item.cache_origin_call_id is not None and item.cache_origin_call_id not in audits
            ):
                raise archive_error("ARCHIVE_CACHE_ORIGIN_MISMATCH")
            row = AgentToolResultArchive(
                owner_user_id=owner_id,
                chat_id=chat_id,
                turn_id=turn_id,
                **item.model_dump(mode="python"),
            )
            self.db.add(row)
            self.db.flush()
            tool_rows[item.tool_call_id] = row
        binding_rows = []
        for item in draft.bindings:
            data = item.model_dump(mode="python", exclude={"tool_call_id"})
            row = AgentEvidenceArchiveBinding(
                owner_user_id=owner_id,
                chat_id=chat_id,
                turn_id=turn_id,
                tool_result_archive_id=tool_rows[item.tool_call_id].id,
                **data,
            )
            self.db.add(row)
            self.db.flush()
            binding_rows.append(row)
        digest = compiled_message_digest(assistant.content, assistant.metadata_json)
        body = {
            "manifest_version": ARCHIVE_VERSION,
            "owner_user_id": str(owner_id),
            "chat_id": str(chat_id),
            "turn_id": str(turn_id),
            "assistant_message_id": str(assistant.id),
            "archive_status": draft.archive_status,
            "required_evidence_ids": draft.required_evidence_ids,
            "claim_digest": draft.claim_digest,
            "compiled_message_digest": digest,
            "tools": [
                item.model_dump(
                    mode="json", exclude={"payload_json", "arguments_json", "input_schema_json"}
                )
                for item in draft.tools
            ],
            "bindings": [
                item.model_dump(mode="json", exclude={"ref_json", "source_projection_json"})
                for item in draft.bindings
            ],
        }
        total = (
            sum(archive_storage_size(item.model_dump(mode="json")) for item in draft.tools)
            + sum(archive_storage_size(item.model_dump(mode="json")) for item in draft.bindings)
            + archive_storage_size(body)
        )
        if total > max_turn_bytes:
            raise archive_error("ARCHIVE_LIMIT_EXCEEDED")
        manifest = AgentTurnArchiveManifest(
            owner_user_id=owner_id,
            chat_id=chat_id,
            turn_id=turn_id,
            assistant_message_id=assistant.id,
            manifest_version=ARCHIVE_VERSION,
            archive_status=draft.archive_status,
            manifest_json=body,
            manifest_hash=archive_hash(body),
            claim_digest=draft.claim_digest,
            compiled_message_digest=digest,
        )
        self.db.add(manifest)
        self.db.flush()
        return manifest

    def manifest_for_turn(self, owner_id: uuid.UUID, turn_id: uuid.UUID):
        return self.db.scalar(
            select(AgentTurnArchiveManifest).where(
                AgentTurnArchiveManifest.owner_user_id == owner_id,
                AgentTurnArchiveManifest.turn_id == turn_id,
            )
        )

    def load_evidence(
        self,
        owner_id,
        turn_id,
        *,
        max_calls=16,
        max_bindings=100,
        max_bytes=1048576,
        check_budget=lambda: None,
    ):
        check_budget()
        total = 0
        for model, fields, limit in (
            (
                AgentToolResultArchive,
                ("payload_json", "arguments_json", "input_schema_json"),
                max_calls,
            ),
            (AgentEvidenceArchiveBinding, ("source_projection_json", "ref_json"), max_bindings),
        ):
            size = sum(func.octet_length(cast(getattr(model, field), Text)) for field in fields)
            count, byte_size = self.db.execute(
                select(func.count(), func.coalesce(func.sum(size), 0)).where(
                    model.owner_user_id == owner_id, model.turn_id == turn_id
                )
            ).one()
            check_budget()
            total += int(byte_size)
            if count > limit or total > max_bytes:
                raise archive_error("ARCHIVE_LIMIT_EXCEEDED")
        tools = list(
            self.db.scalars(
                select(AgentToolResultArchive)
                .where(
                    AgentToolResultArchive.owner_user_id == owner_id,
                    AgentToolResultArchive.turn_id == turn_id,
                )
                .limit(max_calls + 1)
            )
        )
        check_budget()
        bindings = list(
            self.db.scalars(
                select(AgentEvidenceArchiveBinding)
                .where(
                    AgentEvidenceArchiveBinding.owner_user_id == owner_id,
                    AgentEvidenceArchiveBinding.turn_id == turn_id,
                )
                .limit(max_bindings + 1)
            )
        )
        check_budget()
        audits = list(
            self.db.scalars(
                select(AgentChatToolCall).where(AgentChatToolCall.turn_id == turn_id).limit(17)
            )
        )
        check_budget()
        return tools, bindings, audits
