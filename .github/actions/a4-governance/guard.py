"""Actions-only governance. No application/config/database imports or release credentials."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

POLICY = Path(__file__).with_name("policy.json")
RECEIPT = Path(".codex_tmp/a4-ci/receipt.json")


def require(value, code):
    if not value:
        raise ValueError(code)


def git(*args):
    return subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def validate(env, inputs, policy, suite):
    require(env.get("GITHUB_EVENT_NAME") == "workflow_dispatch", "GOV_DISPATCH_REQUIRED")
    require(inputs.get("confirm_expensive_run") is True, "GOV_CONFIRMATION_REQUIRED")
    target = inputs.get("target_sha", "")
    require(
        isinstance(target, str) and re.fullmatch(r"[0-9a-f]{40}", target), "GOV_FULL_SHA_REQUIRED"
    )
    require(target == env.get("GITHUB_SHA"), "GOV_SHA_MISMATCH")
    require(env.get("GITHUB_REF") == "refs/heads/master", "GOV_MASTER_REQUIRED")
    require(env.get("GITHUB_RUN_ATTEMPT") == "1", "GOV_RERUN_REFUSED")
    require(env.get("GITHUB_REPOSITORY") == policy["repository"], "GOV_REPOSITORY_MISMATCH")
    require(
        env.get("A4_REVIEW_POLICY_ACK") == "a4-ci-1.0-reviewed", "GOV_ADMIN_CONFIGURATION_REQUIRED"
    )
    reason = inputs.get("run_reason")
    require(isinstance(reason, str) and 0 < len(reason.strip()) <= 1000, "GOV_REASON_REQUIRED")
    profile = policy["profiles"].get(suite)
    require(profile and profile["workflow"] == env.get("GITHUB_WORKFLOW"), "GOV_SUITE_MISMATCH")
    require(inputs.get("experiment", suite) == suite, "GOV_SUITE_MISMATCH")
    require(inputs.get("protocol_id") == profile["protocol_id"], "GOV_PROTOCOL_ID_MISMATCH")
    require(
        inputs.get("protocol_sha256") == profile["protocol_sha256"], "GOV_PROTOCOL_HASH_MISMATCH"
    )
    if profile.get("once"):
        # These historical protocols are closed, not a reusable token service.
        require(not profile.get("consumed_run_ids"), "GOV_ONE_SHOT_ID_CONSUMED")
        raise ValueError("GOV_NEW_ONE_SHOT_REQUIRES_SEPARATE_REVIEW")
    return profile


def authorize(env, inputs, policy, suite):
    profile = validate(env, inputs, policy, suite)
    require(
        git("rev-parse", "HEAD").decode().strip() == inputs["target_sha"], "GOV_CHECKOUT_MISMATCH"
    )
    require(not git("status", "--porcelain", "--untracked-files=all").strip(), "GOV_DIRTY_CHECKOUT")
    git("merge-base", "--is-ancestor", policy["baseline_sha"], "HEAD")
    require(
        not git("diff", policy["baseline_sha"], "HEAD", "--", *policy["frozen_paths"]).strip(),
        "GOV_FROZEN_PRODUCTION_CHANGED",
    )
    hashes = {}
    for path, expected in (
        (profile["protocol"], profile["protocol_sha256"]),
        (profile["source"], profile["source_sha256"]),
        ("backend/app/services/data_publication.py", policy["production_source_sha256"]),
    ):
        # Hash canonical committed bytes, not the workstation's CRLF conversion.
        hashes[path] = sha(git("show", "HEAD:" + path))
        require(hashes[path] == expected, "GOV_FROZEN_SOURCE_OR_PROTOCOL_CHANGED")
    for path in policy["frozen_evidence_inputs"]:
        hashes[path] = sha(git("show", "HEAD:" + path))
        require(
            hashes[path] == sha(git("show", policy["baseline_sha"] + ":" + path)),
            "GOV_DATASET_OR_MEASUREMENT_CONTRACT_CHANGED",
        )
    model_args = ("backend/app/models", "migrations", "config")
    model_hash = sha(git("ls-tree", "-r", "HEAD", *model_args))
    require(
        model_hash == sha(git("ls-tree", "-r", policy["baseline_sha"], *model_args)),
        "GOV_MODEL_IDENTITY_CHANGED",
    )
    return {
        "suite": suite,
        "protocol_id": profile["protocol_id"],
        "source_hashes": hashes,
        "model_hash": model_hash,
        "protocol_sha256": profile["protocol_sha256"],
        "run_reason_sha256": sha(inputs["run_reason"].strip().encode()),
        "status": "AUTHORIZED_FOR_SPECIFIED_DIAGNOSTIC_ONLY",
    }


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, path)


def header(env):
    policy = POLICY.read_bytes()
    return {
        "schema_version": "a4-ci-governance-v1",
        "evidence_kind": "GOVERNANCE_ONLY",
        "head_sha": env.get("GITHUB_SHA"),
        "run_id": env.get("GITHUB_RUN_ID"),
        "attempt": env.get("GITHUB_RUN_ATTEMPT"),
        "job_id": env.get("GITHUB_JOB"),
        "policy_version": json.loads(policy)["version"],
        "policy_sha256": sha(policy),
        "governance_source_sha256": sha(Path(__file__).read_bytes()),
        "checked_at": datetime.now(UTC).isoformat(),
        "capacity_ready": False,
        "production_read_authorized": False,
        "formal_capacity_complete": False,
    }


def finalize(env, previous):
    outcome = env.get("A4_JOB_STATUS", "unknown")
    cleanup = env.get("A4_CLEANUP_OUTCOME", "not_required")
    matching = all(
        previous.get(key, env.get(name)) == env.get(name)
        for key, name in (
            ("head_sha", "GITHUB_SHA"),
            ("run_id", "GITHUB_RUN_ID"),
            ("attempt", "GITHUB_RUN_ATTEMPT"),
            ("job_id", "GITHUB_JOB"),
        )
    )
    return {
        **previous,
        **header(env),
        "job_status": outcome,
        "cleanup_outcome": cleanup,
        "status": "FINISHED"
        if matching and outcome == "success" and cleanup in ("success", "not_required")
        else "INCOMPLETE",
    }


def cleanup(env, run=subprocess.run):
    container = env.get("A4_CLEANUP_CONTAINER") or env.get("A421_CONTAINER")
    if not container:
        return "NOT_CREATED"
    require(
        all(env.get(name) for name in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB")),
        "GOV_CONTAINER_OWNERSHIP_MISMATCH",
    )
    require(
        re.fullmatch(r"a4-ci-[0-9]+-[0-9]+-[0-9a-f]{12}", container), "GOV_CONTAINER_NAME_REFUSED"
    )
    result = run(
        ["docker", "ps", "-a", "--filter", f"name=^/{container}$", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )
    require(result.returncode == 0, "GOV_CLEANUP_INSPECTION_FAILED")
    if not result.stdout.strip():
        return "NOT_CREATED"
    require(result.stdout.strip() == container, "GOV_CONTAINER_NAME_REFUSED")
    inspected = run(
        ["docker", "inspect", "--format", "{{json .Config.Labels}}", container],
        capture_output=True,
        text=True,
    )
    require(inspected.returncode == 0, "GOV_CLEANUP_INSPECTION_FAILED")
    labels = json.loads(inspected.stdout)
    require(
        labels.get("purpose") == "ssh-stock-a4-physical-test", "GOV_CONTAINER_OWNERSHIP_MISMATCH"
    )
    require(
        all(
            labels.get(key) == env.get(value)
            for key, value in (
                ("ssh-stock.run-id", "GITHUB_RUN_ID"),
                ("ssh-stock.attempt", "GITHUB_RUN_ATTEMPT"),
                ("ssh-stock.job", "GITHUB_JOB"),
            )
        ),
        "GOV_CONTAINER_OWNERSHIP_MISMATCH",
    )
    removed = run(["docker", "rm", "-f", container], capture_output=True, text=True)
    require(removed.returncode == 0, "GOV_CONTAINER_CLEANUP_FAILED")
    return "REMOVED_OWNED_CONTAINER"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("authorize", "finish", "cleanup"))
    parser.add_argument("--suite")
    args = parser.parse_args()
    env = os.environ
    try:
        if args.mode == "cleanup":
            print(cleanup(env))
            return
        if args.mode == "finish":
            previous = json.loads(RECEIPT.read_text()) if RECEIPT.exists() else {}
            atomic(RECEIPT, finalize(env, previous))
            return
        event = json.loads(Path(env["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        require(
            isinstance(event, dict) and isinstance(event.get("inputs", {}), dict),
            "GOV_EVENT_SCHEMA_INVALID",
        )
        # Dispatch event strings are decoded by the service; booleans in REST
        # payloads can arrive as strings. Only the exact true representation is accepted.
        inputs = dict(event.get("inputs") or {})
        if inputs.get("confirm_expensive_run") == "true":
            inputs["confirm_expensive_run"] = True
        atomic(
            RECEIPT,
            {**header(env), **authorize(env, inputs, json.loads(POLICY.read_text()), args.suite)},
        )
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        code = (
            str(error)
            if isinstance(error, ValueError) and re.fullmatch(r"GOV_[A-Z_]+", str(error))
            else "GOV_VALIDATION_OR_CLEANUP_FAILED"
        )
        previous = json.loads(RECEIPT.read_text()) if RECEIPT.exists() else {}
        current = finalize({**env, "A4_JOB_STATUS": "failure"}, previous)
        current.update(
            status="INCOMPLETE",
            failure_code=code,
            first_failure=previous.get("first_failure", code),
            terminal_failure=code,
        )
        atomic(RECEIPT, current)
        raise SystemExit(code) from None


if __name__ == "__main__":
    main()
