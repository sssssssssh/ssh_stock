"""Exact B0 topology projection. B1 remains disabled pending physical evidence."""

import copy

AGGREGATE = (
    "python -m scripts.ci_test_shards aggregate --cov-fail-under=70 -p scripts.a42331_pytest_safety"
)


def project_test(job):
    value = copy.deepcopy(job)
    value["needs"] = ["python-scope", "python-tests"]
    value["if"] = "always()"
    steps = value["steps"]
    index = next(i for i, s in enumerate(steps) if s.get("id") == "full_tests")
    steps[index]["run"] = AGGREGATE
    steps.insert(
        index,
        {
            "name": "Download exact-run Python shard evidence",
            "id": "python_artifacts",
            "if": "steps.ci_scope.outputs.scope != 'docs'",
            "uses": "actions/download-artifact@v4",
            "with": {
                "pattern": (
                    "ci-opt-02-*-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}"
                ),
                "path": ".codex_tmp/shard-input",
            },
        },
    )
    return value


def shard_job(test):
    # Fresh GitHub VM and PG service for each matrix member, never shared DBs.
    steps = copy.deepcopy(test["steps"][:6])
    # through original V14 physical-instance provisioning, before targeted tests
    assert steps[-1].get("id") == "ci_full_04"
    full = "steps.ci_scope.outputs.scope != 'docs'"
    steps += [
        {
            "name": "Formal parent schema for sensitive shard",
            "if": full + " && matrix.shard == 'serial'",
            "run": "python -m alembic upgrade head",
        },
        {
            "name": "Execute exact shard with safety and independent coverage",
            "if": full,
            "run": 'python -m scripts.ci_test_shards run --shard "${{ matrix.shard }}"',
        },
        {
            "name": "Preserve shard evidence even on failure",
            "if": "${{ always() && (" + full + ") }}",
            "uses": "actions/upload-artifact@v4",
            "with": {
                "name": (
                    "ci-opt-02-${{ matrix.shard }}-${{ github.sha }}-"
                    "${{ github.run_id }}-${{ github.run_attempt }}"
                ),
                "path": ".codex_tmp/ci-shards/${{ matrix.shard }}",
                "include-hidden-files": True,
                "if-no-files-found": "error",
            },
        },
        {
            "id": "cleanup",
            "if": "${{ always() && (" + full + ") }}",
            "uses": "./.github/actions/a4-cleanup",
            "with": {"container": "${{ env.V14_CONTAINER }}"},
        },
    ]
    return {
        "needs": ["python-scope"],
        "if": "needs.python-scope.outputs.scope != 'docs'",
        "runs-on": test["runs-on"],
        "timeout-minutes": 90,
        "strategy": {
            "fail-fast": False,
            "max-parallel": 2,
            "matrix": {"shard": ["pilot", "serial"]},
        },
        "services": copy.deepcopy(test["services"]),
        "env": copy.deepcopy(test["env"]),
        "steps": steps,
    }


def project(value):
    result = copy.deepcopy(value)
    old = result["jobs"]["test"]
    result["jobs"]["python-tests"] = shard_job(old)
    result["jobs"]["test"] = project_test(old)
    result["jobs"]["ci-summary"]["needs"].extend(["python-scope", "python-tests"])
    result["jobs"]["python-scope"] = {
        "runs-on": "ubuntu-latest",
        "timeout-minutes": 5,
        "outputs": {"scope": "${{ steps.classify.outputs.scope }}", "head": "${{ github.sha }}"},
        "steps": [
            {"uses": "actions/checkout@v4", "with": {"fetch-depth": 0}},
            {"id": "classify", "uses": "./.github/actions/ci-scope"},
        ],
    }
    return result
