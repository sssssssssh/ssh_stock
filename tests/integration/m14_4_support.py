from dataclasses import dataclass
from datetime import date

from app.models.market_data import IndexDaily
from app.services.performance.risk_application import PerformanceRiskApplicationService
from app.services.performance.trade_application import PerformanceTradeApplicationService
from m14_3_support import TradeCase, seed_trade_case
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class AnalyticsCase:
    trade_case: TradeCase
    risk_id: object
    trade_id: object

    @property
    def run_id(self):
        return self.trade_case.run_id

    @property
    def performance_id(self):
        return self.trade_case.performance_id


def seed_analytics_case(
    db: Session,
    dates: tuple[date, ...],
    *,
    benchmark_code: str = "000300.SH",
) -> AnalyticsCase:
    case = seed_trade_case(db, dates)
    previous = 100.0
    for index, trade_date in enumerate(dates):
        identity = (trade_date, benchmark_code)
        if db.get(IndexDaily, identity) is None:
            close = 101.0 + index
            db.add(
                IndexDaily(
                    trade_date=trade_date,
                    ts_code=benchmark_code,
                    pre_close=previous,
                    close=close,
                )
            )
            previous = close
    db.flush()
    risk = PerformanceRiskApplicationService(db).calculate_now(
        case.run_id, case.performance_id
    ).report
    trade = PerformanceTradeApplicationService(db).calculate_now(
        case.run_id, case.performance_id
    ).report
    return AnalyticsCase(case, risk.id, trade.id)
