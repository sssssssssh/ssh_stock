import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.domain.agent.contracts import EvidenceRef, json_safe


def evidence_ref(
    *,
    layer: str,
    source_type: str,
    entity_id: str,
    date_value: date | None = None,
    source_record_id: str | None = None,
    calc_version: str | None = None,
    algo_version: str | None = None,
    config_hash: str | None = None,
    source_hash: str | None = None,
    report_id: str | None = None,
    calc_run_id: str | None = None,
    content: Any | None = None,
    observed_at: datetime | None = None,
    quality_status: str = "UNKNOWN",
    limitations: list[str] | None = None,
) -> EvidenceRef:
    normalized_limitations = sorted(set(limitations or []))
    content_hash = canonical_content_hash(content if content is not None else {})
    identity: dict[str, Any] = {
        "evidence_version": "v2",
        "layer": layer,
        "source_type": source_type,
        "entity_id": entity_id,
        "trade_date": date_value,
        "source_record_id": source_record_id,
        "calc_version": calc_version,
        "algo_version": algo_version,
        "config_hash": config_hash,
        "source_hash": source_hash,
        "report_id": report_id,
        "calc_run_id": calc_run_id,
        "content_hash": content_hash,
        "quality_status": quality_status,
        "limitations": normalized_limitations,
    }
    return EvidenceRef(
        evidence_id=canonical_content_hash(identity),
        evidence_version="v2",
        layer=layer,
        source_type=source_type,
        entity_id=entity_id,
        trade_date=date_value,
        source_record_id=source_record_id,
        calc_version=calc_version,
        algo_version=algo_version,
        config_hash=config_hash,
        source_hash=source_hash,
        report_id=report_id,
        calc_run_id=calc_run_id,
        content_hash=content_hash,
        observed_at=observed_at,
        quality_status=quality_status,
        limitations=normalized_limitations,
    )


def canonical_content_hash(value: Any) -> str:
    canonical = json.dumps(
        _canonical_value(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [_canonical_value(item) for item in value]
        return sorted(
            items,
            key=lambda item: json.dumps(
                item, ensure_ascii=True, sort_keys=True, separators=(",", ":")
            ),
        )
    if isinstance(value, Decimal):
        return json_safe(value)
    return json_safe(value)
