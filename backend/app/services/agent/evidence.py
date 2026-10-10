import hashlib
import json
from datetime import date, datetime
from typing import Any

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
    observed_at: datetime | None = None,
    quality_status: str = "UNKNOWN",
    limitations: list[str] | None = None,
) -> EvidenceRef:
    identity: dict[str, Any] = {
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
    }
    canonical = json.dumps(
        json_safe(identity), ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    return EvidenceRef(
        evidence_id=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
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
        observed_at=observed_at,
        quality_status=quality_status,
        limitations=limitations or [],
    )
