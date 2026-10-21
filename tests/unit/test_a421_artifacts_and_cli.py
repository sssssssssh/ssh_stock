"""CLI compatibility, atomic files, cancellation and missing-artifact gates."""

import ast
import json
import os
import subprocess
from pathlib import Path
from time import monotonic

import pytest

from scripts.a42_artifacts import BudgetExhausted, JobCancelled, Writer, atomic
from scripts.a42_ci_contract import Group, shards
from scripts.a42_gate_io import load_groups
from scripts.a42_receipt_contract import ReceiptError
from scripts.a42_scope import ordered, parse
from scripts.ci_release_gate_v14_a4_2_1 import gate
from scripts.data_publication_capacity_v12 import parse_args, selected_levels


@pytest.mark.parametrize("shard", shards())
def test_new_scope_is_explicit_and_rejects_silent_count_or_scope_changes(shard):
    args = parse(["--job-id", shard.job_id, "--scope", shard.scope,
                  "--container", "own-test", "--output", "unused"])
    assert args.shard == shard
    with pytest.raises(SystemExit):
        parse(["--job-id", shard.job_id, "--container", "own-test", "--output", "unused",
               "--public-rows", "1"])


@pytest.mark.parametrize("names,expected", [([], ["L1", "L2", "L3-scaled-10pct"]),
    (["--levels", "all"], ["L1", "L2", "L3-scaled-10pct"]),
    (["--levels", "smoke"], ["L1"]), (["--level", "L2"], ["L2"]),
    (["--level", "L3-scaled-10pct"], ["L3-scaled-10pct"])])
def test_capacity_old_and_single_cli(names, expected):
    assert [r[2] for r in selected_levels(parse_args(["--confirm-synthetic", *names]))] == expected


def test_cli_level_options_mutually_exclusive():
    with pytest.raises(SystemExit):
        parse_args(["--confirm-synthetic", "--level", "L1", "--levels", "all"])


def test_run_level_actual_workload_ast_is_frozen():
    baseline = subprocess.check_output(["git", "show",
        "02c69c612786:scripts/data_publication_capacity_v12.py"], text=True)
    current = Path("scripts/data_publication_capacity_v12.py").read_text()
    def body(text):
        return ast.dump(next(n for n in ast.parse(text).body
                            if isinstance(n, ast.FunctionDef) and n.name=="run_level"))
    assert body(baseline) == body(current)


def test_original_core_steps_and_every_release_assertion_are_preserved():
    import yaml

    baseline = subprocess.check_output([
        "git", "show", "02c69c612786:.github/workflows/ci.yml"], text=True)
    old = yaml.safe_load(baseline)["jobs"]["test"]["steps"]
    new_ci = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())
    new = new_ci["jobs"]["test"]["steps"]
    removed = {"Cold start L1 L2 L3 isolated publication capacity",
               "Data publication exact SHA release receipt"}
    for step in old:
        if step.get("name") not in removed:
            assert step in new
    source = next(s["run"] for s in old
                  if s.get("name")=="Data publication exact SHA release receipt")
    original = source.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    checks = Path("scripts/publication_release_checks_v14_a4_2_1.py").read_text()
    def assertions(text):
        return sorted(ast.dump(n) for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Assert))
    assert assertions(original) == assertions(checks)
    release = new_ci["jobs"]["publication-release-gate"]
    assert release["needs"] == ["test", "capacity"] and "always()" in release["if"]
    assert new_ci["jobs"]["capacity"]["strategy"]["matrix"]["level"] == [
        "L1", "L2", "L3-scaled-10pct"]


def test_provisioning_keeps_the_frozen_resource_sampler_marker_contract():
    source = subprocess.check_output([
        "git", "show", "02c69c612786:scripts/ab_read_profile_v14_a4.py"], text=True)
    purpose = "ssh-stock-a4-physical-test"
    assert purpose in source
    action = Path(".github/actions/a421-pg/action.yml").read_text()
    assert "--label purpose="+purpose in action
    assert "--label stage=A4-2.1" in action


def test_successful_gate_still_never_claims_production_performance(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from scripts import ci_release_gate_v14_a4_2_1 as cli
    from scripts.a42_artifacts import header

    monkeypatch.setenv("GITHUB_SHA", header("core")["head_sha"])
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("GITHUB_REPOSITORY", "synthetic/unit")
    monkeypatch.setenv("GITHUB_RUN_ID", "1")
    monkeypatch.setenv("A421_NEEDS", json.dumps({k:{"result":"success"}
                                              for k in ("test", "capacity")}))
    core_dir = tmp_path/"input/core"
    core = {**header("core"), "status":"COMPLETE", "working_tree_dirty":False}
    atomic(core_dir/"status.json", core)
    # Pure gate-control unit; actual merger, original assertions and real L1
    # are independently exercised, never replace those real CI checks.
    monkeypatch.setattr(cli, "merge_capacity", lambda *a,**k:{"synthetic_unit_only":True})
    from scripts import publication_release_checks_v14_a4_2_1 as checks

    monkeypatch.setattr(checks, "validate", lambda *a,**k:{"synthetic_unit_only":True})
    args = SimpleNamespace(mode="publication", input=tmp_path/"input", output=tmp_path/"gate.json")
    gate(args)
    result = json.loads(args.output.read_text())
    assert result["INFRASTRUCTURE_PASS"] and result["CORRECTNESS_PASS"]
    assert not result["READ_PERFORMANCE_PASS"] and not result["production_read_authorized"]


def test_atomic_files_do_not_leave_partial_json(tmp_path):
    path = tmp_path/"state.json"
    atomic(path, {"status":"NOT_STARTED"})
    atomic(path, {"status":"INCOMPLETE"})
    assert json.loads(path.read_text()) == {"status":"INCOMPLETE"}
    assert not list(tmp_path.glob("*.tmp"))


def test_parameter_redaction_retains_native_query_and_actual_plan_counters(tmp_path):
    value = {"nested":[{"Query Text":"DECLARE synthetic CURSOR FOR SELECT $1",
        "Query Parameters":"sensitive-bind-values-must-not-be-written",
        "Plan":{"Actual Rows":10,"Actual Loops":1,"Shared Read Blocks":2}}]}
    path = tmp_path/"plan.json"
    atomic(path, value)
    data = json.loads(path.read_text())
    assert "sensitive-bind-values" not in path.read_text()
    assert data["nested"][0]["Query Text"] == value["nested"][0]["Query Text"]
    assert data["nested"][0]["Plan"] == value["nested"][0]["Plan"]


def test_unreferenced_old_gzip_cannot_be_mixed_into_complete_shard(tmp_path):
    key = "a"*64
    name = key+".json.gz"
    checksum = atomic(tmp_path/name, {"group_id":key}, compressed=True)
    atomic(tmp_path/"old-head.json.gz", {"head_sha":"old"}, compressed=True)
    manifest = {"entries":{key:dict(status="COMPLETE", file=name, sha256=checksum)}}
    with pytest.raises(ReceiptError, match="UNREFERENCED_GROUP_ARTIFACT"):
        load_groups(tmp_path/"manifest.json", manifest)


def test_whole_workload_deadline_unwinds_and_restores_handler():
    import signal
    import time

    from scripts.a42_artifacts import deadline

    if not hasattr(signal, "setitimer"):
        with pytest.raises(ReceiptError, match="UNSUPPORTED"):
            with deadline(1):
                pytest.fail("unsupported runner must not enter timed workload")
        return
    previous = signal.getsignal(signal.SIGALRM)
    with pytest.raises(BudgetExhausted):
        with deadline(0.02):
            time.sleep(0.2)
    assert signal.getsignal(signal.SIGALRM) == previous
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_budget_stop_does_not_start_next_group_or_report_complete(tmp_path):
    group = Group("10k", "read", "Q1_CURRENT", "0.1", "full", repeat=0)
    writer = Writer(tmp_path/"manifest.json", "unit-budget", {group}, minutes=1)
    writer.deadline = monotonic()+1
    with pytest.raises(BudgetExhausted):
        writer.begin(group)
    writer.fail(BudgetExhausted())
    assert writer.manifest["status"] == "INCOMPLETE"
    assert writer.manifest["entries"][group.id]["status"] == "NOT_STARTED"
    with pytest.raises(ReceiptError):
        writer.finish()


def test_capacity_deadline_survives_rollback_error_without_claiming_success(tmp_path, monkeypatch):
    import signal
    import time

    from sqlalchemy.exc import OperationalError

    from scripts import a42_artifacts as artifacts
    from scripts import data_publication_capacity_v12 as capacity

    if not hasattr(signal, "setitimer"):
        return  # The existing unsupported-deadline test verifies fail-closed behavior.
    original_deadline = artifacts.deadline
    monkeypatch.setattr(artifacts, "deadline", lambda seconds: original_deadline(0.02))
    monkeypatch.setattr(artifacts, "install_signals", lambda: None)
    monkeypatch.setenv("A421_CAPACITY_BUDGET_MINUTES", "270")

    def interrupted_workload(args, result):
        try:
            time.sleep(0.2)
        finally:
            # Reproduce the driver exception that masked SIGALRM in real L2.
            raise OperationalError("private SQL", {"token": "private-bind"},
                                   RuntimeError("private connection details"))

    monkeypatch.setattr(capacity, "run_cli", interrupted_workload)
    path = tmp_path/"capacity.json"
    with pytest.raises(SystemExit) as error:
        capacity.main(["--confirm-synthetic", "--level", "L2", "--output", str(path)])
    assert error.value.code == 1
    receipt = json.loads(path.read_text())
    assert receipt["status"] == "INCOMPLETE" and receipt["completed_groups"] == 0
    assert receipt["results"] == []
    assert receipt["failure_code"] == "RESOURCE_DEFERRED"
    assert receipt["failure_type"] == "OperationalError"  # Keep the cleanup failure too.
    assert receipt["budget_exhausted"] is True
    assert not receipt["production_read_authorized"]
    assert "private" not in path.read_text()


def test_unrelated_database_error_is_not_mislabeled_resource_deferred():
    from sqlalchemy.exc import OperationalError

    from scripts.a42_artifacts import failure

    receipt = failure(OperationalError("private SQL", {}, RuntimeError("private connection")))
    assert receipt["failure_type"] == "OperationalError"
    assert receipt["failure_code"] is None
    assert not receipt.get("budget_exhausted")


def test_cancel_keeps_completed_files_but_cannot_pass_manifest(tmp_path):
    group = Group("10k", "read", "Q1_CURRENT", "0.1", "full", repeat=0)
    writer = Writer(tmp_path/"manifest.json", "unit-cancel", {group}, minutes=120)
    writer.begin(group)
    writer.fail(JobCancelled())
    assert writer.manifest["status"] == "INCOMPLETE"
    with pytest.raises(ReceiptError, match="INCOMPLETE"):
        load_groups(writer.path, writer.manifest)


def test_wrong_digest_rejects_damaged_complete_group(tmp_path):
    group = Group("10k", "read", "Q1_CURRENT", "0.1", "full", repeat=0)
    entry = dict(status="COMPLETE", file=group.id+".json.gz", sha256="corrupt")
    atomic(tmp_path/entry["file"], {"group_id":group.id}, compressed=True)
    with pytest.raises(ReceiptError, match="DIGEST"):
        load_groups(tmp_path/"manifest.json", {"entries":{group.id:entry}})


@pytest.mark.parametrize("mode,needs", [("lab", {"contract-and-safety": "success",
    "laboratory":"success"}), ("publication", {"test":"success", "capacity":"success"})])
def test_upstream_success_but_missing_artifact_writes_failed_gate(
    tmp_path, monkeypatch, mode, needs
):
    from types import SimpleNamespace

    monkeypatch.setenv("GITHUB_SHA", "a"*40)
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("A421_NEEDS", json.dumps({k:{"result":v} for k,v in needs.items()}))
    args = SimpleNamespace(mode=mode, input=tmp_path/"missing", output=tmp_path/"failed.json")
    with pytest.raises(SystemExit) as error:
        gate(args)
    assert error.value.code == 1
    receipt = json.loads(args.output.read_text())
    assert receipt["status"] == "INCOMPLETE" and not receipt["INFRASTRUCTURE_PASS"]
    assert receipt["errors"] and not receipt["production_read_authorized"]


def test_month_chain_read_order_is_not_interleaved():
    from scripts.a42_ci_contract import expected_groups

    groups = expected_groups(next(s for s in shards() if s.scope=="million-monthly"))
    sequence = ordered(groups)
    for start in range(0, len(sequence), 3):
        chain = sequence[start:start+3]
        assert len({(g.variant,g.repeat) for g in chain}) == 1
        assert [g.scope for g in chain] == ["month_1", "month_2", "month_3"]


def test_bad_business_target_never_imports_settings(tmp_path):
    env = {**os.environ, "TEST_DATABASE_URL":"postgresql://private:secret@business/db",
           "DATABASE_URL":"invalid-must-not-be-imported"}
    result = subprocess.run([os.sys.executable, "scripts/data_publication_capacity_v12.py",
        "--confirm-synthetic", "--level", "L1", "--output", str(tmp_path/"refused.json")],
        env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1 and "secret" not in result.stderr
    receipt = json.loads((tmp_path/"refused.json").read_text())
    assert receipt["status"] == "INCOMPLETE" and receipt["results"] == []
    assert "physical_system_identifier" not in receipt
