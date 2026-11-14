"""Read fixed P1-04 OFFLINE_FIXTURE inputs; describe hypotheses, never execute."""

import argparse
import sys
from pathlib import Path

from scripts import biz_perf_p1_04_diagnostic as d
from scripts import biz_perf_p1_04_measure_wiring as wiring

MAX_REPORT_BYTES = 2 * 1024**2
FOCUS = (
    "factors.compute", "candidate_lookup_batch", "candidate_store_batch", "publication.verify",
)
LIMITATIONS = (
    "ROOT_EXCLUDES_POST_ROOT_VALIDATION",
    "WORKER_IS_CHILD_OF_ROOT_DO_NOT_ADD",
    "STAGE_INCLUSIVE_OVERLAP_DO_NOT_SUM_OR_TREAT_AS_GLOBAL_SHARES",
    "SQL_AND_FETCH_MAY_OVERLAP_DO_NOT_SUM",
    "SQL_EXECUTE_IS_NOT_SERVER_CPU_OR_NETWORK_TIME",
    "RSS_IS_PROCESS_LIFETIME_HIGH_WATER_MARK_NOT_STAGE_ALLOCATION",
    "FIXTURE_SORT_IS_NOT_A_PROVEN_BOTTLENECK",
    "NO_REAL_RESOURCE_OR_SOURCE_AUTHENTICATION",
    "NO_SPEEDUP_PERCENTILES_OR_QUERY_PLAN_CLAIM",
)


def gates():
    return dict(
        source_evidence_kind=wiring.EVIDENCE_KIND, status="HYPOTHESIS_ONLY",
        hotspot_decision="NONE_PROVEN", root_attempts=0,
        b_gate="NOT_APPROVED", targeted_pg17_gate="NOT_APPROVED",
        authorization="AUTHORIZATION_PENDING", budget="DRAFT_NOT_APPROVED",
        production_read_authorized=False,
    )


class ReportRejected(ValueError):
    """Messages are fixed codes, never input or exception text."""


def summarize_offline(input_dir, expected_sha):
    """Replay preflight.json/events.jsonl without writing validator artifacts.

    The caller supplies a trusted, stable fixture directory and an external SHA.
    Even a perfectly forged fixture can only yield HYPOTHESIS_ONLY. No admission,
    journal, executor, environment configuration, or application is consulted.
    """
    try:
        return _summarize(input_dir, expected_sha)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        raise ReportRejected("PRETEST_EVIDENCE_REJECTED") from None


def _summarize(input_dir, expected_sha):
    d.require(type(input_dir) in (str, Path, type(Path()))
              and d.hex_value(expected_sha, 40), "EVIDENCE_INVALID")
    source = d.directory(input_dir)
    preflight_raw = d.read_file(source / "preflight.json", d.MAX_LINE_BYTES)
    contract = d.preflight(d.decode(preflight_raw), expected_sha)
    raw = d.read_file(source / "events.jsonl", d.MAX_RAW_BYTES)
    d.require(raw.endswith(b"\n"), "EVIDENCE_INCOMPLETE")
    replay = d.Replay(contract)
    for line in raw.splitlines(keepends=True):
        d.require(line.endswith(b"\n") and len(line) <= d.MAX_LINE_BYTES,
                  "EVIDENCE_INVALID")
        event = d.decode(line)
        if type(event) is dict and event.get("event_kind") == "root_started":
            # Reuse E02's read-only digest predicate; Replay checks the binding.
            d.require(wiring._hex64(event.get("preflight_sha256")), "IDENTITY_REJECTED")
        replay.accept(event)
    summary = replay.summary()  # Sole authority for completeness and stage semantics.
    snapshot, post = replay.snapshot, replay.post
    observations = summary["stage_observations"]
    result = dict(
        **gates(), evidence_complete=summary["evidence_complete"],
        measurement_implementation_sha=contract["measurement_implementation_sha"],
        run_uuid=contract["run_uuid"], root_job_id=replay.root_id,
        measurement_boundary=d.BOUNDARY,
        root_elapsed_ms=snapshot["root_elapsed_ms"],
        execute_claimed_job_ms=snapshot["execute_claimed_job_ms"],
        post_root_validation_ms=post["post_root_validation_ms"],
        sql_snapshot=snapshot["sql_snapshot"],
        sql_calls=snapshot["sql_snapshot"]["total"],
        # The root snapshot has counts but no root SQL duration field. Stage
        # durations cannot be summed to manufacture that missing observation.
        sql_execute_ms=d.UNKNOWN,
        fetch_observed_ms=snapshot["fetch_observed_ms"],
        fetched_rows=snapshot["fetched_rows"],
        process_cpu_ms=snapshot["process_cpu_ms"], rss_peak_bytes=snapshot["rss_peak_bytes"],
        wall_per_cpu=summary["wall_per_cpu"], aggregation=summary["aggregation"],
        fixture_stage_top3=summary["fixture_stage_top3"],
        stage_observations=observations,
        diagnostic_positions={
            "factors.input_verify": dict(
                coverage_reason=wiring.NOT_INSTRUMENTED, stage_inclusive_ms=d.UNKNOWN,
                mapping="SOURCE_PROGRESS_NAME_ABSENT_FROM_FROZEN_STAGE_ALLOWLIST",
            ),
            **{name: [row for row in observations if row["stage_name"] == name]
               for name in FOCUS},
        },
        investigation_priorities=[
            dict(hypothesis="H01_INPUT_WINDOW_FINGERPRINT", status="HYPOTHESIS"),
            dict(hypothesis="H02_CANDIDATE_LOOKUP_SERIALIZATION_STORE", status="HYPOTHESIS"),
            dict(hypothesis="H03_PUBLICATION_VERIFY_OVERLAP", status="HYPOTHESIS"),
        ],
        limitations=list(LIMITATIONS), real_measurement="REAL_NOT_RUN",
    )
    d.require(len(d.encode(result)) <= MAX_REPORT_BYTES, "SIZE_LIMIT")
    return result


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ReportRejected("PRETEST_ARGUMENTS_REJECTED")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    result = None
    if argv and argv[0] == "execute":
        result = dict(**gates(), error_code="AUTHORIZATION_PENDING", evidence_complete=False)
    else:
        try:
            parser = Parser(add_help=False, allow_abbrev=False)
            parser.add_argument("command", choices=["summarize-offline"])
            parser.add_argument("--input-dir", required=True)
            parser.add_argument("--expected-implementation-sha", required=True)
            args = parser.parse_args(argv)
            result = summarize_offline(args.input_dir, args.expected_implementation_sha)
        except ReportRejected as exc:
            result = dict(**gates(), error_code=str(exc), evidence_complete=False)
    sys.stdout.write(d.encode(result).decode("ascii"))
    return 0 if result["evidence_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
