"""Fixed offline CPU fixture: timer overhead only, NOT root/PG performance acceptance."""

import argparse
import json
import statistics
import tempfile
from pathlib import Path
from time import perf_counter

from app.services.performance_diagnostics import Trace, active_trace, span


def measure():
    observations = []
    for pair in range(3):
        for enabled in ((False, True) if pair % 2 == 0 else (True, False)):
            began = perf_counter()
            trace = Trace("synthetic-cpu-fixture") if enabled else None
            token = active_trace.set(trace)
            try:
                with span("factor.compute"):
                    output = sum((i * i) % 7919 for i in range(2_000_000))
                if trace:
                    trace.status = "success"
                    with tempfile.TemporaryDirectory() as directory:
                        trace.flush(directory)
            finally:
                active_trace.reset(token)
            observations.append(dict(pair=pair + 1, enabled=enabled,
                                     wall_ms=(perf_counter() - began) * 1000, output=output))
    medians = {label: statistics.median(x["wall_ms"] for x in observations
        if x["enabled"] == enabled) for label, enabled in (("off", False), ("on", True))}
    return dict(evidence_kind="OFFLINE_CPU_TIMER_ONLY_NOT_ROOT_ACCEPTANCE",
        observations=observations, medians_ms=medians,
        overhead_percent=(medians["on"] / medians["off"] - 1) * 100,
        outputs_equal=len({x["output"] for x in observations}) == 1,
        database_calls=0, root_overhead_acceptance="NOT_MEASURED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root-arm", choices=("off", "on"))
    args = parser.parse_args()
    if args.root_arm:
        root_arm(args.output, enabled=args.root_arm == "on")
        return
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(measure(), handle, indent=2)


def root_arm(output, *, enabled):
    """One isolated synthetic arm; invoke in a separately supervised process.

    Physical identity validation precedes app imports. This command does not
    provision a server or select a database from application configuration.
    A parent must enforce the registered 180-second setup/root deadlines.
    """
    from scripts.v14_test_database import isolated_v14_database, verified_test_url

    verified_test_url()
    if output.exists():
        raise ValueError("PERFORMANCE_EVIDENCE_ALREADY_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    import pytest
    from app.core.config import Settings

    Settings.model_config = {**Settings.model_config, "env_file": None}
    from app.core.config import get_settings
    from app.models.data_publication import DataPublication
    from app.models.job import JobRun
    from app.services import job_worker
    from app.services.calculation_policy import runtime_source, worker_source
    from app.services.recalculation import create_recalculation_job

    from tests.integration.test_business_recalc_performance import seed

    result = dict(enabled=enabled, status="INCOMPLETE", evidence_kind="LOCALIZATION_ONLY")
    # Keep a durable failure prefix even if native code kills this child.
    with output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle)
    with pytest.MonkeyPatch.context() as patch:
        settings = get_settings()
        patch.setattr(settings, "perf_diagnostics_enabled", enabled)
        patch.setattr(settings, "perf_diagnostics_directory", output.parent / "traces")
        try:
            with isolated_v14_database(patch) as (factory, engine):
                days = seed(factory, include_closed=False, history_days=420)
                patch.setattr(job_worker, "SessionLocal", factory)
                source = runtime_source()
                token = worker_source.set(source)
                try:
                    with factory() as db:
                        job = create_recalculation_job(db, start=days[-2], end=days[-1],
                                                      evaluate_signals=False, mode="manual")
                        assert job_worker.claim_next_job(db, "perf03-r1-synthetic") == job.id
                        db.refresh(job)
                        began = perf_counter()
                        job_worker.execute_claimed_job(db, job.id,
                            expected_worker=job.worker_id, expected_token=job.execution_token)
                        elapsed = (perf_counter() - began) * 1000
                        db.expire_all()
                        job = db.get(JobRun, job.id)
                        ledger = db.get(DataPublication, job.id)
                        result.update(root_id=str(job.id), job_status=job.status,
                            publication=ledger.state, source=source, wall_ms=elapsed,
                            status="COMPLETE" if job.status == "SUCCESS"
                                and ledger.state == "PUBLISHED" else "FAILED")
                finally:
                    worker_source.reset(token)
        except Exception as error:
            result.update(status="FAILED", error_type=type(error).__name__)
        finally:
            pending = output.with_suffix(".pending")
            pending.write_text(json.dumps(result, indent=2), encoding="utf-8")
            pending.replace(output)
    if result["status"] != "COMPLETE":
        raise RuntimeError("PERFORMANCE_ROOT_LOCALIZATION_INCOMPLETE")


if __name__ == "__main__":
    main()
