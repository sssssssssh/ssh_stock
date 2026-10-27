"""Symmetric synthetic business matrix; no automatic cloud/CI dispatch.

Requires the existing explicit PG17 marker and physical-ID safety contract.
Baseline source is extracted without switching/replacing the current branch.
All slow/failed samples remain in the output; no outlier removal or retry.
"""

import argparse
import gzip
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tarfile
from pathlib import Path

BASELINE = "1e510532bd140110e29b10b6e4eed30fbd573159"


def summarize(samples, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "raw").mkdir(exist_ok=True)
    baseline, after, golden, end_to_end, queries = [], [], [], [], []
    for sample in samples:
        original = sample.read_bytes()
        record = json.loads(original)
        record["artifact_sha256"] = hashlib.sha256(original).hexdigest()
        packed = gzip.compress(original, mtime=0)
        raw_name = sample.name + ".gz"
        (output / "raw" / raw_name).write_bytes(packed)
        record["raw_artifact"] = dict(path="raw/" + raw_name,
            sha256=hashlib.sha256(packed).hexdigest(),
            uncompressed_sha256=record["artifact_sha256"])
        fetch_summary = {}
        for fetch in record.pop("fetches", []):
            key = "/".join([fetch["stage"], fetch["cursor"], fetch["operation"]])
            totals = fetch_summary.setdefault(key, dict(calls=0, rows=0, seconds=0.0,
                                                       scalar_payload_estimate_bytes=0))
            totals["calls"] += 1
            for field in ("rows", "seconds", "scalar_payload_estimate_bytes"):
                totals[field] += fetch[field]
        record["fetch_summary"] = fetch_summary
        record.pop("implementation_sources", None)  # Full maps remain in the lossless raw receipt.
        (after if record["optimized"] else baseline).append(record)
    for old, new in zip(baseline, after, strict=True):
        golden.append(dict(months=old["months"], dataset_equal=(
            bool(old.get("dataset_sha256")) and
            old.get("dataset_sha256") == new.get("dataset_sha256")),
            tables_equal=bool(old.get("tables")) and old.get("tables") == new.get("tables"),
            identity_equal=bool(old.get("financial_identity")) and
            old.get("financial_identity") == new.get("financial_identity")))
        for item in (old, new):
            end_to_end.append({k: item.get(k) for k in (
                "head_sha", "implementation_sha256", "months", "stocks", "optimized", "runs",
                    "raw_snapshot", "windows", "dataset_sha256", "git_text_sources_sha256",
                "root_row_counts", "candidate_source_mismatches",
                "independent_rr_readers_no_candidate_leak", "peak_process_rss_bytes")})
            queries.append(dict(months=item["months"], optimized=item["optimized"],
                                runs=[{k: r.get(k) for k in (
                                    "sql_counts", "delivered_rows", "sql_driver_seconds")}
                                      for r in item["runs"]]))
    comparisons = []
    for months in (1, 3, 12):
        old_runs = [r["overall"] for b in baseline if b["months"] == months for r in b["runs"]]
        new_runs = [r["overall"] for b in after if b["months"] == months for r in b["runs"]]
        if old_runs and new_runs:
            comparisons.append(dict(months=months, baseline_runs=len(old_runs),
                after_runs=len(new_runs), baseline_median=statistics.median(old_runs),
                after_median=statistics.median(new_runs), improvement=(
                    1 - statistics.median(new_runs) / statistics.median(old_runs))))
    # Full scale, full success, golden and controlled measurement are independent
    # requirements. This reporter deliberately cannot grant release/production status.
    common = dict(schema="biz-perf-01.matrix.v1", status="PERFORMANCE_OPEN",
                  cloud_status="REAL_CLOUD_RECALC_NOT_AUTHORIZED", baseline_commit=BASELINE)
    for filename, value in {
        "baseline.json": {**common, "samples": baseline},
        "after.json": {**common, "samples": after, "comparisons": comparisons},
        "financial_golden.json": {**common, "pairs": golden,
            "scope": "root UUID mapped to ROOT; audit timestamps omitted; NULL/other IDs retained"},
        "end_to_end.json": {**common, "samples": end_to_end},
        "query_counts.json": {**common, "samples": queries},
    }.items():
        (output / filename).write_text(json.dumps(value, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stocks", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.stocks <= 5000 or not 1 <= args.repeats <= 10:
        parser.error("invalid bounded matrix size")
    from scripts.v14_test_database import verified_test_url

    verified_test_url()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    reference = output / "baseline-source"
    if reference.exists():
        raise RuntimeError("BUSINESS_MATRIX_OUTPUT_MUST_BE_NEW")
    reference.mkdir()
    archive = output / "baseline-source.tar"
    subprocess.run(["git", "archive", "--format=tar", f"--output={archive}", BASELINE], check=True)
    with tarfile.open(archive) as source:
        source.extractall(reference, filter="data")
    samples = []
    try:
        for months in (1, 3, 12):
            for repeat in range(args.repeats):
                # Alternating AB/BA limits systematic warm-cache order advantage.
                for optimized in ((False, True) if repeat % 2 == 0 else (True, False)):
                    filename = output / f"{months}m-{repeat}-{'after' if optimized else 'old'}.json"
                    environment = dict(os.environ)
                    root = Path.cwd()
                    backend = root / "backend" if optimized else reference / "backend"
                    environment["PYTHONPATH"] = os.pathsep.join([str(backend), str(root)])
                    command = [sys.executable, "-u", "-m", "scripts.business_recalc_measure",
                        "--stocks", str(args.stocks), "--months", str(months),
                        "--output", str(filename)] + (["--optimized"] if optimized else [])
                    with filename.with_suffix(".log").open("w", encoding="utf-8") as log:
                        result = subprocess.run(command, env=environment, stdout=log,
                                                stderr=subprocess.STDOUT, check=False)
                    if filename.exists():
                        samples.append(filename)
                    else:
                        filename.write_text(json.dumps(dict(months=months, stocks=args.stocks,
                            optimized=optimized, runs=[], failure_class="CHILD_EXIT_NO_RECEIPT",
                            returncode=result.returncode)), encoding="utf-8")
                        samples.append(filename)
                    print(json.dumps(dict(months=months, repeat=repeat, optimized=optimized,
                                          returncode=result.returncode)), flush=True)
                    # Failures are retained, not retried and not replaced by best samples.
    finally:
        order = sorted(samples, key=lambda p: (
            int(p.name.split("m-")[0]), int(p.name.split("-")[1]), "after" in p.name))
        summarize(order, output / "receipts")


if __name__ == "__main__":
    main()
