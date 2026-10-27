"""Seventh exact overlay and cumulative compatibility view; historical manifests immutable."""

from scripts.a42364_source_guard import MANIFEST as ENGINEERING_MANIFEST
from scripts.a42364_source_guard import PINNED as ENGINEERING_PINNED
from scripts.a42364_source_guard import STAGE_PATHS as ENGINEERING_PATHS

BASELINE = "a8a675ea8b93dadbba9e905a7a4af67eba163d99"
MANIFEST = "docs/acceptance/a42363_review_overlay_manifest.json"
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
        "scripts/a42363_complete_guard.py",
        *(
            "scripts/a42363_" + n + ".py"
            for n in (
                "resources",
                "harness",
                "owner",
                "absence",
                "supervisor",
                "services",
                "review",
                "proposals",
                "installation",
                "review_guard",
            )
        ),
        "tests/unit/test_a42363_review.py",
        "tests/unit/test_a42363_review_guard.py",
        "tests/integration_offline/test_a42363_review_process.py",
        *(
            "docs/acceptance/a42363_review_" + n + ".md"
            for n in (
                "baseline",
                "architecture",
                "ADR_BOOTSTRAP_AND_BUDGET",
                "ADR_SAFE_VOLUME_DISPOSAL",
                "ADR_TARGET_SESSION_GUC",
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
    "docs/acceptance/a42363_overlay_manifest.json": "d31b07a4e33d50ac00ade3e1eff60e091fe78041",
    "docs/acceptance/a42363_complete_overlay_manifest.json": BASELINE,
}

# Preserve the seventh-stage declarations as history. The current compatibility
# facade includes only the independently validated eighth exact overlay.
LEGACY_MANIFEST, LEGACY_STAGE_PATHS, LEGACY_PINNED = MANIFEST, STAGE_PATHS, PINNED
MANIFEST = ENGINEERING_MANIFEST
STAGE_PATHS = LEGACY_STAGE_PATHS | ENGINEERING_PATHS
PINNED = LEGACY_PINNED | ENGINEERING_PINNED


def validate_paths(paths):
    from scripts.a4235_calibration_adapter_contract import require

    require(set(paths) == STAGE_PATHS, "A4235_FROZEN_FILE_CHANGED")


def validate(g, root, head):
    from scripts.a42364_source_guard import validate as current_validate

    return current_validate(g, root, head)
