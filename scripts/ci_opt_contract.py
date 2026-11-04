"""Versioned CI topology projection; no capacity or execution authority."""

import copy
import json
import subprocess
from functools import lru_cache
from pathlib import Path

BASELINE = "e697fc80a098726f4e73f04ac71f5eb6cfb62b03"
ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "ci.yml": ("test", "lookup-diagnosis"),
    "ab-read-a4-baseline.yml": ("contracts",),
    "ab-read-a4-2.yml": ("contract-and-safety",),
    "publication-v13.yml": ("contracts",),
}
FULL = "steps.ci_scope.outputs.scope != 'docs'"


@lru_cache(maxsize=4)
def baseline_bytes(name):
    return subprocess.check_output(
        ["git", "show", f"{BASELINE}:.github/workflows/{name}"], cwd=ROOT,
    )


def baseline(name):
    import yaml

    # Cache only immutable historical Git bytes, never a mutable parsed contract.
    return yaml.safe_load(baseline_bytes(name))


def guarded(expression=None):
    if expression is None:
        return FULL
    expression = expression.removeprefix("${{").removesuffix("}}").strip()
    return "${{ (" + FULL + ") && (" + expression + ") }}"


def scope_step():
    return {"name": "Classify changes and validate registered prose", "id": "ci_scope",
            "uses": "./.github/actions/ci-scope"}


def result_step(name, job):
    return {
        "name": "Verify the actual route and mandatory step outcomes", "id": "ci_result",
        "if": "always()",
        "env": {"CI_OPT_STEPS": "${{ toJSON(steps) }}", "CI_OPT_STATUS": "${{ job.status }}"},
        "run": f"python -m scripts.ci_status_summary job --workflow {name} --job {job}",
    }


def artifact_step():
    return {
        "name": "Upload CI routing evidence, never a performance receipt",
        "uses": "actions/upload-artifact@v4", "if": "always()",
        "with": {
            "name": ("ci-opt-01-${{ github.job }}-${{ github.sha }}-"
                     "${{ github.run_id }}-${{ github.run_attempt }}"),
            "path": ".codex_tmp/ci-opt", "include-hidden-files": True,
            "if-no-files-found": "error",
        },
    }


def transformed_job(name, key, original):
    job = copy.deepcopy(original)
    old = job["steps"]
    if old[0].get("uses") != "actions/checkout@v4":
        raise ValueError("CI_OPT_CHECKOUT_CONTRACT")
    steps = [old[0], scope_step()]
    for i, step in enumerate(old[1:], 1):
        step.setdefault("id", f"ci_full_{i:02d}")
        step["if"] = guarded(step.get("if"))
        steps.append(step)
    steps.extend((result_step(name, key), artifact_step()))
    job["steps"] = steps
    job.setdefault("outputs", {}).update(
        ci_opt_verified="${{ steps.ci_result.outputs.verified }}",
        ci_opt_scope="${{ steps.ci_scope.outputs.scope }}",
        ci_opt_head="${{ steps.ci_result.outputs.head_sha }}",
    )
    return job


def summary_job(name):
    needs = (["workflow-contracts", "dependency-audit", "lookup-diagnosis", "test"]
             if name == "ci.yml" else list(TARGETS[name]))
    return {
        "name": "ci-opt-01-" + name.removesuffix(".yml"),
        "if": "always()", "needs": needs, "runs-on": "ubuntu-latest", "timeout-minutes": 5,
        "steps": [
            {"uses": "actions/checkout@v4", "with": {"fetch-depth": 0}},
            {"name": "Reject missing, skipped, cancelled or failed mandatory checks",
             "env": {"CI_OPT_NEEDS": "${{ toJSON(needs) }}"},
             "run": f"python -m scripts.ci_status_summary workflow --workflow {name}"},
        ],
    }


def transform(name, original):
    value = copy.deepcopy(original)
    if name not in TARGETS:
        return value
    for key in TARGETS[name]:
        value["jobs"][key] = transformed_job(name, key, value["jobs"][key])
    if name == "ci.yml":
        step = value["jobs"]["workflow-contracts"]["steps"][3]
        step["run"] = step["run"].replace(
            "tests/unit/test_a4_ci_governance.py -q",
            "tests/unit/test_a4_ci_governance.py tests/unit/test_ci_opt_01.py "
            "tests/unit/test_a4233_background_observer.py "
            "tests/unit/test_a42341_environment_guard.py::"
            "test_AT20_exact_ci_additions_no_other_workflow_or_old_step_change "
            "tests/unit/test_business_source_contract.py -q",
        )
    value["jobs"]["ci-summary"] = summary_job(name)
    if name == "ci.yml":
        from scripts.ci_opt_02_topology import project
        value = project(value)
    return value


def restore(name, current):
    """Accept only the complete reviewed transformation, not an arbitrary new digest."""
    old = baseline(name)
    if current != transform(name, old):
        raise ValueError("CI_OPT_UNREVIEWED_WORKFLOW_CHANGE")
    return old


def restore_test_job(current):
    old = baseline("ci.yml")["jobs"]["test"]
    from scripts.ci_opt_02_topology import project_test
    if current != project_test(transformed_job("ci.yml", "test", old)):
        raise ValueError("CI_OPT_UNREVIEWED_TEST_JOB")
    return old


@lru_cache(maxsize=1)
def environment_guard_test_baseline():
    return subprocess.check_output(
        ["git", "show", f"{BASELINE}:tests/unit/test_a42341_environment_guard.py"],
        cwd=ROOT,
    )


def restore_environment_guard_test(current):
    """Project only the exact CI-OPT AT20 edit for the older test-body contract.

    This is static test compatibility, never a source identity or execution grant.
    The original business verifier and its negative cases remain unchanged.
    """
    before = environment_guard_test_baseline()
    old = (
        b"    for name in ('ci.yml', 'ab-read-a4-baseline.yml', 'ab-read-a4-2.yml',\n"
        b"                 'publication-v13.yml', 'a4232-statistics-tail-diagnostic.yml'):\n"
        b"        assert (ROOT / '.github/workflows' / name).read_bytes() == c.git(\n"
    )
    new = (
        b"    from scripts.ci_opt_contract import TARGETS, baseline_bytes, restore\n\n"
        b"    for name in ('ci.yml', 'ab-read-a4-baseline.yml', 'ab-read-a4-2.yml',\n"
        b"                 'publication-v13.yml', 'a4232-statistics-tail-diagnostic.yml'):\n"
        b"        actual = (ROOT / '.github/workflows' / name).read_bytes()\n"
        b"        if name in TARGETS:\n"
        b"            restore(name, yaml.safe_load(actual))\n"
        b"            actual = baseline_bytes(name)\n"
        b"        assert actual == c.git(\n"
    )
    if before.count(old) != 1 or current.replace(b"\r\n", b"\n") != before.replace(old, new, 1):
        raise ValueError("CI_OPT_UNREVIEWED_TEST_SOURCE_CHANGE")
    return before


def plans():
    result = {}
    for name, keys in TARGETS.items():
        jobs = baseline(name)["jobs"]
        result[name] = {}
        for key in keys:
            steps = jobs[key]["steps"][1:]
            result[name][key] = {
                "all": [s.get("id", f"ci_full_{i:02d}") for i, s in enumerate(steps, 1)],
                "mandatory": [s.get("id", f"ci_full_{i:02d}")
                              for i, s in enumerate(steps, 1)
                              if s.get("if", "always()") == "always()"],
            }
    result["ci.yml"]["test"]["all"].append("python_artifacts")
    result["ci.yml"]["test"]["mandatory"].append("python_artifacts")
    return result


def write_plans(path):
    Path(path).write_text(json.dumps(plans(), indent=2) + "\n", encoding="utf-8")
