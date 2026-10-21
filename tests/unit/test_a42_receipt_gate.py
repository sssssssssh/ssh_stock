import copy
from dataclasses import asdict

import pytest

from scripts.a42_ci_contract import BASELINE_SHA, SCHEMA_VERSION, Group, digest, fixture_recipe
from scripts.a42_receipt_contract import (
    ReceiptError,
    merge_capacity,
    report,
    require_jobs,
    validate_group,
    validate_set,
)

HEAD = "a" * 40
MODEL = "b" * 40
MARKER = "6f6d5295-3ede-456c-bca7-6a83f8e9390c"
COLS = ["trade_date", "ts_code", "is_active", "is_suspended", "is_st", "st_status_unknown"]


def envelope(job):
    return dict(schema_version=SCHEMA_VERSION, head_sha=HEAD, baseline_sha=BASELINE_SHA,
        attempt=1, job_id=job, production_read_authorized=False, authorize_a4_3=False,
        read_performance_pass="NOT_CLAIMED", status="COMPLETE", started_at="synthetic-start",
        finished_at="synthetic-end", model_hash=MODEL, database_instance=MARKER,
        physical_system_identifier="123456", postgres_version="17.11",
        isolation=dict(before_ddl=True, verified=True, expected_marker=MARKER,
            observed_marker=MARKER, expected_system_identifier="123456",
            observed_system_identifier="123456"))


def sample(group):
    receipt = envelope("job")
    recipe = fixture_recipe(group)
    rows = 3104443 if group.scale == "million" else 9471
    batches, tail = divmod(rows, 5000)
    fetches = [dict(rows=5000) for _ in range(batches)]
    if tail:
        fetches.append(dict(rows=tail))
    fetches.append(dict(rows=0))
    receipt.update(group=asdict(group), group_id=group.id, fixture=recipe,
        fixture_digest=digest(recipe), resources=dict(cpu_limit=2, memory_bytes=3*1024**3),
        settings=dict(statement_timeout_ms=300000, read_flag=False),
        census=dict(complete=True, cursor_closed=True, cursor_name="census",
                    actual_counts=recipe["counts"], rows=sum(recipe["counts"].values())),
        result=dict(variant=group.variant, repeat=group.repeat, cursor_fraction=group.fraction,
            rows=rows, hash="c"*64, key_hash="d"*64, dtypes={c:"object" for c in COLS},
            columns=COLS, null_counts={c:0 for c in COLS}, duplicate_keys=0,
            telemetry=dict(reader_errors=[]), protection="E0", final_verification_applied=True,
            phase_distributions={p:dict(count=1) for p in (
                "T4_candidate_validation_sql", "T3_fingerprint_inclusive", "T8_verify_inclusive")},
            cursors=[dict(name="synthetic-cursor", closed=True, until_eof_seconds=1,
                          fetches=fetches)]))
    return receipt


GROUP = Group("million", "read", "Q1_CURRENT", "0.1", "full", repeat=0)


def check(receipt, group=GROUP):
    return validate_group(receipt, group, head=HEAD, attempt=1, job_id="job", model_hash=MODEL)


def test_valid_complete_read_is_correct_but_never_production_authorized():
    check(sample(GROUP))
    assert report(successful=True) == dict(INFRASTRUCTURE_PASS=True, CORRECTNESS_PASS=True,
        READ_PERFORMANCE_PASS=False, read_performance_pass="NOT_CLAIMED",
        production_read_authorized=False, authorize_a4_3=False,
        state="A4_2_NO_SAFE_WINNER", errors=[])


@pytest.mark.parametrize("field,value", [
    ("head_sha", "0"*40), ("baseline_sha", "1"*40), ("attempt", 2),
    ("fixture_digest", "corrupt"), ("model_hash", "corrupt"), ("status", "INCOMPLETE"),
    ("status", "NOT_STARTED"), ("failure_type", "JobCancelled"), ("sqlstate", "57014"),
    ("production_read_authorized", True), ("authorize_a4_3", True),
])
def test_wrong_identity_partial_or_failed_receipt_is_rejected(field, value):
    receipt = sample(GROUP)
    receipt[field] = value
    with pytest.raises(ReceiptError):
        check(receipt)


@pytest.mark.parametrize("damage", ["closed", "eof", "name", "rows", "nulls", "duplicates",
                                   "final", "prepare", "physical", "system", "census", "timeout"])
def test_missing_cursor_golden_or_isolation_evidence_is_rejected(damage):
    receipt = sample(GROUP)
    result = receipt["result"]
    if damage == "closed":
        result["cursors"][0]["closed"] = False
    elif damage == "eof":
        result["cursors"][0].pop("until_eof_seconds")
    elif damage == "name":
        result["cursors"][0]["name"] = ""
    elif damage == "rows":
        result["rows"] -= 1
    elif damage == "nulls":
        result["null_counts"].pop("is_st")
    elif damage == "duplicates":
        result["duplicate_keys"] = 1
    elif damage == "final":
        result["final_verification_applied"] = False
    elif damage == "prepare":
        result["phase_distributions"] = {}
    elif damage == "physical":
        receipt["isolation"]["observed_marker"] = "wrong"
    elif damage == "system":
        receipt["isolation"]["observed_system_identifier"] = "9999"
    elif damage == "census":
        receipt["census"]["actual_counts"]["a"] -= 1
    else:
        receipt["settings"]["statement_timeout_ms"] += 1
    with pytest.raises(ReceiptError):
        check(receipt)


def test_missing_duplicate_or_plan_group_cannot_pass_complete_matrix():
    expected = {GROUP}
    for receipts in ([], [sample(GROUP), sample(GROUP)]):
        with pytest.raises(ReceiptError):
            validate_set(receipts, expected, head=HEAD, attempt=1, job_id="job", model_hash=MODEL)
    plan = Group("million", "plan", "Q1_CURRENT", "0.1", "full")
    with pytest.raises(ReceiptError, match="MISSING_OR_EXTRA_GROUP"):
        validate_set([sample(GROUP)], {GROUP, plan}, head=HEAD, attempt=1,
                     job_id="job", model_hash=MODEL)


@pytest.mark.parametrize("status", ["cancelled", "skipped", "neutral", "failure", "timed_out"])
def test_upstream_success_is_mandatory_even_when_other_artifact_is_complete(status):
    with pytest.raises(ReceiptError, match="UPSTREAM_NOT_SUCCESS"):
        require_jobs({"core":"success", "capacity":status}, {"core", "capacity"})
    assert not report(successful=False, errors=[status])["INFRASTRUCTURE_PASS"]


def capacity(level, stocks, days):
    receipt = envelope("capacity-"+level)
    receipt.update(level=level, results=[dict(level=level, stocks=stocks, days=days,
        final_root_status="SUCCESS", final_ledger_state="PUBLISHED", reader_errors=[],
        reader_samples=3, max_running=1, row_budget=10000000, merge_timeout_ms=300000,
        rows=200, publish_seconds=1, rollback_probes=[dict(mode=mode,
            a_digest_unchanged=True, queue_slot_held=True, a_before={"table":"digest"},
            a_after={"table":"digest"}, root_status="RUNNING", ledger_state="PREPARING")
            for mode in ("row_budget", "sql_timeout_after_first_table")])])
    return receipt


def test_three_capacity_levels_merge_in_stable_order_not_input_order():
    receipts = [capacity("L3-scaled-10pct", 500, 120), capacity("L1", 10, 2),
                capacity("L2", 5000, 20)]
    result = merge_capacity(receipts, head=HEAD, attempt=1, model_hash=MODEL)
    assert [r["level"] for r in result["results"]] == ["L1", "L2", "L3-scaled-10pct"]
    for broken in (receipts[:2], receipts+[copy.deepcopy(receipts[0])]):
        with pytest.raises(ReceiptError):
            merge_capacity(broken, head=HEAD, attempt=1, model_hash=MODEL)


def test_capacity_cannot_rename_smoke_as_l2_or_drop_rollback_probe():
    receipts = [capacity("L1", 10, 2), capacity("L2", 5000, 20),
                capacity("L3-scaled-10pct", 500, 120)]
    for damage in ("stocks", "probe"):
        broken = copy.deepcopy(receipts)
        if damage == "stocks":
            broken[1]["results"][0]["stocks"] = 10
        else:
            broken[1]["results"][0]["rollback_probes"].pop()
        with pytest.raises(ReceiptError):
            merge_capacity(broken, head=HEAD, attempt=1, model_hash=MODEL)
