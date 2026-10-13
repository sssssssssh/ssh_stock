import json
from typing import Any

from app.domain.agent.contracts import json_safe
from app.services.agent.evidence import canonical_content_hash


def contract_hash(value: Any) -> str:
    # Matches Evidence v2 canonical bytes without changing its published implementation.
    return canonical_content_hash(value)


def contract_json(value: Any) -> Any:
    return json.loads(json.dumps(json_safe(value), ensure_ascii=True, allow_nan=False))


def contract_storage_size(value: Any) -> int:
    return len(json.dumps(contract_json(value), ensure_ascii=False, sort_keys=True).encode("utf-8"))
