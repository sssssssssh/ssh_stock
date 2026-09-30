from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.market_data import StockAdjFactor, StockDaily, StockTradeStatusDaily
from app.services.analysis_identity import TRADE_STATUS_CALC_VERSION, analysis_strategy_hash
from app.services.portfolio.accounting import AccountingMarketSnapshot


class AccountingMarketDataProvider:
    """Load each required Raw/derived layer in one batch query."""

    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def load_start_of_day(
        self,
        *,
        previous_trade_date: date | None,
        trade_date: date,
        held_codes: Sequence[str],
    ) -> dict[str, AccountingMarketSnapshot]:
        codes = tuple(sorted(set(held_codes)))
        if not codes:
            return {}
        strategy_hash = analysis_strategy_hash(self.settings.strategy)
        statuses = {
            row.ts_code: row
            for row in self.db.execute(
                select(StockTradeStatusDaily).where(
                    StockTradeStatusDaily.trade_date == trade_date,
                    StockTradeStatusDaily.ts_code.in_(codes),
                    StockTradeStatusDaily.calc_version == TRADE_STATUS_CALC_VERSION,
                    StockTradeStatusDaily.config_hash == strategy_hash,
                )
            ).scalars()
        }
        factor_dates = [trade_date]
        if previous_trade_date is not None:
            factor_dates.append(previous_trade_date)
        factors = {
            (row.trade_date, row.ts_code): row.adj_factor
            for row in self.db.execute(
                select(StockAdjFactor).where(
                    StockAdjFactor.trade_date.in_(factor_dates),
                    StockAdjFactor.ts_code.in_(codes),
                )
            ).scalars()
        }
        result: dict[str, AccountingMarketSnapshot] = {}
        for code in codes:
            status = statuses.get(code)
            previous_factor = (
                factors.get((previous_trade_date, code))
                if previous_trade_date is not None
                else factors.get((trade_date, code))
            )
            result[code] = AccountingMarketSnapshot(
                ts_code=code,
                status_present=status is not None,
                is_active=status.is_active if status is not None else None,
                is_suspended=status.is_suspended if status is not None else None,
                close_price=None,
                previous_adj_factor=(
                    Decimal(str(previous_factor))
                    if previous_factor is not None
                    else None
                ),
                current_adj_factor=(
                    Decimal(str(factors[(trade_date, code)]))
                    if factors.get((trade_date, code)) is not None
                    else None
                ),
            )
        return result

    def load_close(
        self,
        *,
        trade_date: date,
        held_codes: Sequence[str],
    ) -> dict[str, AccountingMarketSnapshot]:
        codes = tuple(sorted(set(held_codes)))
        if not codes:
            return {}
        strategy_hash = analysis_strategy_hash(self.settings.strategy)
        statuses = {
            row.ts_code: row
            for row in self.db.execute(
                select(StockTradeStatusDaily).where(
                    StockTradeStatusDaily.trade_date == trade_date,
                    StockTradeStatusDaily.ts_code.in_(codes),
                    StockTradeStatusDaily.calc_version == TRADE_STATUS_CALC_VERSION,
                    StockTradeStatusDaily.config_hash == strategy_hash,
                )
            ).scalars()
        }
        closes = {
            row.ts_code: row.close
            for row in self.db.execute(
                select(StockDaily).where(
                    StockDaily.trade_date == trade_date,
                    StockDaily.ts_code.in_(codes),
                )
            ).scalars()
        }
        factors = {
            row.ts_code: row.adj_factor
            for row in self.db.execute(
                select(StockAdjFactor).where(
                    StockAdjFactor.trade_date == trade_date,
                    StockAdjFactor.ts_code.in_(codes),
                )
            ).scalars()
        }
        result: dict[str, AccountingMarketSnapshot] = {}
        for code in codes:
            status = statuses.get(code)
            factor = factors.get(code)
            result[code] = AccountingMarketSnapshot(
                ts_code=code,
                status_present=status is not None,
                is_active=status.is_active if status is not None else None,
                is_suspended=status.is_suspended if status is not None else None,
                close_price=(
                    Decimal(str(closes[code]))
                    if closes.get(code) is not None
                    else None
                ),
                previous_adj_factor=None,
                current_adj_factor=(
                    Decimal(str(factor)) if factor is not None else None
                ),
            )
        return result
