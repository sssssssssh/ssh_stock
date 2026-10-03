import hashlib
import json
import uuid
from typing import Any

from app.domain.performance.risk_contracts import RiskSourceRow
from app.services.performance.identity import canonical_decimal

BENCHMARK_PRICE_QUANTUM_VERSION = "benchmark_price_0.0001_v1"


def performance_risk_lock_key(performance_id: uuid.UUID) -> int:
    digest = hashlib.sha256(
        f"portfolio_performance_risk:{performance_id}".encode()
    ).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def benchmark_source_hash(
    *, benchmark_code: str, rows: tuple[RiskSourceRow, ...]
) -> str:
    payload: dict[str, Any] = {
        "benchmark_code": benchmark_code,
        "price_precision_version": BENCHMARK_PRICE_QUANTUM_VERSION,
        "price_quantum": "0.0001",
        "rows": [
            {
                "trade_date": row.trade_date.isoformat(),
                "pre_close": canonical_decimal(row.benchmark_pre_close),
                "close": canonical_decimal(row.benchmark_close),
            }
            for row in sorted(rows, key=lambda value: value.trade_date)
        ],
    }
    return _sha256(payload)


def risk_source_hash(
    *,
    performance_id: uuid.UUID,
    performance_version: str,
    performance_config_hash: str,
    performance_source_hash: str,
    risk_version: str,
    risk_config_hash: str,
    benchmark_code: str,
    benchmark_hash: str,
) -> str:
    return _sha256(
        {
            "performance_id": str(performance_id),
            "performance_version": performance_version,
            "performance_config_hash": performance_config_hash,
            "performance_source_hash": performance_source_hash,
            "risk_version": risk_version,
            "risk_config_hash": risk_config_hash,
            "benchmark_code": benchmark_code,
            "benchmark_source_hash": benchmark_hash,
        }
    )


def _sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
