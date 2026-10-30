"""Versioned static development checks; never an execution authority."""

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

DEVELOPMENT = "development.source.v1"
HISTORICAL = "a42366.source.v1"
HISTORICAL_SHA = "2779a2a7a7120c86f67b4991bce196c652b5ebb0"
HISTORICAL_TREE = "27d9e7a9b384c063f0e7b4e5364d35b1761e6121"
GOVERNANCE_BASELINE = "010dc6bfaeaaacdceafa48d7dcd5f56a10d180f7"
HISTORICAL_MODULES = (
    "tests/unit/test_a4236_source_guard.py",
    "tests/unit/test_a42362_source_guard.py",
    "tests/unit/test_a42363_source_guard.py",
    "tests/unit/test_a42363_complete_guard.py",
    "tests/unit/test_a42363_review_guard.py",
    "tests/unit/test_a42364_source_guard.py",
    "tests/unit/test_a42366_source_guard.py",
)
# This assertion describes one historical development stage, not today's tests.
# Its original source and assertions execute in the pinned historical checkout.
HISTORICAL_NODES = frozenset((
    "tests/unit/test_a42366_source_guard.py::"
    "test_AT_W09_historical_manifests_and_all_original_tests_keep_their_blobs",
))


@lru_cache(maxsize=8)
def historical_manifests(root):
    """Cache only immutable Git objects, never live bytes or an approval."""
    from scripts.business_source_contract import git, git_blobs

    manifest = "docs/acceptance/a42366_overlay_manifest.json"
    if git(root, "rev-parse", HISTORICAL_SHA + "^{tree}").decode().strip() != HISTORICAL_TREE:
        raise ValueError("SOURCE_CONTRACT_HISTORY_TREE_MISMATCH")
    raw = git(root, "show", HISTORICAL_SHA + ":" + manifest)
    paths = (manifest, *json.loads(raw)["historical_manifest_sha256"])
    blobs = git_blobs(root, [HISTORICAL_SHA + ":" + p for p in paths])
    return tuple((p, blobs[HISTORICAL_SHA + ":" + p]) for p in paths)


def development_receipt(root, *, expected_sha=None):
    from scripts import a4235_capability_guard as g
    from scripts.a42361_source_guard import verify_full_worktree
    from scripts.business_source_contract import git, git_blobs

    root = Path(root)
    head = git(root, "rev-parse", "HEAD").decode().strip()
    g.require(re.fullmatch(r"[0-9a-f]{40}", head) is not None, "A4235_FULL_SHA_REQUIRED")
    g.require(expected_sha is None or expected_sha == head, "A4235_HEAD_MISMATCH")
    g.require(head == g.git(root, "rev-parse", "HEAD").decode().strip(), "A4235_HEAD_MISMATCH")
    g.require(not g.git(root, "status", "--porcelain").strip(), "A4235_DIRTY_TREE")
    # Neither independent reader can vouch for itself. Preserve the old injected
    # reader negatives without imposing the old 33-path set on new development.
    diff = ("diff", "--name-only", "-z", GOVERNANCE_BASELINE)
    g.require(g.git(root, *diff) == git(root, *diff), "A4235_FROZEN_FILE_CHANGED")
    for path, original in historical_manifests(root):
        g.require((root / path).read_bytes() == original, "A4235_OVERLAY_BYTES_MISMATCH")
        g.require(g.path_sha(root / path) == hashlib.sha256(original).hexdigest(),
                  "A4235_OVERLAY_BYTES_MISMATCH")
    from scripts.business_source_contract import HISTORICAL_SOURCE

    paths = g.PATCH_PATHS | g.NEXT_PATCH_PATHS
    objects = git_blobs(root, [HISTORICAL_SOURCE + ":" + p for p in paths])
    for path in paths:
        original = objects[HISTORICAL_SOURCE + ":" + path]
        g.require(g.git(root, "show", HISTORICAL_SOURCE + ":" + path) == original,
                  "A4235_OVERLAY_BYTES_MISMATCH")
    # The six original patch pins remain independently checked in the live tree.
    pins = json.loads(dict(historical_manifests(root))[g.OVERLAY_MANIFEST])["patch_sha256"]
    for path in g.PATCH_PATHS:
        g.require(g.path_sha(root / path) == pins[path], "A4235_OVERLAY_BYTES_MISMATCH")
    tree_args = ("ls-tree", "-r", head, "--", "infra")
    g.require(g.git(root, *tree_args) == git(root, *tree_args), "A4235_HEAD_BYTES_MISMATCH")
    verify_full_worktree(g, root, head)
    tree = git(root, "rev-parse", head + "^{tree}").decode().strip()
    g.require(head == git(root, "rev-parse", "HEAD").decode().strip()
              == g.git(root, "rev-parse", "HEAD").decode().strip()
              and not g.git(root, "status", "--porcelain").strip(), "A4235_DIRTY_TREE")
    return dict(contract_version=DEVELOPMENT, purpose="DEVELOPMENT_STATIC_ONLY",
                head_sha=head, tree_sha=tree, historical_source_sha=HISTORICAL_SHA,
                historical_evidence_kind="HISTORICAL_NOT_CURRENT_PERFORMANCE",
                performance_eligible=False, capacity_ready=False, g1_authorized=False,
                production_read_authorized=False, recovery_authorized=False)


def require_historical_source(root, expected_sha):
    from scripts.business_source_contract import git

    if expected_sha != HISTORICAL_SHA:
        raise ValueError("SOURCE_CONTRACT_EXPLICIT_HISTORICAL_SHA_REQUIRED")
    if git(root, "rev-parse", "HEAD").decode().strip() != HISTORICAL_SHA:
        raise ValueError("SOURCE_CONTRACT_HISTORICAL_SOURCE_MISMATCH")
    if git(root, "rev-parse", "HEAD^{tree}").decode().strip() != HISTORICAL_TREE:
        raise ValueError("SOURCE_CONTRACT_HISTORY_TREE_MISMATCH")


def require_purpose(version, purpose):
    # A version name, static receipt or owner's governance authorization cannot
    # act as a grant. Real entry points keep their separate existing validators.
    if version != DEVELOPMENT or purpose != "DEVELOPMENT_STATIC_ONLY":
        raise ValueError("SOURCE_CONTRACT_NOT_EXECUTION_AUTHORITY")


def fingerprint(receipt):
    require_purpose(receipt["contract_version"], receipt["purpose"])
    return hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()
