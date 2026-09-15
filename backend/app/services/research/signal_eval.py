from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from loguru import logger
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import (
    SignalForwardEval,
    StockDaily,
    StockFactorDaily,
    StockTradeStatusDaily,
    StrategySignal,
    TradeCalendar,
)
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


def evaluate_forward_returns_v2(
    signal_trade_date: date,
    market_trade_dates: Sequence[date],
    rows: Sequence[dict[str, Any]],
    *,
    entry_basis: str = "NEXT_OPEN",
) -> dict[str, Any] | None:
    dates = sorted(set(market_trade_dates))
    if signal_trade_date not in dates:
        return None
    signal_index = dates.index(signal_trade_date)
    entry_offset = 0 if entry_basis == "SIGNAL_CLOSE" else 1
    if signal_index + entry_offset >= len(dates):
        return None
    entry_date = dates[signal_index + entry_offset]
    by_date = {row["trade_date"]: row for row in rows}
    entry_row = by_date.get(entry_date)
    entry_price_field = "adj_open" if entry_basis == "NEXT_OPEN" else "adj_close"
    entry_price, entry_reason = _executable_entry(
        entry_row,
        entry_price_field,
        use_open_limit=entry_basis == "NEXT_OPEN",
    )
    entry_executable = entry_reason is None
    result: dict[str, Any] = {
        "eval_version": "eval_v2",
        "entry_basis": entry_basis,
        "horizon_basis": "MARKET_TRADING_DAY",
        "entry_trade_date": entry_date,
        "entry_price": entry_price if entry_executable else None,
        "entry_executable": entry_executable,
        "exit_executable": None,
        "non_executable_reason": entry_reason,
        "ret5": None,
        "ret10": None,
        "ret20": None,
        "ret60": None,
        "mfe20": None,
        "mae20": None,
        "evaluated_until_date": dates[min(signal_index + 60, len(dates) - 1)],
    }
    if not entry_executable or entry_price is None:
        return result

    for horizon in (5, 10, 20, 60):
        target_index = signal_index + horizon
        if target_index >= len(dates):
            continue
        target_date = dates[target_index]
        exit_price, exit_reason = _executable_exit(by_date.get(target_date))
        if horizon == 20:
            result["exit_executable"] = exit_reason is None
            if exit_reason:
                result["non_executable_reason"] = f"HORIZON20_{exit_reason}"
        if exit_reason is None and exit_price is not None:
            result[f"ret{horizon}"] = exit_price / entry_price - 1.0

    window_dates = dates[signal_index + 1 : signal_index + 21]
    highs = [
        float(by_date[current]["adj_high"])
        for current in window_dates
        if current in by_date and _positive(by_date[current].get("adj_high"))
    ]
    lows = [
        float(by_date[current]["adj_low"])
        for current in window_dates
        if current in by_date and _positive(by_date[current].get("adj_low"))
    ]
    if highs:
        result["mfe20"] = max(highs) / entry_price - 1.0
    if lows:
        result["mae20"] = min(lows) / entry_price - 1.0
    return result


def _executable_entry(
    row: dict[str, Any] | None,
    price_field: str,
    *,
    use_open_limit: bool,
) -> tuple[float | None, str | None]:
    if row is None:
        return None, "NO_STOCK_ROW"
    if row.get("is_suspended") is True or row.get("tradable") is False:
        return None, "SUSPENDED"
    price = row.get(price_field)
    if not _positive(price):
        return None, "ENTRY_PRICE_MISSING"
    limit_up = row.get("up_limit")
    if use_open_limit and _prices_match(row.get("raw_open"), limit_up):
        return None, "LIMIT_UP"
    if not use_open_limit and row.get("is_limit_up_close") is True:
        return None, "LIMIT_UP"
    return float(price), None


def _executable_exit(row: dict[str, Any] | None) -> tuple[float | None, str | None]:
    if row is None:
        return None, "NO_STOCK_ROW"
    if row.get("is_suspended") is True or row.get("tradable") is False:
        return None, "SUSPENDED"
    if row.get("is_limit_down_close") is True:
        return None, "LIMIT_DOWN"
    price = row.get("adj_close")
    if not _positive(price):
        return None, "EXIT_PRICE_MISSING"
    return float(price), None


def _positive(value: Any) -> bool:
    return value is not None and float(value) > 0


def _prices_match(left: Any, right: Any) -> bool:
    if not _positive(left) or not _positive(right):
        return False
    left_value = float(left)
    right_value = float(right)
    return abs(left_value - right_value) <= max(0.001, abs(right_value) * 1e-6)


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
        eval_version: str = "eval_v2",
        entry_basis: str = "NEXT_OPEN",
    ) -> dict[str, int]:
        if eval_version not in {"eval_v1", "eval_v2"}:
            raise ValueError(f"unsupported eval_version: {eval_version}")
        if entry_basis not in {"SIGNAL_CLOSE", "NEXT_OPEN", "NEXT_CLOSE"}:
            raise ValueError(f"unsupported entry_basis: {entry_basis}")
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
            if eval_version == "eval_v1":
                forward_rows = self._read_forward_factor_rows(
                    signal["ts_code"], signal["trade_date"]
                )
                evaluated = evaluate_forward_returns(signal["trade_date"], forward_rows)
                if evaluated:
                    evaluated = {
                        "eval_version": "eval_v1",
                        "entry_basis": "SIGNAL_CLOSE",
                        "horizon_basis": "STOCK_ROW",
                        "entry_trade_date": signal["trade_date"],
                        "entry_price": forward_rows[0].get("adj_close"),
                        "entry_executable": None,
                        "exit_executable": None,
                        "non_executable_reason": None,
                        **evaluated,
                    }
            else:
                market_dates = self._read_market_trade_dates(signal["trade_date"])
                forward_rows = self._read_forward_v2_rows(
                    signal["ts_code"], market_dates
                )
                evaluated = evaluate_forward_returns_v2(
                    signal["trade_date"],
                    market_dates,
                    forward_rows,
                    entry_basis=entry_basis,
                )
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

        evaluated_count = upsert_rows(
            self.db,
            SignalForwardEval,
            rows,
            ["signal_id", "eval_version", "entry_basis"],
        )
        self.db.commit()
        logger.info(
            "evaluated signals signal_type={} algo_version={} signals={} evaluated={}",
            signal_type,
            version,
            len(signals),
            evaluated_count,
        )
        return {"signals": len(signals), "evaluated": evaluated_count}

    def _read_market_trade_dates(self, trade_date: date) -> list[date]:
        return list(
            self.db.execute(
                select(TradeCalendar.cal_date)
                .where(
                    TradeCalendar.cal_date >= trade_date,
                    TradeCalendar.is_open.is_(True),
                )
                .order_by(TradeCalendar.cal_date)
                .limit(61)
            )
            .scalars()
            .all()
        )

    def _read_forward_v2_rows(
        self,
        ts_code: str,
        market_dates: Sequence[date],
    ) -> list[dict[str, Any]]:
        if not market_dates:
            return []
        factor_join = and_(
            StockFactorDaily.trade_date == StockTradeStatusDaily.trade_date,
            StockFactorDaily.ts_code == StockTradeStatusDaily.ts_code,
        )
        daily_join = and_(
            StockDaily.trade_date == StockTradeStatusDaily.trade_date,
            StockDaily.ts_code == StockTradeStatusDaily.ts_code,
        )
        stmt = (
            select(
                StockTradeStatusDaily.trade_date,
                StockTradeStatusDaily.is_suspended,
                StockTradeStatusDaily.tradable,
                StockTradeStatusDaily.up_limit,
                StockTradeStatusDaily.is_limit_up_close,
                StockTradeStatusDaily.is_limit_down_close,
                StockFactorDaily.adj_open,
                StockFactorDaily.adj_high,
                StockFactorDaily.adj_low,
                StockFactorDaily.adj_close,
                StockDaily.open.label("raw_open"),
            )
            .select_from(StockTradeStatusDaily)
            .outerjoin(StockFactorDaily, factor_join)
            .outerjoin(StockDaily, daily_join)
            .where(
                StockTradeStatusDaily.ts_code == ts_code,
                StockTradeStatusDaily.trade_date.in_(market_dates),
            )
            .order_by(StockTradeStatusDaily.trade_date)
        )
        return list(self.db.execute(stmt).mappings().all())

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
