from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def storage_json_bytes(value: Any) -> bytes:
    """Approximate PostgreSQL JSONB text size using its spaced representation."""

    return json.dumps(
        _normalize(value), ensure_ascii=False, sort_keys=True
    ).encode("utf-8")


def decimal_text(value: str | int | float | Decimal) -> str:
    if isinstance(value, bool):
        raise ValueError("boolean is not a numeric report value")
    decimal = Decimal(str(value))
    if not decimal.is_finite():
        raise ValueError("non-finite numeric report value")
    text = format(decimal.normalize(), "f")
    return "0" if text in {"-0", ""} else text


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float is not canonical")
        return decimal_text(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")
