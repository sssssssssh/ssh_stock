"""P0-only historical replay with the exact neighbouring C0 samples; no DB/config."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.a42_artifacts import atomic  # noqa: E402
from scripts.a42_receipt_contract import require  # noqa: E402
from scripts.publication_lookup_tail_review_a423 import (  # noqa: E402
    SOURCE_ARTIFACT,
    SOURCE_DIGEST,
    SOURCE_RUN,
    SOURCE_SHA,
    load_source,
    project,
    review,
)

BASELINE_SHA = "3bdfc3713fea595eaf913bbc347e76510d340b60"


def historical_replay(source, raw_digest):
    original = review(source, raw_digest)  # Revalidate all 1100 samples, order and quantiles.
    ordered = source["samples"]
    c0 = [(index, sample) for index, sample in enumerate(ordered)
          if sample["statistics"] == "analyzed" and sample["variant"] == "C0"
          and sample["table"] == "stock_trade_status_daily"]
    limit = next(g["c0_p95_limit"] for g in original["groups"]
                 if g["statistics"] == "analyzed" and g["variant"] == "C1")

    def point(index, sample):
        return dict(source_sample_index=index, rotation_position=index % 5, **project(sample))

    anomalies = []
    for index, sample in enumerate(ordered):
        if not (sample["statistics"] == "analyzed" and sample["variant"] == "C1"
                and sample["table"] == "stock_trade_status_daily"
                and sample["wall_seconds"] > limit):
            continue
        matched = next((i, s) for i, s in c0 if s["repeat"] == sample["repeat"])
        previous = next(((i, s) for i, s in reversed(c0) if i < index), None)
        following = next(((i, s) for i, s in c0 if i > index), None)
        anomalies.append(dict(c1=point(index, sample), c0_same_repeat=point(*matched),
            c0_previous=point(*previous) if previous else None,
            c0_following=point(*following) if following else None))
    require([row["c1"]["repeat"] for row in anomalies] == [5, 13, 19, 25, 41, 66, 81],
            "A4231_HISTORICAL_TAIL_CHANGED")
    return dict(schema_version="a4231-historical-replay-v1",
        evidence_kind="HISTORICAL_NOT_ACCEPTANCE", baseline_sha=BASELINE_SHA,
        source_sha=SOURCE_SHA, source_run_id=SOURCE_RUN, source_attempt=1,
        source_artifact_id=SOURCE_ARTIFACT, source_zip_sha256=SOURCE_DIGEST,
        source_json_sha256=raw_digest, original_review=original,
        analyzed_c1_anomalies_with_c0_neighbours=anomalies,
        tail_causality="CORRELATED_NOT_CAUSAL", capacity_ready=False,
        production_read_authorized=False, p2="NOT_AUTHORIZED", p3="NOT_AUTHORIZED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "A4231_OUTPUT_EXISTS_NO_OVERWRITE")
    value, raw_digest = load_source(args.archive)
    atomic(args.output, historical_replay(value, raw_digest))
    print("A4231_HISTORICAL_REPLAY_COMPLETE_NOT_ACCEPTANCE")


if __name__ == "__main__":
    main()
