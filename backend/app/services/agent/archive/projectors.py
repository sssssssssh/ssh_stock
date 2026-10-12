"""V1 projectors for the exact content passed to Evidence v2, never business SQL."""

from typing import Any

from app.domain.agent.archive import PROJECTOR_VERSION, archive_error
from app.domain.agent.contracts import AgentToolResult, EvidenceRef
from app.services.agent.archive.canonical import archive_hash, archive_json
from app.services.agent.evidence import evidence_ref

RECORD_KEYS = {
    "data.coverage": {"quality_status", "dataset_coverage", "latest_trading_date"},
    "market.snapshot": {"regime", "market_score", "breadth", "liquidity"},
    "sector.top": {
        "sector_id",
        "sector_code",
        "sector_name",
        "heat_score",
        "heat_rank",
        "momentum",
        "lifecycle",
        "member_count",
    },
    "theme.top": {
        "theme_code",
        "theme_name",
        "heat_score",
        "heat_rank",
        "momentum",
        "lifecycle",
        "source_coverage",
        "data_coverage",
        "member_snapshot_date",
        "quality_warnings",
    },
    "opportunity.list": {
        "ts_code",
        "name",
        "state",
        "stage",
        "score",
        "left_reversal_score",
        "right_side_score",
        "trend_score",
        "reason_codes",
        "versions",
        "quality_warnings",
    },
    "backtest.summary": {
        "run_id",
        "status",
        "start_date",
        "end_date",
        "initial_cash",
        "latest_nav_date",
        "latest_nav",
        "latest_total_assets",
        "result_summary",
        "source_identity",
    },
    "performance.summary": {"report_ids", "performance", "risk", "trade", "period"},
    "walk_forward.summary": {
        "result_stage",
        "oos_sample",
        "returns",
        "parameter_switching",
        "train_to_oos_degradation",
        "policy_identity",
    },
    "walk_forward.window_lineage": {
        "study_id",
        "validation_id",
        "window_no",
        "train_start",
        "train_end",
        "test_start",
        "test_end",
        "train_run_id",
        "train_performance_id",
        "oos_run_id",
        "oos_performance_id",
        "selected_trial_id",
        "train_evaluation_id",
        "report_status",
        "validation_status",
        "train_report_status",
        "oos_report_status",
        "train_metrics",
        "oos_metrics",
        "degradation",
        "readiness",
    },
}
ARTIFACT_TYPES = {
    "performance_id": "PortfolioPerformanceReport",
    "risk_id": "PortfolioPerformanceRiskReport",
    "trade_id": "PortfolioPerformanceTradeReport",
    "period_id": "PortfolioPerformancePeriodReport",
}
SENSITIVE_KEYS = {
    "token",
    "api_key",
    "cookie",
    "authorization",
    "password",
    "secret",
    "database_url",
    "dsn",
    "system_prompt",
    "user_prompt",
    "prompt",
}


def check_safe(value: Any, depth: int = 0) -> None:
    if depth > 16:
        raise archive_error("ARCHIVE_LIMIT_EXCEEDED")
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in SENSITIVE_KEYS or any(
                lowered.endswith(f"_{word}")
                for word in ("token", "api_key", "password", "secret", "cookie")
            ):
                raise archive_error("ARCHIVE_UNSAFE_CONTENT")
            check_safe(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 4096:
            raise archive_error("ARCHIVE_LIMIT_EXCEEDED")
        for item in value:
            check_safe(item, depth + 1)


def validate_payload(payload: dict[str, Any]) -> None:
    AgentToolResult.model_validate(payload)
    name = payload["tool_name"]
    if name not in RECORD_KEYS or payload["tool_version"] != "1.0":
        raise archive_error("UNSUPPORTED_TOOL_VERSION")
    check_safe(payload)
    for record in payload["records"]:
        if set(record) - RECORD_KEYS[name]:
            raise archive_error("ARCHIVE_UNSAFE_CONTENT")


def verify_evidence_identity(ref: dict[str, Any], projection: dict[str, Any]) -> None:
    parsed = EvidenceRef.model_validate(ref)
    if parsed.evidence_version != "v2":
        raise archive_error("UNSUPPORTED_EVIDENCE_VERSION")
    regenerated = evidence_ref(
        layer=parsed.layer,
        source_type=parsed.source_type,
        entity_id=parsed.entity_id,
        date_value=parsed.trade_date,
        source_record_id=parsed.source_record_id,
        calc_version=parsed.calc_version,
        algo_version=parsed.algo_version,
        config_hash=parsed.config_hash,
        source_hash=parsed.source_hash,
        report_id=parsed.report_id,
        calc_run_id=parsed.calc_run_id,
        content=projection,
        quality_status=parsed.quality_status,
        limitations=parsed.limitations,
    )
    if (
        regenerated.content_hash != parsed.content_hash
        or regenerated.evidence_id != parsed.evidence_id
    ):
        raise archive_error("ARCHIVE_EVIDENCE_IDENTITY_MISMATCH")


def validate_projection(
    payload: dict[str, Any],
    ref: dict[str, Any],
    projection: dict[str, Any],
    *,
    version: str = PROJECTOR_VERSION,
) -> str:
    if version != PROJECTOR_VERSION:
        raise archive_error("UNSUPPORTED_PROJECTOR_VERSION")
    validate_payload(payload)
    check_safe(projection)
    name, records = payload["tool_name"], payload["records"]
    if name == "data.coverage":
        if len(records) != 1:
            raise archive_error("ARCHIVE_PROJECTION_MISMATCH")
        matched = [
            (i, row)
            for i, row in enumerate(records[0]["dataset_coverage"])
            if row["dataset"] == ref["entity_id"]
        ]
        if len(matched) != 1 or set(projection) != {"summary", "daily"}:
            raise archive_error("ARCHIVE_PROJECTION_MISMATCH")
        index, record = matched[0]
        daily = projection["daily"]
        if (
            not isinstance(daily, list)
            or not daily
            or any(
                set(row) != {"trade_date", "status", "expected_rows", "actual_rows"}
                for row in daily
            )
            or str(daily[-1]["trade_date"]) != ref["trade_date"]
        ):
            raise archive_error("ARCHIVE_PROJECTION_MISMATCH")
        if archive_hash(projection["summary"]) != archive_hash(record):
            raise archive_error("ARCHIVE_PROJECTION_MISMATCH")
        path = f"records.0.dataset_coverage.{index}"
    elif name in {"performance.summary", "walk_forward.summary"}:
        if len(records) != 1:
            raise archive_error("ARCHIVE_PROJECTION_MISMATCH")
        if name == "performance.summary":
            kinds = [
                kind
                for field, kind in ARTIFACT_TYPES.items()
                if str(payload["identity"].get(field)) == ref.get("report_id")
            ]
            if len(kinds) != 1:
                raise archive_error("ARCHIVE_PROJECTION_MISMATCH")
            expected = {
                "artifact_type": kinds[0],
                "bundle_identity": payload["identity"],
                "summary": records[0],
            }
        else:
            expected = {"identity": payload["identity"], "summary": records[0]}
        if archive_hash(expected) != archive_hash(projection):
            raise archive_error("ARCHIVE_PROJECTION_MISMATCH")
        path = "records.0"
    else:
        entity_fields = {
            "sector.top": "sector_id",
            "theme.top": "theme_code",
            "opportunity.list": "ts_code",
            "backtest.summary": "run_id",
        }
        if name == "market.snapshot":
            matched = [(i, row) for i, row in enumerate(records) if ref["entity_id"] == "market"]
        elif name == "walk_forward.window_lineage":
            matched = [
                (i, row)
                for i, row in enumerate(records)
                if f"{row['study_id']}:window:{row['window_no']}" == ref["entity_id"]
            ]
        else:
            matched = [
                (i, row)
                for i, row in enumerate(records)
                if str(row[entity_fields[name]]) == ref["entity_id"]
            ]
        if len(matched) != 1:
            raise archive_error("ARCHIVE_PROJECTION_MISMATCH")
        index, record = matched[0]
        expected = (
            {
                "study_id": record["study_id"],
                "validation_id": record["validation_id"],
                "window": record,
            }
            if name == "walk_forward.window_lineage"
            else record
        )
        if archive_hash(expected) != archive_hash(projection):
            raise archive_error("ARCHIVE_PROJECTION_MISMATCH")
        path = f"records.{index}"
    verify_evidence_identity(ref, archive_json(projection))
    return path
