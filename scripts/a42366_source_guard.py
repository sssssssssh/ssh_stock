"""Exact source-only overlay. Historical grants are never upgraded to new bytes."""

import hashlib
import json
import re
from pathlib import Path

BASELINE = "f00be6aa149d5fde145ae4137c01368a332b022f"
MANIFEST = "docs/acceptance/a42366_overlay_manifest.json"
DISPATCH = "scripts/business_source_contract.py"
AUTHORITY = frozenset((
    "README.md", "PROJECT_RULES.md", "docs/股票机会发现系统_PRD_V1.0.md",
    "docs/股票机会发现系统_系统设计_V1.0.md",
))
# Paths are individually reviewed, not a directory-prefix permission.
ALLOWED = AUTHORITY | frozenset((
    MANIFEST, DISPATCH, "scripts/a42366_source_guard.py",
    "scripts/a42365_supervisor.py", "scripts/a42365_runtime.py",
    "scripts/a42365_lifecycle.py", "scripts/a42365_budget.py", "scripts/a42365_owner.py",
    "scripts/a42365_runtime_factory.py", "scripts/a42365_ipc.py",
    "scripts/a42364_installation_verify.py", "scripts/a42364_manager.py",
    "scripts/a42366_publication.py", "scripts/a42366_reviewer.py",
    "scripts/a42366_services.py", "scripts/a42366_owner.py",
    "scripts/a42366_mediation.py", "scripts/a42366_installation.py",
    "tests/unit/test_a42366_publication.py", "tests/unit/test_a42366_services.py",
    "tests/unit/test_a42366_reliability.py", "tests/unit/test_a42366_source_guard.py",
    "docs/acceptance/a42366_baseline.md", "docs/acceptance/a42366_capability_matrix.md",
    "docs/acceptance/a42366_closeout.md", "docs/acceptance/a42366_runbook.md",
    "docs/acceptance/a42366_test_matrix.md", "docs/acceptance/a42366_platform_handoff.md",
    "docs/acceptance/a42366_evidence.json",
))


def normalized_dispatch(raw):
    pattern = rb"A42366_MANIFEST_SHA = '[0-9a-f]{64}'"
    if len(re.findall(pattern, raw)) != 1:
        raise ValueError("A42366_DISPATCH_PIN")
    return re.sub(pattern, b"A42366_MANIFEST_SHA = '" + b"0" * 64 + b"'", raw)


def validate_paths(paths):
    from scripts.a42363_contract import require

    require(set(paths) <= ALLOWED, "A42366_UNREGISTERED_PATH")


def verify(g, root, head):
    from scripts import a42361_source_guard as fd_guard
    from scripts import a42364_source_guard as historical
    from scripts import a42365_source_guard as prior
    from scripts import business_source_contract as business

    root = Path(root)
    g.require(re.fullmatch(r"[0-9a-f]{40}", head) is not None, "A4235_FULL_SHA_REQUIRED")
    g.require(head == business.git(root, "rev-parse", "HEAD").decode().strip(),
              "A4235_HEAD_MISMATCH")
    g.require(head == g.git(root, "rev-parse", "HEAD").decode().strip(),
              "A4235_HEAD_MISMATCH")
    g.require(not g.git(root, "status", "--porcelain").strip(), "A4235_DIRTY_TREE")
    raw = (root / MANIFEST).read_bytes()
    g.require(hashlib.sha256(raw).hexdigest() == business.A42366_MANIFEST_SHA,
              "A4235_LIVE_OVERLAY_INVALID")
    data = json.loads(raw)
    g.require(set(data) == {"version", "baseline_sha", "stage_paths", "patch_sha256",
                           "normalized_dispatch_sha256", "historical_manifest_sha256"}
              and data["version"] == "a42366.source.v1" and data["baseline_sha"] == BASELINE,
              "A4235_LIVE_OVERLAY_INVALID")
    changed = set(g.git(root, "diff", "--name-only", "-z", BASELINE).decode().split("\0"))
    changed.discard("")
    g.require(changed == set(data["stage_paths"]), "A4235_FROZEN_FILE_CHANGED")
    validate_paths(changed)
    g.require(set(data["patch_sha256"]) == changed - {MANIFEST, DISPATCH},
              "A4235_LIVE_OVERLAY_INVALID")
    for path, digest in data["patch_sha256"].items():
        g.require(g.path_sha(root / path) == digest, "A4235_HEAD_BYTES_MISMATCH")
    g.require(hashlib.sha256(normalized_dispatch((root / DISPATCH).read_bytes())).hexdigest()
              == data["normalized_dispatch_sha256"], "A4235_OVERLAY_BYTES_MISMATCH")
    histories = {**historical.HISTORICAL,
                 historical.MANIFEST: business.HISTORICAL_SOURCE,
                 business.MANIFEST: prior.BASELINE, prior.MANIFEST: BASELINE}
    g.require(set(histories) == set(data["historical_manifest_sha256"]),
              "A4235_LIVE_OVERLAY_INVALID")
    baseline_manifests = business.git_blobs(root, [BASELINE + ":" + p for p in histories])
    for path, closing in histories.items():
        original = baseline_manifests[BASELINE + ":" + path]
        g.require((root / path).read_bytes() == original
                  and g.path_sha(root / path) == data["historical_manifest_sha256"][path]
                  and hashlib.sha256(original).hexdigest()
                  == data["historical_manifest_sha256"][path], "A4235_OVERLAY_BYTES_MISMATCH")
        pins = json.loads(original)["patch_sha256"]
        blobs = business.git_blobs(root, [closing + ":" + p for p in pins])
        for p, digest in pins.items():
            g.require(hashlib.sha256(blobs[closing + ":" + p]).hexdigest() == digest,
                      "A4235_OVERLAY_BYTES_MISMATCH")
    entries = [r.split(b"\t", 1)[1].decode() for r in
               business.git(root, "ls-tree", "-r", "-z", BASELINE).split(b"\0") if r]
    originals = business.git_blobs(root, [BASELINE + ":" + p for p in entries])
    for p in entries:
        old, current = originals[BASELINE + ":" + p], (root / p).read_bytes()
        if p in AUTHORITY:
            g.require(current.startswith(old), "A4235_FROZEN_FILE_CHANGED")
        elif p not in changed:
            g.require(current == old and g.path_sha(root / p) == hashlib.sha256(old).hexdigest(),
                      "A4235_FROZEN_FILE_CHANGED")
    # Preserve the old independent reader injection/replay contracts as well as
    # the newer complete-tree check. Neither reader may vouch for itself.
    original_paths = g.PATCH_PATHS | g.NEXT_PATCH_PATHS
    old_objects = business.git_blobs(root, [business.HISTORICAL_SOURCE + ":" + p
                                           for p in original_paths])
    for p in original_paths:
        g.require(g.git(root, "show", business.HISTORICAL_SOURCE + ":" + p)
                  == old_objects[business.HISTORICAL_SOURCE + ":" + p],
                  "A4235_OVERLAY_BYTES_MISMATCH")
    g.require(g.git(root, "ls-tree", "-r", head, "--", "infra")
              == business.git(root, "ls-tree", "-r", head, "--", "infra"),
              "A4235_HEAD_BYTES_MISMATCH")
    fd_guard.verify_full_worktree(g, root, head)
    g.require(head == business.git(root, "rev-parse", "HEAD").decode().strip()
              and head == g.git(root, "rev-parse", "HEAD").decode().strip()
              and not g.git(root, "status", "--porcelain").strip(), "A4235_DIRTY_TREE")
    raw_identity = ("SOURCE_ONLY:" + head + business.A42366_MANIFEST_SHA).encode()
    return hashlib.sha256(raw_identity).hexdigest()
