from app.domain.agent.frozen_contracts import (
    M14_CONTRACT_VERSION,
    M15_AGGREGATE_CONTRACT_VERSION,
    M15_WINDOW_CONTRACT_VERSION,
)


def safe_contract_projection(row):
    if row.schema_version not in {
        M14_CONTRACT_VERSION,
        M15_AGGREGATE_CONTRACT_VERSION,
        M15_WINDOW_CONTRACT_VERSION,
    }:
        return None
    body = row.contract_json
    if body["status"] == "GAP":
        return {
            "status": "GAP",
            "reason_codes": body.get("reason_codes", []),
            "selected": body.get("selected"),
            "validation": body.get("validation"),
            "verification_scope": row.verification_scope,
        }
    if row.contract_kind == "M14_EXACT_BUNDLE":
        comparison = body["comparison_contract"]
        return {
            "selected": body["selected"],
            "trade_dates_hash": body["trade_dates_hash"],
            "sample": {
                key: comparison[key]
                for key in (
                    "start_date",
                    "end_date",
                    "trade_days",
                    "frequency",
                    "currency",
                    "initial_cash",
                    "benchmark_code",
                    "benchmark_source_hash",
                )
            },
            "versions_and_hashes": {
                key: value
                for key, value in comparison.items()
                if key.endswith("_version") or key.endswith("_hash")
            },
            "execution_snapshot": body["execution_snapshot"],
            "accounting_snapshot": body["accounting_snapshot"],
            "frozen_facts": body["record"],
        }
    return {
        "study": body["study"],
        "validation": body["validation"],
        "window": {
            key: value
            for key, value in body["window"].items()
            if key not in {"train_trade_dates", "test_trade_dates"}
        },
        "trial": body["trial"],
        "evaluation": body["evaluation"],
        "m14_contract_refs": body["m14_contract_refs"],
        "frozen_metrics": {
            key: body["record"][key] for key in ("train_metrics", "oos_metrics", "degradation")
        },
    }
