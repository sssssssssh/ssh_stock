"""Validate synthetic before/after receipts; never upgrades an OPEN performance result."""

import argparse
import json
import statistics
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


def compare(baseline, current, head):
    for receipt in (baseline, current):
        assert receipt["head_sha"] == head, "MEASUREMENT_SHA_MISMATCH"
        assert not receipt["working_tree_dirty"], "MEASUREMENT_DIRTY_TREE"
        assert receipt["measurement_version"] == "v13-2-excludes-input-build"
        assert all(
            r["synthetic"] and r["production_validation"] == "UNPROVEN" and not r["reader_errors"]
            for r in receipt["results"]
        )
    stable = ("platform", "python", "logical_cpus", "processor", "packages")
    assert all(baseline["environment"][key] == current["environment"][key] for key in stable), (
        "MEASUREMENT_ENVIRONMENT_CHANGED"
    )
    results = []
    for rows in (1000, 100000, 500000):
        before = [r for r in baseline["results"] if r["rows"] == rows]
        after = [r for r in current["results"] if r["rows"] == rows]
        assert {r["repeat"] for r in before} == {r["repeat"] for r in after} == {0, 1, 2}
        assert len(before) == len(after) == 3
        assert {r["candidate_digest"] for r in before} == {r["candidate_digest"] for r in after}, (
            "GOLDEN_DIGEST_MISMATCH"
        )
        assert len({r["candidate_digest"] for r in before}) == 1, "NONDETERMINISTIC_GOLDEN_OUTPUT"
        assert all(r["staged"] == rows for r in before + after)
        assert len({r["postgres"] for r in before + after}) == 1
        assert all(r["database_settings"] == before[0]["database_settings"] for r in before + after)
        assert all(r["public_a"] and r["existing_candidates"] == 0 for r in before + after)
        old = statistics.median(r["prepare_seconds"] for r in before)
        new = statistics.median(r["prepare_seconds"] for r in after)
        old_sql = statistics.median(r["sql_count"] for r in before)
        new_sql = statistics.median(r["sql_count"] for r in after)
        results.append(
            dict(
                rows=rows,
                candidate_digest=before[0]["candidate_digest"],
                baseline_seconds=old,
                current_seconds=new,
                time_reduction=1 - new / old,
                baseline_range=[
                    min(r["prepare_seconds"] for r in before),
                    max(r["prepare_seconds"] for r in before),
                ],
                current_range=[
                    min(r["prepare_seconds"] for r in after),
                    max(r["prepare_seconds"] for r in after),
                ],
                baseline_sql=old_sql,
                current_sql=new_sql,
                sql_reduction=1 - new_sql / old_sql,
                time_target_met=new <= old * 0.5,
                sql_target_met=new_sql <= old_sql * 0.5,
                baseline_peak_rss_bytes=max(r["peak_process_rss_bytes"] for r in before),
                current_peak_rss_bytes=max(r["peak_process_rss_bytes"] for r in after),
                baseline_wal_bytes=[r["wal_bytes"] for r in before],
                current_wal_bytes=[r["wal_bytes"] for r in after],
                resource_budget_status="PENDING_OPERATOR_APPROVAL",
            )
        )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    current = json.loads(args.current.read_text(encoding="utf-8"))
    results = compare(baseline, current, head)
    cases = list(ET.parse(args.junit).getroot().iter("testcase"))
    assert cases and not any(
        list(c.iter("failure")) or list(c.iter("error")) or list(c.iter("skipped")) for c in cases
    ), "TARGETED_JUNIT_NOT_GREEN"
    targets = all(
        r["time_target_met"] and r["sql_target_met"] for r in results if r["rows"] >= 100000
    )
    cold = all(r["cold_cache_claim"] for r in baseline["results"] + current["results"])
    receipt = dict(
        schema_version="v13-performance-comparison-v1",
        head_sha=head,
        targeted_tests=len(cases),
        results=results,
        performance_closed=targets and cold,
        targets_met=targets,
        cold_cache_validated=cold,
        production_validation="PENDING_SEPARATE_APPROVAL",
        full_code_acceptance="Requires all exact-HEAD CI jobs SUCCESS",
        open_reasons=(["B1/B2 50% time/SQL targets not all met"] if not targets else [])
        + (["Cold-cache measurements unavailable; OS cache uncontrolled"] if not cold else []),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
