from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.walk_forward_config import WalkForwardConfig
from app.domain.walk_forward.contracts import WindowPlanResult
from app.domain.walk_forward.windows import WindowPlanError, plan_windows
from app.models.market_data import TradeCalendar
from app.services.walk_forward.identity import calendar_hash


class WalkForwardPlanner:
    def __init__(self, db: Session, config: WalkForwardConfig) -> None:
        self.db = db
        self.config = config

    def plan(
        self,
        *,
        requested_start_date: date,
        requested_end_date: date,
        mode: str,
        train_trade_days: int,
        test_trade_days: int,
        step_trade_days: int,
    ) -> tuple[WindowPlanResult, str]:
        if requested_end_date < requested_start_date:
            raise WindowPlanError(
                "WALK_FORWARD_CONFIG_INVALID",
                "end_date must be on or after start_date",
            )
        dates = tuple(
            self.db.scalars(
                select(TradeCalendar.cal_date)
                .where(
                    TradeCalendar.exchange == self.config.exchange,
                    TradeCalendar.is_open.is_(True),
                    TradeCalendar.cal_date >= requested_start_date,
                    TradeCalendar.cal_date <= requested_end_date,
                )
                .order_by(TradeCalendar.cal_date)
            ).all()
        )
        if not dates:
            raise WindowPlanError(
                "WALK_FORWARD_CALENDAR_INCOMPLETE",
                "no open trade dates exist for the requested range",
            )
        return (
            plan_windows(
                dates,
                mode=mode,
                train_trade_days=train_trade_days,
                test_trade_days=test_trade_days,
                step_trade_days=step_trade_days,
                minimum_windows=self.config.minimum_windows,
                max_windows=self.config.max_windows,
            ),
            calendar_hash(dates),
        )
