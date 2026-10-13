import time
import uuid
from functools import wraps

from app.domain.agent.archive import INTEGRITY_VERSION, archive_error
from app.domain.agent.chat_errors import chat_not_found, turn_not_found
from app.domain.agent.report_errors import report_not_found
from app.models.agent_chat import AgentChatMessage, AgentChatTurn
from app.repositories.agent_archive import AgentArchiveRepository
from app.repositories.agent_chat import AgentChatRepository
from app.repositories.agent_report import AgentReportRepository
from app.services.agent.archive.canonical import archive_hash
from app.services.agent.archive.integrity import ArchiveBundle, verify_archive_integrity
from app.services.agent.archive.recheck import recheck_archive
from app.services.agent.chat.fact_validation import (
    _ClaimValidationError,
    _EvidenceBinding,
    _validate_fact_binding,
)
from app.services.agent.chat.orchestrator import ToolResultContext
from app.services.agent.report.integrity import verify_report


def unavailable():
    return {
        "archive_status": "UNAVAILABLE",
        "manifest_id": None,
        "manifest_version": None,
        "manifest_hash": None,
        "reproduction_level": "SNAPSHOT_ONLY",
        "required_evidence_count": 0,
        "archived_evidence_count": 0,
        "integrity": {"status": "UNVERIFIABLE", "policy_version": INTEGRITY_VERSION},
        "calculation_reproduced": False,
        "warnings": ["ARCHIVE_UNAVAILABLE", "REPLAY_UNAVAILABLE"],
        "limitations": ["历史报告仅含 Claim 快照，无法恢复当次工具原始响应"],
    }


def bounded_read(method):
    @wraps(method)
    def read(self, *args, **kwargs):
        previous = getattr(self, "_deadline", None)
        if previous is None:
            self._deadline = time.monotonic() + self.config.verify_timeout_seconds
        try:
            self._check_budget()
            result = method(self, *args, **kwargs)
            self._check_budget()
            return result
        finally:
            self._deadline = previous

    return read


class AgentArchiveApplication:
    def __init__(self, db, settings):
        self.db = db
        self.config = settings.agent_config.archive
        self.repo = AgentArchiveRepository(db)

    def _check_budget(self):
        if getattr(self, "_deadline", None) is not None and time.monotonic() >= self._deadline:
            raise archive_error("ARCHIVE_VERIFY_TIMEOUT", status_code=504)

    def _integrity(self, bundle):
        return verify_archive_integrity(bundle, self.config, self._check_budget)

    @bounded_read
    def load_bundle(self, owner_id, turn_id):
        manifest = self.repo.manifest_for_turn(owner_id, turn_id)
        if manifest is None:
            return None
        self._check_budget()
        tools, bindings, audits = self.repo.load_evidence(
            owner_id,
            turn_id,
            max_calls=self.config.max_tool_calls,
            max_bindings=self.config.max_bindings,
            max_bytes=self.config.max_turn_bytes,
            check_budget=self._check_budget,
        )
        turn = self.db.get(AgentChatTurn, turn_id)
        self._check_budget()
        message = self.db.get(AgentChatMessage, manifest.assistant_message_id)
        return ArchiveBundle(manifest, tools, bindings, audits, turn, message, owner_id)

    @bounded_read
    def turn_archive(self, *, user, chat_id, request_id):
        owner = uuid.UUID(str(user.id))
        chat_repo = AgentChatRepository(self.db)
        if chat_repo.get_owned_session(chat_id=chat_id, owner_user_id=owner) is None:
            raise chat_not_found()
        turn = chat_repo.get_turn_by_request(chat_id=chat_id, request_id=request_id)
        if turn is None:
            raise turn_not_found()
        bundle = self.load_bundle(owner, turn.id)
        if bundle is None:
            return {**unavailable(), "source_turn_id": str(turn.id)}
        summary = self.summary(bundle)
        return {
            **summary,
            "evidence": [
                self.evidence_summary(row, bundle)
                for row in sorted(bundle.bindings, key=lambda item: item.evidence_id)
            ],
        }

    @bounded_read
    def report_bundle(self, *, user, report_id):
        owner = uuid.UUID(str(user.id))
        row = AgentReportRepository(self.db).get_owned_report(
            owner_user_id=owner, report_id=report_id
        )
        if row is None:
            raise report_not_found()
        snapshot, _ = verify_report(row)
        # A legacy report cannot acquire an Archive merely because its Turn later has one.
        reference = row.snapshot_json.get("archive_reference")
        if reference is None:
            return row, snapshot, None
        bundle = self.load_bundle(owner, row.source_turn_id)
        if bundle is None:
            raise archive_error("REPORT_ARCHIVE_BINDING_MISMATCH")
        manifest = bundle.manifest
        if (
            reference["manifest_id"] != str(manifest.id)
            or reference["manifest_hash"] != manifest.manifest_hash
            or reference["manifest_version"] != manifest.manifest_version
            or reference["archive_status"] != manifest.archive_status
            or manifest.assistant_message_id != row.source_message_id
            or manifest.chat_id != row.source_chat_id
            or archive_hash([item.model_dump(mode="json") for item in snapshot.claims])
            != manifest.claim_digest
        ):
            raise archive_error("REPORT_ARCHIVE_BINDING_MISMATCH")
        if self._integrity(bundle):
            raise archive_error("REPORT_ARCHIVE_UNVERIFIABLE")
        return row, snapshot, bundle

    @bounded_read
    def report_evidence(self, *, user, report_id, limit, offset):
        _, snapshot, bundle = self.report_bundle(user=user, report_id=report_id)
        if bundle is None:
            return [], {**unavailable(), "total": 0, "limit": limit, "offset": offset}
        ids = {item.evidence_id for item in snapshot.citations}
        rows = sorted(
            [row for row in bundle.bindings if row.evidence_id in ids],
            key=lambda row: row.evidence_id,
        )
        return [self.evidence_summary(row, bundle) for row in rows[offset : offset + limit]], {
            **self.summary(bundle),
            "total": len(rows),
            "limit": limit,
            "offset": offset,
        }

    @bounded_read
    def evidence_detail(self, *, user, report_id, evidence_id):
        _, snapshot, bundle = self.report_bundle(user=user, report_id=report_id)
        if evidence_id not in {citation.evidence_id for citation in snapshot.citations}:
            raise archive_error("ARCHIVE_EVIDENCE_NOT_FOUND", status_code=404)
        if bundle is None:
            return {**unavailable(), "evidence_id": evidence_id, "frozen_facts": []}
        binding = next((row for row in bundle.bindings if row.evidence_id == evidence_id), None)
        if binding is None:
            return {**unavailable(), "evidence_id": evidence_id, "frozen_facts": []}
        unsupported = self._integrity(bundle)
        tools = {row.id: row for row in bundle.tools}
        tool = tools[binding.tool_result_archive_id]
        facts = []
        if not unsupported:
            indices = [
                i
                for i, ref in enumerate(tool.payload_json["evidence"])
                if ref["evidence_id"] == evidence_id
            ]
            for claim in snapshot.claims:
                for fact, fact_ref in zip(
                    claim.structured_facts, claim.verified_fact_refs, strict=False
                ):
                    if fact_ref != f"{evidence_id}:{fact.path}":
                        continue
                    try:
                        _validate_fact_binding(
                            fact,
                            _EvidenceBinding(
                                ToolResultContext(
                                    tool.tool_call_id, tool.tool_name, tool.payload_json
                                ),
                                binding.ref_json,
                                indices[0],
                            ),
                        )
                    except _ClaimValidationError:
                        continue
                    facts.append({"claim_id": claim.claim_id, **fact.model_dump(mode="json")})
        allowed_args = {
            "trade_date",
            "start_date",
            "end_date",
            "limit",
            "offset",
            "stage",
            "window_no",
            "run_id",
            "report_id",
            "study_id",
            "validation_id",
        }
        return {
            **self.evidence_summary(binding, bundle),
            **self.summary(bundle),
            "frozen_facts": facts,
            "arguments_summary": {
                key: value for key, value in tool.arguments_json.items() if key in allowed_args
            },
            "arguments_hash": tool.arguments_hash,
            "registry_schema_hash": tool.registry_schema_hash,
            "projection_version": binding.projection_version,
            "warnings": unsupported + ["CALCULATION_NOT_REEXECUTED"],
        }

    @bounded_read
    def verify_report_archive(self, *, user, report_id, body):
        started_at = time.monotonic()
        _, snapshot, bundle = self.report_bundle(user=user, report_id=report_id)
        if bundle is None:
            return {
                **unavailable(),
                "report_id": str(report_id),
                "fact_recheck": {"status": "UNVERIFIABLE", "checked_claim_count": 0, "results": []},
            }
        return {
            "report_id": str(report_id),
            **recheck_archive(
                bundle,
                config=self.config,
                claims=[item.model_dump(mode="json") for item in snapshot.claims],
                max_evidence=body.max_evidence,
                started_at=started_at,
            ),
        }

    def summary(self, bundle):
        unsupported = self._integrity(bundle)
        manifest = bundle.manifest
        return {
            "archive_status": manifest.archive_status,
            "manifest_id": str(manifest.id),
            "manifest_version": manifest.manifest_version,
            "manifest_hash": manifest.manifest_hash,
            "source_turn_id": str(manifest.turn_id),
            "created_at": manifest.created_at.isoformat(),
            "required_evidence_count": len(manifest.manifest_json["required_evidence_ids"]),
            "archived_evidence_count": len(bundle.bindings),
            "integrity": {
                "status": "UNVERIFIABLE" if unsupported else "VERIFIED",
                "policy_version": INTEGRITY_VERSION,
            },
            "reproduction_level": "SNAPSHOT_ONLY"
            if unsupported or manifest.archive_status != "COMPLETE"
            else "FROZEN_FACT_RECHECK",
            "calculation_reproduced": False,
            "warnings": ["CALCULATION_NOT_REEXECUTED", *unsupported],
            "limitations": ["HISTORICAL_TOOL_RESULT_ONLY", "CALCULATION_NOT_REEXECUTED"],
        }

    @staticmethod
    def evidence_summary(binding, bundle):
        tool = next(row for row in bundle.tools if row.id == binding.tool_result_archive_id)
        ref = binding.ref_json
        fields = {
            "layer",
            "entity_id",
            "calc_version",
            "algo_version",
            "config_hash",
            "source_hash",
            "content_hash",
            "quality_status",
            "evidence_version",
            "calc_run_id",
            "report_id",
        }
        return {
            "evidence_id": binding.evidence_id,
            "tool_call_id": tool.tool_call_id,
            "tool_name": tool.tool_name,
            "tool_version": tool.tool_version,
            "as_of_date": ref.get("trade_date"),
            "created_at": binding.created_at.isoformat(),
            "record_path": binding.record_path,
            **{key: ref.get(key) for key in fields},
        }
