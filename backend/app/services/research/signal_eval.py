from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import SignalForwardEval, StockFactorDaily, StrategySignal
from app.repositories.upsert import upsert_rows


def evaluate_forward_returns(
    base_trade_date: date,
    rows: Sequence[dict[str, Any]],
) -> dict[str, Any] | None:
    if not rows:
        return None

    ordered = sorted(rows, key=lambda row: row["trade_date"])
    if ordered[0]["trade_date"] != base_trade_date:
        return None

    base_close = ordered[0].get("adj_close")
    if not base_close or base_close <= 0:
        return None

    result: dict[str, Any] = {
        "ret5": None,
        "ret10": None,
        "ret20": None,
        "ret60": None,
        "mfe20": None,
        "mae20": None,
        "evaluated_until_date": ordered[-1]["trade_date"],
    }
    for horizon in (5, 10, 20, 60):
        if len(ordered) > horizon:
            close = ordered[horizon].get("adj_close")
            if close and close > 0:
                result[f"ret{horizon}"] = close / base_close - 1.0

    window20 = [row.get("adj_close") for row in ordered[1:21]]
    valid_window20 = [close for close in window20 if close and close > 0]
    if valid_window20:
        result["mfe20"] = max(valid_window20) / base_close - 1.0
        result["mae20"] = min(valid_window20) / base_close - 1.0
    return result


class SignalEvaluationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def evaluate(
        self,
        signal_type: str = "RIGHT_SIDE_NEW",
        algo_version: str | None = None,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = None,
    ) -> dict[str, int]:
        version = algo_version or self.settings.algo_version
        stmt = (
            select(
                StrategySignal.id,
                StrategySignal.trade_date,
                StrategySignal.ts_code,
                StrategySignal.signal_type,
                StrategySignal.algo_version,
            )
            .where(
                StrategySignal.signal_type == signal_type,
                StrategySignal.algo_version == version,
            )
            .order_by(StrategySignal.trade_date, StrategySignal.ts_code)
        )
        if start:
            stmt = stmt.where(StrategySignal.trade_date >= start)
        if end:
            stmt = stmt.where(StrategySignal.trade_date <= end)
        if limit:
            stmt = stmt.limit(max(1, limit))

        signals = self.db.execute(stmt).mappings().all()
        rows: list[dict[str, Any]] = []
        for signal in signals:
            forward_rows = self._read_forward_factor_rows(signal["ts_code"], signal["trade_date"])
            evaluated = evaluate_forward_returns(signal["trade_date"], forward_rows)
            if not evaluated:
                continue
            rows.append(
                {
                    "signal_id": signal["id"],
                    "trade_date": signal["trade_date"],
                    "ts_code": signal["ts_code"],
                    "signal_type": signal["signal_type"],
                    "algo_version": signal["algo_version"],
                    **evaluated,
                    "updated_at": datetime.now(UTC),
                }
            )

        evaluated_count = upsert_rows(self.db, SignalForwardEval, rows, ["signal_id"])
        self.db.commit()
        logger.info(
            "evaluated signals signal_type={} algo_version={} signals={} evaluated={}",
            signal_type,
            version,
            len(signals),
            evaluated_count,
        )
        return {"signals": len(signals), "evaluated": evaluated_count}

    def _read_forward_factor_rows(self, ts_code: str, trade_date: date) -> list[dict[str, Any]]:
        stmt = (
            select(
                StockFactorDaily.trade_date,
                StockFactorDaily.ts_code,
                StockFactorDaily.adj_close,
            )
            .where(
                StockFactorDaily.ts_code == ts_code,
                StockFactorDaily.trade_date >= trade_date,
                StockFactorDaily.adj_close.is_not(None),
            )
            .order_by(StockFactorDaily.trade_date)
            .limit(61)
        )
        return list(self.db.execute(stmt).mappings().all())
