"""Scope adapter reusing the frozen fixture, trial, and actual-plan probes."""

import argparse
import subprocess
import sys
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter

from scripts.a42_artifacts import (
    ScopedOutput,
    Writer,
    container_receipt,
    install_signals,
    isolation,
)
from scripts.a42_ci_contract import SCALES, expected_groups, shards
from scripts.a42_receipt_contract import require, validate_set


def parse(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True, choices=[s.job_id for s in shards()])
    parser.add_argument("--scope", choices=sorted({s.scope for s in shards()}))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--container", required=True)
    args = parser.parse_args(argv)
    args.shard = next(s for s in shards() if s.job_id == args.job_id)
    if args.scope and args.scope != args.shard.scope:
        parser.error("scope and job-id disagree; no implicit fixture overrides")
    return args


def ordered(groups):
    # Keep whole monthly chains adjacent. Rotate variants/windows each repeat,
    # preserving the same alternating order as the old runner (no fast filtering).
    variants = list(dict.fromkeys(g.variant for g in sorted(groups, key=lambda g:g.variant)))
    def key(g):
        r = g.repeat or 0
        return (g.kind == "plan", r, g.fraction,
                (variants.index(g.variant)-r) % len(variants),
                ((-1 if g.window_days is None else (1,3,5,10,20).index(g.window_days))-r) % 6,
                g.scope)
    return sorted(groups, key=key)


def execute(args, output, db, engine, job, params, trial, captured):
    from sqlalchemy import text

    from scripts.ab_read_experiment_v14_a4_2 import observe
    from scripts.ab_read_profile_v14_a4 import (
        Profile,
        capture_plans,
        cursor_actual_plans,
        lock_probe,
    )

    writer = output.writer
    groups = args.active_groups
    output["phase"] = "scoped_trials"
    for group in ordered(groups):
        writer.begin(group)
        scope = group.scope.removeprefix("event_")
        is_month = scope.startswith("month_")

        def read(g, scope):
            monthly = scope.startswith("month_")
            kwargs = dict(cursor_fraction=g.fraction, window_days=g.window_days)
            if monthly:
                month = int(scope[-1])
                lo = date(2025, month, 1)
                hi = date(2025, month+1, 1)-timedelta(days=1)
                kwargs.update(values={**params, "lo":lo-timedelta(days=430), "hi":hi},
                    carry=month>1, service_call=True, verify_final=month==3)
            record = trial(g.variant, scope=g.scope, repeat=g.repeat,
                           **kwargs)
            if monthly:
                record.update(input_start=str(lo-timedelta(days=430)), input_end=str(hi),
                    chunk_start=str(lo), chunk_end=str(hi), monthly_protocol="ROOT_TAIL_ONLY",
                    logical_root=f"{job.id}:{g.variant}:{g.repeat}")
            # Bound in-memory records too; raw groups live in independent files.
            output["runs"].clear()
            return record

        if group.kind == "read":
            record = read(group, scope)
        else:
            # Actual-plan jobs capture the actual read statements independently;
            # monthly prelude keeps the real root lifecycle, never fake carries.
            if is_month:
                for month in range(1, int(scope[-1])+1):
                    warmup = replace(group, kind="read", repeat=0, scope=f"month_{month}")
                    read(warmup, warmup.scope)
                key = (group.variant, group.fraction, group.scope, group.window_days)
            else:
                read(replace(group, kind="read", repeat=0), scope)
                key = (group.variant, group.fraction, group.scope, group.window_days)
            statements = captured[key]
            db.execute(text("SELECT set_config('cursor_tuple_fraction',:f,true)"),
                       {"f":group.fraction})
            started = perf_counter()
            select = capture_plans(db, statements)
            profile = Profile(db, engine)
            with observe(profile):
                actual = cursor_actual_plans(db, statements)
            cursors = profile.receipt()["cursors"]
            declared = [p for p in actual if "DECLARE" in p.get("Query Text", "").upper()]
            record = dict(select_and_cursor_estimate=select, actual_cursor_untimed=declared,
                probe_cursors=cursors, expected_cursor_plans=len(cursors),
                untimed_plan_seconds=perf_counter()-started)
        writer.complete(group, record, output)
    output["lock_probe_outside_timed_trials"] = lock_probe(db, engine)
    writer.checkpoint(output)


def main(argv=None):
    from scripts.ab_read_experiment_v14_a4_2 import laboratory_sources, run, source_contract

    args = parse(argv)
    groups = expected_groups(args.shard)
    writer = Writer(args.output, args.job_id, groups, minutes=args.shard.timeout_minutes-5)
    install_signals()
    try:
        writer.manifest.update(container_receipt(args.container, read=True))
        writer.manifest.update(isolation())
        source_contract()
        require(not writer.manifest["working_tree_dirty"], "CLEAN_HEAD_REQUIRED")
        output = ScopedOutput(writer, laboratory_sources=laboratory_sources())
        args.public_rows, args.candidate_rows, args.other_rows = SCALES[args.shard.scale]
        args.repeats, args.reader_pause = 3, 5
        args.variants = tuple(sorted({g.variant for g in groups}))
        args.readers = max(g.readers for g in groups)
        args.monthly = args.window_matrix = args.plans = False
        args.cursor_fractions = sorted({g.fraction for g in groups})
        for coverage,tombstones in sorted({(g.coverage,g.tombstones) for g in groups}):
            args.coverage, args.tombstones = coverage,tombstones
            args.active_groups = {g for g in groups
                                  if (g.coverage,g.tombstones)==(coverage,tombstones)}
            started = perf_counter()
            run(args, output)
            writer.manifest.setdefault("fixture_scope_seconds", {})[
                f"{coverage}-{tombstones}"] = perf_counter()-started
        # Real set validation (checks compressed records and golden), not counts.
        from scripts.a42_gate_io import load_groups

        receipts = load_groups(args.output, writer.manifest)
        validate_set(receipts, groups, head=writer.manifest["head_sha"],
            attempt=writer.manifest["attempt"], job_id=args.job_id,
            model_hash=writer.manifest["model_hash"])
        require(writer.manifest["head_sha"] == subprocess.check_output([
            "git", "rev-parse", "HEAD"], text=True).strip(), "HEAD_CHANGED_DURING_JOB")
        writer.finish()
    except BaseException as error:
        writer.fail(error)
        raise SystemExit(1) from None


if __name__ == "__main__":
    sys.exit(main())
