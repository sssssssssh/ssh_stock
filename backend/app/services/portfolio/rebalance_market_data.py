from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.execution import InstrumentExecutionProfile
from app.models.market_data import StockBasic, StockDaily
from app.services.execution.instrument_rules import AshareInstrumentRuleResolver


class RebalanceMarketDataProvider:
    def __init__(
        self,
        db: Session,
        rules: AshareInstrumentRuleResolver | None = None,
    ) -> None:
        self.db = db
        self.rules = rules or AshareInstrumentRuleResolver()

    def load(
        self, trade_date: date, ts_codes: Sequence[str]
    ) -> tuple[dict[str, Decimal], dict[str, InstrumentExecutionProfile]]:
        codes = tuple(sorted(set(ts_codes)))
        if not codes:
            return {}, {}
        closes = {
            row.ts_code: Decimal(str(row.close))
            for row in self.db.execute(
                select(StockDaily).where(
                    StockDaily.trade_date == trade_date,
                    StockDaily.ts_code.in_(codes),
                    StockDaily.close.is_not(None),
                    StockDaily.close > 0,
                )
            ).scalars()
        }
        profiles: dict[str, InstrumentExecutionProfile] = {}
        for row in self.db.execute(
            select(StockBasic).where(StockBasic.ts_code.in_(codes))
        ).scalars():
            profile = self.rules.resolve(
                ts_code=row.ts_code, exchange=row.exchange, market=row.market
            )
            if profile is not None:
                profiles[row.ts_code] = profile
        return closes, profiles
