"""Fail-closed CI summaries. A prose check cannot issue full-suite or performance evidence."""

import argparse
import json
import os

from scripts.ci_change_scope import ROOT, SCHEMA
from scripts.ci_opt_contract import TARGETS


def verify_job(scope, outcomes, upstream, plan, env, docs=None):
    if (scope.get("schema_version") != SCHEMA or scope.get("scope") not in {"docs", "full"}
            or scope.get("head_sha") != env.get("GITHUB_SHA")
            or scope.get("run_id") != env.get("GITHUB_RUN_ID", "local")
            or scope.get("attempt") != env.get("GITHUB_RUN_ATTEMPT", "1")
            or scope.get("job") != env.get("GITHUB_JOB", "local")
            or upstream != "success" or outcomes.get("ci_scope", {}).get("outcome") != "success"):
        raise ValueError("CI_OPT_ROUTE_OR_UPSTREAM_FAILED")
    if scope["scope"] == "docs":
        if (not docs or docs.get("status") != "DOC_CHECKS_PASS"
                or docs.get("full_regression") != "NOT_RUN"
                or docs.get("checked_files") != len(scope["changed_files"])
                or any(outcomes.get(key, {}).get("outcome") != "skipped" for key in plan["all"])):
            raise ValueError("CI_OPT_DOC_ROUTE_FAILED")
        return "DOC_CHECKS_PASS"
    if any(outcomes.get(key, {}).get("outcome") != "success" for key in plan["mandatory"]):
        raise ValueError("CI_OPT_FULL_STEP_NOT_SUCCESS")
    return "FULL_JOB_CHECKS_PASS"


def verify_workflow(name, needs, env):
    required = (set(TARGETS[name]) | {"workflow-contracts", "dependency-audit"}
                if name == "ci.yml" else set(TARGETS[name]))
    if name == "ci.yml":
        required.update(("python-tests", "python-scope"))
    if name == "ci.yml" and set(needs) == required:
        routing = needs["python-scope"]
        if (routing.get("result") != "success"
                or routing.get("outputs", {}).get("head") != env.get("GITHUB_SHA")
                or routing.get("outputs", {}).get("scope") not in {"docs", "full"}):
            raise ValueError("CI_OPT_MISSING_ROUTE_PROOF")
        if routing["outputs"]["scope"] == "docs":
            if needs["python-tests"].get("result") != "skipped":
                raise ValueError("CI_OPT_DOC_SHARDS_EXECUTED")
            needs = {k: v for k, v in needs.items() if k != "python-tests"}
            required.remove("python-tests")
    if set(needs) != required or any(j.get("result") != "success" for j in needs.values()):
        raise ValueError("CI_OPT_MANDATORY_JOB_NOT_SUCCESS")
    scopes = set()
    for job in TARGETS[name]:
        outputs = needs[job].get("outputs", {})
        if (outputs.get("ci_opt_verified") != "true"
                or outputs.get("ci_opt_head") != env.get("GITHUB_SHA")
                or outputs.get("ci_opt_scope") not in {"docs", "full"}):
            raise ValueError("CI_OPT_MISSING_ROUTE_PROOF")
        scopes.add(outputs["ci_opt_scope"])
    if name == "ci.yml" and scopes != {routing["outputs"]["scope"]}:
        raise ValueError("CI_OPT_INCONSISTENT_ROUTES")
    if len(scopes) != 1:
        raise ValueError("CI_OPT_INCONSISTENT_ROUTES")
    return next(iter(scopes))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("job", "workflow"))
    parser.add_argument("--workflow", choices=tuple(TARGETS), required=True)
    parser.add_argument("--job")
    args = parser.parse_args()
    output = ROOT / ".codex_tmp/ci-opt"
    output.mkdir(parents=True, exist_ok=True)
    result = {"schema_version": "ci-opt-01.result.v1", "status": "INCOMPLETE",
              "head_sha": os.environ.get("GITHUB_SHA"), "performance_eligible": False,
              "production_read_authorized": False, "full_regression": "NOT_VERIFIED"}
    try:
        if args.mode == "job":
            scope = json.loads((output / "scope.json").read_text(encoding="utf-8"))
            docs = (json.loads((output / "docs.json").read_text(encoding="utf-8"))
                    if (output / "docs.json").exists() else None)
            plans = json.loads((ROOT / ".github/ci-opt-steps.json").read_text(encoding="utf-8"))
            result["status"] = verify_job(
                scope, json.loads(os.environ["CI_OPT_STEPS"]), os.environ["CI_OPT_STATUS"],
                plans[args.workflow][args.job], os.environ, docs,
            )
            result["full_regression"] = (
                "NOT_RUN" if scope["scope"] == "docs" else
                "PASS" if args.workflow == "ci.yml" and args.job == "test" else "NOT_THIS_JOB"
            )
        else:
            mode = verify_workflow(
                args.workflow, json.loads(os.environ["CI_OPT_NEEDS"]), os.environ,
            )
            result.update(
                status="DOC_CHECKS_PASS" if mode == "docs" else "FULL_JOB_CHECKS_PASS",
                full_regression=("NOT_RUN" if mode == "docs" else
                                 "PASS" if args.workflow == "ci.yml" else "NOT_THIS_WORKFLOW"),
            )
    except (ValueError, KeyError, TypeError, OSError):
        result["failure_code"] = "CI_OPT_INCOMPLETE_OR_FAILED"
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("CI-OPT-01: " + result["status"] + "; full regression " + result["full_regression"])
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(f"\nCI-OPT-01: **{result['status']}**; "
                         f"full regression: **{result['full_regression']}**. "
                         "No performance or production authorization.\n")
    if result["status"] == "INCOMPLETE":
        raise SystemExit(1)
    if receipt := os.environ.get("GITHUB_OUTPUT"):
        with open(receipt, "a", encoding="utf-8") as stream:
            stream.write(f"verified=true\nhead_sha={result['head_sha']}\n")


if __name__ == "__main__":
    main()
