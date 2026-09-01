import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any


def config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def calculation_metadata(
    *,
    config: dict[str, Any],
    calc_version: str,
    calc_run_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    return {
        "calc_version": calc_version,
        "config_hash": config_hash(config),
        "calc_run_id": calc_run_id or uuid.uuid4(),
        "calculated_at": datetime.now(UTC),
    }
