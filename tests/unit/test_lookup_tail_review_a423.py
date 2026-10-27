"""Offline replay/denial regressions; no Settings, database, network or GC tuning."""

import copy
import gc
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import publication_lookup_diagnostic_a422 as lab
from scripts import publication_lookup_tail_review_a423 as review
from scripts.a42_artifacts import header
from scripts.a42_receipt_contract import ReceiptError
from scripts.ci_release_gate_v14_a4_2_1 import capacity_blocker, gate


@pytest.fixture
def source():
    """Explicitly synthetic gate-control fixture, not recorded performance."""
    source = dict(head_sha=review.SOURCE_SHA, run_id=review.SOURCE_RUN, attempt="1",
        job_id="a422-lookup-diagnosis", working_tree_dirty=False, status="COMPLETE",
        artifact_kind="DIAGNOSTIC_ONLY", formal_capacity_complete=False,
        postgres_version="17.11", production_source_sha256=review.C0_SOURCE,
        proposed_source_sha256=review.C1_SOURCE, production_matches_candidate=False,
        public_stocks=5000, public_days=20, public_total_rows=603040,
        public_counts={"synthetic_only":603040}, candidate_rows={"synthetic_only":503020},
        input_key_sha256=review.INPUT_HASHES,
        candidate_key_hits={t:1000 if t in lab.TABLES[:2] else 2000 for t in lab.TABLES},
        database_instance="00000000-0000-0000-0000-000000000042", physical_system_identifier="42",
        isolation=dict(verified=True, before_ddl=True,
            expected_marker="00000000-0000-0000-0000-000000000042",
            observed_marker="00000000-0000-0000-0000-000000000042", expected_system_identifier="42",
            observed_system_identifier="42"))
    source["samples"] = []
    for regime, table, variant, repeat in review.expected_order():
        seconds = (10 if variant == "C0" else 6) if table in lab.TABLES[:2] else (
            0.08 if variant == "C0" else 0.06)
        if regime == "analyzed" and table == lab.TABLES[2] and variant == "C1" and repeat < 7:
            seconds = 0.2
        source["samples"].append(dict(statistics=regime, table=table, variant=variant,
            repeat=repeat, golden="PASS", keys=2000, batch_size=lab.VARIANTS[variant],
            wall_seconds=seconds, client_cpu_seconds=0.01,
            batch_seconds=[seconds/(2000//lab.VARIANTS[variant])]*(2000//lab.VARIANTS[variant]),
            metrics={key:0 for key in review.METRICS}))
    source["summary"] = lab.summarize(source["samples"])
    source["whole_workloads"] = lab.whole_workloads(source["samples"])
    source["decision"] = lab.performance_decision(source["summary"], source["whole_workloads"])
    source["plans"] = [dict(statistics=r, table=t, variant=v, case=c, plan={"synthetic":True})
        for r in review.REGIMES for t in lab.TABLES for v in lab.VARIANTS
        for c in ("b_present", "late_keys")]
    source["actual_execution_probes"] = {r:dict(cases=[dict(table=t, variant=v, case=c,
        plan={"synthetic":True}, golden="PASS") for t in lab.TABLES for v in ("C0", "C1", "C2")
        for c in ("b_present", "late_keys")]) for r in review.REGIMES}
    return source


def test_all_1100_samples_and_the_original_failed_decision_recompute(source):
    summary, workloads = review.validate_source(source)
    assert len(source["samples"]) == 1100
    assert not lab.performance_decision(summary, workloads)["performance_eligible"]
    assert lab.performance_decision(summary, workloads)["reasons"] == ["P95_REGRESSION"]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reorder", "old_sha",
    "attempt", "golden", "nan", "key_hash", "fewer_repeats", "plan", "probe"])
def test_incomplete_mixed_or_reordered_historical_evidence_is_rejected(source, mutation):
    if mutation == "missing":
        source["samples"].pop()
    elif mutation == "duplicate":
        source["samples"][-1] = source["samples"][-2]
    elif mutation == "reorder":
        source["samples"][0:2] = reversed(source["samples"][0:2])
    elif mutation == "old_sha":
        source["head_sha"] = "0"*40
    elif mutation == "attempt":
        source["attempt"] = "2"
    elif mutation == "golden":
        source["samples"][0]["golden"] = "FAIL"
    elif mutation == "nan":
        source["samples"][0]["wall_seconds"] = float("nan")
    elif mutation == "key_hash":
        source["input_key_sha256"] = {}
    elif mutation == "fewer_repeats":
        source["samples"] = [s for s in source["samples"] if s["statistics"] != "analyzed"]
    elif mutation == "plan":
        source["plans"].pop()
    else:
        source["actual_execution_probes"]["analyzed"]["cases"].pop()
    with pytest.raises((ReceiptError, KeyError)):
        review.validate_source(source)


def test_archive_digest_is_mandatory_not_a_caller_supplied_override(tmp_path):
    archive = tmp_path/"not-source.zip"
    archive.write_bytes(b"not the real historical artifact")
    with pytest.raises(ReceiptError, match="DIGEST_MISMATCH"):
        review.load_source(archive)


def test_committed_historical_400_point_time_series_keeps_all_outliers_and_exact_p95():
    data = json.loads(Path("docs/acceptance/evidence/v14_a423_tail_baseline.json").read_text())
    assert data["evidence_kind"] == "HISTORICAL" and data["sample_count"] == 1100
    assert data["source_zip_sha256"] == review.SOURCE_DIGEST
    assert len(data["control_timelines"]) == 400
    for group in data["groups"]:
        points = [s for s in data["control_timelines"] if (s["statistics"], s["variant"])
                  == (group["statistics"], group["variant"])]
        assert [s["repeat"] for s in points] == list(range(100))
        assert review.quantiles([s["wall_seconds"] for s in points]) == {
            key:group[key] for key in ("p50", "p90", "p95", "p99")}
    groups = {(g["statistics"], g["variant"]):g for g in data["groups"]}
    assert groups["analyzed", "C0"]["p95"] == 0.08875597779998542
    assert groups["analyzed", "C1"]["p95"] == 0.19159500049996722
    assert groups["analyzed", "C1"]["p95"] / groups["analyzed", "C0"]["p95"] > 1.1
    assert {s["repeat"] for s in data["c1_samples_over_c0_p95_limit"]
            if s["statistics"] == "analyzed"} == {5, 13, 19, 25, 41, 66, 81}
    assert data["tail_causality"] == "CORRELATED_NOT_CAUSAL"
    assert Path("docs/acceptance/v14_a4_2_3_baseline.md").read_text() == (
        review.baseline_markdown(data))


@pytest.mark.parametrize("exception", [False, True])
def test_gc_callback_restored_on_success_or_error_without_collecting_or_tuning(exception):
    callbacks, enabled, thresholds = list(gc.callbacks), gc.isenabled(), gc.get_threshold()
    metrics = dict(gc_seconds=0.0, gc_count=0)
    try:
        with lab.observe_gc(metrics):
            callback = gc.callbacks[-1]
            callback("start", {"generation":0})
            callback("stop", {"generation":0})
            if exception:
                raise RuntimeError("synthetic")
    except RuntimeError:
        assert exception
    assert gc.callbacks == callbacks
    assert gc.isenabled() == enabled and gc.get_threshold() == thresholds
    assert metrics["gc_count"] >= 1 and metrics["gc_seconds"] >= 0


@pytest.mark.parametrize("exception", [False, True])
@pytest.mark.parametrize("variant", ["C0", "C1"])
def test_wrapper_single_iteration_and_restores_json_session_on_exception(monkeypatch, exception,
                                                                       variant):
    original_json, calls = lab.json, []
    class Rows:
        def mappings(self):
            calls.append("mappings")
            yield {"synthetic":1}
            if exception:
                raise RuntimeError("synthetic")
    class DB:
        def execute(self, *args):
            calls.append("execute")
            return Rows()
    statement = SimpleNamespace(text="synthetic SQL not executed")
    def lookup(ws, model, payload):
        module.json.dumps(payload)
        return list(ws.db.execute(statement, {}).mappings())
    module = SimpleNamespace(json=original_json, KEYS={"synthetic":()},
                             PublicationWorkspace=SimpleNamespace(_lookup_batch=lookup))
    monkeypatch.setattr(lab, "baseline_module", lambda:module)
    monkeypatch.setattr(lab, "rewrite", lambda sql, keys, v:sql)
    db = DB()
    ws, model = SimpleNamespace(db=db), SimpleNamespace(__tablename__="synthetic")
    metrics = {key:0.0 for key in review.METRICS}
    if exception:
        with pytest.raises(RuntimeError, match="synthetic"):
            lab.lookup(ws, model, [], variant, metrics=metrics)
    else:
        assert lab.lookup(ws, model, [], variant, metrics=metrics) == [{"synthetic":1}]
    assert calls == ["execute", "mappings"]
    assert ws.db is db and module.json is original_json


@pytest.mark.parametrize("change", ["slow_median", "whole_median", "control", "p95"])
def test_original_thresholds_cannot_be_waived(source, change):
    summary, workloads = copy.deepcopy(source["summary"]), copy.deepcopy(source["whole_workloads"])
    if change == "whole_median":
        workloads[1]["median"] = workloads[0]["median"]*0.801
        expected = "WORKLOAD_MEDIAN_TARGET_NOT_MET"
    else:
        row = next(r for r in summary if r["variant"] == "C1"
                   and r["table"] == lab.TABLES[2 if change == "control" else 0])
        before = next(r for r in summary if r["variant"] == "C0"
                      and r["table"] == row["table"] and r["statistics"] == row["statistics"])
        row["p95" if change == "p95" else "median"] = before[
            "p95" if change == "p95" else "median"]*(1.101 if change != "slow_median" else .701)
        expected = {"slow_median":"SLOW_TABLE_MEDIAN_TARGET_NOT_MET",
                    "control":"CONTROL_REGRESSION", "p95":"P95_REGRESSION"}[change]
    decision = lab.performance_decision(summary, workloads)
    assert not decision["performance_eligible"] and expected in decision["reasons"]


@pytest.mark.parametrize("damage", ["rows", "readers", "fifo", "digest", "probe",
    "rollback_code", "row_budget", "merge_timeout", "root", "ledger"])
def test_original_formal_capacity_contract_still_rejects_partial_or_unsafe_l2(damage):
    from scripts.a42_receipt_contract import validate_capacity
    from tests.unit.test_a42_receipt_gate import capacity

    result = capacity("L2", 5000, 20)["results"][0]
    assert result["rows"] == 603040
    validate_capacity(result, "L2")  # Pure gate-control unit, not measured capacity.
    if damage == "rows":
        result["rows"] -= 1
    elif damage == "readers":
        result["reader_errors"] = ["synthetic"]
    elif damage == "fifo":
        result["max_running"] = 2
    elif damage == "digest":
        result["rollback_probes"][0]["a_after"] = {"table":"changed"}
    elif damage == "probe":
        result["rollback_probes"].pop()
    elif damage == "rollback_code":
        result["rollback_probes"][1]["code"] = "OTHER"
    elif damage == "row_budget":
        result["row_budget"] += 1
    elif damage == "merge_timeout":
        result["merge_timeout_ms"] += 1
    elif damage == "root":
        result["final_root_status"] = "RUNNING"
    else:
        result["final_ledger_state"] = "PREPARING"
    with pytest.raises(ReceiptError):
        validate_capacity(result, "L2")


def denial(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "synthetic-current-run")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    value = review.blocked_readiness(dict(evidence_kind="HISTORICAL",
        source_zip_sha256=review.SOURCE_DIGEST, decision=dict(performance_eligible=False)))
    value["working_tree_dirty"] = False  # Synthetic unit identity only.
    path = tmp_path/"lookup/readiness.json"
    path.parent.mkdir()
    path.write_text(json.dumps(value))
    return path, value


@pytest.mark.parametrize("field,value", [("head_sha", "old"), ("attempt", "2"),
    ("run_id", "old"), ("working_tree_dirty", True), ("capacity_ready", True),
    ("performance_eligible", True), ("source_evidence_kind", "FORMAL_ACCEPTANCE"),
    ("reasons", []), ("source_zip_sha256", "other"), ("production_source_sha256", "other"),
    ("production_matches_candidate", True), ("proposed_source_sha256", "other")])
def test_denial_cannot_be_promoted_to_admission_or_mixed_identity(tmp_path, monkeypatch,
                                                               field, value):
    path, receipt = denial(tmp_path, monkeypatch)
    receipt[field] = value
    path.write_text(json.dumps(receipt))
    with pytest.raises(ReceiptError):
        capacity_blocker(tmp_path, header("unit")["head_sha"], "1")


@pytest.mark.parametrize("capacity", ["skipped", "success", "cancelled", "failure"])
def test_release_gate_records_specific_refusal_even_if_upstream_is_green(tmp_path, monkeypatch,
                                                                       capacity):
    _, receipt = denial(tmp_path, monkeypatch)
    monkeypatch.setenv("GITHUB_SHA", receipt["head_sha"])
    monkeypatch.setenv("A421_NEEDS", json.dumps({k:{"result":capacity if k == "capacity"
        else "success"} for k in ("test", "capacity", "lookup-diagnosis", "dependency-audit")}))
    args = SimpleNamespace(mode="publication", input=tmp_path, output=tmp_path/"gate.json")
    with pytest.raises(SystemExit):
        gate(args)
    result = json.loads(args.output.read_text())
    assert result["status"] == "INCOMPLETE" and result["errors"] == ["CAPACITY_NOT_AUTHORIZED"]
    assert not result["capacity_admission"]["capacity_ready"]
    assert "P95_REGRESSION" in result["capacity_admission"]["reasons"]
    assert not result["CORRECTNESS_PASS"] and not result["production_read_authorized"]


def test_workflow_does_not_repeat_the_disallowed_100_trial_or_weaken_capacity():
    import yaml

    jobs = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())["jobs"]
    steps = jobs["lookup-diagnosis"]["steps"]
    runs = "\n".join(s.get("run", "") for s in steps)
    assert "publication_lookup_tail_review_a423.py" in runs
    assert "publication_lookup_diagnostic_a422.py" not in runs
    assert "12429939366/zip" in runs
    assert jobs["lookup-diagnosis"]["outputs"]["capacity_ready"] == (
        "${{ steps.measure.outputs.capacity_ready }}"
    )
    assert "needs.lookup-diagnosis.outputs.capacity_ready == 'true'" in jobs["capacity"]["if"]
    assert "github.event_name == 'workflow_dispatch'" in jobs["capacity"]["if"]
    assert "inputs.confirm_expensive_run == true" in jobs["capacity"]["if"]
    assert "gc.collect(" not in Path(review.__file__).read_text()
    from scripts.business_source_contract import historical_bytes, source_versions

    versions = source_versions(["backend/app/services/data_publication.py"])
    assert not versions["performance_eligible"] and not versions["g1_authorized"]
    current = historical_bytes("backend/app/services/data_publication.py")
    assert hashlib.sha256(current).hexdigest() == review.C0_SOURCE

    from scripts.business_source_contract import verify as verify_current_business

    assert len(verify_current_business()) == 64
