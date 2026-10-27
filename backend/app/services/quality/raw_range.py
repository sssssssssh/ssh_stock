"""Bounded read-only preflight inputs; evaluation stays in RawCompleteness.

Only recalculation opts in. Ingestion and persisted quality checks are unchanged.
Unusual price-limit exceptions still use the original calendar/exemption reader.
"""

from collections import defaultdict

from sqlalchemy import and_, func, select, text

from app.models.market_data import (
    DataQualityDaily,
    IndexDaily,
    StockAdjFactor,
    StockBasic,
    StockDaily,
    StockDailyBasic,
    StockLimitDaily,
    StockStDaily,
    StockSuspendDaily,
)
from app.services.calculation_memory import check_calculation_memory
from app.services.job_execution import checkpoint
from app.services.quality.raw_completeness import check_raw_completeness
from app.services.universe import is_stock_active_on


def _read(db, statement):
    result = db.execute(statement.execution_options(yield_per=5000))
    try:
        for batch in result.partitions(5000):
            checkpoint()
            check_calculation_memory()
            yield from batch
    finally:
        result.close()


class RawRangeFacts:
    def __init__(self, db, start, end):
        if (end - start).days > 30 or end < start:
            raise ValueError("RAW_PREFLIGHT_WINDOW_UNBOUNDED")
        # Hold a stable read set until the caller's ORIGINAL checkpoint commit;
        # no per-day/month commit and no candidate/public write is introduced.
        names = (StockBasic, StockDaily, StockAdjFactor, StockDailyBasic, IndexDaily,
                 StockLimitDaily, StockStDaily, StockSuspendDaily, DataQualityDaily)
        db.execute(text("LOCK TABLE " + ",".join(
            f'public."{model.__tablename__}"' for model in names) + " IN SHARE MODE"))
        self.basic = list(_read(db, select(
            StockBasic.ts_code, StockBasic.list_date, StockBasic.delist_date)))
        self.daily, self.suspended = defaultdict(set), defaultdict(set)
        self.validity, self.invalid_limits = {}, defaultdict(list)
        self.qualities, self.event_counts = {}, {}
        for row in _read(db, select(StockDaily.trade_date, StockDaily.ts_code).where(
                StockDaily.trade_date.between(start, end))):
            self.daily[row.trade_date].add(row.ts_code)
        for model, required, positive in (
            (StockAdjFactor, (), (StockAdjFactor.adj_factor,)),
            (StockDailyBasic, (StockDailyBasic.close, StockDailyBasic.total_mv,
                               StockDailyBasic.circ_mv), ()),
            (IndexDaily, (), (IndexDaily.close, IndexDaily.pre_close)),
            (StockLimitDaily, (), (StockLimitDaily.up_limit, StockLimitDaily.down_limit)),
        ):
            checks = [c.is_not(None) for c in (*required, *positive)]
            checks.extend(c > 0 for c in positive)
            extra = [StockLimitDaily.up_limit, StockLimitDaily.down_limit] \
                if model is StockLimitDaily else []
            statement = select(model.trade_date, model.ts_code,
                               and_(*checks).label("valid"), *extra).where(
                                   model.trade_date.between(start, end))
            for row in _read(db, statement):
                key = model.__tablename__, row.trade_date
                valid, invalid = self.validity.setdefault(key, (set(), set()))
                (valid if row.valid else invalid).add(row.ts_code)
                if model is StockLimitDaily and not row.valid:
                    self.invalid_limits[row.trade_date].append(dict(
                        ts_code=row.ts_code, up_limit=row.up_limit, down_limit=row.down_limit))
        for model, dataset in ((StockStDaily, "stock_st"), (StockSuspendDaily, "suspend_d")):
            for day, count in _read(db, select(model.trade_date, func.count()).where(
                    model.trade_date.between(start, end)).group_by(model.trade_date)):
                self.event_counts[day, dataset] = count
        for day, code in _read(db, select(StockSuspendDaily.trade_date, StockSuspendDaily.ts_code)
                .where(StockSuspendDaily.trade_date.between(start, end),
                       StockSuspendDaily.suspend_type == "S")):
            self.suspended[day].add(code)
        for row in _read(db, select(DataQualityDaily.trade_date, DataQualityDaily.dataset,
                DataQualityDaily.status, DataQualityDaily.issue_codes).where(
                DataQualityDaily.trade_date.between(start, end),
                DataQualityDaily.dataset.in_(["stock_st", "suspend_d", "stk_limit"]))):
            self.qualities[row.trade_date, row.dataset] = row

    def expected(self, day):
        return {row.ts_code for row in self.basic
                if is_stock_active_on(row.list_date, row.delist_date, day)} - self.suspended[day]


def check_raw_range(db, days, *, strategy):
    # One calendar month at a time, not all requested history in memory.
    remaining = iter(days)
    day = next(remaining, None)
    while day is not None:
        group = [day]
        following = next(remaining, None)
        while following is not None and (following.year, following.month) == (day.year, day.month):
            group.append(following)
            following = next(remaining, None)
        facts = RawRangeFacts(db, group[0], group[-1])
        for target in group:
            checkpoint()
            yield check_raw_completeness(db, target, strategy=strategy, persist=False, _facts=facts)
        day = following
