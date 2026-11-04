"""Validate the intentionally narrow prose route; never execute Markdown examples."""

import argparse
import json
import os
from pathlib import Path

from scripts.ci_change_scope import POLICY, ROOT, SCHEMA, blob, prose_projection

JSON_INPUTS = frozenset((
    ".github/ci-opt-policy.json", ".github/ci-opt-steps.json",
    "docs/acceptance/biz_perf_03_a_r1/verification.json",
))


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("CI_OPT_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def check_metadata(root, receipt):
    checked = 0
    for change in receipt.get("changed_files", []):
        path = change["path"]
        if path not in JSON_INPUTS or change["status"] == "D":
            continue
        data = json.loads(blob(root, receipt["comparison_head"], path),
                          object_pairs_hook=unique_object)
        if not isinstance(data, dict):
            raise ValueError("CI_OPT_JSON_OBJECT_REQUIRED")
        checked += 1
    return checked


def validate(root, receipt, policy, env):
    if (receipt.get("schema_version") != SCHEMA or receipt.get("scope") != "docs"
            or receipt.get("head_sha") != env.get("GITHUB_SHA")
            or receipt.get("run_id") != env.get("GITHUB_RUN_ID", "local")
            or receipt.get("attempt") != env.get("GITHUB_RUN_ATTEMPT", "1")
            or receipt.get("job") != env.get("GITHUB_JOB", "local")
            or receipt.get("event") not in {"push", "pull_request"}
            or receipt.get("reason") != "REGISTERED_PROSE_ONLY"
            or receipt.get("performance_eligible") is not False
            or receipt.get("production_read_authorized") is not False):
        raise ValueError("CI_OPT_DOC_IDENTITY")
    changes = receipt["changed_files"]
    if not changes:
        raise ValueError("CI_OPT_EMPTY_DOC_CHECK")
    for change in changes:
        path = change["path"]
        if change["status"] != "M" or path not in policy["prose_block_files"]:
            raise ValueError("CI_OPT_UNREGISTERED_DOC")
        old = blob(root, receipt["base_sha"], path)
        new = blob(root, receipt["comparison_head"], path)
        if prose_projection(old, policy) != prose_projection(new, policy):
            raise ValueError("CI_OPT_CHANGED_CONTRACT")
        # Outside-block links, code examples and JSON are byte-identical to the
        # validated baseline. Inside the block those constructs are forbidden.
        if "\ufffd" in new or any(line.rstrip() != line for line in new.splitlines()):
            raise ValueError("CI_OPT_DOC_TEXT")
    return {"checked_files": len(changes), "status": "DOC_CHECKS_PASS",
            "full_regression": "NOT_RUN", "performance_eligible": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    count = check_metadata(ROOT, receipt)
    result = {"status": "STATIC_CHECKS_PASS", "checked_json": count}
    if receipt["scope"] == "docs":
        result = validate(ROOT, receipt, json.loads(POLICY.read_text(encoding="utf-8")), os.environ)
        result["checked_json"] = count
    (args.receipt.parent / "docs.json").write_text(json.dumps(result, indent=2) + "\n")
    print("CI-OPT-01: " + result["status"])


if __name__ == "__main__":
    main()
