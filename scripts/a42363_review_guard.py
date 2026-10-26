"""Seventh exact overlay and cumulative compatibility view; historical manifests immutable."""

import hashlib
import json

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


def validate_paths(paths):
    from scripts.a4235_calibration_adapter_contract import require

    require(set(paths) == STAGE_PATHS, "A4235_FROZEN_FILE_CHANGED")


def validate(g, root, head):
    from scripts import a42361_source_guard as fd_guard
    from scripts import a42362_source_guard as inherited
    from scripts import a42363_complete_guard as previous

    require = g.require
    require(g.path_sha(root / MANIFEST) == g.COMPLETE_MANIFEST_SHA, "A4235_LIVE_OVERLAY_INVALID")
    data = json.loads((root / MANIFEST).read_bytes())
    require(
        set(data)
        == {
            "schema_version",
            "baseline_sha",
            "stage_paths",
            "cumulative_paths",
            "patch_sha256",
            "old_sha256",
            "historical_sha256",
            "normalized_guard_sha256",
        }
        and data["schema_version"] == "a42363.review-overlay.v1"
        and data["baseline_sha"] == BASELINE
        and data["stage_paths"] == sorted(STAGE_PATHS)
        and data["cumulative_paths"] == sorted(previous.STAGE_PATHS)
        and set(data["patch_sha256"]) == previous.PINNED
        and set(data["historical_sha256"]) == set(HISTORICAL),
        "A4235_LIVE_OVERLAY_INVALID",
    )
    validate_paths(
        set(
            g.git(root, "diff", "--no-ext-diff", "--name-only", "-z", BASELINE).decode().split("\0")
        )
        - {""}
    )
    require(
        set(
            g.git(root, "diff", "--no-ext-diff", "--name-only", "-z", previous.BASELINE, BASELINE)
            .decode()
            .split("\0")
        )
        - {""}
        == previous.LEGACY_STAGE_PATHS,
        "A4235_FROZEN_FILE_CHANGED",
    )
    for path, closing in HISTORICAL.items():
        raw = g.git(root, "show", f"{BASELINE}:{path}")
        require(
            raw == (root / path).read_bytes()
            and hashlib.sha256(raw).hexdigest() == data["historical_sha256"][path],
            "A4235_LIVE_OVERLAY_INVALID",
        )
        for name, expected in json.loads(raw)["patch_sha256"].items():
            require(
                hashlib.sha256(g.git(root, "show", f"{closing}:{name}")).hexdigest() == expected,
                "A4235_OVERLAY_BYTES_MISMATCH",
            )
    for path in previous.STAGE_PATHS:
        raw = (root / path).read_bytes()
        require(raw == g.git(root, "show", f"{head}:{path}"), "A4235_HEAD_BYTES_MISMATCH")
        if path in previous.PINNED:
            require(
                hashlib.sha256(raw).hexdigest() == data["patch_sha256"][path],
                "A4235_LIVE_OVERLAY_INVALID",
            )
    old_paths = set()
    for path in STAGE_PATHS:
        if g.git(root, "ls-tree", "-z", BASELINE, "--", path):
            old_paths.add(path)
            before = g.git(root, "show", f"{BASELINE}:{path}")
            require(
                hashlib.sha256(before).hexdigest() == data["old_sha256"].get(path),
                "A4235_LIVE_OVERLAY_INVALID",
            )
            if path in AUTHORITY:
                require((root / path).read_bytes().startswith(before), "A4235_FROZEN_FILE_CHANGED")
    require(set(data["old_sha256"]) == old_paths, "A4235_LIVE_OVERLAY_INVALID")
    require(
        hashlib.sha256(
            previous.normalized((root / "scripts/a4235_capability_guard.py").read_bytes())
        ).hexdigest()
        == data["normalized_guard_sha256"],
        "A4235_LIVE_OVERLAY_INVALID",
    )
    # No old test is edited to accommodate this view. Every historical test blob must
    # still match the actual baseline, including the source-guard compatibility tests.
    for row in g.git(root, "ls-tree", "-r", "-z", BASELINE, "--", "tests").split(b"\0"):
        if not row:
            continue
        metadata, name = row.split(b"\t", 1)
        path = name.decode()
        mode, kind, oid = metadata.split()
        require(mode in (b"100644", b"100755") and kind == b"blob", "A4235_FROZEN_FILE_CHANGED")
        raw = (root / path).read_bytes()
        require(
            hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest().encode()
            == oid,
            "A4235_FROZEN_FILE_CHANGED",
        )
    inherited.verify_inherited_checks(g, root, head)
    fd_guard.verify_full_worktree(g, root, head)
    require(
        head == g.git(root, "rev-parse", "HEAD").decode().strip()
        and not g.git(root, "status", "--porcelain").strip(),
        "A4235_DIRTY_TREE",
    )
    return g.COMPLETE_MANIFEST_SHA
