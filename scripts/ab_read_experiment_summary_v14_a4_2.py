"""Conservative A4-2 receipts: diagnostics never authorize production reads."""

import argparse
import json
import statistics
from pathlib import Path


def summarize(output):
    groups = {}
    goldens = {}
    for run in output.get("runs", []):
        scope = run.get("scope", "full")
        golden = (run["rows"], run["hash"], run["dtypes"], run["columns"])
        if scope in goldens and golden != goldens[scope]:
            raise ValueError("A42_GOLDEN_MISMATCH")
        goldens[scope] = golden
        if not run["cursors"] or any(not c.get("closed") for c in run["cursors"]):
            raise ValueError("A42_CURSOR_INCOMPLETE")
        fetched = sum(f.get("rows", 0) for c in run["cursors"] for f in c["fetches"])
        if fetched != run["rows"]:
            raise ValueError("A42_FETCH_COUNT_MISMATCH")
        key = (scope, run["variant"], run.get("window_days"), run.get("cursor_fraction", "0.1"))
        groups.setdefault(key, []).append(run)
    tables = []
    for key, runs in groups.items():
        values = [r["read_plus_final_seconds"] for r in runs]
        p95 = statistics.quantiles(values, n=100, method="inclusive")[94] if len(values)>1 else None
        tables.append({"scope": key[0], "variant": key[1], "window_days": key[2],
                       "cursor_fraction": key[3], "repeats": len(values),
                       "p50": statistics.median(values), "p95": p95,
                       "range": [min(values), max(values)], "samples": values,
                       "protection": runs[0]["protection"]})
    return {"tables": tables, "golden": "PASS" if groups else "UNPROVEN",
            "state": "A4_2_NO_SAFE_WINNER", "read_performance_pass": "NOT_CLAIMED",
            "authorize_a4_3": False,
            "reason": "No equivalent cheaper validation proved; E3 requires new contract",
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
