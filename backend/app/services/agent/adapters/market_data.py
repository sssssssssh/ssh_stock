from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.agent.contracts import (
    AgentToolResult,
    DataCoverageInput,
    MarketSnapshotInput,
    OpportunityListInput,
    Readiness,
    SectorTopInput,
    ThemeTopInput,
)
from app.domain.agent.errors import identity_mismatch, not_ready
from app.models.market_data import (
    DataQualityDaily,
    MarketDaily,
    Sector,
    SectorFactorDaily,
    StockBasic,
    StockOpportunityDaily,
    Theme,
    ThemeFactorDaily,
    TradeCalendar,
)
from app.services.agent.evidence import evidence_ref
from app.services.analysis_filters import (
    opportunity_identity_filters,
    theme_factor_identity_filters,
)
from app.services.analysis_identity import (
    MARKET_CALC_VERSION,
    OPPORTUNITY_CALC_VERSION,
    SECTOR_CALC_VERSION,
    THEME_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash


class MarketDataAgentAdapter:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.strategy_hash = analysis_strategy_hash(settings.strategy)
        self.opportunity_hash = config_hash(settings.opportunity_config)

    def data_coverage(self, request: DataCoverageInput) -> AgentToolResult:
        open_dates = list(
            self.db.scalars(
                select(TradeCalendar.cal_date)
                .where(
                    TradeCalendar.cal_date >= request.start_date,
                    TradeCalendar.cal_date <= request.end_date,
                    TradeCalendar.is_open.is_(True),
                )
                .order_by(TradeCalendar.cal_date)
            ).all()
        )
        rows = list(
            self.db.scalars(
                select(DataQualityDaily)
                .where(
                    DataQualityDaily.trade_date >= request.start_date,
                    DataQualityDaily.trade_date <= request.end_date,
                )
                .order_by(DataQualityDaily.dataset, DataQualityDaily.trade_date)
            ).all()
        )
        latest_trading_date = self.db.scalar(
            select(func.max(TradeCalendar.cal_date)).where(
                TradeCalendar.cal_date <= request.end_date,
                TradeCalendar.is_open.is_(True),
            )
        )
        grouped: dict[str, list[DataQualityDaily]] = defaultdict(list)
        for row in rows:
            grouped[row.dataset].append(row)
        records: list[dict[str, Any]] = []
        warnings: list[str] = []
        evidence = []
        overall = "PASS"
        for dataset, dataset_rows in sorted(grouped.items()):
            expected = sum(int(row.expected_rows or 0) for row in dataset_rows)
            actual = sum(int(row.actual_rows or 0) for row in dataset_rows)
            statuses = [row.status for row in dataset_rows]
            quality = _quality_status(statuses)
            overall = _worse_quality(overall, quality)
            coverage = actual / expected if expected else None
            records.append(
                {
                    "dataset": dataset,
                    "quality_status": quality,
                    "expected_rows": expected,
                    "actual_rows": actual,
                    "coverage_rate": coverage,
                    "quality_days": len(dataset_rows),
                    "open_trade_days": len(open_dates),
                    "missing_quality_days": max(len(open_dates) - len(dataset_rows), 0),
                }
            )
            if coverage is None:
                warnings.append(f"DATA_UNAVAILABLE:{dataset}:coverage_rate")
                overall = _worse_quality(overall, "WARNING")
            if len(dataset_rows) < len(open_dates):
                warnings.append(f"DATA_UNAVAILABLE:{dataset}:quality_days")
                overall = _worse_quality(overall, "WARNING")
            evidence.append(
                evidence_ref(
                    layer="DATA",
                    source_type="dataset",
                    entity_id=dataset,
                    date_value=dataset_rows[-1].trade_date,
                    source_record_id=f"{request.start_date}:{request.end_date}",
                    observed_at=dataset_rows[-1].checked_at,
                    quality_status=quality,
                )
            )
        if not open_dates or not records:
            overall = "ERROR"
            warnings.append("DATA_UNAVAILABLE:coverage")
        status = "READY" if overall == "PASS" else "DATA_INCOMPLETE"
        return AgentToolResult(
            tool_name="data.coverage",
            status=status,
            as_of_date=latest_trading_date,
            identity={
                "start_date": request.start_date,
                "end_date": request.end_date,
                "calendar": "trade_calendar",
            },
            records=[
                {
                    "quality_status": overall,
                    "dataset_coverage": records,
                    "latest_trading_date": latest_trading_date,
                }
            ],
            evidence=evidence,
            warnings=sorted(set(warnings)),
            readiness=Readiness(
                ready=status == "READY",
                code=status,
                details={"quality_status": overall, "open_trade_days": len(open_dates)},
            ),
        )

    def market_snapshot(self, request: MarketSnapshotInput) -> AgentToolResult:
        identity = (
            MarketDaily.calc_version == MARKET_CALC_VERSION,
            MarketDaily.config_hash == self.strategy_hash,
        )
        target = self._derived_date(MarketDaily, request.trade_date, identity)
        row = self.db.scalar(select(MarketDaily).where(MarketDaily.trade_date == target, *identity))
        if row is None:
            raise not_ready("market snapshot is not ready for the requested identity")
        record = {
            "regime": row.regime,
            "market_score": row.market_score,
            "breadth": {
                "breadth20": row.breadth20,
                "breadth60": row.breadth60,
                "up_count": row.up_count,
                "down_count": row.down_count,
                "up_rate": row.up_rate,
            },
            "liquidity": {
                "total_amount": row.total_amount,
                "amount_ratio20": row.amount_ratio20,
                "liquidity_score": row.liquidity_score,
            },
        }
        warnings = _null_warnings(record, "market")
        return self._derived_result(
            "market.snapshot",
            target,
            [record],
            calc_version=row.calc_version,
            config_hash=row.config_hash,
            entity_ids=["market"],
            observed_at=row.calculated_at,
            warnings=warnings,
        )

    def sector_top(self, request: SectorTopInput) -> AgentToolResult:
        identity = (
            SectorFactorDaily.calc_version == SECTOR_CALC_VERSION,
            SectorFactorDaily.config_hash == self.strategy_hash,
        )
        target = self._derived_date(SectorFactorDaily, request.trade_date, identity)
        rows = self.db.execute(
            select(SectorFactorDaily, Sector)
            .join(Sector, Sector.sector_id == SectorFactorDaily.sector_id)
            .where(SectorFactorDaily.trade_date == target, *identity)
            .order_by(SectorFactorDaily.heat_rank, desc(SectorFactorDaily.heat_score))
            .limit(request.limit)
        ).all()
        records = [
            {
                "sector_id": factor.sector_id,
                "sector_code": sector.source_code,
                "sector_name": sector.name,
                "heat_score": factor.heat_score,
                "heat_rank": factor.heat_rank,
                "momentum": {
                    "heat_momentum1": factor.heat_momentum1,
                    "heat_momentum3": factor.heat_momentum3,
                    "rank_change": factor.rank_change,
                },
                "lifecycle": factor.lifecycle,
                "member_count": factor.member_count,
            }
            for factor, sector in rows
        ]
        if not rows:
            return self._empty_result("sector.top", target, self._analysis_identity())
        return self._derived_result(
            "sector.top",
            target,
            records,
            calc_version=rows[0][0].calc_version,
            config_hash=rows[0][0].config_hash,
            entity_ids=[str(row[0].sector_id) for row in rows],
            observed_at=rows[0][0].calculated_at,
            warnings=_null_warnings(records, "sector"),
        )

    def theme_top(self, request: ThemeTopInput) -> AgentToolResult:
        identity = theme_factor_identity_filters(self.settings)
        target = self._derived_date(ThemeFactorDaily, request.trade_date, identity)
        rows = self.db.execute(
            select(ThemeFactorDaily, Theme)
            .join(Theme, Theme.theme_code == ThemeFactorDaily.theme_code)
            .where(ThemeFactorDaily.trade_date == target, *identity)
            .order_by(ThemeFactorDaily.heat_rank, desc(ThemeFactorDaily.heat_score))
            .limit(request.limit)
        ).all()
        if not rows:
            return self._empty_result("theme.top", target, self._theme_identity())
        warnings: list[str] = []
        degraded = False
        records = []
        evidence = []
        for factor, theme in rows:
            row_warnings = []
            if factor.source_coverage is None or factor.source_coverage < 1:
                row_warnings.append("SOURCE_DEGRADED")
                degraded = True
            if factor.member_snapshot_date is None:
                row_warnings.append("DATA_UNAVAILABLE:member_snapshot")
                degraded = True
            records.append(
                {
                    "theme_code": factor.theme_code,
                    "theme_name": theme.name,
                    "heat_score": factor.heat_score,
                    "heat_rank": factor.heat_rank,
                    "momentum": {
                        "heat_momentum1": factor.heat_momentum1,
                        "heat_momentum3": factor.heat_momentum3,
                        "rank_change": factor.rank_change,
                    },
                    "lifecycle": factor.lifecycle,
                    "source_coverage": factor.source_coverage,
                    "data_coverage": factor.data_coverage,
                    "member_snapshot_date": factor.member_snapshot_date,
                    "quality_warnings": row_warnings,
                }
            )
            row_warnings.extend(_null_warnings(records[-1], f"theme.{factor.theme_code}"))
            warnings.extend(row_warnings)
            evidence.append(
                evidence_ref(
                    layer="FACTOR_TREND",
                    source_type="derived_record",
                    entity_id=factor.theme_code,
                    date_value=target,
                    source_record_id=f"{target}:{factor.theme_code}",
                    calc_version=factor.calc_version,
                    config_hash=factor.config_hash,
                    observed_at=factor.calculated_at,
                    quality_status="WARNING" if row_warnings else "PASS",
                    limitations=[
                        f"member_snapshot_date={factor.member_snapshot_date}",
                        *row_warnings,
                    ],
                )
            )
        status = "SOURCE_DEGRADED" if degraded else "READY"
        return AgentToolResult(
            tool_name="theme.top",
            status=status,
            as_of_date=target,
            identity=self._theme_identity(),
            records=records,
            evidence=evidence,
            warnings=sorted(set(warnings)),
            readiness=Readiness(ready=True, code=status),
        )

    def opportunity_list(self, request: OpportunityListInput) -> AgentToolResult:
        identity = opportunity_identity_filters(self.settings)
        target = self._derived_date(StockOpportunityDaily, request.trade_date, identity)
        filters: list[Any] = [StockOpportunityDaily.trade_date == target, *identity]
        if request.stage:
            filters.append(StockOpportunityDaily.opportunity_stage == request.stage)
        rows = self.db.execute(
            select(StockOpportunityDaily, StockBasic.name)
            .outerjoin(StockBasic, StockBasic.ts_code == StockOpportunityDaily.ts_code)
            .where(*filters)
            .order_by(
                desc(StockOpportunityDaily.opportunity_score),
                StockOpportunityDaily.ts_code,
            )
            .limit(request.limit)
        ).all()
        if not rows:
            return self._empty_result("opportunity.list", target, self._opportunity_identity())
        records = []
        evidence = []
        warnings: list[str] = []
        for row, name in rows:
            record = {
                "ts_code": row.ts_code,
                "name": name,
                "state": row.state,
                "stage": row.opportunity_stage,
                "score": row.opportunity_score,
                "left_reversal_score": row.left_reversal_score,
                "right_side_score": row.right_side_score,
                "trend_score": row.trend_score,
                "reason_codes": row.reason_codes,
                "versions": {
                    "algo_version": row.algo_version,
                    "calc_version": row.calc_version,
                    "config_hash": row.config_hash,
                    "source_strategy_config_hash": row.source_strategy_config_hash,
                },
            }
            row_warnings = _null_warnings(record, f"opportunity.{row.ts_code}")
            record["quality_warnings"] = row_warnings
            records.append(record)
            warnings.extend(row_warnings)
            evidence.append(
                evidence_ref(
                    layer="FACTOR_TREND",
                    source_type="derived_record",
                    entity_id=row.ts_code,
                    date_value=target,
                    source_record_id=f"{target}:{row.ts_code}:{row.algo_version}",
                    calc_version=row.calc_version,
                    algo_version=row.algo_version,
                    config_hash=row.config_hash,
                    observed_at=row.calculated_at,
                    quality_status="WARNING" if row_warnings else "PASS",
                    limitations=[
                        "same-day snapshot; no forward returns",
                        *row_warnings,
                    ],
                )
            )
        return AgentToolResult(
            tool_name="opportunity.list",
            status="READY",
            as_of_date=target,
            identity=self._opportunity_identity(),
            records=records,
            evidence=evidence,
            warnings=sorted(set(warnings)),
            readiness=Readiness(ready=True, code="READY"),
        )

    def _derived_date(self, model: Any, requested: date | None, identity: tuple[Any, ...]) -> date:
        if requested is None:
            target = self.db.scalar(select(func.max(model.trade_date)).where(*identity))
            if target is None:
                raise not_ready(f"{model.__tablename__} has no current-identity data")
            return target
        exists = self.db.scalar(
            select(func.count()).select_from(model).where(model.trade_date == requested, *identity)
        )
        if int(exists or 0) > 0:
            return requested
        any_identity = self.db.scalar(
            select(func.count()).select_from(model).where(model.trade_date == requested)
        )
        if int(any_identity or 0) > 0:
            raise identity_mismatch(
                f"{model.__tablename__} exists for {requested} under another identity"
            )
        raise not_ready(f"{model.__tablename__} is not ready for {requested}")

    def _derived_result(
        self,
        tool_name: str,
        target: date,
        records: list[dict[str, Any]],
        *,
        calc_version: str | None,
        config_hash: str | None,
        entity_ids: list[str],
        observed_at: Any,
        warnings: list[str] | None = None,
    ) -> AgentToolResult:
        identity = {
            "calc_version": calc_version,
            "config_hash": config_hash,
        }
        return AgentToolResult(
            tool_name=tool_name,
            status="READY",
            as_of_date=target,
            identity=identity,
            records=records,
            evidence=[
                evidence_ref(
                    layer="FACTOR_TREND",
                    source_type="derived_record",
                    entity_id=entity_id,
                    date_value=target,
                    source_record_id=f"{target}:{entity_id}",
                    calc_version=calc_version,
                    config_hash=config_hash,
                    observed_at=observed_at,
                    quality_status="WARNING" if warnings else "PASS",
                    limitations=warnings or [],
                )
                for entity_id in entity_ids
            ],
            warnings=warnings or [],
            readiness=Readiness(ready=True, code="READY"),
        )

    @staticmethod
    def _empty_result(tool_name: str, target: date, identity: dict[str, Any]) -> AgentToolResult:
        return AgentToolResult(
            tool_name=tool_name,
            status="EMPTY_RESULT",
            as_of_date=target,
            identity=identity,
            warnings=["EMPTY_RESULT"],
            readiness=Readiness(ready=True, code="EMPTY_RESULT"),
        )

    def _analysis_identity(self) -> dict[str, Any]:
        return {
            "algo_version": self.settings.algo_version,
            "config_hash": self.strategy_hash,
        }

    def _opportunity_identity(self) -> dict[str, Any]:
        return {
            **self._analysis_identity(),
            "calc_version": OPPORTUNITY_CALC_VERSION,
            "opportunity_config_hash": self.opportunity_hash,
        }

    def _theme_identity(self) -> dict[str, Any]:
        return {
            **self._analysis_identity(),
            "calc_version": THEME_CALC_VERSION,
            "theme_config_hash": self.opportunity_hash,
            "source_strategy_config_hash": self.strategy_hash,
        }


_QUALITY_ORDER = {"PASS": 0, "UNKNOWN": 1, "WARNING": 2, "ERROR": 3}


def _quality_status(statuses: list[str]) -> str:
    mapped = []
    for status in statuses:
        if status == "PASS":
            mapped.append("PASS")
        elif status == "WARNING":
            mapped.append("WARNING")
        elif status in {"ERROR", "FAILED"}:
            mapped.append("ERROR")
        else:
            mapped.append("UNKNOWN")
    return max(mapped or ["UNKNOWN"], key=_QUALITY_ORDER.__getitem__)


def _worse_quality(left: str, right: str) -> str:
    return max((left, right), key=_QUALITY_ORDER.__getitem__)


def _null_warnings(value: Any, prefix: str) -> list[str]:
    if value is None:
        return [f"DATA_UNAVAILABLE:{prefix}"]
    warnings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            warnings.extend(_null_warnings(item, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            warnings.extend(_null_warnings(item, f"{prefix}[{index}]"))
    return sorted(set(warnings))
