"""Fail-closed A4-2.1 artifact validation. No database/config imports."""

import re
import uuid
from dataclasses import asdict

from scripts.a42_ci_contract import (
    BASELINE_SHA,
    SCHEMA_VERSION,
    digest,
    fixture_recipe,
)


class ReceiptError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ReceiptError(code)


def identity(receipt, *, head, attempt, job_id):
    require(receipt.get("schema_version") == SCHEMA_VERSION, "SCHEMA_MISMATCH")
    require(re.fullmatch(r"[0-9a-f]{40}", head) is not None, "INVALID_HEAD")
    require(receipt.get("head_sha") == head, "HEAD_MISMATCH")
    require(receipt.get("baseline_sha") == BASELINE_SHA, "BASELINE_MISMATCH")
    require(str(receipt.get("attempt")) == str(attempt), "ATTEMPT_MISMATCH")
    require(receipt.get("job_id") == job_id, "JOB_MISMATCH")
    require(receipt.get("production_read_authorized") is False
            and receipt.get("authorize_a4_3") is False
            and receipt.get("read_performance_pass") == "NOT_CLAIMED", "UNAUTHORIZED_CLAIM")


def physical(receipt):
    proof = receipt.get("isolation", {})
    try:
        uuid.UUID(receipt["database_instance"])
    except (KeyError, TypeError, ValueError):
        raise ReceiptError("INVALID_PHYSICAL_MARKER") from None
    require(proof.get("before_ddl") is True and proof.get("verified") is True,
            "PHYSICAL_PROOF_MISSING")
    require(proof.get("expected_marker") == proof.get("observed_marker")
            == receipt["database_instance"], "PHYSICAL_MARKER_MISMATCH")
    require(proof.get("expected_system_identifier") == proof.get("observed_system_identifier")
            == receipt.get("physical_system_identifier")
            and str(receipt.get("physical_system_identifier", "")).isdigit(), "SYSTEM_ID_MISMATCH")
    require(str(receipt.get("postgres_version", "")).split(".")[0] == "17", "PG17_REQUIRED")


def cursor(cursor):
    require(bool(cursor.get("name")) and cursor.get("closed") is True
            and cursor.get("until_eof_seconds") is not None, "CURSOR_INCOMPLETE")
    fetches = cursor.get("fetches", [])
    require(bool(fetches) and fetches[-1].get("rows") == 0, "CURSOR_EOF_MISSING")
    require(all(isinstance(f.get("rows"), int) and 0 <= f["rows"] <= 5000 for f in fetches),
            "UNBOUNDED_OR_INVALID_FETCH")
    return sum(f["rows"] for f in fetches)


def base_scope(scope):
    return scope.removeprefix("event_")


def validate_group(receipt, group, *, head, attempt, job_id, model_hash):
    identity(receipt, head=head, attempt=attempt, job_id=job_id)
    require(receipt.get("status") == "COMPLETE", "GROUP_INCOMPLETE")
    require(receipt.get("expected_groups") == receipt.get("completed_groups") == 1,
            "GROUP_COMPLETENESS_COUNTS_MISSING")
    require(not any(receipt.get(k) for k in ("failure_type", "sqlstate", "failed_phase")),
            "GROUP_FAILURE")
    require(receipt.get("group") == asdict(group) and receipt.get("group_id") == group.id,
            "GROUP_KEY_MISMATCH")
    require(bool(receipt.get("started_at")) and bool(receipt.get("finished_at")),
            "TIMESTAMPS_MISSING")
    require(receipt.get("model_hash") == model_hash, "MODEL_HASH_MISMATCH")
    require(receipt.get("fixture") == fixture_recipe(group)
            and receipt.get("fixture_digest") == digest(fixture_recipe(group)), "FIXTURE_MISMATCH")
    physical(receipt)
    require(receipt.get("settings", {}).get("statement_timeout_ms") == 300000
            and receipt.get("settings", {}).get("read_flag") is False, "SAFETY_BUDGET_CHANGED")
    require(receipt.get("resources") == dict(cpu_limit=2, memory_bytes=3*1024**3),
            "RESOURCE_CLASS_MISMATCH")
    census = receipt.get("census", {})
    require(census.get("complete") is True and census.get("cursor_closed") is True
            and bool(census.get("cursor_name"))
            and census.get("actual_counts") == fixture_recipe(group)["counts"]
            and census.get("rows") == sum(fixture_recipe(group)["counts"].values()),
            "FIXTURE_CENSUS_INCOMPLETE")
    result = receipt.get("result", {})
    if group.kind == "plan":
        validate_plan(result)
        return
    require(result.get("variant") == group.variant and result.get("repeat") == group.repeat
            and result.get("cursor_fraction") == group.fraction
            and result.get("window_days") == group.window_days, "RESULT_KEY_MISMATCH")
    cursors = result.get("cursors", [])
    require(bool(cursors), "CURSOR_MISSING")
    require(sum(cursor(c) for c in cursors) == result.get("rows"), "FETCH_COUNT_MISMATCH")
    require(re.fullmatch(r"[0-9a-f]{64}", result.get("hash", "")) is not None
            and re.fullmatch(r"[0-9a-f]{64}", result.get("key_hash", "")) is not None,
            "GOLDEN_DIGEST_MISSING")
    columns = ["trade_date", "ts_code", "is_active", "is_suspended", "is_st", "st_status_unknown"]
    require(result.get("columns") == columns and set(result.get("dtypes", {})) == set(columns)
            and set(result.get("null_counts", {})) == set(columns)
            and result.get("duplicate_keys") == 0, "GOLDEN_TYPE_NULL_KEY_MISSING")
    require(all(type(n) is int and 0 <= n <= result["rows"]
                for n in result["null_counts"].values()), "INVALID_NULL_COUNTS")
    require(result.get("telemetry", {}).get("reader_errors") == [], "RR_READER_ERROR")
    if group.readers:
        require(result.get("reader_count") == 2
                and bool(result.get("telemetry", {}).get("reader_samples_seconds")), "RR2_MISSING")
    protected = group.variant not in ("Q0_LEGACY_RAW", "Q0_SERVICE_CONTROL")
    require(result.get("protection") == ("UNPROVEN_E3_PLUS_E0_FINAL" if group.variant == "E3"
            else "E0" if protected else "NOT_EQUIVALENT"), "PROTECTION_CHANGED")
    monthly = base_scope(group.scope).startswith("month_")
    final = protected and (not monthly or group.scope.endswith("_3"))
    require(result.get("final_verification_applied") is final, "FINAL_VERIFY_PROTOCOL")
    if protected and group.variant != "E3":
        phases = result.get("phase_distributions", {})
        require(phases.get("T4_candidate_validation_sql", {}).get("count", 0) >= 1
                and phases.get("T3_fingerprint_inclusive", {}).get("count", 0) >= 1,
                "E0_PREPARE_MISSING")
        require(phases.get("T8_verify_inclusive", {}).get("count", 0) == int(final), "T8_MISSING")
    if group.coverage == "partial" and group.tombstones == 1:
        require(result.get("rows") == {"10k":9471, "100k":120592, "million":3104443}[group.scale],
                "FROZEN_GOLDEN_CARDINALITY")
    if monthly:
        require(bool(result.get("logical_root"))
                and result.get("monthly_protocol") == "ROOT_TAIL_ONLY",
                "MONTHLY_ROOT_MISSING")
        require(result.get("input_start") == {
            "1": "2023-10-29", "2": "2023-11-29", "3": "2023-12-27"}[group.scope[-1]],
                "MONTHLY_HISTORY_SHORTENED")
        if group.scope[-1] != "1" and protected:
            require(result.get("previous_read_set_dates", 0) > 0, "MONTHLY_READ_SET_LOST")


def validate_plan(result):
    from scripts.a42_artifacts import contains_query_parameters

    require(not contains_query_parameters(result) and result.get("log_parameter_max_length") == 0,
            "UNSAFE_PARAMETER_LOGGING")
    queries = result.get("select_and_cursor_estimate", {})
    require(bool(queries.get("T5_declare")) and all(entries for entries in queries.values())
        and all(p.get("select_actual") and p.get("cursor_estimated")
        for entries in queries.values() for p in entries), "SELECT_OR_DECLARE_PLAN_MISSING")
    actual = [p for p in result.get("actual_cursor_untimed", [])
              if "DECLARE" in p.get("Query Text", "").upper()]
    cursors = result.get("probe_cursors", [])
    require(len(actual) == len(cursors) == result.get("expected_cursor_plans")
            == len(queries["T5_declare"])
            and bool(actual), "ACTUAL_CURSOR_PLAN_MISSING")
    require(all("Actual Rows" in p.get("Plan", {}) and "Actual Loops" in p["Plan"]
                and "Shared Read Blocks" in p["Plan"] for p in actual),
            "ACTUAL_PLAN_COUNTERS_MISSING")
    require(all(cursor(c) == p["Plan"]["Actual Rows"]
                for c,p in zip(cursors, actual, strict=True)), "ACTUAL_PLAN_FETCH_MISMATCH")


def validate_set(receipts, expected, *, head, attempt, job_id, model_hash):
    by_id = {}
    for receipt in receipts:
        key = receipt.get("group_id")
        require(key not in by_id, "DUPLICATE_GROUP")
        by_id[key] = receipt
    require(set(by_id) == {g.id for g in expected}, "MISSING_OR_EXTRA_GROUP")
    golden, roots = {}, {}
    for group in expected:
        receipt = by_id[group.id]
        validate_group(receipt, group, head=head, attempt=attempt, job_id=job_id,
                       model_hash=model_hash)
        if group.kind == "plan":
            continue
        result = receipt["result"]
        scope = base_scope(group.scope)
        scope = scope if scope.startswith("month_") else "full"
        key = (receipt["fixture_digest"], scope)
        signature = {k:result[k] for k in (
            "rows", "hash", "key_hash", "dtypes", "columns", "null_counts")}
        require(key not in golden or golden[key] == signature, "GOLDEN_MISMATCH")
        golden[key] = signature
        if scope.startswith("month_"):
            chain = (group.variant, group.fraction, group.repeat)
            require(chain not in roots or roots[chain] == result["logical_root"],
                    "MONTHLY_ROOT_CHANGED")
            roots[chain] = result["logical_root"]
    return dict(groups=len(by_id), golden="PASS")


def report(*, successful, errors=()):
    return dict(INFRASTRUCTURE_PASS=successful, CORRECTNESS_PASS=successful,
                READ_PERFORMANCE_PASS=False, read_performance_pass="NOT_CLAIMED",
                production_read_authorized=False, authorize_a4_3=False,
                state="A4_2_NO_SAFE_WINNER", errors=list(errors))


def require_jobs(needs, required):
    require(set(needs) == set(required), "REQUIRED_JOBS_MISSING")
    require(all(needs[job] == "success" for job in required), "UPSTREAM_NOT_SUCCESS")


def validate_capacity(result, level):
    from scripts.a42_ci_contract import CAPACITY_LEVELS

    require(level in CAPACITY_LEVELS and (result.get("stocks"), result.get("days"))
            == CAPACITY_LEVELS[level] and result.get("level") == level, "CAPACITY_SCALE_CHANGED")
    require(result.get("final_root_status") == "SUCCESS"
            and result.get("final_ledger_state") == "PUBLISHED", "CAPACITY_NOT_PUBLISHED")
    require(result.get("reader_errors") == [] and result.get("reader_samples", 0) > 0
            and result.get("max_running", 2) <= 1, "CAPACITY_READER_OR_FIFO_FAILURE")
    require(result.get("row_budget") == 10000000 and result.get("merge_timeout_ms") == 300000
            and 0 < result.get("rows", 0) < 10000000
            and 0 <= result.get("publish_seconds", 301) < 300, "CAPACITY_BUDGET_CHANGED")
    expected_rows = result["days"] * (6*result["stocks"]
        + min(50,result["stocks"]) + min(100,result["stocks"]) + 2)
    require(result["rows"] == expected_rows, "CAPACITY_ROW_SCALE_CHANGED")
    probes = result.get("rollback_probes", [])
    require(len(probes) == 2 and {p.get("mode") for p in probes}
            == {"row_budget", "sql_timeout_after_first_table"}, "CAPACITY_ROLLBACK_PROBES_MISSING")
    require(all(p.get("a_digest_unchanged") is True and p.get("queue_slot_held") is True
                and p.get("a_before") == p.get("a_after") and p.get("a_before")
                and p.get("root_status") == "RUNNING" and p.get("ledger_state") == "PREPARING"
                for p in probes), "CAPACITY_ROLLBACK_CHANGED_A")
    require(all(p.get("code") == ("PUBLICATION_ROW_BUDGET_EXCEEDED" if p["mode"]=="row_budget"
                else "PG_SQLSTATE_57014") and p.get("test_only_known_rollback") is True
                for p in probes), "CAPACITY_ROLLBACK_FAILURE_CODE_MISSING")


def merge_capacity(receipts, *, head, attempt, model_hash):
    from scripts.a42_ci_contract import CAPACITY_LEVELS

    results, systems = {}, set()
    for receipt in receipts:
        level = receipt.get("level")
        require(level in CAPACITY_LEVELS and level not in results, "DUPLICATE_OR_UNKNOWN_CAPACITY")
        identity(receipt, head=head, attempt=attempt, job_id="capacity-"+level)
        physical(receipt)
        require(receipt["physical_system_identifier"] not in systems, "CAPACITY_INSTANCE_REUSED")
        systems.add(receipt["physical_system_identifier"])
        require(receipt.get("model_hash") == model_hash and receipt.get("status") == "COMPLETE"
                and not receipt.get("failure_type") and not receipt.get("sqlstate")
                and not receipt.get("failed_phase")
                and not receipt.get("working_tree_dirty", False),
                "CAPACITY_INCOMPLETE")
        require(len(receipt.get("results", [])) == 1, "CAPACITY_LEVEL_NOT_UNIQUE")
        require(receipt.get("expected_groups") == receipt.get("completed_groups") == 1,
                "CAPACITY_COMPLETENESS_COUNTS_MISSING")
        validate_capacity(receipt["results"][0], level)
        results[level] = receipt["results"][0]
    require(set(results) == set(CAPACITY_LEVELS), "CAPACITY_LEVEL_MISSING")
    return dict(head_sha=head, working_tree_dirty=False,
                results=[results[level] for level in CAPACITY_LEVELS])
