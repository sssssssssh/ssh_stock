"""Sixth exact overlay: five original manifests, historical blobs, full current FD walk."""

import hashlib
import json
import re

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


def normalized(raw):
    pattern = rb"COMPLETE_MANIFEST_SHA = '[0-9a-f]{64}'"
    if len(re.findall(pattern, raw)) != 1:
        raise ValueError("A4235_LIVE_OVERLAY_INVALID")
    return re.sub(pattern, b"COMPLETE_MANIFEST_SHA = '" + b"0" * 64 + b"'", raw)


def validate_paths(paths):
    from scripts.a4235_calibration_adapter_contract import require

    require(set(paths) == STAGE_PATHS, "A4235_FROZEN_FILE_CHANGED")


def validate(g, root, head):
    from scripts import a42361_source_guard as fd_guard
    from scripts import a42362_source_guard as layer4
    from scripts import a42363_source_guard as layer5

    require = g.require
    require(g.path_sha(root / MANIFEST) == g.COMPLETE_MANIFEST_SHA, "A4235_LIVE_OVERLAY_INVALID")
    data = json.loads((root / MANIFEST).read_bytes())
    require(
        set(data)
        == {
            "schema_version",
            "baseline_sha",
            "stage_paths",
            "patch_sha256",
            "old_sha256",
            "historical_sha256",
            "normalized_guard_sha256",
        }
        and data["schema_version"] == "a42363.complete-overlay.v1"
        and data["baseline_sha"] == BASELINE
        and data["stage_paths"] == sorted(STAGE_PATHS)
        and set(data["patch_sha256"]) == PINNED
        and set(data["historical_sha256"]) == set(HISTORICAL),
        "A4235_LIVE_OVERLAY_INVALID",
    )
    paths = set(
        g.git(root, "diff", "--no-ext-diff", "--name-only", "-z", BASELINE).decode().split("\0")
    ) - {""}
    validate_paths(paths)
    layer5.validate_paths(
        set(
            g.git(root, "diff", "--no-ext-diff", "--name-only", "-z", layer5.BASELINE, BASELINE)
            .decode()
            .split("\0")
        )
        - {""}
    )
    # Every historical pin is independently checked at its actual closing commit.
    # Current changes require this layer's exact path AND new committed byte pin.
    for path, closing in HISTORICAL.items():
        raw = g.git(root, "show", f"{BASELINE}:{path}")
        require(
            raw == (root / path).read_bytes()
            and hashlib.sha256(raw).hexdigest() == data["historical_sha256"][path],
            "A4235_LIVE_OVERLAY_INVALID",
        )
        old = json.loads(raw)
        for name, expected in old["patch_sha256"].items():
            require(
                hashlib.sha256(g.git(root, "show", f"{closing}:{name}")).hexdigest() == expected,
                "A4235_OVERLAY_BYTES_MISMATCH",
            )
    legacy = json.loads(g.git(root, "show", f"{BASELINE}:{layer5.MANIFEST}"))
    require(
        g.path_sha(root / layer5.MANIFEST) == g.CLOSEOUT_MANIFEST_SHA, "A4235_LIVE_OVERLAY_INVALID"
    )
    for path in layer5.PINNED - STAGE_PATHS:
        require(
            g.path_sha(root / path) == legacy["patch_sha256"][path], "A4235_LIVE_OVERLAY_INVALID"
        )
    old_paths = set()
    for path in STAGE_PATHS:
        raw = (root / path).read_bytes()
        require(raw == g.git(root, "show", f"{head}:{path}"), "A4235_HEAD_BYTES_MISMATCH")
        if path in PINNED:
            require(
                hashlib.sha256(raw).hexdigest() == data["patch_sha256"][path],
                "A4235_LIVE_OVERLAY_INVALID",
            )
        exists = g.git(root, "ls-tree", "-z", BASELINE, "--", path)
        if exists:
            old_paths.add(path)
            old = g.git(root, "show", f"{BASELINE}:{path}")
            require(
                hashlib.sha256(old).hexdigest() == data["old_sha256"].get(path),
                "A4235_LIVE_OVERLAY_INVALID",
            )
            if path in AUTHORITY:
                require(raw.startswith(old), "A4235_FROZEN_FILE_CHANGED")
    require(set(data["old_sha256"]) == old_paths, "A4235_LIVE_OVERLAY_INVALID")
    require(
        hashlib.sha256(normalized((root / layer4.OLD_GUARD).read_bytes())).hexdigest()
        == data["normalized_guard_sha256"],
        "A4235_LIVE_OVERLAY_INVALID",
    )
    layer4.verify_inherited_checks(g, root, head)
    fd_guard.verify_full_worktree(g, root, head)
    require(
        head == g.git(root, "rev-parse", "HEAD").decode().strip()
        and not g.git(root, "status", "--porcelain").strip(),
        "A4235_DIRTY_TREE",
    )
    return g.COMPLETE_MANIFEST_SHA
