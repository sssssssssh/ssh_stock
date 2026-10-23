"""Read-only Actions contracts; never dispatch a workflow or start PostgreSQL."""

import ast
import copy
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "c076fa49fdd82ea07f5939f4ec6c190b1b19785b"
GOVERNANCE_BASELINE = "d123bdad4c2c04105d068fceb8f33ecb58e33d30"
SPEC = importlib.util.spec_from_file_location(
    "a4_governance_guard", ROOT / ".github/actions/a4-governance/guard.py"
)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)
POLICY = json.loads(guard.POLICY.read_text())
EXPENSIVE = {
    "ab-read-a4-baseline.yml": {"isolated-baseline": "a41"},
    "ab-read-a4-2.yml": {"laboratory": "a42"},
    "publication-v13.yml": {"candidate-performance": "publication-v13"},
    "ci.yml": {"lookup-tail-attribution": "a4231", "capacity": "capacity"},
    "a4232-statistics-tail-diagnostic.yml": {"attribution": "a4232"},
}


class WorkflowLoader(yaml.SafeLoader):
    pass


# YAML 1.2 booleans: unquoted `on` must remain a trigger key, not True.
WorkflowLoader.yaml_implicit_resolvers = copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)
for first, rules in WorkflowLoader.yaml_implicit_resolvers.items():
    WorkflowLoader.yaml_implicit_resolvers[first] = [
        rule for rule in rules if rule[0] != "tag:yaml.org,2002:bool"
    ]
WorkflowLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$", re.I), list("tTfF")
)


def workflow(name):
    return yaml.load((ROOT / ".github/workflows" / name).read_text(), Loader=WorkflowLoader)


def frozen(path, *, revision=BASELINE):
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT)


def condition(expression, context):
    """Evaluate only the boolean subset present in job ifs, not arbitrary code."""
    tokens = re.findall(r"'[^']*'|\d+|[A-Za-z_][\w.\-]*|==|!=|&&|\|\||[!()]", expression)
    source = expression.removeprefix("${{").removesuffix("}}").strip()
    assert "".join(tokens) == re.sub(r"\s+", "", source)
    index = 0

    def atom():
        nonlocal index
        token = tokens[index]
        index += 1
        if token == "!":
            return not atom()
        if token == "(":
            result = logical_or()
            assert tokens[index] == ")"
            index += 1
            return result
        if token in ("always", "cancelled"):
            assert tokens[index : index + 2] == ["(", ")"]
            index += 2
            return token == "always" or context.get("cancelled", False)
        if token.startswith("'"):
            return ast.literal_eval(token)
        if token in ("true", "false"):
            return token == "true"
        if token.isdigit():
            return int(token)
        return context.get(token, "")

    def compare():
        nonlocal index
        left = atom()
        if index < len(tokens) and tokens[index] in ("==", "!="):
            operator = tokens[index]
            index += 1
            right = atom()
            if type(left) is not type(right) and str(left).isdigit() and str(right).isdigit():
                left, right = int(left), int(right)
            return (left == right) if operator == "==" else (left != right)
        return left

    def logical_and():
        nonlocal index
        result = compare()
        while index < len(tokens) and tokens[index] == "&&":
            index += 1
            other = compare()
            result = bool(result) and bool(other)
        return result

    def logical_or():
        nonlocal index
        result = logical_and()
        while index < len(tokens) and tokens[index] == "||":
            index += 1
            other = logical_and()
            result = bool(result) or bool(other)
        return result

    result = logical_or()
    assert index == len(tokens)
    return bool(result)


def context(event="workflow_dispatch"):
    return {
        "github.event_name": event,
        "github.ref": "refs/heads/master",
        "github.sha": "a" * 40,
        "github.run_attempt": 1,
        "needs.authorize.result": "success",
        "needs.lookup-diagnosis.outputs.capacity_ready": "true",
        "inputs.target_sha": "a" * 40,
        "inputs.confirm_expensive_run": True,
    }


def request(suite="a41"):
    profile = POLICY["profiles"][suite]
    env = dict(
        GITHUB_EVENT_NAME="workflow_dispatch",
        GITHUB_REF="refs/heads/master",
        GITHUB_SHA="a" * 40,
        GITHUB_RUN_ATTEMPT="1",
        GITHUB_RUN_ID="123",
        GITHUB_JOB="measurement",
        GITHUB_REPOSITORY=POLICY["repository"],
        GITHUB_WORKFLOW=profile["workflow"],
        A4_REVIEW_POLICY_ACK="a4-ci-1.0-reviewed",
    )
    inputs = dict(
        target_sha=env["GITHUB_SHA"],
        confirm_expensive_run=True,
        run_reason="synthetic contract only; no experiment",
        experiment=suite,
        protocol_id=profile["protocol_id"],
        protocol_sha256=profile["protocol_sha256"],
    )
    return env, inputs


def test_yaml_loader_preserves_unquoted_on_and_typed_booleans():
    parsed = yaml.load("on: {push: null}\nconfirm: false\n", Loader=WorkflowLoader)
    assert "on" in parsed and True not in parsed and parsed["confirm"] is False


def test_inventory_covers_every_workflow_and_no_hidden_trigger_chain():
    contracts_only = {"a4233-observer-contracts.yml"}
    assert {p.name for p in (ROOT / ".github/workflows").glob("*.yml")} == (
        set(EXPENSIVE) | contracts_only
    )
    inventory = (ROOT / "docs/acceptance/a4_ci_workflow_inventory.md").read_text(encoding="utf-8")
    for name in EXPENSIVE:
        value = workflow(name)
        assert name in inventory and set(value["on"]) == {
            "push",
            "pull_request",
            "workflow_dispatch",
        }
        assert not any(key in value for key in ("workflow_run", "repository_dispatch", "schedule"))
    for name in contracts_only:
        value = workflow(name)
        assert name in inventory
        assert set(value["on"]) == {"push", "pull_request"}
        assert set(value["jobs"]) == {"contracts"}
        assert value["jobs"]["contracts"]["timeout-minutes"] <= 12
        assert not any(key in value["on"] for key in
                       ("workflow_dispatch", "workflow_run", "repository_dispatch", "schedule"))


@pytest.mark.parametrize("event", ["push", "pull_request"])
def test_ordinary_events_never_measure_even_with_confirmation_and_ready_capacity(event):
    for name, jobs in EXPENSIVE.items():
        value = workflow(name)
        for job, suite in jobs.items():
            ctx = context(event)
            ctx.update(
                {
                    "inputs.experiment": suite,
                    "inputs.protocol_id": POLICY["profiles"][suite]["protocol_id"],
                }
            )
            assert not condition(value["jobs"][job]["if"], ctx), (name, job)
        assert not condition(value["jobs"]["authorize"]["if"], context(event))
        for job in ("contracts", "contract-and-safety"):
            if job in value["jobs"]:
                ctx = context(event)
                ctx["needs.authorize.result"] = "skipped"
                assert condition(value["jobs"][job]["if"], ctx)


@pytest.mark.parametrize("name,jobs", EXPENSIVE.items())
def test_dispatch_schema_guard_order_and_shared_non_cancelling_mutex(name, jobs):
    value = workflow(name)
    inputs = value["on"]["workflow_dispatch"]["inputs"]
    for key in (
        "target_sha",
        "confirm_expensive_run",
        "run_reason",
        "protocol_id",
        "protocol_sha256",
    ):
        assert inputs[key]["required"] is True
    assert inputs["confirm_expensive_run"]["type"] == "boolean"
    assert inputs["confirm_expensive_run"]["default"] is False
    concurrency = value["concurrency"]
    assert concurrency["cancel-in-progress"] is False
    assert set(concurrency) == {"group", "cancel-in-progress"}
    assert "ssh-stock-a4-expensive" in concurrency["group"]
    assert "github.event_name == 'workflow_dispatch'" in concurrency["group"]
    assert "github.run_id" in concurrency["group"]  # L0 cannot replace a pending manual run.
    authorization = value["jobs"]["authorize"]
    assert authorization["environment"] == "a4-expensive-measurements"
    assert "services" not in authorization
    for job, suite in jobs.items():
        measured = value["jobs"][job]
        assert "authorize" in measured["needs"]
        assert measured["environment"] == "a4-expensive-measurements"
        assert "services" not in measured  # Services must not precede the guard.
        steps = measured["steps"]
        guard_index = next(
            i for i, s in enumerate(steps) if s.get("uses") == "./.github/actions/a4-governance"
        )
        assert steps[guard_index]["with"]["suite"] == suite
        assert all(s.get("uses") == "actions/checkout@v4" for s in steps[:guard_index])
        assert any(s.get("uses") == "./.github/actions/a421-pg" for s in steps[guard_index + 1 :])
        assert any(
            s.get("uses") == "./.github/actions/a4-cleanup" and s["if"] == "always()" for s in steps
        )
        assert any(
            s.get("uses") == "./.github/actions/a4-finish" and s["if"] == "always()" for s in steps
        )
        assert not any(s.get("continue-on-error") for s in steps)


def test_manual_dispatch_selects_only_one_ci_experiment_and_never_overrides_readiness():
    jobs = workflow("ci.yml")["jobs"]
    for selected in ("a4231", "capacity", "none"):
        ctx = context()
        ctx.update(
            {"inputs.experiment": selected, "inputs.protocol_id": "[a4231-attribution-once]"}
        )
        assert condition(jobs["lookup-tail-attribution"]["if"], ctx) == (selected == "a4231")
        assert condition(jobs["capacity"]["if"], ctx) == (selected == "capacity")
        ctx["needs.lookup-diagnosis.outputs.capacity_ready"] = "false"
        assert not condition(jobs["capacity"]["if"], ctx)


@pytest.mark.parametrize("event", ["push", "pull_request", "workflow_dispatch"])
@pytest.mark.parametrize("selected", ["none", "capacity", "a4231"])
@pytest.mark.parametrize("confirmed", [False, True])
def test_ci_l0_authorization_and_formal_gate_trigger_matrix(event, selected, confirmed):
    jobs = workflow("ci.yml")["jobs"]
    ctx = context(event)
    ctx.update({
        "inputs.experiment": selected,
        "inputs.confirm_expensive_run": confirmed,
        "inputs.protocol_id": "[a4231-attribution-once]",
    })
    manual = event == "workflow_dispatch"
    assert condition(jobs["authorize"]["if"], ctx) is (manual and selected != "none")
    for job in ("test", "dependency-audit", "lookup-diagnosis", "workflow-contracts"):
        assert condition(jobs[job].get("if", "true"), ctx), job
        assert not jobs[job].get("needs"), job
    for job, suite in EXPENSIVE["ci.yml"].items():
        assert condition(jobs[job]["if"], ctx) is (manual and confirmed and selected == suite)
    assert condition(jobs["publication-release-gate"]["if"], ctx) is (
        manual and confirmed and selected == "capacity"
    )


@pytest.mark.parametrize("event", ["push", "pull_request", "workflow_dispatch"])
@pytest.mark.parametrize("confirmed", [False, True])
def test_a42_l0_and_formal_gate_trigger_matrix(event, confirmed):
    jobs = workflow("ab-read-a4-2.yml")["jobs"]
    ctx = context(event)
    ctx["inputs.confirm_expensive_run"] = confirmed
    manual = event == "workflow_dispatch"
    assert condition(jobs["authorize"]["if"], ctx) is manual
    assert condition(jobs["laboratory"]["if"], ctx) is (manual and confirmed)
    assert condition(jobs["a42-acceptance-gate"]["if"], ctx) is (manual and confirmed)
    if not manual:
        ctx["needs.authorize.result"] = "skipped"
        assert condition(jobs["contract-and-safety"]["if"], ctx)


@pytest.mark.parametrize("mode", ["publication", "lab"])
@pytest.mark.parametrize("upstream", ["skipped", "failure", "cancelled", "timed_out", "success"])
def test_confirmed_formal_gate_runs_and_rejects_failed_or_missing_evidence(
    tmp_path, monkeypatch, mode, upstream
):
    from scripts.ci_release_gate_v14_a4_2_1 import gate

    filename, job, measured, required = (
        ("ci.yml", "publication-release-gate", "capacity",
         ["test", "capacity", "lookup-diagnosis", "dependency-audit"])
        if mode == "publication" else
        ("ab-read-a4-2.yml", "a42-acceptance-gate", "laboratory",
         ["contract-and-safety", "laboratory"])
    )
    spec = workflow(filename)["jobs"][job]
    ctx = context()
    ctx.update({
        "inputs.experiment": "capacity",
        "needs.authorize.result": "failure",
        "needs.lookup-diagnosis.outputs.capacity_ready": "false",
        "cancelled": upstream == "cancelled",
        **{f"needs.{key}.result": upstream if key == measured else "success" for key in required},
    })
    assert "always()" in spec["if"]  # Avoid GitHub's implicit success() after skipped needs.
    assert condition(spec["if"], ctx)
    monkeypatch.setenv("GITHUB_SHA", subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip())
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("GITHUB_RUN_ID", "synthetic-governance-only")
    monkeypatch.setenv("A421_NEEDS", json.dumps({
        key: {"result": upstream if key == measured else "success"} for key in required
    }))
    args = SimpleNamespace(mode=mode, input=tmp_path / "missing", output=tmp_path / "gate.json")
    with pytest.raises(SystemExit) as caught:
        gate(args)
    assert caught.value.code == 1
    receipt = json.loads(args.output.read_text())
    assert receipt["status"] == "INCOMPLETE" and receipt["errors"]
    if upstream != "success":
        assert receipt["errors"] == ["UPSTREAM_NOT_SUCCESS"]
    assert all(receipt[key] is False for key in (
        "INFRASTRUCTURE_PASS", "CORRECTNESS_PASS", "READ_PERFORMANCE_PASS",
        "production_read_authorized", "authorize_a4_3",
    ))


@pytest.mark.parametrize("name", EXPENSIVE)
def test_only_reviewed_job_conditions_change_from_ci_1_0(name):
    before = yaml.load(frozen(".github/workflows/" + name, revision=GOVERNANCE_BASELINE),
                       Loader=WorkflowLoader)
    after = workflow(name)
    if name == 'ci.yml':
        from scripts.a42331_ci_contract import normalize_test_job

        after['jobs']['test'] = normalize_test_job(after['jobs']['test'])
    allowed = {
        "ci.yml": {"authorize", "publication-release-gate"},
        "ab-read-a4-2.yml": {"a42-acceptance-gate"},
    }.get(name, set())
    for job in allowed:
        assert after["jobs"][job]["if"] != before["jobs"][job]["if"]
        after["jobs"][job]["if"] = before["jobs"][job]["if"]
    assert after == before  # Includes every L0 step, gate dependency/command and matrix budget.


def test_governance_guard_policy_and_consumed_tokens_remain_frozen():
    for path in (".github/actions/a4-governance/guard.py",
                 ".github/actions/a4-governance/policy.json"):
        assert (ROOT / path).read_text(encoding="utf-8") == frozen(
            path, revision=GOVERNANCE_BASELINE
        ).decode("utf-8")


def test_l0_retains_original_contract_cases_and_uses_only_read_resource_class():
    for filename, expensive in EXPENSIVE.items():
        value = workflow(filename)
        for job, spec in value["jobs"].items():
            if job in expensive:
                continue
            for step in spec.get("steps", []):
                if step.get("uses") == "./.github/actions/a421-pg":
                    assert step.get("with", {}).get("resource-class", "read") == "read"
        if filename in ("ab-read-a4-baseline.yml", "publication-v13.yml"):
            before = yaml.load(frozen(".github/workflows/" + filename), Loader=WorkflowLoader)
            old_cases = set(re.findall(r"tests/[\w./_\-]+\.py", json.dumps(before)))
            new_cases = set(
                re.findall(r"tests/[\w./_\-]+\.py", json.dumps(value["jobs"]["contracts"]))
            )
            assert old_cases <= new_cases


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("confirm_expensive_run", False, "CONFIRMATION_REQUIRED"),
        ("confirm_expensive_run", "true", "CONFIRMATION_REQUIRED"),
        ("target_sha", "abc123", "FULL_SHA_REQUIRED"),
        ("target_sha", "b" * 40, "SHA_MISMATCH"),
        ("run_reason", "  ", "REASON_REQUIRED"),
        ("protocol_id", "different-protocol", "PROTOCOL_ID_MISMATCH"),
        ("protocol_sha256", "0" * 64, "PROTOCOL_HASH_MISMATCH"),
        ("experiment", "capacity", "SUITE_MISMATCH"),
    ],
)
def test_invalid_inputs_refused_before_git_or_expensive_operations(monkeypatch, field, value, code):
    env, inputs = request()
    inputs[field] = value
    monkeypatch.setattr(
        guard, "git", lambda *a: pytest.fail("must refuse before git/PG/dependencies")
    )
    with pytest.raises(ValueError, match="GOV_" + code):
        guard.authorize(env, inputs, POLICY, "a41")


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("GITHUB_EVENT_NAME", "push", "DISPATCH_REQUIRED"),
        ("GITHUB_REF", "refs/heads/other", "MASTER_REQUIRED"),
        ("GITHUB_REF", "refs/tags/master", "MASTER_REQUIRED"),
        ("GITHUB_RUN_ATTEMPT", "2", "RERUN_REFUSED"),
        ("GITHUB_REPOSITORY", "untrusted/fork", "REPOSITORY_MISMATCH"),
        ("GITHUB_WORKFLOW", "another-workflow", "SUITE_MISMATCH"),
        ("A4_REVIEW_POLICY_ACK", "", "ADMIN_CONFIGURATION_REQUIRED"),
    ],
)
def test_invalid_context_refused(monkeypatch, field, value, code):
    env, inputs = request()
    env[field] = value
    with pytest.raises(ValueError, match="GOV_" + code):
        guard.authorize(env, inputs, POLICY, "a41")


def fake_git(*args):
    if args == ("rev-parse", "HEAD"):
        return b"a" * 40
    if args[0] in ("status", "diff", "merge-base"):
        return b""
    if args[0] == "ls-tree":
        return subprocess.check_output(["git", "ls-tree", "-r", BASELINE, *args[3:]], cwd=ROOT)
    assert args[0] == "show"
    return frozen(args[1].split(":", 1)[1])


@pytest.mark.parametrize("suite", ["a41", "a42", "publication-v13", "capacity"])
def test_valid_request_authorizes_only_the_named_diagnostic(monkeypatch, suite):
    env, inputs = request(suite)
    monkeypatch.setattr(guard, "git", fake_git)
    receipt = {**guard.header(env), **guard.authorize(env, inputs, POLICY, suite)}
    assert receipt["suite"] == suite and receipt["evidence_kind"] == "GOVERNANCE_ONLY"
    assert not receipt["capacity_ready"] and not receipt["formal_capacity_complete"]
    assert not receipt["production_read_authorized"]
    assert inputs["run_reason"] not in json.dumps(receipt)


@pytest.mark.parametrize("suite", ["a4231", "a4232"])
def test_consumed_one_shot_is_not_reusable_even_in_a_new_run(monkeypatch, suite):
    env, inputs = request(suite)
    env["GITHUB_RUN_ID"] = "999999999"
    monkeypatch.setattr(guard, "git", lambda *a: pytest.fail("closed protocol must stop first"))
    with pytest.raises(ValueError, match="ONE_SHOT_ID_CONSUMED"):
        guard.authorize(env, inputs, POLICY, suite)


@pytest.mark.parametrize(
    "operation,value,code",
    [
        ("status", b" M synthetic-file", "DIRTY_CHECKOUT"),
        ("rev-parse", b"b" * 40, "CHECKOUT_MISMATCH"),
        ("diff", b"production changed", "FROZEN_PRODUCTION_CHANGED"),
        ("show", b"modified source/protocol", "FROZEN_SOURCE_OR_PROTOCOL_CHANGED"),
    ],
)
def test_dirty_checkout_and_changed_frozen_inputs_refused(monkeypatch, operation, value, code):
    env, inputs = request()
    monkeypatch.setattr(guard, "git", lambda *a: value if a[0] == operation else fake_git(*a))
    with pytest.raises(ValueError, match=code):
        guard.authorize(env, inputs, POLICY, "a41")


@pytest.mark.parametrize(
    "status,cleanup",
    [
        ("cancelled", "success"),
        ("timed_out", "success"),
        ("failure", "success"),
        ("success", "failure"),
        ("unknown", "not_required"),
    ],
)
def test_partial_cancel_timeout_and_cleanup_failure_never_become_pass(status, cleanup):
    env, _ = request()
    env.update(A4_JOB_STATUS=status, A4_CLEANUP_OUTCOME=cleanup)
    previous = {**guard.header(env), "checkpoints": ["synthetic-partial"]}
    result = guard.finalize(env, previous)
    assert result["status"] == "INCOMPLETE" and result["checkpoints"] == previous["checkpoints"]
    assert result["evidence_kind"] == "GOVERNANCE_ONLY" and not result["formal_capacity_complete"]


def test_finished_governance_is_never_a_formal_receipt_and_stale_identity_is_rejected():
    from scripts.a42_receipt_contract import ReceiptError, identity

    env, _ = request()
    env["A4_JOB_STATUS"] = "success"
    result = guard.finalize(env, {})
    assert result["status"] == "FINISHED"
    with pytest.raises(ReceiptError, match="SCHEMA_MISMATCH"):
        identity(result, head=env["GITHUB_SHA"], attempt=1, job_id="measurement")
    assert guard.finalize(env, {"head_sha": "b" * 40})["status"] == "INCOMPLETE"


@pytest.mark.parametrize("failure", [None, "labels", "inspect", "remove", "docker-unavailable"])
def test_cleanup_only_removes_own_container_and_reports_failures(failure):
    env, _ = request()
    env["A421_CONTAINER"] = "a4-ci-123-1-abcdef123456"
    labels = {
        "purpose": "ssh-stock-a4-physical-test",
        "ssh-stock.run-id": "123",
        "ssh-stock.attempt": "1",
        "ssh-stock.job": "measurement",
    }
    calls = []
    if failure == "labels":
        labels["ssh-stock.run-id"] = "another-run"

    def run(args, **kwargs):
        calls.append(args)
        command = args[1]
        code = int(
            (failure == "inspect" and command == "inspect")
            or (failure == "remove" and command == "rm")
            or failure == "docker-unavailable"
        )
        output = env["A421_CONTAINER"] if command == "ps" else json.dumps(labels)
        return SimpleNamespace(returncode=code, stdout=output, stderr="sensitive driver details")

    if failure:
        with pytest.raises(ValueError, match="GOV_") as caught:
            guard.cleanup(env, run)
        assert "sensitive" not in str(caught.value)
    else:
        assert guard.cleanup(env, run) == "REMOVED_OWNED_CONTAINER"
    assert any(c[1] == "rm" for c in calls) == (failure in (None, "remove"))


def test_unique_container_names_labels_and_dual_identity_are_preserved():
    action = (ROOT / ".github/actions/a421-pg/action.yml").read_text()
    assert (
        "a4-ci-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT-" in action and "uuid.uuid4().hex[:12]" in action
    )
    for label in ("ssh-stock.run-id", "ssh-stock.attempt", "ssh-stock.job"):
        assert label in action
    assert "pg_controldata" in action and "verified_test_url()" in action
    assert (
        "--cpus=2 --memory=3g" in action
        and "GOVERNANCE_ONLY" in guard.header(request()[0]).values()
    )


def test_release_gate_and_historical_evidence_are_frozen_and_missing_capacity_still_fails():
    from scripts.a42_receipt_contract import ReceiptError, merge_capacity, require_jobs

    for name in (
        "scripts/ci_release_gate_v14_a4_2_1.py",
        "scripts/a42_receipt_contract.py",
        "scripts/publication_release_checks_v14_a4_2_1.py",
        "docs/acceptance/evidence/a4232_stability_review.json",
        "docs/acceptance/evidence/a4232_source_manifest.json",
    ):
        assert (ROOT / name).read_text(encoding="utf-8") == frozen(name).decode("utf-8")
    for filename, job in (("ci.yml", "publication-release-gate"),
                          ("ab-read-a4-2.yml", "a42-acceptance-gate")):
        release = workflow(filename)["jobs"][job]
        original = yaml.load(frozen(".github/workflows/" + filename), Loader=WorkflowLoader)[
            "jobs"
        ][job]
        assert "always()" in release.pop("if")
        original.pop("if")
        assert release == original  # Only event selection may change, never strict validation.
    for status in ("skipped", "cancelled", "failure"):
        with pytest.raises(ReceiptError, match="UPSTREAM_NOT_SUCCESS"):
            require_jobs({"test": "success", "capacity": status}, {"test", "capacity"})
    with pytest.raises(ReceiptError, match="CAPACITY_LEVEL_MISSING"):
        merge_capacity([], head="a" * 40, attempt=1, model_hash="b" * 64)


def test_policy_protocol_and_measurement_sources_match_the_reviewed_baseline():
    assert POLICY["baseline_sha"] == BASELINE
    for profile in POLICY["profiles"].values():
        for path, expected in (
            (profile["protocol"], profile["protocol_sha256"]),
            (profile["source"], profile["source_sha256"]),
        ):
            assert hashlib.sha256(frozen(path)).hexdigest() == expected


def test_changed_dataset_recipe_refused(monkeypatch):
    env, inputs = request()
    target = POLICY["frozen_evidence_inputs"][0]
    monkeypatch.setattr(
        guard,
        "git",
        lambda *a: b"changed fixture" if a == ("show", "HEAD:" + target) else fake_git(*a),
    )
    with pytest.raises(ValueError, match="DATASET_OR_MEASUREMENT_CONTRACT_CHANGED"):
        guard.authorize(env, inputs, POLICY, "a41")


@pytest.mark.parametrize(
    "event_inputs,code",
    [
        ({}, "GOV_CONFIRMATION_REQUIRED"),
        ([], "GOV_EVENT_SCHEMA_INVALID"),
    ],
)
def test_real_guard_cli_fails_before_git_dependencies_or_database_and_redacts(
    tmp_path, event_inputs, code
):
    import os

    env, _ = request()
    path = tmp_path / "event.json"
    path.write_text(json.dumps({"inputs": event_inputs}), encoding="utf-8")
    env.update(GITHUB_EVENT_PATH=str(path), LLM_API_KEY="SECRET_DO_NOT_EXPORT")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / ".github/actions/a4-governance/guard.py"),
            "authorize",
            "--suite",
            "a41",
        ],
        env={**os.environ, **env},
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1 and code in result.stderr
    receipt = json.loads((tmp_path / guard.RECEIPT).read_text())
    assert receipt["status"] == "INCOMPLETE" and receipt["first_failure"] == code
    assert "SECRET_DO_NOT_EXPORT" not in result.stdout + result.stderr + json.dumps(receipt)
    assert not receipt["capacity_ready"] and not receipt["formal_capacity_complete"]


def test_missing_or_foreign_container_never_runs_removal():
    env, _ = request()
    assert (
        guard.cleanup(env, lambda *a, **k: pytest.fail("no container was created")) == "NOT_CREATED"
    )
    env["A421_CONTAINER"] = "business-postgres"
    with pytest.raises(ValueError, match="CONTAINER_NAME_REFUSED"):
        guard.cleanup(env, lambda *a, **k: pytest.fail("must not inspect or remove a foreign name"))


def test_measurement_commands_scales_repetitions_and_budgets_are_unchanged():
    def runs(job, script):
        return [
            s["run"]
            .replace("--container a4-isolated-pg17", '--container "$A421_CONTAINER"')
            .replace("--container a421-pg17", '--container "$A421_CONTAINER"')
            for s in job["steps"]
            if f"python {script}" in s.get("run", "")
        ]

    for name, jobs in EXPENSIVE.items():
        old = yaml.load(frozen(".github/workflows/" + name), Loader=WorkflowLoader)["jobs"]
        new = workflow(name)["jobs"]
        for job, suite in jobs.items():
            source = POLICY["profiles"][suite]["source"]
            assert runs(old[job], source) and runs(old[job], source) == runs(new[job], source)
            assert old[job]["timeout-minutes"] == new[job]["timeout-minutes"]
            if "strategy" in old[job]:
                assert old[job]["strategy"] == new[job]["strategy"]


def test_dispatch_text_is_never_interpolated_into_a_shell_command():
    for name in EXPENSIVE:
        for job in workflow(name)["jobs"].values():
            for step in job.get("steps", []):
                assert not re.search(r"\$\{\{\s*inputs\.", step.get("run", ""))
    action = (ROOT / ".github/actions/a4-governance/action.yml").read_text()
    assert '--suite "$A4_SUITE"' in action


def test_changed_model_identity_is_rejected(monkeypatch):
    env, inputs = request()
    monkeypatch.setattr(
        guard,
        "git",
        lambda *a: b"changed models" if a[:3] == ("ls-tree", "-r", "HEAD") else fake_git(*a),
    )
    with pytest.raises(ValueError, match="MODEL_IDENTITY_CHANGED"):
        guard.authorize(env, inputs, POLICY, "a41")
