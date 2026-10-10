import hashlib
import json
from typing import Any

from app.domain.agent.contracts import AgentToolResult, json_safe
from app.domain.agent.errors import AgentError


def serialized_result(result: AgentToolResult, *, max_output_bytes: int) -> dict[str, Any]:
    payload = json_safe(result.model_dump(mode="python"))
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    if len(encoded) > max_output_bytes:
        raise AgentError(
            "OUTPUT_LIMIT_EXCEEDED",
            f"tool result exceeds {max_output_bytes} bytes",
            status_code=422,
        )
    return payload


def user_audit_hash(user: Any) -> str:
    value = str(getattr(user, "id", None) or getattr(user, "username", "unknown"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
