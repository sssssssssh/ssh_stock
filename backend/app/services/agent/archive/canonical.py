import json
from typing import Any

from app.domain.agent.contracts import json_safe
from app.services.agent.evidence import canonical_content_hash

archive_hash = canonical_content_hash  # Explicitly freeze the published Evidence v2 algorithm.


def archive_json(value: Any) -> Any:
    return json.loads(json.dumps(json_safe(value), ensure_ascii=True, allow_nan=False))


def archive_storage_size(value: Any) -> int:
    # PostgreSQL JSONB text contains spacing and Unicode; account for that representation.
    return len(json.dumps(archive_json(value), ensure_ascii=False, sort_keys=True).encode("utf-8"))
