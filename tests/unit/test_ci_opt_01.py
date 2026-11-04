"""CI-OPT-01: actual Git comparisons, negative routing and unchanged full-suite contracts."""

import ast
import importlib.util
import json
import shutil
import subprocess
import sys

import pytest
import yaml

from scripts import ci_change_scope as scope
from scripts.ci_docs_check import check_metadata, unique_object, validate
from scripts.ci_opt_contract import (
    BASELINE,
    ROOT,
    TARGETS,
    baseline,
    guarded,
    plans,
    restore,
    transformed_job,
)
from scripts.ci_status_summary import verify_job, verify_workflow

POLICY = json.loads(scope.POLICY.read_text(encoding="utf-8"))
NOTE = ("# Notes\n\n" + POLICY["block_start"] + "\n说明阅读流程。\n"
        + POLICY["block_end"] + "\n")


def git(root, *args):
    return scope.git(root, "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false", *args)


def commit(root, changes):
    for path, content in changes.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if content is None:
            target.unlink()
        else:
            target.write_text(content, encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "synthetic fixture")
    return git(root, "rev-parse", "HEAD").decode().strip()


@pytest.fixture(scope="session")
def base_repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("ci-opt-synthetic-git")
    git(root, "init", "-b", "master", "-q")
    git(root, "config", "user.name", "Synthetic CI")
    git(root, "config", "user.email", "synthetic@example.invalid")
    before = commit(root, {
        "README.md": NOTE, "PROJECT_STATUS.md": NOTE, "backend/sample.py": "value = 1\n",
        "frontend/sample.ts": "export const value = 1\n", "requirements.lock": "fixture\n",
        "migrations/sample.py": "fixture\n", "tests/sample.py": "fixture\n",
        ".github/workflows/sample.yml": "fixture\n", ".github/actions/guard.py": "fixture\n",
        "docs/contract.md": "fixture\n", "config/strategy.yaml": "fixture\n",
        "docs/acceptance/biz_perf_03_a_r1/verification.json": '{"acceptance":"PARTIAL"}\n',
    })
    return root, before


@pytest.fixture
def repo(tmp_path, base_repo):
    # Each case gets an independent repository; only immutable synthetic seed bytes are reused.
    root, before = base_repo
    target = tmp_path / "repo"
    shutil.copytree(root, target)
    return target, before


def classify(repo, changes, **event_overrides):
    root, before = repo
    after = commit(root, changes)
    env = {"GITHUB_SHA": after, "GITHUB_REF": "refs/heads/master"}
    event = {"before": before, "after": after, "forced": False, **event_overrides}
    return scope.classify(root, "push", event, env, POLICY), env


def test_T01_readme_prose_uses_real_complete_git_diff(repo):
    receipt, env = classify(repo, {"README.md": NOTE.replace("阅读流程", "阅读与导航流程")})
    assert receipt["scope"] == "docs"
    assert receipt["reason"] == "REGISTERED_PROSE_ONLY"
    result = validate(repo[0], receipt, POLICY, env)
    assert result["status"] == "DOC_CHECKS_PASS" and result["full_regression"] == "NOT_RUN"


def test_T02_status_and_json_are_static_checked_but_contract_json_requires_full(repo):
    receipt, _ = classify(repo, {
        "PROJECT_STATUS.md": NOTE.replace("阅读流程", "页面阅读流程"),
        "docs/acceptance/biz_perf_03_a_r1/verification.json": '{"acceptance":"PARTIAL","note":1}\n',
    })
    assert receipt["scope"] == "full"
    assert check_metadata(repo[0], receipt) == 1
    with pytest.raises(ValueError, match="DUPLICATE_JSON"):
        json.loads('{"status":1,"status":2}', object_pairs_hook=unique_object)


@pytest.mark.parametrize("path", [
    "backend/sample.py", "tests/sample.py", "migrations/sample.py", "requirements.lock",
    "frontend/sample.ts", ".github/workflows/sample.yml", ".github/actions/guard.py",
    "config/strategy.yaml", "docs/contract.md",
])
def test_T03_T04_T05_T06_sensitive_paths_require_full(repo, path):
    receipt, _ = classify(repo, {path: "changed\n"})
    assert receipt["scope"] == "full"


def test_T07_mixed_docs_and_backend_requires_full(repo):
    receipt, _ = classify(repo, {
        "README.md": NOTE.replace("阅读流程", "阅读与导航流程"), "backend/sample.py": "value=2\n",
    })
    assert receipt["scope"] == "full"
    assert len(receipt["changed_files"]) == 2


@pytest.mark.parametrize("changes", [
    {"unknown.md": NOTE}, {"README.md": None}, {"README.md": None, "renamed.md": NOTE},
    {"README.md": NOTE.replace("# Notes", "# New executable contract")},
    {"README.md": NOTE.replace("说明阅读流程。", "生产授权通过。")},
    {"README.md": NOTE.replace("说明阅读流程。", "[link](https://example.invalid)")},
    {"README.md": NOTE.replace("说明阅读流程。", "```python\nprint(1)\n```")},
])
def test_T08_unknown_deleted_renamed_case_and_contract_changes_require_full(repo, changes):
    receipt, _ = classify(repo, changes)
    assert receipt["scope"] == "full"


def test_T08_case_only_rename_uses_git_index_on_case_insensitive_filesystems(repo):
    root, before = repo
    git(root, "mv", "README.md", "temporary-name.md")
    git(root, "mv", "temporary-name.md", "readme.md")
    git(root, "commit", "-qm", "synthetic case rename")
    after = git(root, "rev-parse", "HEAD").decode().strip()
    receipt = scope.classify(root, "push", {"before": before, "after": after},
                             {"GITHUB_SHA": after, "GITHUB_REF": "refs/heads/master"}, POLICY)
    assert receipt["scope"] == "full"
    assert {r["status"] for r in receipt["changed_files"]} == {"A", "D"}


@pytest.mark.parametrize("override", [{"before": "0" * 40}, {"before": "f" * 40}, {"forced": True}])
def test_T09_invalid_or_forced_push_requires_full(repo, override):
    receipt, _ = classify(repo, {"README.md": NOTE.replace("阅读流程", "阅读顺序")}, **override)
    assert receipt["scope"] == "full"


def test_T09_multicommit_push_sees_earlier_code_change(repo):
    commit(repo[0], {"backend/sample.py": "value=2\n"})
    receipt, _ = classify(repo, {"README.md": NOTE.replace("阅读流程", "阅读顺序")})
    assert receipt["scope"] == "full" and len(receipt["changed_files"]) == 2


def test_T09_pr_merge_base_and_manual_always_full(repo):
    receipt, env = classify(repo, {"README.md": NOTE.replace("阅读流程", "阅读顺序")})
    pr = {"pull_request": {"base": {"sha": repo[1]}, "head": {"sha": env["GITHUB_SHA"]}}}
    assert scope.classify(repo[0], "pull_request", pr, env, POLICY)["scope"] == "docs"
    pr["pull_request"]["head"]["sha"] = "f" * 40
    assert scope.classify(repo[0], "pull_request", pr, env, POLICY)["scope"] == "full"
    for event in ("workflow_dispatch", "workflow_run", "", "repository_dispatch"):
        assert scope.classify(repo[0], event, {}, env, POLICY)["scope"] == "full"
    assert receipt["performance_eligible"] is False


def test_T09_actual_two_parent_pr_merge_checkout(repo):
    root, before = repo
    _, env = classify(repo, {"README.md": NOTE.replace("阅读流程", "阅读顺序")})
    after = env["GITHUB_SHA"]
    tree = git(root, "rev-parse", f"{after}^{{tree}}").decode().strip()
    merge = git(root, "commit-tree", tree, "-p", before, "-p", after,
                "-m", "synthetic PR merge").decode().strip()
    git(root, "checkout", "--detach", "-q", merge)
    event = {"pull_request": {"base": {"sha": before}, "head": {"sha": after}}}
    result = scope.classify(root, "pull_request", event, {"GITHUB_SHA": merge}, POLICY)
    assert result["scope"] == "docs" and result["comparison_head"] == after


def test_T08_executable_or_symlink_mode_cannot_use_prose_route(repo):
    root, before = repo
    git(root, "update-index", "--chmod=+x", "README.md")
    git(root, "commit", "-qm", "synthetic executable mode")
    after = git(root, "rev-parse", "HEAD").decode().strip()
    result = scope.classify(root, "push", {"before": before, "after": after},
                            {"GITHUB_SHA": after, "GITHUB_REF": "refs/heads/master"}, POLICY)
    assert result["scope"] == "full" and result["reason"] == "NOT_ORDINARY_FILE"


def test_T08_diff_failure_is_full_not_an_empty_success(repo, monkeypatch):
    def fail(*args):
        raise subprocess.CalledProcessError(1, ["git"])

    monkeypatch.setattr(scope, "git", fail)
    result = scope.classify(repo[0], "push", {"before": repo[1], "after": repo[1]},
                            {"GITHUB_SHA": repo[1]}, POLICY)
    assert result["scope"] == "full" and result["reason"] == "COMPARISON_FAILED"


def job_fixture(mode="full"):
    env = {"GITHUB_SHA": "a" * 40}
    receipt = {"schema_version": scope.SCHEMA, "scope": mode, "head_sha": env["GITHUB_SHA"],
               "run_id": "local", "attempt": "1", "job": "local", "changed_files": ["fixture"]}
    plan = {"all": ["full_tests", "optional_upload"], "mandatory": ["full_tests"]}
    outcomes = {"ci_scope": {"outcome": "success"}, "full_tests": {"outcome": "success"}}
    return env, receipt, plan, outcomes


@pytest.mark.parametrize("bad", ["skipped", "cancelled", "failure", "", None])
def test_T10_full_step_never_aggregates_skipped_failed_cancelled_or_missing(bad):
    env, receipt, plan, outcomes = job_fixture()
    outcomes["full_tests"]["outcome"] = bad
    with pytest.raises(ValueError, match="FULL_STEP"):
        verify_job(receipt, outcomes, "success", plan, env)


def test_T10_positive_full_job_requires_all_original_mandatory_steps():
    env, receipt, plan, outcomes = job_fixture()
    assert verify_job(receipt, outcomes, "success", plan, env) == "FULL_JOB_CHECKS_PASS"
    for upstream in ("failure", "cancelled"):
        with pytest.raises(ValueError, match="ROUTE_OR_UPSTREAM"):
            verify_job(receipt, outcomes, upstream, plan, env)


def test_T10_docs_route_requires_executed_checks_and_skipped_heavy_steps():
    env, receipt, plan, outcomes = job_fixture("docs")
    outcomes.update({key: {"outcome": "skipped"} for key in plan["all"]})
    doc = {"status": "DOC_CHECKS_PASS", "full_regression": "NOT_RUN", "checked_files": 1}
    assert verify_job(receipt, outcomes, "success", plan, env, doc) == "DOC_CHECKS_PASS"
    with pytest.raises(ValueError):
        verify_job(receipt, outcomes, "success", plan, env)
    outcomes["full_tests"]["outcome"] = "success"
    with pytest.raises(ValueError):
        verify_job(receipt, outcomes, "success", plan, env, doc)


@pytest.mark.parametrize("bad", ["skipped", "cancelled", "failure", "timed_out", "unknown"])
def test_T10_summary_rejects_non_success_required_job(bad):
    needs = {"contracts": {"result": bad, "outputs": {}}}
    with pytest.raises(ValueError, match="MANDATORY_JOB"):
        verify_workflow("publication-v13.yml", needs, {"GITHUB_SHA": "a" * 40})


def test_T10_success_requires_current_head_route_proof_not_only_green_status():
    env = {"GITHUB_SHA": "a" * 40}
    outputs = {"ci_opt_verified": "true", "ci_opt_head": env["GITHUB_SHA"], "ci_opt_scope": "docs"}
    needs = {"contracts": {"result": "success", "outputs": outputs}}
    assert verify_workflow("publication-v13.yml", needs, env) == "docs"
    outputs["ci_opt_head"] = "b" * 40
    with pytest.raises(ValueError, match="MISSING_ROUTE_PROOF"):
        verify_workflow("publication-v13.yml", needs, env)


@pytest.mark.parametrize("name", TARGETS)
def test_T11_exact_workflow_projection_preserves_every_old_command_and_authorization(name):
    current = yaml.safe_load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"))
    original = restore(name, current)
    for key in TARGETS[name]:
        old_steps = original["jobs"][key]["steps"]
        new_steps = current["jobs"][key]["steps"]
        assert len(new_steps) == len(old_steps) + 3
        for old, new in zip(old_steps[1:], new_steps[2:-2], strict=True):
            assert new["if"] == guarded(old.get("if"))
            assert old.get("run") == new.get("run")
        assert current["jobs"][key].get("services") == original["jobs"][key].get("services")
    assert current["on"] == original["on"]
    assert current["concurrency"] == original["concurrency"]


@pytest.mark.parametrize("mutation", ["drop", "coverage", "guard", "gate", "authorization"])
def test_T11_negative_workflow_mutations_are_rejected(mutation):
    value = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    step = next(s for s in value["jobs"]["test"]["steps"] if s.get("id") == "full_tests")
    if mutation == "drop":
        value["jobs"]["test"]["steps"].remove(step)
    elif mutation == "coverage":
        step["run"] = step["run"].replace("under=70", "under=1")
    elif mutation == "guard":
        step["if"] = "false"
    elif mutation == "gate":
        value["jobs"]["publication-release-gate"]["needs"] = ["test"]
    else:
        value["jobs"]["authorize"].pop("environment")
    with pytest.raises(ValueError, match="UNREVIEWED_WORKFLOW"):
        restore("ci.yml", value)


def test_T11_runtime_step_plan_is_exactly_derived_from_original_steps():
    assert json.loads((ROOT / ".github/ci-opt-steps.json").read_text()) == plans()
    original = baseline("ci.yml")["jobs"]["test"]
    candidate = transformed_job("ci.yml", "test", original)
    full = next(s for s in candidate["steps"] if s.get("id") == "full_tests")
    assert "--cov-fail-under=70" in full["run"]
    assert "-p scripts.a42331_pytest_safety" in full["run"]


def test_T10_actual_guard_expressions_accept_full_and_empty_but_never_docs():
    spec = importlib.util.spec_from_file_location(
        "ci_opt_existing_conditions", ROOT / "tests/unit/test_a4_ci_governance.py",
    )
    conditions = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conditions)
    for name, keys in TARGETS.items():
        current = yaml.safe_load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"))
        for key in keys:
            for step in current["jobs"][key]["steps"][2:-2]:
                assert step["if"].startswith((
                    "steps.ci_scope.outputs.scope != 'docs'",
                    "${{ (steps.ci_scope.outputs.scope != 'docs') && (",
                ))
            for step in (current["jobs"][key]["steps"][2], next(
                s for s in current["jobs"][key]["steps"] if s.get("id") == "cleanup"
            )):
                for value in ("docs", "full", ""):
                    assert conditions.condition(step["if"], {
                        "steps.ci_scope.outputs.scope": value,
                    }) is (value != "docs")


def test_T06_scope_action_has_no_fallback_that_can_forge_docs_or_skip_validation():
    action = yaml.safe_load((ROOT / ".github/actions/ci-scope/action.yml").read_text())
    steps = action["runs"]["steps"]
    assert action["outputs"]["scope"]["value"] == "${{ steps.classify.outputs.scope }}"
    assert [s["run"] for s in steps] == [
        "python -m scripts.ci_change_scope --output .codex_tmp/ci-opt/scope.json",
        "python -m scripts.ci_docs_check --receipt .codex_tmp/ci-opt/scope.json",
    ]
    assert all("if" not in s and "continue-on-error" not in s for s in steps)
    assert all(p.endswith(".md") for p in POLICY["prose_block_files"])


def test_T01_T10_real_entrypoints_emit_only_docs_proof(repo, monkeypatch):
    from scripts import ci_docs_check, ci_status_summary

    root, before = repo
    _, env = classify(repo, {"README.md": NOTE.replace("阅读流程", "阅读顺序")})
    event_path, output = root / "event.json", root / "output.txt"
    event_path.write_text(json.dumps({"before": before, "after": env["GITHUB_SHA"]}))
    for key, value in {**env, "GITHUB_EVENT_NAME": "push", "GITHUB_EVENT_PATH": str(event_path),
                       "GITHUB_OUTPUT": str(output), "GITHUB_RUN_ID": "fixture",
                       "GITHUB_RUN_ATTEMPT": "1", "GITHUB_JOB": "test"}.items():
        monkeypatch.setenv(key, value)
    receipt = root / ".codex_tmp/ci-opt/scope.json"
    monkeypatch.setattr(scope, "ROOT", root)
    monkeypatch.setattr(sys, "argv", ["scope", "--output", str(receipt)])
    scope.main()
    monkeypatch.setattr(ci_docs_check, "ROOT", root)
    monkeypatch.setattr(sys, "argv", ["docs", "--receipt", str(receipt)])
    ci_docs_check.main()
    plan = plans()
    target = root / ".github/ci-opt-steps.json"
    target.write_text(json.dumps(plan))
    outcomes = {key: {"outcome": "skipped"} for key in plan["ci.yml"]["test"]["all"]}
    outcomes["ci_scope"] = {"outcome": "success"}
    monkeypatch.setenv("CI_OPT_STEPS", json.dumps(outcomes))
    monkeypatch.setenv("CI_OPT_STATUS", "success")
    monkeypatch.setattr(ci_status_summary, "ROOT", root)
    monkeypatch.setattr(sys, "argv", ["result", "job", "--workflow", "ci.yml", "--job", "test"])
    ci_status_summary.main()
    result = json.loads((receipt.parent / "result.json").read_text())
    assert result["status"] == "DOC_CHECKS_PASS" and result["full_regression"] == "NOT_RUN"
    assert not result["performance_eligible"] and "verified=true" in output.read_text()
    assert not (root / ".codex_tmp/a421").exists()


def test_T11_only_reviewed_test_functions_changed_and_no_original_test_removed():
    allowed = {
        "tests/unit/test_a4_ci_governance.py": {
            "test_only_reviewed_job_conditions_change_from_ci_1_0",
            "test_inventory_covers_every_workflow_and_no_hidden_trigger_chain",
        },
        "tests/unit/test_a42331_ci_evidence.py": {
            "test_only_exact_reviewed_test_job_changes_and_every_gate_stays_frozen",
            "test_skipped_optional_uploads_are_guarded_and_mandatory_evidence_not_optional",
        },
        "tests/unit/test_a4233_background_observer.py": {
            "test_frozen_baseline_bytes_and_old_workflows_unchanged",
        },
        "tests/unit/test_a42341_environment_guard.py": {
            "test_AT20_exact_ci_additions_no_other_workflow_or_old_step_change",
        },
        "tests/unit/test_business_source_contract.py": {
            "test_exact_function_compatibility_keeps_negative_cases_signatures_and_assertions",
        },
    }
    for path, exceptions in allowed.items():
        original = ast.parse(git(ROOT, "show", f"{BASELINE}:{path}").decode("utf-8"))
        current = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        old = {n.name: ast.dump(n) for n in original.body if isinstance(n, ast.FunctionDef)}
        new = {n.name: ast.dump(n) for n in current.body if isinstance(n, ast.FunctionDef)}
        assert old.keys() == new.keys()
        assert {n for n in old if old[n] != new[n]} == exceptions


def test_T11_legacy_test_projection_preserves_the_original_business_verifier():
    from scripts.business_source_contract import BASELINE as business_baseline
    from scripts.business_source_contract import TEST_ADAPTATIONS, verify_test_adaptation
    from scripts.ci_opt_contract import restore_environment_guard_test

    path = "tests/unit/test_a42341_environment_guard.py"
    raw = (ROOT / path).read_bytes()
    old = git(ROOT, "show", f"{business_baseline}:{path}")
    with pytest.raises(ValueError, match="BUSINESS_UNREVIEWED_TEST_CHANGE"):
        verify_test_adaptation(old, raw, TEST_ADAPTATIONS[path])
    restored = restore_environment_guard_test(raw)
    assert restored == git(ROOT, "show", f"{BASELINE}:{path}")
    verify_test_adaptation(old, restored, TEST_ADAPTATIONS[path])


@pytest.mark.parametrize("damage", ["assertion", "outside", "unregistered_body"])
def test_T11_legacy_test_projection_refuses_any_extra_edit(damage):
    from scripts.ci_opt_contract import restore_environment_guard_test

    raw = (ROOT / "tests/unit/test_a42341_environment_guard.py").read_bytes()
    if damage == "assertion":
        raw = raw.replace(b"assert actual == c.git(", b"assert True or actual == c.git(", 1)
    elif damage == "outside":
        raw += b"\n# not a registered change\n"
    else:
        raw = raw.replace(
            b"            restore(name, yaml.safe_load(actual))", b"            pass", 1,
        )
    with pytest.raises(ValueError, match="CI_OPT_UNREVIEWED_TEST_SOURCE_CHANGE"):
        restore_environment_guard_test(raw)


def test_T12_baseline_evidence_not_candidate_performance_and_single_revert_documented():
    document = (ROOT / "docs/tasks/CI-OPT-01.md").read_text(encoding="utf-8")
    assert BASELINE in document and "41571974306" in document
    assert "git revert" in document and "BIZ-PERF-03-A-R1" in document
    assert "PARTIAL" in document and "DEFERRED" in document
