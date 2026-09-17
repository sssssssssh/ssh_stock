from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.market_data import (
    DataQualityDaily,
    StockOpportunityDaily,
    StockStateDaily,
    ThemeFactorDaily,
)
from app.services.analysis_identity import (
    OPPORTUNITY_CALC_VERSION,
    THEME_CALC_VERSION,
    TREND_CALC_VERSION,
)


@dataclass(frozen=True)
class OpportunityQualityResult:
    counts: dict[str, int]
    results: dict[str, str]

    @property
    def is_complete(self) -> bool:
        return all(status != "ERROR" for status in self.results.values())


def check_opportunity_quality(
    db: Session,
    trade_date: date,
    *,
    strategy_hash: str,
    opportunity_hash: str,
    algo_version: str,
    config: dict[str, Any],
) -> OpportunityQualityResult:
    state_count = _count(
        db,
        StockStateDaily,
        StockStateDaily.trade_date == trade_date,
        StockStateDaily.algo_version == algo_version,
        StockStateDaily.calc_version == TREND_CALC_VERSION,
        StockStateDaily.config_hash == strategy_hash,
    )
    opportunity_count = _count(
        db,
        StockOpportunityDaily,
        StockOpportunityDaily.trade_date == trade_date,
        StockOpportunityDaily.algo_version == algo_version,
        StockOpportunityDaily.calc_version == OPPORTUNITY_CALC_VERSION,
        StockOpportunityDaily.config_hash == opportunity_hash,
    )
    source_quality = db.execute(
        select(
            DataQualityDaily.status,
            DataQualityDaily.actual_rows,
        ).where(
            DataQualityDaily.trade_date == trade_date,
            DataQualityDaily.dataset == "ths_theme_daily",
        )
    ).first()
    source_status = source_quality.status if source_quality else None
    theme_expected = (
        int(source_quality.actual_rows or 0)
        if source_quality and source_status in {"PASS", "WARNING"}
        else 0
    )
    theme_factor_count = _count(
        db,
        ThemeFactorDaily,
        ThemeFactorDaily.trade_date == trade_date,
        ThemeFactorDaily.calc_version == THEME_CALC_VERSION,
        ThemeFactorDaily.config_hash == opportunity_hash,
    )
    quality = config.get("opportunity_quality", {})
    results = {
        "opportunity_vs_state": _coverage_status(
            state_count,
            opportunity_count,
            quality.get("opportunity_vs_state", {}),
            empty_expected_status="PASS",
        ),
        "theme_factor_vs_theme_daily": (
            _coverage_status(
                theme_expected,
                theme_factor_count,
                quality.get("theme_factor_vs_theme_daily", {}),
                empty_expected_status="PASS",
            )
            if source_status in {"PASS", "WARNING"}
            else "SKIPPED"
        ),
    }
    return OpportunityQualityResult(
        counts={
            "state": state_count,
            "opportunity": opportunity_count,
            "theme_daily": theme_expected,
            "theme_factor": theme_factor_count,
        },
        results=results,
    )


def _coverage_status(
    expected: int,
    actual: int,
    config: dict[str, Any],
    *,
    empty_expected_status: str,
) -> str:
    if expected <= 0:
        return empty_expected_status
    coverage = min(actual / expected, 1.0)
    error_rate = float(config.get("error_coverage_rate", 0.90))
    warning_rate = float(config.get("warning_coverage_rate", 0.98))
    if coverage < error_rate:
        return "ERROR"
    if coverage < warning_rate:
        return "WARNING"
    return "PASS"


def _count(db: Session, model: type, *criteria: Any) -> int:
    return int(
        db.execute(select(func.count()).select_from(model).where(*criteria)).scalar_one()
    )
