"""Third exact overlay; history bytes and full committed trees stay independently bound."""

import hashlib
import json
import re

from scripts.a42361_contract import BASELINE

SOURCES = tuple(
    f"scripts/a42361_{n}.py"
    for n in (
        "contract",
        "deployment",
        "trust_verifier",
        "one_shot_store",
        "fixture_controller",
        "live_probe_worker",
        "watchdog",
        "trusted_evidence",
        "control_service",
        "source_guard",
        "offline_cases",
    )
)
TESTS = tuple(
    f"tests/unit/test_a42361_{n}.py"
    for n in ("trust", "store", "controller_watchdog", "worker_evidence", "source_entrypoints")
)
DOCS = tuple(
    f"docs/acceptance/a42361_{n}.md"
    for n in (
        "baseline",
        "dependency_review",
        "trust_model",
        "approval_and_deploy_runbook",
        "capability_matrix",
        "unresolved_methods",
        "test_traceability",
        "closeout",
    )
)
INFRA = (
    "infra/g1_control_plane/001_control.sql",
    "infra/g1_control_plane/README.md",
    *(
        "infra/g1_harness/" + n
        for n in (
            "pg17-spec.json",
            "init_owner.sql",
            "probe_roles.sql",
            "runtime-lock.json",
            "deployment.example.json",
            "README.md",
        )
    ),
)
AUTHORITY = frozenset(
    (
        "README.md",
        "PROJECT_RULES.md",
        "docs/股票机会发现系统_PRD_V1.0.md",
        "docs/股票机会发现系统_系统设计_V1.0.md",
    )
)
OLD_TEST = "tests/unit/test_a4236_source_guard.py"
OLD_GUARD = "scripts/a4235_capability_guard.py"
MANIFEST = "docs/acceptance/a42361_overlay_manifest.json"
STAGE_PATHS = frozenset(
    (*SOURCES, *TESTS, *DOCS, *INFRA, *AUTHORITY, OLD_TEST, OLD_GUARD, MANIFEST)
)
PINNED = STAGE_PATHS - {OLD_GUARD, MANIFEST}


def normalized_guard(raw):
    # A manifest cannot contain its own digest through the guard. The one digest
    # literal is normalized; ALL other guard bytes are pinned. Raw bytes still must
    # match independently fetched HEAD, and the literal must match the manifest hash.
    pattern = rb"LIVE_MANIFEST_SHA = '[0-9a-f]{64}'"
    assert len(re.findall(pattern, raw)) == 1
    return re.sub(pattern, b"LIVE_MANIFEST_SHA = '" + b"0" * 64 + b"'", raw)


def validate_paths(actual):
    from scripts.a4235_calibration_adapter_contract import require

    require(set(actual) == STAGE_PATHS, "A4235_FROZEN_FILE_CHANGED")


def validate(g, root, head):
    """Uses guard's independent git/path readers, so legacy tamper tests still apply."""
    require = g.require
    validate_paths(
        g.git(root, "diff", "--no-ext-diff", "--name-only", BASELINE).decode().splitlines()
    )
    require(g.path_sha(root / MANIFEST) == g.LIVE_MANIFEST_SHA, "A4235_LIVE_OVERLAY_INVALID")
    manifest = json.loads((root / MANIFEST).read_bytes())
    require(
        set(manifest)
        == {
            "schema_version",
            "baseline_sha",
            "stage_paths",
            "patch_sha256",
            "old_sha256",
            "normalized_guard_sha256",
        }
        and manifest["schema_version"] == "a42361.exact-overlay.v1"
        and manifest["baseline_sha"] == BASELINE
        and manifest["stage_paths"] == sorted(STAGE_PATHS)
        and set(manifest["patch_sha256"]) == PINNED
        and set(manifest["old_sha256"]) == {OLD_GUARD, OLD_TEST},
        "A4235_LIVE_OVERLAY_INVALID",
    )
    for name in STAGE_PATHS:
        raw = (root / name).read_bytes()
        current = g.path_sha(root / name)
        require(raw == g.git(root, "show", f"{head}:{name}"), "A4235_HEAD_BYTES_MISMATCH")
        if name in PINNED:
            require(current == manifest["patch_sha256"][name], "A4235_LIVE_OVERLAY_INVALID")
        if name in (OLD_GUARD, OLD_TEST):
            old = g.git(root, "show", f"{BASELINE}:{name}")
            require(
                hashlib.sha256(old).hexdigest() == manifest["old_sha256"][name],
                "A4235_LIVE_OVERLAY_INVALID",
            )
        if name == OLD_GUARD:
            require(
                hashlib.sha256(normalized_guard(raw)).hexdigest()
                == manifest["normalized_guard_sha256"],
                "A4235_LIVE_OVERLAY_INVALID",
            )
        if name in AUTHORITY:
            require(
                raw.startswith(g.git(root, "show", f"{BASELINE}:{name}")),
                "A4235_FROZEN_FILE_CHANGED",
            )
    # Infra is intentionally NOT inserted in historic PROTECTED: doing so would
    # change its frozen tree digest. This separate full-tree read closes hidden index.
    for row in g.git(root, "ls-tree", "-r", head, "--", "infra").splitlines():
        meta, name = row.split(b"\t", 1)
        mode, kind, oid = meta.split()
        require(mode in {b"100644", b"100755"} and kind == b"blob", "A4235_HEAD_BYTES_MISMATCH")
        path = root / name.decode()
        g.path_sha(path)
        raw = path.read_bytes()
        require(
            hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest().encode()
            == oid,
            "A4235_HEAD_BYTES_MISMATCH",
        )
    require(
        head == g.git(root, "rev-parse", "HEAD").decode().strip()
        and not g.git(root, "status", "--porcelain").strip(),
        "A4235_DIRTY_TREE",
    )
    return g.LIVE_MANIFEST_SHA


def independent_binding(run_id, attempt, fixture_uuid, nonce, marker_sha256):
    from scripts import a4235_capability_guard as g
    from scripts.a42361_contract import Binding

    identity = g.expected_identity(run_id=run_id, attempt=attempt)
    return Binding(
        identity=identity,
        overlay_sha256=g.overlay_fingerprint(),
        fixture_uuid=fixture_uuid,
        nonce=nonce,
        marker_sha256=marker_sha256,
    )
