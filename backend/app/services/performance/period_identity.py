import hashlib
import json
import uuid
from typing import Any

from app.domain.performance.period_contracts import PeriodSourceSnapshot


def performance_period_lock_key(
    performance_id: uuid.UUID, risk_id: uuid.UUID, trade_id: uuid.UUID
) -> int:
    identity = f"portfolio_performance_period:{performance_id}:{risk_id}:{trade_id}"
    return int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], "big", signed=True)


def period_source_hash(source: PeriodSourceSnapshot) -> str:
    return period_identity_hash(
        run_id=source.run_id,
        performance_id=source.performance_id,
        performance_version=source.performance_version,
        performance_config_hash=source.performance_config_hash,
        performance_source_hash=source.performance_source_hash,
        risk_id=source.risk_id,
        risk_version=source.risk_version,
        risk_config_hash=source.risk_config_hash,
        risk_source_hash=source.risk_source_hash,
        benchmark_source_hash=source.benchmark_source_hash,
        trade_id=source.trade_id,
        trade_version=source.trade_version,
        trade_config_hash=source.trade_config_hash,
        trade_source_hash=source.trade_source_hash,
        period_version=source.period_version,
        period_config_hash=source.period_config_hash,
    )


def period_identity_hash(**identity: Any) -> str:
    payload = {
        key: str(value) if isinstance(value, uuid.UUID) else value
        for key, value in identity.items()
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
