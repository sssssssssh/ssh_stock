"""BIZ-PERF-02 interleaved full-root comparison on explicit synthetic PG17 only.

Does not enable BIZ-PERF-01 flags or grant formal capacity/production acceptance.
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

BASELINE = "3940d9b905e5234368f8a7474ae2ce6de73b0cb3"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(old, new):
    return dict(
        dataset_equal=bool(old.get("dataset_sha256"))
        and old.get("dataset_sha256") == new.get("dataset_sha256"),
        tables_equal=bool(old.get("tables")) and old.get("tables") == new.get("tables"),
        financial_identity_equal=bool(old.get("financial_identity"))
        and old.get("financial_identity") == new.get("financial_identity"),
        windows_equal=bool(old.get("windows")) and old.get("windows") == new.get("windows"),
        publication_counts_equal=bool(old.get("root_row_counts"))
        and old.get("root_row_counts") == new.get("root_row_counts"),
        published=all(
            isinstance(r.get("runs"), list)
            and len(r["runs"]) == 1
            and r["runs"][0]["job_status"] == "SUCCESS"
            and r["runs"][0]["publication_state"] == "PUBLISHED"
            for r in (old, new)
        ),
    )


def p95(values):
    ordered = sorted(values)
    position = (len(ordered) - 1) * 0.95
    lo = int(position)
    return ordered[lo] + (ordered[min(lo + 1, len(ordered) - 1)] - ordered[lo]) * (position - lo)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stocks", type=int, default=4)
    parser.add_argument("--months", type=int, nargs="+", choices=(1, 3, 12), default=[1, 3, 12])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.stocks <= 100 or not 3 <= args.repeats <= 5:
        parser.error("bounded diagnostic only: stocks 1..100, repeats 3..5")
    if args.output.exists():
        parser.error("existing evidence must not be overwritten")
    from scripts.v14_test_database import verified_test_url

    verified_test_url()  # Before archives, app imports, children or any DDL.
    if subprocess.check_output(["git", "branch", "--show-current"], text=True).strip() != "master":
        raise RuntimeError("BIZ02_MASTER_REQUIRED")
    args.output.mkdir(parents=True)
    root = Path.cwd()
    archive = args.output / "baseline.tar"
    reference = args.output / "baseline-source"
    reference.mkdir()
    subprocess.run(["git", "archive", "--format=tar", f"--output={archive}", BASELINE], check=True)
    with tarfile.open(archive) as source:
        source.extractall(reference, filter="data")
    report = dict(
        schema="biz-perf-02.matrix.v1",
        status="INCOMPLETE",
        performance_status="PERFORMANCE_OPEN",
        capacity_status="RESOURCE_DEFERRED",
        cloud_status="REAL_CLOUD_RECALC_NOT_AUTHORIZED",
        baseline_sha=BASELINE,
        candidate_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        harness_sha256=digest(root / "scripts/business_recalc_measure.py"),
        observer_sha256=digest(root / "scripts/business_candidate_observer.py"),
        strategy_sha256=digest(root / "config/strategy.yaml"),
        marker=os.environ["V14_TEST_INSTANCE"],
        system_identifier=os.environ["V14_TEST_SYSTEM_IDENTIFIER"],
        stocks=args.stocks,
        months=args.months,
        repeats=args.repeats,
        plan_protocol="actual timed first lookup per table with auto_explain; "
        "same instrumentation on both versions; no extra warmup; default cache policy; "
        "inclusive stages overlap and must not be summed; p95 linear inclusive",
        samples=[],
        pairs=[],
        comparisons=[],
    )
    report_path = args.output / "matrix.json"

    def save():
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    save()
    all_ok = True
    for months in args.months:
        for repeat in range(args.repeats):
            pair = {}
            for variant in ("old", "new") if repeat % 2 == 0 else ("new", "old"):
                name = f"{months}m-{repeat}-{variant}"
                output = args.output / (name + ".json")
                env = dict(os.environ)
                backend = (reference if variant == "old" else root) / "backend"
                env["PYTHONPATH"] = os.pathsep.join([str(backend.resolve()), str(root)])
                for key in (
                    "FACTOR_INPUT_REUSE_ENABLED",
                    "RAW_PREFLIGHT_BATCH_ENABLED",
                    "FACTOR_CPU_OPTIMIZATION_ENABLED",
                    "AB_MERGE_READ_ENABLED",
                ):
                    env[key] = "false"
                with output.with_suffix(".log").open("w", encoding="utf-8") as log:
                    child = subprocess.run(
                        [
                            sys.executable,
                            "-u",
                            "-m",
                            "scripts.business_recalc_measure",
                            "--stocks",
                            str(args.stocks),
                            "--months",
                            str(months),
                            "--candidate-diagnostics",
                            "--implementation-sha",
                            BASELINE if variant == "old" else report["candidate_sha"],
                            "--output",
                            str(output),
                        ],
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )
                record = json.loads(output.read_bytes()) if output.exists() else {}
                packed = gzip.compress(output.read_bytes(), mtime=0) if output.exists() else b""
                if packed:
                    output.with_suffix(".json.gz").write_bytes(packed)
                pair[variant] = record
                report["samples"].append(
                    dict(
                        name=name,
                        variant=variant,
                        months=months,
                        repeat=repeat,
                        returncode=child.returncode,
                        sha256=digest(output) if output.exists() else None,
                        compressed_sha256=hashlib.sha256(packed).hexdigest() if packed else None,
                        root_runs=record.get("runs"),
                        raw_daily_rows=record.get("raw_daily_rows"),
                        dataset_sha256=record.get("dataset_sha256"),
                        implementation_sha256=record.get("implementation_sha256"),
                        git_text_sources_sha256=record.get("git_text_sources_sha256"),
                        peak_process_rss_bytes=record.get("peak_process_rss_bytes"),
                        cross_quality_seconds=record.get("candidate_diagnostics", {})
                        .get("stages", {})
                        .get("cross_table_quality:-", {})
                        .get("wall_seconds"),
                    )
                )
                all_ok = all_ok and child.returncode == 0
                save()
                print(json.dumps(dict(sample=name, returncode=child.returncode)), flush=True)
            comparison = compare(pair["old"], pair["new"])
            report["pairs"].append(dict(months=months, repeat=repeat, **comparison))
            all_ok = all_ok and all(comparison.values())
            save()
    for months in args.months:
        groups = {
            v: [
                s["root_runs"][0]["overall"]
                for s in report["samples"]
                if s["months"] == months and s["variant"] == v and s["root_runs"]
            ]
            for v in ("old", "new")
        }
        if all(len(values) == args.repeats for values in groups.values()):
            old, new = (statistics.median(groups[v]) for v in ("old", "new"))
            report["comparisons"].append(
                dict(
                    months=months,
                    old=groups["old"],
                    new=groups["new"],
                    old_median=old,
                    new_median=new,
                    old_p95=p95(groups["old"]),
                    new_p95=p95(groups["new"]),
                    median_improvement=1 - new / old,
                )
            )
    retention = []
    for months in args.months:
        groups = {
            v: [
                s["cross_quality_seconds"]
                for s in report["samples"]
                if s["months"] == months and s["variant"] == v
            ]
            for v in ("old", "new")
        }
        comparison = next((c for c in report["comparisons"] if c["months"] == months), None)
        complete = all(
            len(a) == args.repeats and all(isinstance(x, (int, float)) and x > 0 for x in a)
            for a in groups.values()
        )
        if complete and comparison:
            old, new = (statistics.median(groups[v]) for v in ("old", "new"))
            improved = sum(n < o for o, n in zip(groups["old"], groups["new"], strict=True))
            keep = (
                1 - new / old >= 0.15
                and improved >= 2
                and comparison["median_improvement"] >= -0.05
                and (months != 12 or comparison["median_improvement"] > 0)
            )
            retention.append(
                dict(
                    months=months,
                    old_quality=groups["old"],
                    new_quality=groups["new"],
                    median_improvement=1 - new / old,
                    improved_pairs=improved,
                    retain=keep,
                )
            )
    report["retention"] = retention
    report["retain_candidate"] = (
        all_ok and len(retention) == len(args.months) and all(r["retain"] for r in retention)
    )
    report["status"] = "SMALL_CONTROLLED_COMPLETE" if all_ok else "FAILED"
    save()
    if not all_ok:
        raise SystemExit(1)
    if not report["retain_candidate"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
