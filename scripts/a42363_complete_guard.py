"""Sixth exact overlay: five original manifests, historical blobs, full current FD walk."""

import re

from scripts.a42363_review_guard import MANIFEST as REVIEW_MANIFEST
from scripts.a42363_review_guard import PINNED as REVIEW_PINNED
from scripts.a42363_review_guard import STAGE_PATHS as REVIEW_PATHS

BASELINE = "d31b07a4e33d50ac00ade3e1eff60e091fe78041"
MANIFEST = "docs/acceptance/a42363_complete_overlay_manifest.json"
AUTHORITY = frozenset(
    (
        "README.md",
        "PROJECT_RULES.md",
        "docs/股票机会发现系统_PRD_V1.0.md",
        "docs/股票机会发现系统_系统设计_V1.0.md",
    )
)
STAGE_PATHS = AUTHORITY | frozenset(
    (
        "scripts/a4235_capability_guard.py",
        "scripts/a42361_source_guard.py",
        *(
            "scripts/a42363_" + n + ".py"
            for n in (
                "contract",
                "identity",
                "harness",
                "rpc",
                "owner",
                "resources",
                "absence",
                "supervisor",
                "services",
                "stores",
                "review",
                "complete_guard",
            )
        ),
        "tests/unit/test_a4236_source_guard.py",
        "tests/unit/test_a42362_source_guard.py",
        "tests/unit/test_a42363_complete.py",
        "tests/unit/test_a42363_complete_guard.py",
        "tests/integration_offline/test_a42363_complete_process.py",
        *(
            "docs/acceptance/a42363_complete_" + n + ".md"
            for n in (
                "baseline",
                "architecture",
                "protocol_ADR",
                "platform_ADR",
                "runbook",
                "test_matrix",
                "closeout",
            )
        ),
        MANIFEST,
    )
)
PINNED = STAGE_PATHS - {MANIFEST, "scripts/a4235_capability_guard.py"}
HISTORICAL = {
    "docs/acceptance/a42351_reviewer_overlay_manifest.json": (
        "af08f8724e988121402988b4e8fb70c8ef5b53f2"
    ),
    "docs/acceptance/a4236_overlay_manifest.json": "6d54841522bc013ad21a52bc45d75218de2d9ce6",
    "docs/acceptance/a42361_overlay_manifest.json": "b32b9271596d92cfbec571fd3170aacbe17370cd",
    "docs/acceptance/a42362_overlay_manifest.json": "5acc2e71c43cc77172e9caca103cc843c04d704d",
    "docs/acceptance/a42363_overlay_manifest.json": BASELINE,
}

# The original six-stage declaration and manifest remain immutable historical data.
# Existing consumers ask this facade for the current cumulative view. The seventh
# guard separately checks the exact a8a675e delta and ALL original test/blob bytes.
LEGACY_MANIFEST, LEGACY_STAGE_PATHS, LEGACY_PINNED = MANIFEST, STAGE_PATHS, PINNED

MANIFEST = REVIEW_MANIFEST
STAGE_PATHS = LEGACY_STAGE_PATHS | REVIEW_PATHS
PINNED = LEGACY_PINNED | REVIEW_PINNED


def normalized(raw):
    pattern = rb"COMPLETE_MANIFEST_SHA = '[0-9a-f]{64}'"
    if len(re.findall(pattern, raw)) != 1:
        raise ValueError("A4235_LIVE_OVERLAY_INVALID")
    return re.sub(pattern, b"COMPLETE_MANIFEST_SHA = '" + b"0" * 64 + b"'", raw)


def validate_paths(paths):
    from scripts.a4235_calibration_adapter_contract import require

    require(set(paths) == STAGE_PATHS, "A4235_FROZEN_FILE_CHANGED")


def validate(g, root, head):
    from scripts.a42363_review_guard import validate as current_validate

    return current_validate(g, root, head)
