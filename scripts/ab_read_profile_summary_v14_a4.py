"""Compact, reproducible A4-1 evidence index; never marks optimization PASS."""

import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path


def quantiles(values):
    ordered = sorted(values)
    if not ordered:
        return None
    p95 = (statistics.quantiles(ordered, n=100, method="inclusive")[94]
           if len(ordered) > 1 else ordered[0])
    return {"n": len(ordered), "p50": statistics.median(ordered), "p95": p95,
            "raw": values}


def cpu_seconds(snapshot):
    lines = snapshot.get("resource", {}).get("cgroup_raw", "").splitlines()
    return next((int(line.split()[1])/1e6 for line in lines
                 if line.startswith("usage_usec ")), None)


def compact_run(run):
    before, after = cpu_seconds(run["before"]), cpu_seconds(run["after"])
    result = {key: run[key] for key in (
        "variant", "seconds", "rows", "hash", "dtypes", "frame_deep_bytes",
        "client_cpu_seconds", "process_lifetime_peak_rss_bytes", "phase_distributions",
        "driver_fetch", "resident_memory", "read_wall_components_seconds",
        "final_verify_seconds", "read_plus_final_verify_seconds") if key in run}
    for key in ("round", "chunk_start", "chunk_end", "input_start", "input_end"):
        if key in run:
            result[key] = run[key]
    result["isolated_container_cpu_seconds"] = after-before if before is not None else None
    result["container_limits"] = {key: run["before"].get("resource", {}).get(key)
                                  for key in ("cpu_limit_nano", "memory_limit_bytes")}
    counters = run["before"].get("database", {}).get("database", {})
    after_counters = run["after"].get("database", {}).get("database", {})
    result["postgres_observed_counter_delta"] = {
        key: after_counters[key]-value if value is not None and after_counters.get(key) is not None
        else None for key, value in counters.items()}
    result["maintenance_before_after"] = [
        run[stage].get("database", {}).get("maintenance", []) for stage in ("before", "after")]
    result["cursor_count"] = len(run["cursors"])
    result["cursor_latency_seconds"] = {key: quantiles([
        c[key] for c in run["cursors"] if c.get(key) is not None]) for key in (
            "first_row_seconds", "first_5000_seconds", "until_eof_seconds")}
    result["all_cursors_closed"] = all(c["closed"] for c in run["cursors"])
    result["fetch_requests"] = dict(Counter(str(f["requested"]) for c in run["cursors"]
                                           for f in c["fetches"]))
    result["total_driver_fetched_rows"] = sum(f["rows"] for c in run["cursors"]
                                             for f in c["fetches"])
    if (not result["all_cursors_closed"]
            or result["total_driver_fetched_rows"] != run["rows"]):
        raise ValueError("A4_INCOMPLETE_OR_UNCLOSED_CURSOR")
    result["read_to_final_verify_trace_span_seconds"] = max(
        [run["seconds"]] + [e["offset_seconds"]+e["seconds"] for e in run["events"]
                            if e["phase"] == "T8_verify_inclusive"])
    result["fingerprint_ranges"] = [e for e in run["events"]
                                    if e["phase"] == "T3_fingerprint_inclusive"]
    result["windows"] = [m for m in run["metrics"] if m["event"] == "window"]
    return result


def verify_monthly(runs):
    groups = {}
    for run in runs:
        groups.setdefault((run["chunk_start"], run["chunk_end"]), []).append(run)
    for group in groups.values():
        if {r["variant"] for r in group} != {"q0", "q1", "q2"}:
            raise ValueError("A4_INCOMPLETE_MONTHLY_COMPARISON")
        golden = {(r["rows"], r["hash"], json.dumps(r["dtypes"], sort_keys=True)) for r in group}
        if len(golden) != 1:
            raise ValueError("A4_MONTHLY_GOLDEN_MISMATCH")
    return {"chunks": len(groups), "status": "PASS" if groups else "NOT_RUN"}


def summarize(path):
    raw = path.read_bytes()
    data = json.loads(raw)
    if data.get("failure") or len(data["runs"]) < 9:
        raise ValueError("A4_INCOMPLETE_BASELINE_NOT_ACCEPTED")
    if any(sum(r["variant"] == name for r in data["runs"]) < 3 for name in ("q0", "q1", "q2")):
        raise ValueError("A4_THREE_REPETITIONS_PER_VARIANT_REQUIRED")
    monthly_comparison = verify_monthly(data["monthly"])
    result = {key: data[key] for key in (
        "head", "dirty", "script_sha256", "production_source_hashes", "versions",
        "python", "pg_version", "settings", "fixture", "comparison", "orders",
        "physical_system_identifier", "lock_probe_separate_from_trials",
        "actual_cursor_plans_untimed") if key in data}
    result.update(raw_file=path.name, raw_sha256=hashlib.sha256(raw).hexdigest(),
                  runs=[compact_run(run) for run in data["runs"]],
                  monthly=[compact_run(run) for run in data["monthly"]],
                  monthly_comparison=monthly_comparison,
                  q0_service_control=compact_run(data["q0_service_control"]),
                  plans=data["plans"], phase_summary={})
    golden = {(r["rows"], r["hash"], json.dumps(r["dtypes"], sort_keys=True)) for r in data["runs"]}
    if len(golden) != 1:
        raise ValueError("A4_GOLDEN_MISMATCH")
    for variant in ("q0", "q1", "q2"):
        runs = [r for r in data["runs"] if r["variant"] == variant]
        result["phase_summary"][variant] = {
            "read_seconds": quantiles([r["seconds"] for r in runs]),
            "phases_inclusive_seconds": {phase: quantiles([
                r["phase_distributions"].get(phase, {}).get("seconds", 0) for r in runs])
                for phase in sorted({p for r in runs for p in r["phase_distributions"]})}}
    return result


def brief(evidence):
    """Lossless per-run costs, projected plan nodes; full raw sealed by SHA256."""
    keep = {"Node Type", "Join Type", "Relation Name", "Index Name", "Plan Rows", "Plans",
        "Actual Rows", "Actual Loops", "Actual Startup Time", "Actual Total Time",
        "Shared Hit Blocks", "Shared Read Blocks", "Temp Read Blocks", "Temp Written Blocks",
        "Sort Method", "Sort Space Used", "Sort Space Type", "Sort Key", "Hash Batches",
        "Heap Fetches", "Rows Removed by Filter", "Index Cond", "Hash Cond", "Merge Cond",
        "Filter", "Join Filter", "Execution Time", "Planning Time", "Plan", "Query Text"}

    def project(value):
        if isinstance(value, dict):
            return {k: project(v) for k, v in value.items() if k in keep}
        if isinstance(value, list):
            return [project(v) for v in value]
        return value

    for data in evidence["raw"]:
        daily = data["fixture"].pop("public_rows_by_day", [])
        data["fixture"]["public_daily_summary"] = {
            "days": len(daily), "total_rows": sum(r["rows"] for r in daily),
            "first": daily[0] if daily else None, "last": daily[-1] if daily else None}
        for run in data["runs"] + data["monthly"] + [data["q0_service_control"]]:
            windows = run.pop("windows")
            run["window_summary"] = {"count": len(windows),
                "total_rows": sum(w["rows"] for w in windows),
                "first": windows[0] if windows else None,
                "last": windows[-1] if windows else None}
            # Exclusive components and per-run T8 remain raw, not just averages.
            run["phase_distributions"] = {p: {k: v for k, v in stats.items()
                if k in {"count", "seconds", "p50", "p95"}}
                for p, stats in run["phase_distributions"].items()}
        for phases in data["plans"].values():
            for plans in phases.values():
                for entry in plans:
                    entry["select_actual"] = project(entry["select_actual"])
                    entry["cursor_estimated"] = project(entry["cursor_estimated"])
        if "actual_cursor_plans_untimed" in data:
            data["actual_cursor_plans_untimed"] = {
                v: project(plans) for v, plans in data["actual_cursor_plans_untimed"].items()}
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--brief", action="store_true")
    args = parser.parse_args()
    evidence = {"schema": "a4-1-local-evidence-index-v1", "read_performance": "OPEN",
        "scope": "diagnosis only; no optimization, no production validation",
        "cache": "UNCONTROLLED; no controlled cold claim",
        "raw": [summarize(p) for p in args.inputs]}
    print(json.dumps(brief(evidence) if args.brief else evidence, default=str, indent=2))


if __name__ == "__main__":
    main()
