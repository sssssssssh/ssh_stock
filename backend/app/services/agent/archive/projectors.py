"""V1 projectors for the exact content passed to Evidence v2, never business SQL."""

from typing import Any

from app.domain.agent.archive import PROJECTOR_VERSION, archive_error
from app.domain.agent.chat import ChatCitation
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


def verify_citation(citation: ChatCitation, ref, tool_name):
    fields = {
        "evidence_id",
        "evidence_version",
        "entity_id",
        "report_id",
        "calc_run_id",
        "calc_version",
        "algo_version",
        "config_hash",
        "source_hash",
        "content_hash",
    }
    data = citation.model_dump(mode="json")
    if (
        citation.tool_name != tool_name
        or data["as_of_date"] != ref.get("trade_date")
        or any(data[field] != ref.get(field) for field in fields)
    ):
        raise archive_error("ARCHIVE_CITATION_MISMATCH")


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

RUN_IDENTITY_KEYS = {
    "algo_version",
    "source_strategy_config_hash",
    "opportunity_calc_version",
    "opportunity_config_hash",
    "portfolio_version",
    "portfolio_config_hash",
    "execution_version",
    "execution_config_hash",
    "accounting_version",
    "accounting_config_hash",
    "backtest_engine_version",
}
NESTED_RECORD_KEYS = {
    "market.snapshot": {
        "breadth": {"breadth20", "breadth60", "up_count", "down_count", "up_rate"},
        "liquidity": {"total_amount", "amount_ratio20", "liquidity_score"},
    },
    "sector.top": {"momentum": {"heat_momentum1", "heat_momentum3", "rank_change"}},
    "theme.top": {"momentum": {"heat_momentum1", "heat_momentum3", "rank_change"}},
    "opportunity.list": {
        "versions": {"algo_version", "calc_version", "config_hash", "source_strategy_config_hash"}
    },
    "backtest.summary": {
        "source_identity": RUN_IDENTITY_KEYS,
        "result_summary": {
            "total_trade_days",
            "completed_trade_days",
            "final_trade_date",
            "final_nav",
            "checkpoint_version",
        },
    },
    "performance.summary": {
        "report_ids": set(ARTIFACT_TYPES),
        "performance": {
            "start_date",
            "end_date",
            "trade_days",
            "final_nav",
            "cumulative_return",
            "annualized_return",
            "max_drawdown",
        },
        "risk": {
            "benchmark_code",
            "benchmark_cumulative_return",
            "excess_cumulative_return",
            "sharpe_ratio",
            "sortino_ratio",
            "calmar_ratio",
        },
        "trade": {
            "total_turnover",
            "total_execution_cost",
            "closed_episode_count",
            "open_episode_count",
            "win_rate",
            "profit_factor",
        },
        "period": {"month_count", "year_count"},
    },
    "walk_forward.summary": {
        "oos_sample": {
            "window_count",
            "total_oos_trade_days",
            "positive_oos_window_count",
            "positive_oos_window_rate",
        },
        "returns": {
            "stitched_oos_final_nav",
            "stitched_oos_cumulative_return",
            "stitched_oos_annualized_return",
            "stitched_oos_max_drawdown",
            "stitched_excess_cumulative_return",
        },
        "parameter_switching": {
            "unique_selected_parameter_hash_count",
            "dominant_parameter_hash",
            "dominant_parameter_hash_rate",
            "transition_count",
            "switch_count",
            "switch_rate",
        },
        "train_to_oos_degradation": {
            "mean_return_degradation",
            "median_return_degradation",
            "mean_drawdown_worsening",
            "median_drawdown_worsening",
        },
        "policy_identity": {"policy_identity_version", "validation_policy_hash"},
    },
    "walk_forward.window_lineage": {
        "train_metrics": {
            "annualized_return",
            "max_drawdown_abs",
            "sharpe_ratio",
            "annualized_turnover",
        },
        "oos_metrics": {
            "cumulative_return",
            "annualized_return",
            "max_drawdown_abs",
            "sharpe_ratio",
            "annualized_turnover",
            "total_cost_to_initial_capital",
            "win_rate",
            "profit_factor",
        },
        "degradation": {"return", "sharpe", "drawdown", "turnover"},
        "readiness": {"ready", "code", "details"},
    },
}
IDENTITY_KEYS = {
    "data.coverage": {"start_date", "end_date", "calendar"},
    "market.snapshot": {"calc_version", "config_hash"},
    "sector.top": {"calc_version", "config_hash"},
    "theme.top": {
        "algo_version",
        "config_hash",
        "calc_version",
        "theme_config_hash",
        "source_strategy_config_hash",
    },
    "opportunity.list": {"algo_version", "config_hash", "calc_version", "opportunity_config_hash"},
    "backtest.summary": RUN_IDENTITY_KEYS,
    "performance.summary": {
        "run_id",
        "run_identity",
        "run_start_date",
        "run_end_date",
        "initial_cash",
        "benchmark_code",
        *ARTIFACT_TYPES,
        *[
            f"{prefix}_{suffix}"
            for prefix in ("performance", "risk", "trade", "period")
            for suffix in ("version", "config_hash", "source_hash")
        ],
    },
    "walk_forward.summary": {
        "study_id",
        "validation_id",
        "walk_forward_version",
        "walk_forward_config_hash",
        "policy_identity_version",
        "validation_policy_hash",
        "source_hash",
        "definition_hash",
    },
    "walk_forward.window_lineage": {
        "study_id",
        "validation_id",
        "walk_forward_version",
        "policy_identity_version",
        "validation_policy_hash",
        "source_hash",
        "definition_hash",
        "total",
        "limit",
        "offset",
    },
}


def _check_object_keys(value, allowed):
    if value is not None and (not isinstance(value, dict) or set(value) - allowed):
        raise archive_error("ARCHIVE_UNSAFE_CONTENT")


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
    if any(ref.get("evidence_version") not in {"v1", "v2"} for ref in payload.get("evidence", [])):
        raise archive_error("UNSUPPORTED_EVIDENCE_VERSION")
    AgentToolResult.model_validate(payload)
    name = payload["tool_name"]
    if name not in RECORD_KEYS or payload["tool_version"] != "1.0":
        raise archive_error("UNSUPPORTED_TOOL_VERSION")
    check_safe(payload)
    _check_object_keys(payload["identity"], IDENTITY_KEYS[name])
    if "run_identity" in payload["identity"]:
        _check_object_keys(payload["identity"]["run_identity"], RUN_IDENTITY_KEYS)
    for record in payload["records"]:
        if set(record) - RECORD_KEYS[name]:
            raise archive_error("ARCHIVE_UNSAFE_CONTENT")
        for field, keys in NESTED_RECORD_KEYS.get(name, {}).items():
            if field in record:
                _check_object_keys(record[field], keys)
        if name == "data.coverage":
            for row in record.get("dataset_coverage", []):
                _check_object_keys(
                    row,
                    {
                        "dataset",
                        "quality_status",
                        "expected_rows",
                        "actual_rows",
                        "coverage_rate",
                        "quality_days",
                        "open_trade_days",
                        "missing_quality_days",
                    },
                )
        if name == "walk_forward.window_lineage" and "readiness" in record:
            _check_object_keys(record["readiness"].get("details"), {"train_bundle", "oos_bundle"})


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
