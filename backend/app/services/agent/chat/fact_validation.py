"""Pure, frozen field-validation contract shared by online and offline evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

from app.domain.agent.chat import StructuredFact


@dataclass(frozen=True)
class ComparisonFactContext:
    tool_name: str
    entity: str
    trade_date: str
    path: str
    unit: str
    sample_role: str
    evidence: dict[str, Any]
    identity: dict[str, Any]


_ALLOWED_PATHS: dict[str, tuple[str, ...]] = {
    "test.read": ("records.*.value",),
    "data.coverage": (
        "records.*.dataset_coverage.*.expected_rows",
        "records.*.dataset_coverage.*.actual_rows",
        "records.*.dataset_coverage.*.coverage_rate",
        "records.*.dataset_coverage.*.quality_days",
        "records.*.dataset_coverage.*.open_trade_days",
        "records.*.dataset_coverage.*.missing_quality_days",
        "records.*.latest_trading_date",
    ),
    "market.snapshot": (
        "records.*.market_score",
        "records.*.breadth.breadth20",
        "records.*.breadth.breadth60",
        "records.*.breadth.up_count",
        "records.*.breadth.down_count",
        "records.*.breadth.up_rate",
        "records.*.liquidity.total_amount",
        "records.*.liquidity.amount_ratio20",
        "records.*.liquidity.liquidity_score",
    ),
    "sector.top": (
        "records.*.sector_id",
        "records.*.sector_code",
        "records.*.heat_score",
        "records.*.heat_rank",
        "records.*.momentum.heat_momentum1",
        "records.*.momentum.heat_momentum3",
        "records.*.momentum.rank_change",
        "records.*.member_count",
    ),
    "theme.top": (
        "records.*.theme_code",
        "records.*.heat_score",
        "records.*.heat_rank",
        "records.*.momentum.heat_momentum1",
        "records.*.momentum.heat_momentum3",
        "records.*.momentum.rank_change",
        "records.*.source_coverage",
        "records.*.data_coverage",
        "records.*.member_snapshot_date",
    ),
    "opportunity.list": (
        "records.*.ts_code",
        "records.*.score",
        "records.*.left_reversal_score",
        "records.*.right_side_score",
        "records.*.trend_score",
    ),
    "backtest.summary": (
        "records.*.run_id",
        "records.*.start_date",
        "records.*.end_date",
        "records.*.initial_cash",
        "records.*.latest_nav_date",
        "records.*.latest_nav",
        "records.*.latest_total_assets",
    ),
    "performance.summary": (
        "records.*.performance.start_date",
        "records.*.performance.end_date",
        "records.*.performance.trade_days",
        "records.*.performance.final_nav",
        "records.*.performance.cumulative_return",
        "records.*.performance.annualized_return",
        "records.*.performance.max_drawdown",
        "records.*.risk.benchmark_cumulative_return",
        "records.*.risk.excess_cumulative_return",
        "records.*.risk.sharpe_ratio",
        "records.*.risk.sortino_ratio",
        "records.*.risk.calmar_ratio",
        "records.*.trade.total_turnover",
        "records.*.trade.total_execution_cost",
        "records.*.trade.closed_episode_count",
        "records.*.trade.open_episode_count",
        "records.*.trade.win_rate",
        "records.*.trade.profit_factor",
        "records.*.period.month_count",
        "records.*.period.year_count",
    ),
    "walk_forward.summary": (
        "records.*.oos_sample.window_count",
        "records.*.oos_sample.total_oos_trade_days",
        "records.*.oos_sample.positive_oos_window_count",
        "records.*.oos_sample.positive_oos_window_rate",
        "records.*.returns.stitched_oos_final_nav",
        "records.*.returns.stitched_oos_cumulative_return",
        "records.*.returns.stitched_oos_annualized_return",
        "records.*.returns.stitched_oos_max_drawdown",
        "records.*.returns.stitched_excess_cumulative_return",
        "records.*.parameter_switching.unique_selected_parameter_hash_count",
        "records.*.parameter_switching.dominant_parameter_hash_rate",
        "records.*.parameter_switching.transition_count",
        "records.*.parameter_switching.switch_count",
        "records.*.parameter_switching.switch_rate",
        "records.*.train_to_oos_degradation.mean_return_degradation",
        "records.*.train_to_oos_degradation.median_return_degradation",
        "records.*.train_to_oos_degradation.mean_drawdown_worsening",
        "records.*.train_to_oos_degradation.median_drawdown_worsening",
    ),
    "walk_forward.window_lineage": (
        "records.*.study_id",
        "records.*.validation_id",
        "records.*.selected_trial_id",
        "records.*.train_run_id",
        "records.*.oos_run_id",
        "records.*.train_performance_id",
        "records.*.oos_performance_id",
        "records.*.train_evaluation_id",
        "records.*.window_no",
        "records.*.train_start",
        "records.*.train_end",
        "records.*.test_start",
        "records.*.test_end",
        "records.*.train_metrics.annualized_return",
        "records.*.train_metrics.max_drawdown_abs",
        "records.*.train_metrics.sharpe_ratio",
        "records.*.train_metrics.annualized_turnover",
        "records.*.oos_metrics.cumulative_return",
        "records.*.oos_metrics.annualized_return",
        "records.*.oos_metrics.max_drawdown_abs",
        "records.*.oos_metrics.sharpe_ratio",
        "records.*.oos_metrics.annualized_turnover",
        "records.*.oos_metrics.total_cost_to_initial_capital",
        "records.*.oos_metrics.win_rate",
        "records.*.oos_metrics.profit_factor",
        "records.*.degradation.return",
        "records.*.degradation.sharpe",
        "records.*.degradation.drawdown",
        "records.*.degradation.turnover",
    ),
}


@dataclass(frozen=True)
class _EvidenceBinding:
    context: Any
    ref: dict[str, Any]
    ref_index: int


class _ClaimValidationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _validate_fact_binding(
    fact: StructuredFact,
    binding: _EvidenceBinding,
) -> ComparisonFactContext:
    tool_name = binding.context.tool_name
    parts = fact.path.split(".")
    if not any(
        len(parts) == len(pattern.split("."))
        and all(
            token == expected or (expected == "*" and token.isdigit())
            for token, expected in zip(parts, pattern.split("."), strict=True)
        )
        for pattern in _ALLOWED_PATHS.get(tool_name, ())
    ):
        raise _ClaimValidationError("UNCONTROLLED_FIELD_PATH")
    records = binding.context.payload.get("records")
    if not isinstance(records, list):
        raise _ClaimValidationError("EVIDENCE_RECORD_MISMATCH")
    record_index = int(fact.path.split(".")[1])
    refs = binding.context.payload.get("evidence")
    if (
        isinstance(refs, list)
        and len(records) > 1
        and len(refs) == len(records)
        and binding.ref_index != record_index
    ):
        raise _ClaimValidationError("EVIDENCE_RECORD_MISMATCH")
    if str(binding.ref.get("entity_id")) != fact.entity:
        raise _ClaimValidationError("ENTITY_MISMATCH")
    evidence_date = binding.ref.get("trade_date") or binding.context.payload.get("as_of_date")
    if str(evidence_date) != fact.trade_date.isoformat():
        raise _ClaimValidationError("TRADE_DATE_MISMATCH")
    actual = _resolve_path(binding.context.payload, fact.path, allow_text=fact.unit == "identifier")
    identity = binding.context.payload.get("identity")
    identity = identity if isinstance(identity, dict) else {}
    if tool_name == "performance.summary":
        section = fact.path.split(".")[2]
        expected_report_id = identity.get(f"{section}_id")
        if section not in {"performance", "risk", "trade", "period"}:
            raise _ClaimValidationError("EVIDENCE_RECORD_MISMATCH")
        if expected_report_id is not None and str(binding.ref.get("report_id")) != str(
            expected_report_id
        ):
            raise _ClaimValidationError("EVIDENCE_RECORD_MISMATCH")
    if tool_name == "data.coverage":
        parts = fact.path.split(".")
        if len(parts) >= 5 and parts[2] == "dataset_coverage":
            dataset = _resolve_path(
                binding.context.payload,
                f"records.{parts[1]}.dataset_coverage.{parts[3]}.dataset",
                allow_text=True,
            )
            if str(dataset) != fact.entity:
                raise _ClaimValidationError("ENTITY_MISMATCH")
    _compare_value(actual, fact.value, fact.unit, fact.path)
    return ComparisonFactContext(
        tool_name=tool_name,
        entity=fact.entity,
        trade_date=fact.trade_date.isoformat(),
        path=fact.path,
        unit=fact.unit,
        sample_role=fact.sample_role,
        evidence=binding.ref,
        identity=identity,
    )


def _resolve_path(
    payload: dict[str, Any],
    path: str,
    *,
    allow_text: bool = False,
) -> Any:
    value: Any = payload
    try:
        for part in path.split("."):
            value = value[int(part)] if isinstance(value, list) else value[part]
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise _ClaimValidationError("EVIDENCE_RECORD_MISMATCH") from exc
    if value is None or isinstance(value, (dict, list, bool)):
        raise _ClaimValidationError("EVIDENCE_RECORD_MISMATCH")
    if not allow_text and isinstance(value, str) and not _looks_numeric_or_date(value):
        raise _ClaimValidationError("EVIDENCE_RECORD_MISMATCH")
    return value


def _compare_value(actual: Any, claimed: Any, unit: str, path: str) -> None:
    if unit not in _allowed_units(path):
        raise _ClaimValidationError("UNIT_MISMATCH")
    if unit == "date":
        actual_date = actual.isoformat() if isinstance(actual, date) else str(actual)
        try:
            date.fromisoformat(actual_date)
            date.fromisoformat(str(claimed))
        except ValueError as exc:
            raise _ClaimValidationError("VALUE_MISMATCH") from exc
        if actual_date != str(claimed):
            raise _ClaimValidationError("VALUE_MISMATCH")
        return
    if unit == "identifier":
        if str(actual) != str(claimed):
            raise _ClaimValidationError("VALUE_MISMATCH")
        return
    try:
        actual_decimal = Decimal(str(actual))
        claimed_decimal = Decimal(str(claimed))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise _ClaimValidationError("VALUE_MISMATCH") from exc
    if (
        not actual_decimal.is_finite()
        or not claimed_decimal.is_finite()
        or any(
            len(value.as_tuple().digits) > 128 or abs(value.as_tuple().exponent) > 128
            for value in (actual_decimal, claimed_decimal)
        )
    ):
        raise _ClaimValidationError("VALUE_MISMATCH")
    with localcontext() as context:
        context.prec = 1000
        if unit == "percent":
            actual_decimal *= Decimal("100")
        if actual_decimal != claimed_decimal:
            raise _ClaimValidationError("VALUE_MISMATCH")


def _allowed_units(path: str) -> set[str]:
    leaf = path.split(".")[-1]
    if leaf.endswith("_id") or leaf in {"ts_code", "theme_code", "sector_code"}:
        return {"identifier"}
    if leaf in {"train_start", "train_end", "test_start", "test_end"}:
        return {"date"}
    if leaf.endswith("date"):
        return {"date"}
    if leaf.endswith("rank") or leaf == "rank_change":
        return {"rank"}
    if any(token in leaf for token in ("count", "rows", "days")):
        return {"count"}
    if any(token in leaf for token in ("return", "drawdown", "rate", "coverage", "ratio")):
        return {"decimal", "ratio", "percent"}
    if any(token in leaf for token in ("cash", "assets", "amount", "cost", "turnover")):
        return {"currency", "decimal"}
    if "nav" in leaf:
        return {"nav", "decimal"}
    if "score" in leaf or "momentum" in leaf:
        return {"score", "decimal"}
    return {"decimal"}


def _looks_numeric_or_date(value: str) -> bool:
    try:
        Decimal(value)
        return True
    except InvalidOperation:
        pass
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False
