"""Tenth exact overlay. Nine prior manifests are immutable historical contracts."""

import hashlib
import json
import re
from pathlib import Path

BASELINE = "2c8870f67d65e20465ad8a88affac3e1b32e9da3"
MANIFEST = "docs/acceptance/a42365_overlay_manifest.json"
GUARD = "scripts/a4235_capability_guard.py"
AUTHORITY = (
    "README.md",
    "PROJECT_RULES.md",
    "docs/股票机会发现系统_PRD_V1.0.md",
    "docs/股票机会发现系统_系统设计_V1.0.md",
)
COMPATIBILITY = frozenset(
    (GUARD, "scripts/business_source_contract.py", "scripts/a42364_manager.py")
)


def normalized(raw):
    pattern = rb"A42365_MANIFEST_SHA = '[0-9a-f]{64}'"
    if len(re.findall(pattern, raw)) != 1:
        raise ValueError("A42365_NORMALIZED_GUARD")
    return re.sub(pattern, b"A42365_MANIFEST_SHA = '" + b"0" * 64 + b"'", raw)


def validate_paths(paths):
    from scripts.a42363_contract import require

    require(
        all(
            p in (*AUTHORITY, *COMPATIBILITY, MANIFEST)
            or re.fullmatch(r"scripts/a42365_[a-z_]+\.py", p)
            or re.fullmatch(r"tests/unit/test_a42365_[a-z_]+\.py", p)
            or re.fullmatch(r"docs/acceptance/a42365_[a-z0-9_]+\.md", p)
            for p in paths
        ),
        "A42365_UNREGISTERED_PATH",
    )


def verify(g, root, head):
    from scripts import a42361_source_guard as fd_guard
    from scripts import a42364_source_guard as legacy
    from scripts import business_source_contract as business

    root = Path(root)
    g.require(re.fullmatch(r"[0-9a-f]{40}", head) is not None, "A4235_FULL_SHA_REQUIRED")
    g.require(
        head == business.git(root, "rev-parse", "HEAD").decode().strip(), "A4235_HEAD_MISMATCH"
    )
    g.require(not g.git(root, "status", "--porcelain").strip(), "A4235_DIRTY_TREE")
    g.require(g.path_sha(root / MANIFEST) == g.A42365_MANIFEST_SHA, "A4235_LIVE_OVERLAY_INVALID")
    data = json.loads((root / MANIFEST).read_bytes())
    g.require(
        set(data)
        == {
            "version",
            "baseline_sha",
            "stage_paths",
            "patch_sha256",
            "normalized_guard_sha256",
            "historical_manifest_sha256",
        }
        and data["version"] == "a42365.source.v4"
        and data["baseline_sha"] == BASELINE,
        "A4235_LIVE_OVERLAY_INVALID",
    )
    changed = set(g.git(root, "diff", "--name-only", "-z", BASELINE).decode().split("\0")) - {""}
    validate_paths(changed)
    g.require(changed == set(data["stage_paths"]), "A4235_FROZEN_FILE_CHANGED")
    g.require(
        set(data["patch_sha256"]) == changed - {MANIFEST, GUARD}, "A4235_LIVE_OVERLAY_INVALID"
    )
    for path, digest in data["patch_sha256"].items():
        g.require(g.path_sha(root / path) == digest, "A4235_HEAD_BYTES_MISMATCH")
    g.require(
        hashlib.sha256(normalized((root / GUARD).read_bytes())).hexdigest()
        == data["normalized_guard_sha256"],
        "A4235_LIVE_OVERLAY_INVALID",
    )
    histories = {
        **legacy.HISTORICAL,
        legacy.MANIFEST: business.HISTORICAL_SOURCE,
        business.MANIFEST: BASELINE,
    }
    g.require(
        set(data["historical_manifest_sha256"]) == set(histories), "A4235_LIVE_OVERLAY_INVALID"
    )
    old_manifests = business.git_blobs(root, [BASELINE + ":" + p for p in histories])
    for path, closing in histories.items():
        old = old_manifests[BASELINE + ":" + path]
        g.require(
            old == (root / path).read_bytes()
            and g.path_sha(root / path)
            == data["historical_manifest_sha256"][path]
            == hashlib.sha256(old).hexdigest(),
            "A4235_OVERLAY_BYTES_MISMATCH",
        )
        pins = json.loads(old)["patch_sha256"]
        blobs = business.git_blobs(root, [closing + ":" + p for p in pins])
        for p, digest in pins.items():
            g.require(
                hashlib.sha256(blobs[closing + ":" + p]).hexdigest() == digest,
                "A4235_OVERLAY_BYTES_MISMATCH",
            )
    # Compare all baseline paths, not just selected trees. Old tests/infra/config
    # and dependencies cannot be edited under a directory-wide whitelist.
    entries = [
        r.split(b"\t", 1)[1].decode()
        for r in business.git(root, "ls-tree", "-r", "-z", BASELINE).split(b"\0")
        if r
    ]
    originals = business.git_blobs(root, [BASELINE + ":" + p for p in entries])
    old_guard = originals[BASELINE + ":" + GUARD]
    business_literal = b"BUSINESS_MANIFEST_SHA = '" + g.BUSINESS_MANIFEST_SHA.encode() + b"'"
    expected_guard = old_guard.replace(
        business_literal, business_literal + b"\nA42365_MANIFEST_SHA = '" + b"0" * 64 + b"'"
    )
    g.require(
        normalized((root / GUARD).read_bytes()) == expected_guard, "A4235_OVERLAY_BYTES_MISMATCH"
    )
    for p in entries:
        old, current = originals[BASELINE + ":" + p], (root / p).read_bytes()
        if p in AUTHORITY:
            g.require(current.startswith(old), "A4235_FROZEN_FILE_CHANGED")
        elif p not in COMPATIBILITY:
            g.require(current == old, "A4235_FROZEN_FILE_CHANGED")
    # Preserve independent-reader negative injection checks from prior stages.
    original_paths = g.PATCH_PATHS | g.NEXT_PATCH_PATHS
    hist = business.git_blobs(root, [business.HISTORICAL_SOURCE + ":" + p for p in original_paths])
    for p in original_paths:
        old = hist[business.HISTORICAL_SOURCE + ":" + p]
        expected = data["patch_sha256"].get(
            p, hashlib.sha256(originals[BASELINE + ":" + p]).hexdigest()
        )
        if p == GUARD:
            expected = hashlib.sha256((root / GUARD).read_bytes()).hexdigest()
        g.require(
            g.git(root, "show", business.HISTORICAL_SOURCE + ":" + p) == old
            and g.path_sha(root / p) == expected,
            "A4235_OVERLAY_BYTES_MISMATCH",
        )
    g.require(
        g.git(root, "ls-tree", "-r", head, "--", "infra")
        == business.git(root, "ls-tree", "-r", head, "--", "infra"),
        "A4235_HEAD_BYTES_MISMATCH",
    )
    fd_guard.verify_full_worktree(g, root, head)
    g.require(
        not g.git(root, "status", "--porcelain").strip()
        and head == g.git(root, "rev-parse", "HEAD").decode().strip(),
        "A4235_DIRTY_TREE",
    )
    return hashlib.sha256((head + g.A42365_MANIFEST_SHA).encode()).hexdigest()
