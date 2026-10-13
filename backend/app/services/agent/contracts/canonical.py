import json
from typing import Any

from app.domain.agent.archive import archive_error
from app.domain.agent.contracts import json_safe
from app.services.agent.evidence import canonical_content_hash


def contract_hash(value: Any) -> str:
    # Matches Evidence v2 canonical bytes without changing its published implementation.
    return canonical_content_hash(value)


def contract_json(value: Any) -> Any:
    return json.loads(json.dumps(json_safe(value), ensure_ascii=True, allow_nan=False))


def contract_storage_size(value: Any) -> int:
    return len(json.dumps(contract_json(value), ensure_ascii=False, sort_keys=True).encode("utf-8"))


def remember_contract_evidence(row, seen):
    # TRAIN/OOS and distinct subjects legitimately share a window evidence anchor.
    digest = contract_hash(row.contract_json)
    for anchor in row.contract_json.get("evidence", []):
        key = (anchor["evidence_id"], row.contract_kind, row.subject_id, row.role)
        previous = seen.setdefault(key, digest)
        if previous != digest:
            raise archive_error("CONTRACT_EVIDENCE_CONFLICT")
