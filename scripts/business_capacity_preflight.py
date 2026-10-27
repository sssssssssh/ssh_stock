"""Read-only local capacity reservation, never a performance or G1 admission.

No business settings are loaded before the explicit synthetic PG17 target is
verified. Resource refusal does not reduce the required million-row matrix.
"""

import argparse
import hashlib
import inspect
import json
import os
import shutil
from pathlib import Path


def decision(available, free_disk, worker_rss, shared, work_mem, connections, maintenance):
    values = (available, free_disk, worker_rss, shared, work_mem, connections, maintenance)
    if any(type(v) is not int or v < 0 for v in values) or worker_rss == 0 or connections == 0:
        raise ValueError("BUSINESS_RESOURCE_OBSERVATION_INVALID")
    # A conservative reservation, not a prediction, cgroup limit, or memory proof.
    # work_mem can be consumed by multiple plan nodes; this is only a lower floor.
    reserve = worker_rss + shared + work_mem * connections + maintenance
    reasons = []
    if available <= reserve:
        reasons.append("AVAILABLE_MEMORY_BELOW_REGISTERED_RESERVATION")
    if free_disk < 8 * 1024**3:
        reasons.append("SYNTHETIC_DISK_RESERVE_EXHAUSTED")
    return dict(status="RESOURCE_DEFERRED" if reasons else "RESOURCE_FLOOR_OBSERVED",
                refusal_reasons=reasons, available_memory_estimate_bytes=available,
                memory_reservation_bytes=reserve, free_disk_bytes=free_disk,
                disk_reservation_bytes=8 * 1024**3, performance_status="PERFORMANCE_OPEN",
                capacity_accepted=False, jobs_started=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("existing evidence cannot be overwritten")
    from scripts.v14_test_database import verified_test_url

    url = verified_test_url()
    os.environ.update(DATABASE_URL=url.render_as_string(hide_password=False),
                      TUSHARE_TOKEN="synthetic-capacity-preflight", LLM_ENABLED="false")
    from app.core.config import Settings

    Settings.model_config = {**Settings.model_config, "env_file": None}
    from app.services.calculation_memory import available_memory_bytes, check_calculation_memory
    from app.services.calculation_policy import runtime_source
    from sqlalchemy import create_engine, text

    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.connect() as db:
            directory = db.scalar(text("SHOW data_directory"))
            settings = {name: int(db.scalar(text(
                "SELECT pg_size_bytes(current_setting(:name))"), {"name": name}))
                for name in ("shared_buffers", "work_mem", "maintenance_work_mem")}
            connections = int(db.scalar(text("SHOW max_connections")))
            server = db.scalar(text("SHOW server_version"))
    finally:
        engine.dispose()
    worker = inspect.signature(check_calculation_memory).parameters["limit"].default
    report = decision(available_memory_bytes(), shutil.disk_usage(directory).free, worker,
                      settings["shared_buffers"], settings["work_mem"], connections,
                      settings["maintenance_work_mem"])
    report.update(schema="biz-perf-01.capacity-preflight.v1", source=runtime_source(),
                  harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  server_version=server, postgres_settings=settings,
                  max_connections=connections, worker_rss_failure_threshold_bytes=worker,
                  required_months=[1, 3, 12], repeats_per_version=3,
                  versions=["old", "new"], minimum_raw_rows=1_000_000,
                  warmup_trading_days=250, monthly_lookback_calendar_days=430,
                  representative_nonempty_tables_required=10, required_successful_jobs=18,
                  actual_successful_jobs=0, matrix_status="NOT_RUN", cloud_access=False,
                  limitations=["Quiet-host resource reservation only; no Worker started",
                               "Memory estimate and failure thresholds are not hard limits",
                               "Resource headroom alone never establishes fixture correctness",
                               "All required scales, repetitions and financial gates unchanged"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(report, target, indent=2, allow_nan=False)
        target.write("\n")


if __name__ == "__main__":
    main()
