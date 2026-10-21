"""Exact-SHA always-run gate. Missing/cancelled/partial evidence is a failure."""

import argparse
import json
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.a42_artifacts import atomic, header, isolation, model_hash, now  # noqa: E402
from scripts.a42_gate_io import validate_lab  # noqa: E402
from scripts.a42_receipt_contract import (  # noqa: E402
    identity,
    merge_capacity,
    physical,
    report,
    require,
    require_jobs,
)


def junit(path):
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    require(bool(cases) and not any(c.find(tag) is not None for c in cases
            for tag in ("failure", "error", "skipped")), "SAFETY_JUNIT_INCOMPLETE")
    return len(cases)


def status(directory, job, *, core=False, safety=False):
    directory = Path(directory)
    value = dict(**header(job), status="INCOMPLETE", finished_at=now(),
                 workflow_job_status=os.environ.get("UPSTREAM_STATUS", "unknown"))
    if core:
        files = [".codex_tmp/data-queue-containers.json",
            "frontend/coverage/runtime-reliability-browser/result.json",
            ".codex_tmp/data-publication-targeted.xml", ".codex_tmp/m17_1_2-full.xml",
            ".codex_tmp/cold-start-targeted.xml", ".codex_tmp/cold-start-comparison.json"]
        for name in files:
            source = ROOT/name
            if source.is_file():
                target = directory/name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        value["expected_files"] = files
        if (value["workflow_job_status"] == "success"
                and all((directory/p).is_file() for p in files)):
            value["status"] = "COMPLETE"
    elif safety and value["workflow_job_status"] == "success":
        value.update(isolation())
        value["testcases"] = junit(directory/"a42-targeted.xml")
        value["status"] = "COMPLETE"
    atomic(directory/"status.json", value)


def gate(args):
    head = os.environ["GITHUB_SHA"]
    attempt = os.environ["GITHUB_RUN_ATTEMPT"]
    needs = json.loads(os.environ["A421_NEEDS"])
    needs = {key:value["result"] for key,value in needs.items()}
    result = {**header("release-"+args.mode), "status":"INCOMPLETE", "finished_at":now(),
              **report(successful=False)}
    try:
        if args.mode == "lab":
            require_jobs(needs, {"contract-and-safety", "laboratory"})
            safety_files = list(args.input.rglob("contract/status.json"))
            require(len(safety_files) == 1, "SAFETY_ARTIFACT_MISSING")
            safety = json.loads(safety_files[0].read_text())
            identity(safety, head=head, attempt=attempt, job_id="contract-and-safety")
            physical(safety)
            require(safety.get("status") == "COMPLETE" and not safety["working_tree_dirty"]
                    and safety["model_hash"] == model_hash()
                    and safety.get("run_id") == os.environ["GITHUB_RUN_ID"], "SAFETY_INCOMPLETE")
            result["safety_testcases"] = junit(safety_files[0].parent/"a42-targeted.xml")
            result["matrix"] = validate_lab(args.input, head=head, attempt=attempt,
                                           model_hash=model_hash(), needs=needs)
            for path in args.input.rglob("manifest.json"):
                require(json.loads(path.read_text()).get("run_id") == os.environ["GITHUB_RUN_ID"],
                        "MANIFEST_RUN_MISMATCH")
        else:
            require_jobs(needs, {"test", "capacity"})
            core_files = list(args.input.rglob("core/status.json"))
            require(len(core_files) == 1, "CORE_ARTIFACT_MISSING")
            core = json.loads(core_files[0].read_text())
            identity(core, head=head, attempt=attempt, job_id="core")
            require(core.get("status") == "COMPLETE" and not core["working_tree_dirty"]
                    and core["model_hash"] == model_hash()
                    and core.get("run_id") == os.environ["GITHUB_RUN_ID"], "CORE_INCOMPLETE")
            files = list(args.input.rglob("capacity.json"))
            receipts = [json.loads(p.read_text()) for p in files]
            require(all(r.get("run_id") == os.environ["GITHUB_RUN_ID"] for r in receipts),
                    "CAPACITY_RUN_MISMATCH")
            capacity = merge_capacity(receipts,
                                      head=head, attempt=attempt, model_hash=model_hash())
            atomic(args.output.parent/"cold-start-capacity.json", capacity)
            from scripts.publication_release_checks_v14_a4_2_1 import validate

            result["publication"] = validate(core_files[0].parent, capacity, head)
        result.update(report(successful=True), status="COMPLETE")
    except BaseException as error:
        result.update(report(successful=False, errors=[str(error) if isinstance(error, ValueError)
            else type(error).__name__]), failure_type=type(error).__name__)
        atomic(args.output, result)
        raise SystemExit(1) from None
    atomic(args.output, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=(
        "lab", "publication", "status", "core-status", "safety-status"))
    parser.add_argument("--input", type=Path, default=Path(".codex_tmp/a421-input"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--job-id", default="unknown")
    args = parser.parse_args()
    if args.mode.endswith("status"):
        status(args.output, args.job_id,
               core=args.mode=="core-status", safety=args.mode=="safety-status")
    else:
        gate(args)


if __name__ == "__main__":
    main()
