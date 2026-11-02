"""Read-only full-scale resource estimate; never acquires a DB or starts a job."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

ROWS = 1_443_097
ROUNDS = 3
# Planning reserve for simultaneous source frames, Python dictionaries, status
# frame/records and candidate assembly, not an empirically proved peak or OOM.
MEMORY_RESERVE_BYTES = 4 * 1024**3


def resource_preflight():
    from app.services.calculation_memory import available_memory_bytes, process_memory_bytes

    available = available_memory_bytes()
    rss, peak = process_memory_bytes()
    return dict(schema_version="biz-worker-02.resources.v1", target_rows=ROWS,
                planned_rounds=ROUNDS, available_memory_bytes=available,
                process_memory_bytes=rss, peak_rss_bytes=peak,
                planning_reserve_bytes=MEMORY_RESERVE_BYTES,
                status="RESOURCE_DEFERRED" if available < MEMORY_RESERVE_BYTES else
                       "PRECHECK_ONLY_NOT_BENCHMARKED",
                measurement_kind="ESTIMATE_NOT_ACTUAL_ALLOCATION_OR_OOM",
                database_contacted=False, rounds_completed=0, rows_measured=0,
                performance_qualified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = resource_preflight()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(report["status"])
    return 2 if report["status"] == "RESOURCE_DEFERRED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
