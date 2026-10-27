"""Eighth exact overlay, with one explicitly reviewed test-contract adaptation."""

import ast
import hashlib
import json
import re

BASELINE = "60eeb0f123d61c082a6bb9bab53cd0f45b45202f"
MANIFEST = "docs/acceptance/a42364_overlay_manifest.json"
OLD_GUARD = "scripts/a4235_capability_guard.py"
ALLOWED_TEST = "tests/unit/test_a42363_review_guard.py"
ALLOWED_FUNCTION = "test_RF_AT59_candidate_cannot_change_sql_or_enable_protocol"
STAGE_PATHS = frozenset(
    (
        "PROJECT_RULES.md",
        "README.md",
        "docs/acceptance/a42364_ADR_BOOTSTRAP_AND_BUDGET.md",
        "docs/acceptance/a42364_ADR_SAFE_VOLUME_DISPOSAL.md",
        "docs/acceptance/a42364_ADR_TARGET_SESSION_GUC.md",
        "docs/acceptance/a42364_L2_NOT_RUN.md",
        "docs/acceptance/a42364_architecture.md",
        "docs/acceptance/a42364_baseline_and_red.md",
        "docs/acceptance/a42364_capability_matrix.md",
        "docs/acceptance/a42364_closeout.md",
        "docs/acceptance/a42364_cost_ledger.md",
        "docs/acceptance/a42364_overlay_manifest.json",
        "docs/acceptance/a42364_runbook.md",
        "docs/acceptance/a42364_test_matrix.md",
        "docs/\u80a1\u7968\u673a\u4f1a\u53d1\u73b0\u7cfb\u7edf_PRD_V1.0.md",
        "docs/\u80a1\u7968\u673a\u4f1a\u53d1\u73b0\u7cfb\u7edf_\u7cfb\u7edf\u8bbe\u8ba1_V1.0.md",
        "infra/g1_manager/README.md",
        "infra/g1_manager/install_manifest.schema.json",
        "infra/g1_manager/read_only_auditor.service",
        "infra/g1_manager/root_manager.service",
        "infra/g1_manager/worker.service",
        "infra/g1_pg17_image/Containerfile",
        "infra/g1_pg17_image/README.md",
        "infra/g1_pg17_image/bootstrap.c",
        "infra/g1_pg17_image/bootstrap.sh",
        "infra/g1_pg17_image/build_offline.sh",
        "infra/g1_pg17_image/healthcheck.sh",
        "infra/g1_pg17_image/pg_hba.template",
        "infra/g1_pg17_image/supply_chain_manifest.schema.json",
        "infra/g1_pg17_image/verify_supply_chain.sh",
        "scripts/a4235_capability_guard.py",
        "scripts/a42363_absence.py",
        "scripts/a42363_complete_guard.py",
        "scripts/a42363_harness.py",
        "scripts/a42363_installation.py",
        "scripts/a42363_owner.py",
        "scripts/a42363_proposals.py",
        "scripts/a42363_resources.py",
        "scripts/a42363_review.py",
        "scripts/a42363_review_guard.py",
        "scripts/a42363_services.py",
        "scripts/a42363_supervisor.py",
        "scripts/a42364_bootstrap_builder.py",
        "scripts/a42364_collector.py",
        "scripts/a42364_costs.py",
        "scripts/a42364_entry.py",
        "scripts/a42364_evidence_gate.py",
        "scripts/a42364_installation_verify.py",
        "scripts/a42364_manager.py",
        "scripts/a42364_owner.py",
        "scripts/a42364_protocol_decision.py",
        "scripts/a42364_session.py",
        "scripts/a42364_source_guard.py",
        "scripts/a42364_volume_exclusion.py",
        "tests/integration_offline/test_a42364_chain.py",
        "tests/integration_offline/test_a42364_process.py",
        "tests/unit/test_a42363_review_guard.py",
        "tests/unit/test_a42364_bootstrap.py",
        "tests/unit/test_a42364_evidence.py",
        "tests/unit/test_a42364_installation.py",
        "tests/unit/test_a42364_owner.py",
        "tests/unit/test_a42364_protocol.py",
        "tests/unit/test_a42364_red.py",
        "tests/unit/test_a42364_session.py",
        "tests/unit/test_a42364_source_guard.py",
        "tests/unit/test_a42364_volume.py",
    )
)
INFRA = frozenset(
    (
        "infra/g1_pg17_image/Containerfile",
        "infra/g1_pg17_image/bootstrap.sh",
        "infra/g1_pg17_image/bootstrap.c",
        "infra/g1_pg17_image/pg_hba.template",
        "infra/g1_pg17_image/healthcheck.sh",
        "infra/g1_pg17_image/README.md",
        "infra/g1_pg17_image/supply_chain_manifest.schema.json",
        "infra/g1_pg17_image/build_offline.sh",
        "infra/g1_pg17_image/verify_supply_chain.sh",
        "infra/g1_manager/install_manifest.schema.json",
        "infra/g1_manager/root_manager.service",
        "infra/g1_manager/worker.service",
        "infra/g1_manager/read_only_auditor.service",
        "infra/g1_manager/README.md",
    )
)
AUTHORITY = frozenset(
    (
        "PROJECT_RULES.md",
        "README.md",
        "docs/\u80a1\u7968\u673a\u4f1a\u53d1\u73b0\u7cfb\u7edf_PRD_V1.0.md",
        "docs/\u80a1\u7968\u673a\u4f1a\u53d1\u73b0\u7cfb\u7edf_\u7cfb\u7edf\u8bbe\u8ba1_V1.0.md",
    )
)
PINNED = STAGE_PATHS - {MANIFEST, OLD_GUARD}
HISTORICAL = {
    "docs/acceptance/a42351_reviewer_overlay_manifest.json": (
        "af08f8724e988121402988b4e8fb70c8ef5b53f2"
    ),
    "docs/acceptance/a4236_overlay_manifest.json": "6d54841522bc013ad21a52bc45d75218de2d9ce6",
    "docs/acceptance/a42361_overlay_manifest.json": "b32b9271596d92cfbec571fd3170aacbe17370cd",
    "docs/acceptance/a42362_overlay_manifest.json": "5acc2e71c43cc77172e9caca103cc843c04d704d",
    "docs/acceptance/a42363_overlay_manifest.json": "d31b07a4e33d50ac00ade3e1eff60e091fe78041",
    "docs/acceptance/a42363_complete_overlay_manifest.json": (
        "a8a675ea8b93dadbba9e905a7a4af67eba163d99"
    ),
    "docs/acceptance/a42363_review_overlay_manifest.json": BASELINE,
}


def normalized(raw):
    pattern = rb"COMPLETE_MANIFEST_SHA = '[0-9a-f]{64}'"
    if len(re.findall(pattern, raw)) != 1:
        raise ValueError("A4235_LIVE_OVERLAY_INVALID")
    return re.sub(pattern, b"COMPLETE_MANIFEST_SHA = '" + b"0" * 64 + b"'", raw)


def validate_paths(paths):
    from scripts.a4235_calibration_adapter_contract import require

    require(set(paths) == STAGE_PATHS, "A4235_FROZEN_FILE_CHANGED")


def verify_test_adaptation(before, after):
    """Only AT59 source may change; even whitespace outside that function is frozen."""
    from scripts.a4235_calibration_adapter_contract import require

    def separate(raw):
        text = raw.decode("utf8")
        tree = ast.parse(text)
        matches = [
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == ALLOWED_FUNCTION
        ]
        require(len(matches) == 1, "A4235_FROZEN_FILE_CHANGED")
        node = matches[0]
        segment = ast.get_source_segment(text, node)
        return text.replace(segment, "<REVIEWED_AT59_FUNCTION>", 1), ast.dump(node)

    original, old_function = separate(before)
    current, new_function = separate(after)
    require(original == current and old_function != new_function, "A4235_FROZEN_FILE_CHANGED")


def cumulative():
    from scripts import a42363_complete_guard as facade
    from scripts import a42363_review_guard as previous

    paths = facade.LEGACY_STAGE_PATHS | previous.LEGACY_STAGE_PATHS | STAGE_PATHS
    pins = facade.LEGACY_PINNED | previous.LEGACY_PINNED | PINNED
    return paths, pins


def validate(g, root, head):
    from scripts import a42361_source_guard as fd_guard
    from scripts import a42362_source_guard as inherited
    from scripts import a42363_review_guard as previous

    require = g.require
    require(g.path_sha(root / MANIFEST) == g.COMPLETE_MANIFEST_SHA, "A4235_LIVE_OVERLAY_INVALID")
    data = json.loads((root / MANIFEST).read_bytes())
    paths, pins = cumulative()
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
        and data["schema_version"] == "a42364.engineering-overlay.v1"
        and data["baseline_sha"] == BASELINE
        and data["stage_paths"] == sorted(STAGE_PATHS)
        and data["cumulative_paths"] == sorted(paths)
        and set(data["patch_sha256"]) == pins
        and set(data["historical_sha256"]) == set(HISTORICAL),
        "A4235_LIVE_OVERLAY_INVALID",
    )
    delta = set(
        g.git(root, "diff", "--no-ext-diff", "--name-only", "-z", BASELINE).decode().split("\0")
    ) - {""}
    validate_paths(delta)
    old_delta = set(
        g.git(root, "diff", "--no-ext-diff", "--name-only", "-z", previous.BASELINE, BASELINE)
        .decode()
        .split("\0")
    ) - {""}
    require(old_delta == previous.LEGACY_STAGE_PATHS, "A4235_FROZEN_FILE_CHANGED")
    for path, closing in HISTORICAL.items():
        raw = g.git(root, "show", f"{BASELINE}:{path}")
        require(
            raw == (root / path).read_bytes()
            and hashlib.sha256(raw).hexdigest() == data["historical_sha256"][path],
            "A4235_LIVE_OVERLAY_INVALID",
        )
        record = json.loads(raw)
        for name, expected in record["patch_sha256"].items():
            require(
                hashlib.sha256(g.git(root, "show", f"{closing}:{name}")).hexdigest() == expected,
                "A4235_OVERLAY_BYTES_MISMATCH",
            )
        if "normalized_guard_sha256" in record:
            variable = (
                "LIVE_MANIFEST_SHA"
                if "a42361_" in path
                else "SERVICE_MANIFEST_SHA"
                if "a42362_" in path
                else "CLOSEOUT_MANIFEST_SHA"
                if path.endswith("a42363_overlay_manifest.json")
                else "COMPLETE_MANIFEST_SHA"
            )
            guard = g.git(root, "show", f"{closing}:{OLD_GUARD}")
            pattern = variable.encode() + rb" = '[0-9a-f]{64}'"
            require(len(re.findall(pattern, guard)) == 1, "A4235_LIVE_OVERLAY_INVALID")
            guard = re.sub(pattern, variable.encode() + b" = '" + b"0" * 64 + b"'", guard)
            require(
                hashlib.sha256(guard).hexdigest() == record["normalized_guard_sha256"],
                "A4235_LIVE_OVERLAY_INVALID",
            )
    baseline_files = set()
    for row in g.git(root, "ls-tree", "-r", "-z", BASELINE).split(b"\0"):
        if row:
            baseline_files.add(row.split(b"\t", 1)[1].decode())
    old_paths = STAGE_PATHS & baseline_files
    require(set(data["old_sha256"]) == old_paths, "A4235_LIVE_OVERLAY_INVALID")
    for path in paths:
        raw = (root / path).read_bytes()
        require(raw == g.git(root, "show", f"{head}:{path}"), "A4235_HEAD_BYTES_MISMATCH")
        if path in pins:
            require(
                hashlib.sha256(raw).hexdigest() == data["patch_sha256"][path],
                "A4235_LIVE_OVERLAY_INVALID",
            )
        if path in old_paths:
            before = g.git(root, "show", f"{BASELINE}:{path}")
            require(
                hashlib.sha256(before).hexdigest() == data["old_sha256"][path],
                "A4235_LIVE_OVERLAY_INVALID",
            )
            if path in AUTHORITY:
                require(raw.startswith(before), "A4235_FROZEN_FILE_CHANGED")
    for row in g.git(root, "ls-tree", "-r", "-z", BASELINE, "--", "tests").split(b"\0"):
        if not row:
            continue
        metadata, name = row.split(b"\t", 1)
        path = name.decode()
        raw = (root / path).read_bytes()
        if path == ALLOWED_TEST:
            verify_test_adaptation(g.git(root, "show", f"{BASELINE}:{path}"), raw)
        else:
            require(
                hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest().encode()
                == metadata.split()[2],
                "A4235_FROZEN_FILE_CHANGED",
            )
    require(
        hashlib.sha256(normalized((root / OLD_GUARD).read_bytes())).hexdigest()
        == data["normalized_guard_sha256"],
        "A4235_LIVE_OVERLAY_INVALID",
    )
    inherited.verify_inherited_checks(g, root, head)
    fd_guard.verify_full_worktree(g, root, head)
    require(
        head == g.git(root, "rev-parse", "HEAD").decode().strip()
        and not g.git(root, "status", "--porcelain").strip(),
        "A4235_DIRTY_TREE",
    )
    return g.COMPLETE_MANIFEST_SHA
