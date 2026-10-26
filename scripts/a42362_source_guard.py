"""Fourth exact overlay: canonical historical trees plus full current no-follow HEAD walk."""

import hashlib
import json
import re

BASELINE = "b32b9271596d92cfbec571fd3170aacbe17370cd"
MANIFEST = "docs/acceptance/a42362_overlay_manifest.json"
STAGE_PATHS = frozenset(
    (
        "PROJECT_RULES.md",
        "README.md",
        "docs/acceptance/a42362_architecture.md",
        "docs/acceptance/a42362_baseline.md",
        "docs/acceptance/a42362_capability_matrix.md",
        "docs/acceptance/a42362_closeout.md",
        "docs/acceptance/a42362_g1_deployment_request_TEMPLATE.md",
        "docs/acceptance/a42362_method_decisions.md",
        "docs/acceptance/a42362_overlay_manifest.json",
        "docs/acceptance/a42362_recovery_and_faults.md",
        "docs/acceptance/a42362_schema_and_budget.md",
        "docs/acceptance/a42362_test_traceability.md",
        "docs/股票机会发现系统_PRD_V1.0.md",
        "docs/股票机会发现系统_系统设计_V1.0.md",
        "infra/g1_control_plane/002_services.sql",
        "infra/g1_harness/a42362-deployment.md",
        "infra/g1_harness/a42362-installation.example.json",
        "infra/g1_harness/a42362-service@.service",
        "infra/g1_harness/a42362-socket@.socket",
        "infra/g1_harness/owner_bootstrap.sql",
        "infra/g1_harness/owner_role_audit.sql",
        "scripts/a4235_capability_guard.py",
        "scripts/a42361_control_service.py",
        "scripts/a42361_deployment.py",
        "scripts/a42361_fixture_controller.py",
        "scripts/a42361_live_probe_worker.py",
        "scripts/a42361_one_shot_store.py",
        "scripts/a42361_source_guard.py",
        "scripts/a42361_watchdog.py",
        "scripts/a42362_absence_auditor.py",
        "scripts/a42362_approval_registry_service.py",
        "scripts/a42362_contract.py",
        "scripts/a42362_ledger.py",
        "scripts/a42362_pg_owner_service.py",
        "scripts/a42362_reconcile.py",
        "scripts/a42362_service_host.py",
        "scripts/a42362_source_guard.py",
        "scripts/a42362_supervisor_service.py",
        "tests/integration_offline/test_a42362_ipc_process.py",
        "tests/unit/test_a42361_controller_watchdog.py",
        "tests/unit/test_a42361_source_entrypoints.py",
        "tests/unit/test_a42361_worker_evidence.py",
        "tests/unit/test_a42362_approval_ledger.py",
        "tests/unit/test_a42362_audit_supervisor.py",
        "tests/unit/test_a42362_contract.py",
        "tests/unit/test_a42362_owner_recovery.py",
        "tests/unit/test_a42362_source_guard.py",
        "tests/unit/test_a4236_source_guard.py",
    )
)
AUTHORITY = frozenset(
    (
        "README.md",
        "PROJECT_RULES.md",
        "docs/股票机会发现系统_PRD_V1.0.md",
        "docs/股票机会发现系统_系统设计_V1.0.md",
    )
)
OLD_GUARD = "scripts/a4235_capability_guard.py"
INFRA = frozenset(
    (
        "infra/g1_control_plane/002_services.sql",
        "infra/g1_harness/owner_bootstrap.sql",
        "infra/g1_harness/owner_role_audit.sql",
        "infra/g1_harness/a42362-service@.service",
        "infra/g1_harness/a42362-socket@.socket",
        "infra/g1_harness/a42362-installation.example.json",
        "infra/g1_harness/a42362-deployment.md",
    )
)
PINNED = STAGE_PATHS - {MANIFEST, OLD_GUARD}


def normalize_guard(raw):
    pattern = rb"SERVICE_MANIFEST_SHA = '[0-9a-f]{64}'"
    if len(re.findall(pattern, raw)) != 1:
        raise ValueError("A4235_LIVE_OVERLAY_INVALID")
    return re.sub(pattern, b"SERVICE_MANIFEST_SHA = '" + b"0" * 64 + b"'", raw)


def validate_paths(paths):
    from scripts.a4235_calibration_adapter_contract import require

    require(set(paths) == STAGE_PATHS, "A4235_FROZEN_FILE_CHANGED")


def verify_inherited_checks(g, root, head):
    """Retain both legacy independent checks and their first-error classification."""
    require = g.require
    require(
        g.path_sha(root / g.OVERLAY_MANIFEST) == g.OVERLAY_MANIFEST_SHA,
        "A4235_OVERLAY_MANIFEST_INVALID",
    )
    legacy = json.loads((root / g.OVERLAY_MANIFEST).read_bytes())
    require(set(legacy["patch_sha256"]) == g.PATCH_PATHS, "A4235_OVERLAY_MANIFEST_INVALID")
    for name in g.PATCH_PATHS:
        require(
            g.path_sha(root / name) == legacy["patch_sha256"][name],
            "A4235_OVERLAY_BYTES_MISMATCH",
        )
    # This historical targeted read is additional to, never a replacement for, the
    # final entire-HEAD NUL/no-follow FD walk below.
    for row in g.git(root, "ls-tree", "-r", head, "--", "infra").splitlines():
        metadata, name = row.split(b"\t", 1)
        mode, kind, oid = metadata.split()
        require(mode in {b"100644", b"100755"} and kind == b"blob", "A4235_HEAD_BYTES_MISMATCH")
        path = root / name.decode()
        g.path_sha(path)
        raw = path.read_bytes()
        require(
            hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest().encode()
            == oid,
            "A4235_HEAD_BYTES_MISMATCH",
        )


def validate(g, root, head):
    from scripts import a42361_source_guard as old

    require = g.require
    require(g.path_sha(root / MANIFEST) == g.SERVICE_MANIFEST_SHA, "A4235_LIVE_OVERLAY_INVALID")
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
        and manifest["schema_version"] == "a42362.exact-overlay.v1"
        and manifest["baseline_sha"] == BASELINE
        and manifest["stage_paths"] == sorted(STAGE_PATHS)
        and set(manifest["patch_sha256"]) == PINNED,
        "A4235_LIVE_OVERLAY_INVALID",
    )
    validate_paths(
        set(
            g.git(root, "diff", "--no-ext-diff", "--name-only", "-z", BASELINE).decode().split("\0")
        )
        - {""}
    )
    # Independently verify immutable stage-3 objects, not a rewritten working manifest.
    historical = g.git(root, "show", f"{BASELINE}:{old.MANIFEST}")
    require(
        hashlib.sha256(historical).hexdigest() == g.LIVE_MANIFEST_SHA
        and (root / old.MANIFEST).read_bytes() == historical,
        "A4235_LIVE_OVERLAY_INVALID",
    )
    previous = json.loads(historical)
    require(
        previous["stage_paths"] == sorted(old.STAGE_PATHS)
        and set(previous["patch_sha256"]) == old.PINNED,
        "A4235_LIVE_OVERLAY_INVALID",
    )
    old.validate_paths(
        set(
            g.git(root, "diff", "--no-ext-diff", "--name-only", "-z", old.BASELINE, BASELINE)
            .decode()
            .split("\0")
        )
        - {""}
    )
    for name in old.PINNED:
        raw = g.git(root, "show", f"{BASELINE}:{name}")
        require(
            hashlib.sha256(raw).hexdigest() == previous["patch_sha256"][name],
            "A4235_LIVE_OVERLAY_INVALID",
        )
        if name not in STAGE_PATHS:
            require(
                g.path_sha(root / name) == previous["patch_sha256"][name],
                "A4235_LIVE_OVERLAY_INVALID",
            )
    old_guard = g.git(root, "show", f"{BASELINE}:{old.OLD_GUARD}")
    require(
        hashlib.sha256(old.normalized_guard(old_guard)).hexdigest()
        == previous["normalized_guard_sha256"],
        "A4235_LIVE_OVERLAY_INVALID",
    )
    for name in STAGE_PATHS:
        raw = (root / name).read_bytes()
        require(raw == g.git(root, "show", f"{head}:{name}"), "A4235_HEAD_BYTES_MISMATCH")
        if name in PINNED:
            require(
                g.path_sha(root / name) == manifest["patch_sha256"][name],
                "A4235_LIVE_OVERLAY_INVALID",
            )
        if name in manifest["old_sha256"]:
            require(
                hashlib.sha256(g.git(root, "show", f"{BASELINE}:{name}")).hexdigest()
                == manifest["old_sha256"][name],
                "A4235_LIVE_OVERLAY_INVALID",
            )
        if name in AUTHORITY:
            require(
                raw.startswith(g.git(root, "show", f"{BASELINE}:{name}")),
                "A4235_FROZEN_FILE_CHANGED",
            )
    require(
        hashlib.sha256(normalize_guard((root / OLD_GUARD).read_bytes())).hexdigest()
        == manifest["normalized_guard_sha256"],
        "A4235_LIVE_OVERLAY_INVALID",
    )
    verify_inherited_checks(g, root, head)
    # The original entire-HEAD FD walk remains the final authority, including index flags.
    old.verify_full_worktree(g, root, head)
    require(
        head == g.git(root, "rev-parse", "HEAD").decode().strip()
        and not g.git(root, "status", "--porcelain").strip(),
        "A4235_DIRTY_TREE",
    )
    return g.SERVICE_MANIFEST_SHA
