"""Conservative Git-only CI routing. Never imports application or database settings."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / ".github/ci-opt-policy.json"
SHA = re.compile(r"[0-9a-f]{40}")
SCHEMA = "ci-opt-01.scope.v1"


class ComparisonError(ValueError):
    pass


def git(root, *args):
    return subprocess.check_output(
        ["git", *args], cwd=root, stderr=subprocess.DEVNULL, timeout=30,
    )


def checked_sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value) or value == "0" * 40:
        raise ComparisonError("INVALID_COMPARISON_SHA")
    return value


def blob(root, revision, path):
    entry = git(root, "ls-tree", "-z", revision, "--", path)
    if not entry.startswith(b"100644 blob ") or entry.count(b"\0") != 1:
        raise ComparisonError("NOT_ORDINARY_FILE")
    return git(root, "show", f"{revision}:{path}").decode("utf-8")


def prose_projection(text, policy):
    """Only an explicitly non-contract prose block may change; all other bytes stay fixed."""
    start, end = policy["block_start"], policy["block_end"]
    if text.count(start) != 1 or text.count(end) != 1:
        raise ComparisonError("UNREGISTERED_PROSE_BLOCK")
    prefix, content = text.split(start)
    prose, suffix = content.split(end)
    if not prose.startswith("\n") or not prose.endswith("\n"):
        raise ComparisonError("INVALID_PROSE_BOUNDARY")
    # No directives, links, headings, executable examples, HTML or contract identities.
    if not re.fullmatch(r"[\w\s，。！？、；：‘’“”（）《》…,.!?:;()\-]*", prose):
        raise ComparisonError("NON_PROSE_CONTENT")
    if re.search(
        r"(?i)\b(?:PASS|DONE|SHA|SQL|PIT|ACK|TOKEN|PASSWORD|FULL|pytest|docker|"
        r"python|alembic|http|true|false)\b|授权|审批|门禁|阈值|策略|公式|权限|"
        r"生产|金融|身份|验收|哈希|收益|配置|命令|密钥|口令|密码|[0-9]{3,}", prose,
    ):
        raise ComparisonError("CONTRACT_CONTENT")
    return prefix + start + end + suffix


def classify(root, event_name, event, env, policy=None):
    """Unknown comparisons and every non-allowlisted modification require full CI."""
    root = Path(root)
    result = {
        "schema_version": SCHEMA, "scope": "full", "reason": "CONSERVATIVE_DEFAULT",
        "head_sha": env.get("GITHUB_SHA", ""), "event": event_name,
        "run_id": env.get("GITHUB_RUN_ID", "local"),
        "attempt": env.get("GITHUB_RUN_ATTEMPT", "1"),
        "job": env.get("GITHUB_JOB", "local"), "changed_files": [],
        "performance_eligible": False, "production_read_authorized": False,
    }
    try:
        if event_name not in {"push", "pull_request"}:
            raise ComparisonError("MANUAL_OR_UNKNOWN_EVENT_FULL")
        head = checked_sha(env.get("GITHUB_SHA"))
        if git(root, "rev-parse", "HEAD").decode().strip() != head:
            raise ComparisonError("CHECKOUT_IDENTITY_MISMATCH")
        if event_name == "push":
            if env.get("GITHUB_REF") != "refs/heads/master" or event.get("forced"):
                raise ComparisonError("NONMASTER_OR_FORCED_PUSH")
            before, after = checked_sha(event.get("before")), checked_sha(event.get("after"))
            if after != head:
                raise ComparisonError("PUSH_IDENTITY_MISMATCH")
            git(root, "merge-base", "--is-ancestor", before, after)
            base = before
        else:
            pr = event["pull_request"]
            before, after = checked_sha(pr["base"]["sha"]), checked_sha(pr["head"]["sha"])
            # The checkout must be the PR head or its actual two-parent test merge.
            if head != after:
                parents = git(root, "show", "-s", "--format=%P", head).decode().split()
                if parents != [before, after]:
                    raise ComparisonError("PR_CHECKOUT_IDENTITY_MISMATCH")
            base = checked_sha(git(root, "merge-base", before, after).decode().strip())
        policy = policy or json.loads(POLICY.read_text(encoding="utf-8"))
        if policy.get("schema_version") != "ci-opt-01.policy.v1":
            raise ComparisonError("INVALID_POLICY")
        raw = git(root, "diff", "--name-status", "--no-renames", "-z", base, after, "--")
        fields = raw.split(b"\0")
        if fields[-1] != b"" or (len(fields) - 1) % 2:
            raise ComparisonError("INCOMPLETE_DIFF")
        changes = [(fields[i].decode("ascii"), fields[i + 1].decode("utf-8"))
                   for i in range(0, len(fields) - 1, 2)]
        result.update(base_sha=base, comparison_head=after,
                      changed_files=[{"status": s, "path": p} for s, p in changes])
        if not changes:
            raise ComparisonError("EMPTY_COMPARISON")
        names = [p.casefold() for _, p in changes]
        if len(names) != len(set(names)):
            raise ComparisonError("CASE_COLLISION")
        for status, path in changes:
            if (status != "M" or "\\" in path or PurePosixPath(path).is_absolute()
                    or ".." in PurePosixPath(path).parts or any(ord(c) < 32 for c in path)):
                raise ComparisonError("UNKNOWN_OR_NONMODIFICATION")
            if path in policy["protected_paths"] or path not in policy["prose_block_files"]:
                raise ComparisonError("CONTRACT_OR_UNKNOWN_PATH")
            old, new = blob(root, base, path), blob(root, after, path)
            if prose_projection(old, policy) != prose_projection(new, policy):
                raise ComparisonError("OUTSIDE_REGISTERED_PROSE")
        result.update(scope="docs", reason="REGISTERED_PROSE_ONLY")
    except (ComparisonError, KeyError, TypeError, UnicodeError, OSError,
            subprocess.SubprocessError, json.JSONDecodeError) as error:
        result["reason"] = str(error) if isinstance(error, ComparisonError) else "COMPARISON_FAILED"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    except (KeyError, OSError, ValueError):
        event = {}
    receipt = classify(ROOT, os.environ.get("GITHUB_EVENT_NAME", ""), event, os.environ)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=True, indent=2) + "\n", encoding="utf-8",
    )
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"scope={receipt['scope']}\n")
    print(f"CI-OPT-01: {receipt['scope']} ({receipt['reason']})")


if __name__ == "__main__":
    main()
