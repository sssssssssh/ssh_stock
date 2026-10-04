import hashlib
import json
import uuid
from typing import Any

from app.domain.performance.trade_contracts import TradeSourceSnapshot
from app.services.performance.identity import canonical_decimal


def performance_trade_lock_key(performance_id: uuid.UUID) -> int:
    digest = hashlib.sha256(f"portfolio_performance_trade:{performance_id}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def trade_source_hash(source: TradeSourceSnapshot) -> str:
    payload: dict[str, Any] = {
        "performance_id": str(source.performance_id),
        "performance_version": source.performance_version,
        "performance_config_hash": source.performance_config_hash,
        "performance_source_hash": source.performance_source_hash,
        "trade_version": source.trade_version,
        "trade_config_hash": source.trade_config_hash,
        "run_id": str(source.run_id),
        "initial_cash": canonical_decimal(source.initial_cash),
        "backtest_engine_version": source.backtest_engine_version,
        "portfolio_version": source.portfolio_version,
        "execution_version": source.execution_version,
        "accounting_version": source.accounting_version,
        "orders": [
            {
                "id": str(row.order_id),
                "signal_trade_date": row.signal_trade_date.isoformat(),
                "scheduled_trade_date": row.scheduled_trade_date.isoformat(),
                "ts_code": row.ts_code,
                "side": row.side,
                "status": row.status,
                "attempt_count": row.attempt_count,
            }
            for row in sorted(source.orders, key=lambda value: str(value.order_id))
        ],
        "attempts": [
            {
                "id": str(row.attempt_id),
                "order_id": str(row.order_id),
                "attempt_trade_date": row.attempt_trade_date.isoformat(),
                "attempt_no": row.attempt_no,
                "outcome": row.outcome,
                "reason_code": row.reason_code,
                "requested_quantity": row.requested_quantity,
                "fill_quantity": row.fill_quantity,
                "reference_price": _decimal(row.reference_price),
                "fill_price": _decimal(row.fill_price),
                "gross_amount": canonical_decimal(row.gross_amount),
                "commission": canonical_decimal(row.commission),
                "stamp_tax": canonical_decimal(row.stamp_tax),
                "transfer_fee": canonical_decimal(row.transfer_fee),
                "cash_fee_total": canonical_decimal(row.cash_fee_total),
                "slippage_cost": canonical_decimal(row.slippage_cost),
                "total_cost": canonical_decimal(row.total_cost),
            }
            for row in sorted(source.attempts, key=lambda value: str(value.attempt_id))
        ],
        "fills": [
            {
                "id": str(row.fill_id),
                "order_id": str(row.order_id),
                "attempt_id": str(row.attempt_id),
                "scheduled_trade_date": row.scheduled_trade_date.isoformat(),
                "trade_date": row.trade_date.isoformat(),
                "ts_code": row.ts_code,
                "side": row.side,
                "quantity": row.quantity,
                "price": canonical_decimal(row.price),
                "reference_price": canonical_decimal(row.reference_price),
                "gross_amount": canonical_decimal(row.gross_amount),
                "commission": canonical_decimal(row.commission),
                "stamp_tax": canonical_decimal(row.stamp_tax),
                "transfer_fee": canonical_decimal(row.transfer_fee),
                "cash_fee_total": canonical_decimal(row.cash_fee_total),
                "slippage_cost": canonical_decimal(row.slippage_cost),
                "total_cost": canonical_decimal(row.total_cost),
            }
            for row in sorted(
                source.fills,
                key=lambda value: (value.trade_date, str(value.fill_id)),
            )
        ],
        "nav": [
            {
                "trade_date": row.trade_date.isoformat(),
                "total_assets": canonical_decimal(row.total_assets),
                "trading_cost": canonical_decimal(row.trading_cost),
            }
            for row in sorted(source.nav, key=lambda value: value.trade_date)
        ],
        "positions": [
            {
                "trade_date": row.trade_date.isoformat(),
                "ts_code": row.ts_code,
                "quantity": row.quantity,
                "avg_cost": canonical_decimal(row.avg_cost),
                "realized_pnl": canonical_decimal(row.realized_pnl),
                "unrealized_pnl": canonical_decimal(row.unrealized_pnl),
            }
            for row in sorted(
                source.positions,
                key=lambda value: (value.trade_date, value.ts_code),
            )
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _decimal(value) -> str | None:
    return canonical_decimal(value) if value is not None else None
