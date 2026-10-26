"""Fifth exact overlay, immutable historical manifests and full current FD walk."""

import hashlib
import json
import re

BASELINE = "5acc2e71c43cc77172e9caca103cc843c04d704d"
MANIFEST = "docs/acceptance/a42363_overlay_manifest.json"
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
        "scripts/a42361_deployment.py",
        "tests/unit/test_a4236_source_guard.py",
        "tests/unit/test_a42362_source_guard.py",
        "infra/g1_control_plane/003_closeout.sql",
        *(
            "scripts/a42363_" + n + ".py"
            for n in (
                "contract",
                "stores",
                "owner",
                "resources",
                "absence",
                "supervisor",
                "services",
                "review",
                "source_guard",
            )
        ),
        *("tests/unit/test_a42363_" + n + ".py" for n in ("red", "contracts", "source_guard")),
        "tests/integration_offline/test_a42363_process.py",
        *(
            "docs/acceptance/a42363_" + n + ".md"
            for n in (
                "baseline_and_red",
                "architecture_and_acl",
                "session_method_ADR",
                "resource_recovery",
                "supervisor_and_absence",
                "test_matrix",
                "capability_matrix",
                "closeout",
                "deployment_review_TEMPLATE",
            )
        ),
        MANIFEST,
    )
)
PINNED = STAGE_PATHS - {MANIFEST, "scripts/a4235_capability_guard.py"}
HISTORICAL = (
    "docs/acceptance/a42351_reviewer_overlay_manifest.json",
    "docs/acceptance/a4236_overlay_manifest.json",
    "docs/acceptance/a42361_overlay_manifest.json",
    "docs/acceptance/a42362_overlay_manifest.json",
)


def normalized(raw):
    pattern = rb"CLOSEOUT_MANIFEST_SHA = '[0-9a-f]{64}'"
    if len(re.findall(pattern, raw)) != 1:
        raise ValueError("A4235_LIVE_OVERLAY_INVALID")
    return re.sub(pattern, b"CLOSEOUT_MANIFEST_SHA = '" + b"0" * 64 + b"'", raw)


def validate_paths(paths):
    from scripts.a4235_calibration_adapter_contract import require

    require(set(paths) == STAGE_PATHS, "A4235_FROZEN_FILE_CHANGED")


def validate(g, root, head):
    from scripts import a42361_source_guard as fd_guard
    from scripts import a42362_source_guard as previous

    require = g.require
    require(g.path_sha(root / MANIFEST) == g.CLOSEOUT_MANIFEST_SHA, "A4235_LIVE_OVERLAY_INVALID")
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
        and data["schema_version"] == "a42363.exact-overlay.v1"
        and data["baseline_sha"] == BASELINE
        and data["stage_paths"] == sorted(STAGE_PATHS)
        and set(data["patch_sha256"]) == PINNED
        and set(data["historical_sha256"]) == set(HISTORICAL),
        "A4235_LIVE_OVERLAY_INVALID",
    )
    validate_paths(
        set(
            g.git(root, "diff", "--no-ext-diff", "--name-only", "-z", BASELINE).decode().split("\0")
        )
        - {""}
    )
    # Validate stage-four's exact historical diff and every pinned object BEFORE allowing
    # the new precise compatibility overlay. No old manifest is rewritten.
    previous.validate_paths(
        set(
            g.git(root, "diff", "--no-ext-diff", "--name-only", "-z", previous.BASELINE, BASELINE)
            .decode()
            .split("\0")
        )
        - {""}
    )
    for name in HISTORICAL:
        raw = g.git(root, "show", f"{BASELINE}:{name}")
        digest = hashlib.sha256(raw).hexdigest()
        require(g.path_sha(root / name) == digest, "A4235_LIVE_OVERLAY_INVALID")
        require(
            digest == data["historical_sha256"][name] and (root / name).read_bytes() == raw,
            "A4235_LIVE_OVERLAY_INVALID",
        )
        historical = json.loads(raw)
        for path, expected in historical["patch_sha256"].items():
            # Each stage's pinned objects must match its closing historical commit.
            # Stage 3/4 explicitly overlay a few older paths; verify that chain below.
            current = g.git(root, "show", f"{BASELINE}:{path}")
            if path not in fd_guard.STAGE_PATHS | previous.STAGE_PATHS:
                require(
                    hashlib.sha256(current).hexdigest() == expected,
                    "A4235_OVERLAY_BYTES_MISMATCH",
                )
    frozen = json.loads(g.git(root, "show", f"{BASELINE}:{previous.MANIFEST}"))
    require(
        g.path_sha(root / previous.MANIFEST) == g.SERVICE_MANIFEST_SHA, "A4235_LIVE_OVERLAY_INVALID"
    )
    for path in previous.PINNED:
        raw = g.git(root, "show", f"{BASELINE}:{path}")
        require(
            hashlib.sha256(raw).hexdigest() == frozen["patch_sha256"][path],
            "A4235_LIVE_OVERLAY_INVALID",
        )
        if path not in STAGE_PATHS:
            require(
                g.path_sha(root / path) == frozen["patch_sha256"][path],
                "A4235_LIVE_OVERLAY_INVALID",
            )
    for path in STAGE_PATHS:
        raw = (root / path).read_bytes()
        require(raw == g.git(root, "show", f"{head}:{path}"), "A4235_HEAD_BYTES_MISMATCH")
        if path in PINNED:
            require(
                g.path_sha(root / path) == data["patch_sha256"][path], "A4235_LIVE_OVERLAY_INVALID"
            )
        if path in data["old_sha256"]:
            old = g.git(root, "show", f"{BASELINE}:{path}")
            require(
                hashlib.sha256(old).hexdigest() == data["old_sha256"][path],
                "A4235_LIVE_OVERLAY_INVALID",
            )
            if path in AUTHORITY:
                require(raw.startswith(old), "A4235_FROZEN_FILE_CHANGED")
    require(
        hashlib.sha256(normalized((root / previous.OLD_GUARD).read_bytes())).hexdigest()
        == data["normalized_guard_sha256"],
        "A4235_LIVE_OVERLAY_INVALID",
    )
    previous.verify_inherited_checks(g, root, head)
    fd_guard.verify_full_worktree(g, root, head)
    require(
        head == g.git(root, "rev-parse", "HEAD").decode().strip()
        and not g.git(root, "status", "--porcelain").strip(),
        "A4235_DIRTY_TREE",
    )
    return g.CLOSEOUT_MANIFEST_SHA
