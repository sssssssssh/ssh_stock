"""Conservative A4-2 receipts: diagnostics never authorize production reads."""

import argparse
import json
import statistics
from pathlib import Path


def percentile(values, p):
    if not values:
        return None
    return (statistics.quantiles(values,n=100,method="inclusive")[p-1]
            if len(values)>1 else values[0])


def phase_seconds(run, phase, *, read_only=False):
    return sum(e["seconds"] for e in run["events"] if e["phase"]==phase
               and (not read_only or e.get("offset_seconds",float("inf"))<run["read_seconds"]))


def summarize(output):
    groups = {}
    goldens = {}
    for run in output.get("runs", []):
        scope = run.get("scope", "full")
        if (scope in {"full","window_matrix"} and run["protection"]!="NOT_EQUIVALENT"
                and "final_verification_applied" in run
                and run["final_verification_applied"] is not True):
            raise ValueError("A42_PROTECTED_READ_REQUIRES_FINAL_VERIFY")
        if run.get("telemetry", {}).get("reader_errors"):
            raise ValueError("A42_RR_READER_ERROR")
        golden = (run["rows"], run["hash"], run["dtypes"], run["columns"])
        comparison_scope = "full" if scope == "window_matrix" else scope
        if comparison_scope in goldens and golden != goldens[comparison_scope]:
            raise ValueError("A42_GOLDEN_MISMATCH")
        goldens[comparison_scope] = golden
        if not run["cursors"] or any(not c.get("closed") or "until_eof_seconds" not in c
                                     for c in run["cursors"]):
            raise ValueError("A42_CURSOR_INCOMPLETE")
        fetched = sum(f.get("rows", 0) for c in run["cursors"] for f in c["fetches"])
        if fetched != run["rows"]:
            raise ValueError("A42_FETCH_COUNT_MISMATCH")
        key = (scope, run["variant"], run.get("window_days"), run.get("cursor_fraction", "0.1"))
        groups.setdefault(key, []).append(run)
    tables = []
    for key, runs in groups.items():
        values = [r["read_plus_final_seconds"] for r in runs]
        p95 = percentile(values,95)
        components = {}
        if all("events" in r for r in runs):
            components = {phase:statistics.median(phase_seconds(r,phase,read_only=read_only)
                for r in runs) for phase,read_only in (
                    ("T3_fingerprint_inclusive",True),("T4_candidate_validation_sql",True),
                    ("T8_verify_inclusive",False),("T2_lock_hold",False),
                    ("T6_frame",False),("T6_sort",False),("checkpoint",False))}
        fetches = [f["seconds"] for r in runs for c in r["cursors"] for f in c["fetches"]
                   if "seconds" in f]
        readers = [s for r in runs for s in r.get("telemetry",{}).get("reader_samples_seconds",[])]
        tables.append({"scope": key[0], "variant": key[1], "window_days": key[2],
                       "cursor_fraction": key[3], "repeats": len(values),
                       "p50": statistics.median(values), "p95": p95,
                       "range": [min(values), max(values)], "samples": values,
                       "protection": runs[0]["protection"], "nested_phase_p50":components,
                       "fetch_p95":percentile(fetches,95),"fetch_p99":percentile(fetches,99),
                       "reader_p95":percentile(readers,95),
                       "timing_caveat":"Nested phase medians overlap; never add them"})
    chains = {}
    for run in output.get("runs", []):
        if run.get("scope") in {"month_1","month_2","month_3"}:
            chains.setdefault((run["variant"],run.get("cursor_fraction","0.1"),
                               run["repeat"]),[]).append(run)
    chain_groups = {}
    chains_complete = bool(chains)
    for (variant,fraction,repeat), runs in chains.items():
        if sorted(r["scope"] for r in runs) != ["month_1","month_2","month_3"]:
            chains_complete = False
            continue
        ordered = sorted(runs,key=lambda r:r["scope"])
        finals = [r.get("final_verification_applied") for r in ordered]
        protected = ordered[0]["protection"] != "NOT_EQUIVALENT"
        expected = [False,False,True] if protected else [False,False,False]
        tail_only = all(actual is wanted for actual,wanted in zip(finals,expected,strict=True))
        if output.get("monthly_verification_protocol")=="ROOT_TAIL_ONLY" and not tail_only:
            raise ValueError("A42_MONTHLY_FINAL_VERIFY_PROTOCOL")
        protocol = "ROOT_TAIL_ONLY" if tail_only else "LEGACY_PERIODIC_OR_UNRECORDED"
        chain_groups.setdefault((variant,fraction,protocol),[]).append(
            dict(repeat=repeat,seconds=sum(r["read_plus_final_seconds"] for r in ordered)))
    chain_tables = []
    for (variant,fraction,protocol), runs in chain_groups.items():
        values = [r["seconds"] for r in runs]
        chain_tables.append(dict(variant=variant,cursor_fraction=fraction,protocol=protocol,
            repeats=len(runs),p50=statistics.median(values),p95=percentile(values,95),samples=values,
            scope="Sum actual monthly read/commit/final spans under the labelled protocol; "
                "not sum of monthly medians; "
                "excludes numerical engines, golden oracle and harness persistence"))
    return {"tables": tables, "golden": "PASS" if groups else "UNPROVEN",
            "monthly_chain_tables":chain_tables,"monthly_chains_complete":chains_complete,
            "experiment_complete": bool(output.get("experiment_complete"))
                and not output.get("failure_type"),
            "event_install_seconds":output.get("event_install_seconds"),
            "measured_groups_complete": bool(groups) and all(len(r)>=3 for r in groups.values()),
            "state": "A4_2_NO_SAFE_WINNER", "read_performance_pass": "NOT_CLAIMED",
            "authorize_a4_3": False,
            "reason": "No candidate authorized; E0 SQL needs scale/resource review; "
                "E1/E2 rejected and E3 rollback/privileged gaps remain",
            "cloud": "NOT_AUTHORIZED_NOT_PERFORMED", "all_slow_samples_retained": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = [{"receipt": p.name, **summarize(json.loads(p.read_text(encoding="utf-8")))}
               for p in args.receipts]
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
