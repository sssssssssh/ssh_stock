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


def lookup_receipt(directory, head, attempt):
    import hashlib

    from scripts.publication_lookup_diagnostic_a422 import (
        BASELINE,
        CONTROL_REPEATS,
        TABLES,
        VARIANTS,
        candidate_source,
        performance_decision,
        summarize,
        whole_workloads,
    )

    paths = list(directory.rglob('lookup/lookup.json'))
    require(len(paths) == 1, 'LOOKUP_ARTIFACT_MISSING')
    receipt = json.loads(paths[0].read_text())
    identity(receipt, head=head, attempt=attempt, job_id='a422-lookup-diagnosis')
    physical(receipt)
    require(receipt.get('status') == 'COMPLETE' and not receipt['working_tree_dirty']
            and receipt.get('run_id') == os.environ['GITHUB_RUN_ID']
            and receipt.get('model_hash') == model_hash()
            and receipt.get('lookup_baseline_sha') == BASELINE, 'LOOKUP_INCOMPLETE')
    require(receipt.get('candidate_key_hits') == {table:(1000 if table in TABLES[:2] else 2000)
                                                for table in TABLES}, 'LOOKUP_COVERAGE_MISMATCH')
    samples = receipt.get('samples', [])
    expected = {(regime, table, variant, repeat) for regime in ('as_seeded', 'analyzed')
                for table in TABLES for variant in VARIANTS
                for repeat in range(CONTROL_REPEATS if table == TABLES[2] else 5)}
    actual = [(s['statistics'], s['table'], s['variant'], s['repeat']) for s in samples]
    require(len(actual) == len(expected) and set(actual) == expected
            and all(s.get('golden') == 'PASS' and s.get('keys') == 2000 for s in samples),
            'LOOKUP_SAMPLES_INCOMPLETE')
    summary = summarize(samples)
    workloads = whole_workloads(samples)
    require(summary == receipt.get('summary') and workloads == receipt.get('whole_workloads')
            and performance_decision(summary, workloads)
            == receipt.get('decision'), 'LOOKUP_DECISION_MISMATCH')
    require(receipt['decision']['performance_eligible'] is True, 'LOOKUP_TARGET_NOT_MET')
    proposed = candidate_source()
    require((ROOT/'backend/app/services/data_publication.py').read_text() == proposed
            and receipt.get('production_matches_candidate') is True
            and receipt.get('production_source_sha256') == hashlib.sha256(
                proposed.encode()).hexdigest(), 'LOOKUP_PRODUCTION_NOT_VERIFIED_CANDIDATE')
    plans = receipt.get('plans', [])
    require(len(plans) == 60
            and {(p['statistics'], p['table'], p['variant'], p['case']) for p in plans}
            == {(*key[:3], case) for key in expected for case in ('b_present', 'late_keys')}
            and all(p.get('plan') for p in plans),
            'LOOKUP_PLANS_INCOMPLETE')
    require(receipt.get('observer_preflight') == 'PASS', 'LOOKUP_ACTUAL_PLAN_OBSERVER_MISSING')
    for regime in ('as_seeded', 'analyzed'):
        probes = receipt.get('actual_execution_probes', {}).get(regime, {}).get('cases', [])
        require(len(probes) == 18 and {(p['table'], p['variant'], p['case']) for p in probes}
                == {(table, variant, case) for table in TABLES for variant in ('C0', 'C1', 'C2')
                    for case in ('b_present', 'late_keys')}
                and all(p.get('plan') and p.get('golden') == 'PASS' for p in probes),
                'LOOKUP_ACTUAL_PLANS_INCOMPLETE')
    return dict(testcases=junit(paths[0].parent/'tests.xml'), status='COMPLETE')


def audit_receipt(directory, head, attempt):
    import hashlib
    import subprocess

    paths = list(directory.rglob('audit/m17_1-dependency-audit.json'))
    require(len(paths) == 1 and not list(directory.rglob('*audit-incomplete.json')),
            'AUDIT_ARTIFACT_MISSING_OR_INCOMPLETE')
    receipt = json.loads(paths[0].read_text())
    require(receipt.get('schema_version') == 'm17.1-dependency-audit-v1'
            and receipt.get('status') == 'COMPLETE'
            and receipt.get('head_sha') == head and str(receipt.get('attempt')) == str(attempt)
            and receipt.get('run_id') == os.environ['GITHUB_RUN_ID'], 'AUDIT_IDENTITY_MISMATCH')
    lock = ROOT/'frontend/package-lock.json'
    require(receipt.get('lock_sha256') == hashlib.sha256(lock.read_bytes()).hexdigest(),
            'AUDIT_LOCK_MISMATCH')
    require(str(receipt.get('node_version', '')).startswith('v22.'), 'AUDIT_NODE_MISMATCH')
    # Reuse the exact Node report/lock validators, not a looser second schema.
    validation = """const fs=require('node:fs');
const {validateAudit,validateLock}=require('./scripts/m17_1_dependency_audit.cjs');
const a=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
const l=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const reports=['all','production'].map(k=>validateAudit({status:a[k].exit_status,
  stdout:JSON.stringify(a[k].report)}));
if(JSON.stringify(validateLock(...reports,l))!==JSON.stringify(a.packages))process.exit(1);
"""
    checked = subprocess.run(['node', '-e', validation, str(paths[0]), str(lock)],
                             cwd=ROOT, capture_output=True, timeout=30)
    require(checked.returncode == 0, 'AUDIT_REPORT_INVALID')
    return {k:receipt[k]['report']['metadata']['vulnerabilities'] for k in ('all', 'production')}


def status(directory, job, *, core=False, safety=False, audit=False):
    directory = Path(directory)
    value = dict(**header(job), status="INCOMPLETE", finished_at=now(),
                 workflow_job_status=os.environ.get("UPSTREAM_STATUS", "unknown"))
    if audit:
        for name in ('m17_1-dependency-audit.json', 'm17_1-dependency-audit-incomplete.json'):
            source = ROOT/'.codex_tmp'/name
            if source.is_file():
                directory.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, directory/name)
        if value['workflow_job_status'] == 'success':
            value['counts'] = audit_receipt(directory.parent, value['head_sha'], value['attempt'])
            value['status'] = 'COMPLETE'
    elif core:
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
            require_jobs(needs, {"test", "capacity", "lookup-diagnosis", "dependency-audit"})
            result['audit'] = audit_receipt(args.input, head, attempt)
            result['lookup'] = lookup_receipt(args.input, head, attempt)
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
            atomic(args.output.parent/"data-publication-release.json", result["publication"])
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
        "lab", "publication", "status", "core-status", "safety-status", "audit-status"))
    parser.add_argument("--input", type=Path, default=Path(".codex_tmp/a421-input"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--job-id", default="unknown")
    args = parser.parse_args()
    if args.mode.endswith("status"):
        status(args.output, args.job_id,
               core=args.mode=="core-status", safety=args.mode=="safety-status",
               audit=args.mode=="audit-status")
    else:
        gate(args)


if __name__ == "__main__":
    main()
