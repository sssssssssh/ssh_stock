"""Strict on-disk receipt checks; never trusts glob counts or partial JSON."""

import gzip
import hashlib
import json
from pathlib import Path

from scripts.a42_ci_contract import matrix
from scripts.a42_receipt_contract import identity, physical, require, require_jobs, validate_set


def load_groups(path, manifest):
    entries = manifest.get("entries", {})
    require(isinstance(entries, dict) and bool(entries), "MANIFEST_ENTRIES_MISSING")
    result = []
    for group_id, entry in entries.items():
        require(entry.get("status") == "COMPLETE", "MANIFEST_GROUP_INCOMPLETE")
        name = entry.get("file", "")
        require(name == group_id+".json.gz", "INVALID_GROUP_FILE")
        data = (Path(path).parent/name).read_bytes()
        require(hashlib.sha256(data).hexdigest() == entry.get("sha256"), "ARTIFACT_DIGEST_MISMATCH")
        receipt = json.loads(gzip.decompress(data))
        require(receipt.get("group_id") == group_id, "ARTIFACT_KEY_MISMATCH")
        result.append(receipt)
    return result


def validate_lab(directory, *, head, attempt, model_hash, needs):
    expected = matrix()
    require_jobs(needs, {"contract-and-safety", "laboratory"})
    paths = list(Path(directory).rglob("manifest.json"))
    by_job = {}
    for path in paths:
        manifest = json.loads(path.read_text())
        job = manifest.get("job_id")
        require(job in expected and job not in by_job, "UNKNOWN_OR_DUPLICATE_JOB")
        by_job[job] = (path,manifest)
    require(set(by_job) == set(expected), "SHARD_ARTIFACT_MISSING")
    validated, environments, global_goldens = {}, [], {}
    for job, groups in expected.items():
        path, manifest = by_job[job]
        identity(manifest, head=head, attempt=attempt, job_id=job)
        physical(manifest)
        require(manifest.get("status") == "COMPLETE" and not manifest.get("working_tree_dirty")
            and not manifest.get("failure_type") and not manifest.get("sqlstate")
            and not manifest.get("failed_phase"), "MANIFEST_INCOMPLETE")
        require(manifest.get("model_hash") == model_hash, "MANIFEST_MODEL_MISMATCH")
        require(manifest.get("expected_groups") == manifest.get("completed_groups") == len(groups),
                "MANIFEST_COUNT_MISMATCH")
        setup_files = manifest.get("setup_files", {})
        require(bool(setup_files), "SETUP_EVIDENCE_MISSING")
        locks = None
        for name, checksum in setup_files.items():
            require(Path(name).name == name and name.startswith("setup-")
                    and name.endswith(".json"), "INVALID_SETUP_FILE")
            raw = (path.parent/name).read_bytes()
            require(hashlib.sha256(raw).hexdigest() == checksum, "SETUP_DIGEST_MISMATCH")
            data = json.loads(raw)
            if data.get("lock_probe_outside_timed_trials"):
                locks = data["lock_probe_outside_timed_trials"]
        require(locks and set(locks) == {"stock_trade_status_daily", "data_publication_row"}
            and all(p.get("dml_sqlstate") == "55P03" and p.get("acquire_sqlstate") == "55P03"
                    for p in locks.values()), "LOCK_PROBE_MISSING")
        receipts = load_groups(path, manifest)
        validated[job] = validate_set(receipts, groups, head=head, attempt=attempt,
                                     job_id=job, model_hash=model_hash)
        from scripts.ab_read_experiment_summary_v14_a4_2 import summarize_shard

        validated[job]["comparisons"] = summarize_shard(receipts)
        for receipt in receipts:
            if receipt["group"]["kind"] != "read":
                continue
            scope = receipt["group"]["scope"].removeprefix("event_")
            scope = scope if scope.startswith("month_") else "full"
            key = (receipt["fixture_digest"], scope)
            signature = {k:receipt["result"][k] for k in (
                "rows", "hash", "key_hash", "columns", "dtypes", "null_counts")}
            require(key not in global_goldens or signature == global_goldens[key],
                    "CROSS_SHARD_GOLDEN_MISMATCH")
            global_goldens[key] = signature
        environments.append(manifest["physical_system_identifier"])
    require(len(set(environments)) == len(expected), "PHYSICAL_INSTANCES_REUSED")
    return validated
