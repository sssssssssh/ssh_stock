"""Offline performance JSON summary; no application/config/database imports."""

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path


def summary(reports):
    groups = {}
    for report in reports:
        if report.get("schema_version") != "biz-perf-03-a.v1":
            raise ValueError("PERFORMANCE_SCHEMA_UNSUPPORTED")
        key = (report["git_sha"], report["config_fingerprint"],
               json.dumps(report.get("context"), sort_keys=True),
               report.get("source", {}).get("source_sha256")
               or report["git_sha"] or report["trace_id"])
        groups.setdefault(key, []).append(report)
    result = []
    for (sha, config, context, source), runs in groups.items():
        walls = [r["total_wall_ms"] for r in runs]
        stages = {}
        sql = {}
        for run in runs:
            for item in run["stages"]:
                stages.setdefault(item["stage"], []).append(item)
            for item in run["database_summary"]["sql_fingerprints"]:
                target = sql.setdefault(item["sql_fingerprint"], dict(calls=0, total_ms=0))
                target["calls"] += item["calls"]
                target["total_ms"] += item["total_ms"]
        totals = sorted((dict(stage=stage,
            inclusive_ms=sum(s["duration_ms"] for s in spans),
            covered_wall_percent=(sum(interval_union_ms([
                s for s in run["stages"] if s["stage"] == stage]) for run in runs)
                / sum(walls) * 100) if sum(walls) else None,
            output_rows=sum(s["output_rows"] for s in spans
                if s["output_rows"] is not None)
                if any(s["output_rows"] is not None for s in spans) else None,
            note="inclusive_nested_do_not_sum_or_treat_as_wall_share")
            for stage, spans in stages.items()), key=lambda x: -x["inclusive_ms"])
        result.append(dict(git_sha=sha, config_fingerprint=config, runs=len(runs),
            source_group=source,
            context=json.loads(context),
            measured_union_wall_ms=sum(interval_union_ms(r["stages"]) for r in runs),
            measured_union_wall_percent=(sum(interval_union_ms(r["stages"]) for r in runs)
                / sum(walls) * 100) if sum(walls) else None,
            median_ms=statistics.median(walls), min_ms=min(walls), max_ms=max(walls),
            p95_ms=statistics.quantiles(walls, n=100, method="inclusive")[94]
                if len(walls) >= 20 else None,
            p95_note="insufficient_samples" if len(walls) < 20 else "inclusive",
            stdev_ms=statistics.stdev(walls) if len(walls) > 1 else None,
            rss_peak_bytes=max((r["worker_resources"]["final"][
                "process_lifetime_peak_rss_bytes"] for r in runs
                if r["worker_resources"]["final"]["process_lifetime_peak_rss_bytes"] is not None),
                default=None),
            stages=totals,
            sql_top_time=sorted(sql.items(), key=lambda x: -x[1]["total_ms"])[:10],
            sql_top_calls=sorted(sql.items(), key=lambda x: -x[1]["calls"])[:10],
            overlap_note="stage times are inclusive; never added to SQL/fetch or total wall"))
    return result


def interval_union_ms(spans):
    intervals = sorted((datetime.fromisoformat(s["started_at"]).timestamp(),
                        datetime.fromisoformat(s["ended_at"]).timestamp()) for s in spans)
    total, end = 0.0, float("-inf")
    for start, stop in intervals:
        total += max(0, stop - max(start, end))
        end = max(end, stop)
    return total * 1000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, nargs="+")
    args = parser.parse_args()
    print(json.dumps(summary([json.loads(p.read_text(encoding="utf-8"))
                              for p in args.reports]), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
