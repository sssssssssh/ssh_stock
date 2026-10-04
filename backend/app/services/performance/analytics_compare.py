import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.performance_period_config import ANALYTICS_READ_SCHEMA_VERSION
from app.models.performance import PortfolioPerformanceDaily
from app.services.performance.analytics_bundle import (
    AnalyticsArtifactBundle,
    AnalyticsArtifactBundleResolver,
)
from app.services.performance.analytics_read import AnalyticsReadApplicationService


class AnalyticsCompareError(RuntimeError):
    def __init__(self, code: str, message: str, *, mismatch_fields: list[str] | None = None):
        self.code = code
        self.mismatch_fields = mismatch_fields or []
        super().__init__(message)


@dataclass(frozen=True)
class AnalyticsCompareSelection:
    run_id: uuid.UUID
    performance_id: uuid.UUID | None = None
    risk_id: uuid.UUID | None = None
    trade_id: uuid.UUID | None = None


class AnalyticsCompareApplicationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.resolver = AnalyticsArtifactBundleResolver(db)

    def compare(self, items: list[AnalyticsCompareSelection]) -> dict[str, Any]:
        if len(items) < 2:
            raise AnalyticsCompareError(
                "ANALYTICS_COMPARE_TOO_FEW_ITEMS", "at least two compare items are required"
            )
        if len(items) > 20:
            raise AnalyticsCompareError(
                "ANALYTICS_COMPARE_TOO_MANY_ITEMS", "at most twenty compare items are allowed"
            )
        if len({item.run_id for item in items}) != len(items):
            raise AnalyticsCompareError(
                "ANALYTICS_COMPARE_DUPLICATE_RUN", "compare run_id values must be unique"
            )
        bundles = self.resolver.resolve_many(
            [
                (item.run_id, item.performance_id, item.risk_id, item.trade_id)
                for item in items
            ]
        )
        mismatch_fields = self._mismatches(bundles)
        if mismatch_fields:
            raise AnalyticsCompareError(
                "ANALYTICS_COMPARE_INCOMPATIBLE",
                "selected analytics artifacts are not comparable",
                mismatch_fields=mismatch_fields,
            )
        read = AnalyticsReadApplicationService(self.db)
        return {
            "schema_version": ANALYTICS_READ_SCHEMA_VERSION,
            "items": [
                read._summary(bundle).model_dump(mode="json") for bundle in bundles
            ],
        }

    def _mismatches(self, bundles: list[AnalyticsArtifactBundle]) -> list[str]:
        first = bundles[0]
        checks = {
            "performance_version": lambda row: row.performance.performance_version,
            "performance_config_hash": lambda row: row.performance.performance_config_hash,
            "start_date": lambda row: row.performance.start_date,
            "end_date": lambda row: row.performance.end_date,
            "trade_days": lambda row: row.performance.trade_days,
            "risk_version": lambda row: row.risk.risk_version,
            "risk_config_hash": lambda row: row.risk.risk_config_hash,
            "benchmark_code": lambda row: row.risk.benchmark_code,
            "trade_version": lambda row: row.trade.trade_version,
            "trade_config_hash": lambda row: row.trade.trade_config_hash,
        }
        mismatches = [
            field
            for field, getter in checks.items()
            if any(getter(bundle) != getter(first) for bundle in bundles[1:])
        ]
        ids = [bundle.performance.id for bundle in bundles]
        daily_rows = self.db.execute(
            select(
                PortfolioPerformanceDaily.performance_id,
                PortfolioPerformanceDaily.trade_date,
            )
            .where(PortfolioPerformanceDaily.performance_id.in_(ids))
            .order_by(
                PortfolioPerformanceDaily.performance_id,
                PortfolioPerformanceDaily.trade_date,
            )
            .execution_options(populate_existing=True)
        ).all()
        dates_by_id: dict[uuid.UUID, list] = {identity: [] for identity in ids}
        for performance_id, trade_date in daily_rows:
            dates_by_id[performance_id].append(trade_date)
        first_dates = dates_by_id[first.performance.id]
        if any(dates_by_id[bundle.performance.id] != first_dates for bundle in bundles[1:]):
            mismatches.append("trade_date_set")
        return mismatches
