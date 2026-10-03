import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any

from app.domain.performance.contracts import PerformanceSourceRow
from app.models.portfolio import PortfolioBacktestRun


def performance_run_lock_key(run_id: uuid.UUID) -> int:
    """Return one stable signed bigint key for all same-run M14 locks."""
    digest = hashlib.sha256(f"portfolio_performance:{run_id}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def performance_source_hash(
    run: PortfolioBacktestRun,
    rows: tuple[PerformanceSourceRow, ...],
    *,
    performance_version: str,
    performance_config_hash: str,
) -> str:
    payload: dict[str, Any] = {
        "run": {
            "run_id": str(run.id),
            "start_date": run.start_date.isoformat(),
            "end_date": run.end_date.isoformat(),
            "initial_cash": canonical_decimal(run.initial_cash),
            "backtest_engine_version": run.backtest_engine_version,
            "portfolio_version": run.portfolio_version,
            "execution_version": run.execution_version,
            "accounting_version": run.accounting_version,
            "performance_version": performance_version,
            "performance_config_hash": performance_config_hash,
        },
        "nav": [
            {
                "trade_date": row.trade_date.isoformat(),
                "nav": canonical_decimal(row.nav),
                "total_assets": canonical_decimal(row.total_assets),
                "cash": canonical_decimal(row.cash),
                "market_value": canonical_decimal(row.market_value),
                "gross_exposure": canonical_decimal(row.gross_exposure),
                "net_exposure": canonical_decimal(row.net_exposure),
                "position_count": row.position_count,
                "trading_cost": canonical_decimal(row.trading_cost),
            }
            for row in rows
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
