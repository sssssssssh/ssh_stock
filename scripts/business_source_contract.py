"""Independent BIZ current-source contract; immutable A4/G1 history stays historical.

This static fingerprint is never a G1 grant or a performance/capacity admission.
"""

import ast
import hashlib
import json
import subprocess
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "06b4cd6ee1783c399bdb89264c8da6190f282273"
HISTORICAL_SOURCE = "1e510532bd140110e29b10b6e4eed30fbd573159"
MANIFEST = "docs/acceptance/BIZ_PERF_01_review_source_manifest.json"
VERSION = "biz-perf-01.review.20261027.v1"
GUARD = "scripts/a4235_capability_guard.py"
A42366_MANIFEST_SHA = '43ea851cea8741111b8e20edf14b850baedc8966f8057ab2ab720df7a3b2945c'
APPEND_ONLY_TESTS = {
    "tests/unit/test_business_input_records.py",
    "tests/unit/test_business_calculation_memory.py",
}
TEST_ADAPTATIONS = {
    "tests/unit/test_a42341_prepared_capability.py": [
        "test_AT01_frozen_old_files_and_old_execute_and_eight_warmups"
    ],
    "tests/unit/test_a4234_ci_governance.py": [
        "test_all_production_old_scripts_evidence_gates_and_one_shots_frozen"
    ],
    "tests/integration/test_a42_ci_scope_pg17.py": ["exercise"],
    "tests/integration/test_ab_read_experiment_v14_a4_2.py": [
        "database",
        "test_fixture_count_failure_keeps_acquired_catalog_and_fail_closed_receipt",
        "test_full_fixture_census_matches_independent_aggregate_counts",
    ],
    "tests/unit/test_ab_read_experiment_contract_v14_a4_2.py": [
        "test_frozen_backend_migrations_and_a41_evidence_are_unchanged"
    ],
    "tests/unit/test_ab_read_profile_v14_a4.py": ["test_a4_diagnostic_freezes_production_sources"],
    "tests/unit/test_lookup_tail_review_a423.py": [
        "test_workflow_does_not_repeat_the_disallowed_100_trial_or_weaken_capacity"
    ],
    "tests/unit/test_tail_historical_a4231.py": [
        "test_protocol_does_not_change_production_or_authorize_formal_capacity"
    ],
    "tests/unit/test_tail_stability_a4232.py": [
        "test_protocol_is_immutable_and_production_still_exact_c0"
    ],
    "tests/unit/test_a4233_background_observer.py": [
        "test_frozen_baseline_bytes_and_old_workflows_unchanged"
    ],
    "tests/unit/test_a42363_complete_guard.py": [
        "test_CF_AT05_AT21_production_templates_and_old_authorizations_are_unchanged"
    ],
    "tests/unit/test_a42363_source_guard.py": [
        "test_AT09_production_and_frozen_protocols_untouched"
    ],
    "tests/unit/test_a42362_source_guard.py": [
        "test_AT01_AT06_final_commit_has_exact_paths_and_historical_manifests_unchanged",
        "test_AT70_no_production_migrations_workflows_dependencies_or_old_protocol_changes",
    ],
    "tests/unit/test_a42364_source_guard.py": [
        "test_AT02_history_and_all_committed_pins_match_final_stage",
        "test_AT04_production_and_frozen_sql_never_enter_this_stage",
    ],
    "tests/unit/test_a42363_review_guard.py": [
        "test_RF_AT57_all_original_tests_have_identical_git_blobs",
        "test_RF_AT59_candidate_cannot_change_sql_or_enable_protocol",
    ],
    "tests/unit/test_a42351_g1_preflight.py": [
        "test_a42351_AT01_baseline_and_boundaries_are_not_historical_rewrites"
    ],
    "tests/unit/test_a42341_environment_guard.py": [
        "test_A42342_T19_T20_no_workflow_schema_or_other_tool_change"
    ],
    "tests/unit/test_a42_ci_partition_contract.py": [
        "test_production_tree_and_original_a41_evidence_unchanged"
    ],
    "tests/unit/test_a4236_source_guard.py": [
        "test_AT01_AT02_actual_history_unchanged_and_new_source_distinct",
        "test_AT03_actual_exact_26_path_delta_and_pinned_14_patch_blobs",
    ],
    "tests/unit/test_a42361_source_entrypoints.py": [
        "test_AT01_AT02_AT04_actual_source_freeze_and_history"
    ],
}


def a42_static_contract(root=ROOT):
    """Recheck immutable A42 blobs, then bind a distinct current static contract.

    This is callable by --contract-only, never by the measurement source guard.
    """
    baseline = "f8df915febe24bce3f3bcdb8a52ae2f3a5b78e62"
    verify(root)
    paths = [
        "backend",
        "migrations",
        "config",
        "scripts/ab_read_profile_v14_a4.py",
        "scripts/ab_read_profile_summary_v14_a4.py",
        "docs/acceptance/v14_a4_baseline.md",
        "docs/acceptance/evidence",
        "scripts/ab_read_benchmark_v14.py",
        "scripts/v14_test_database.py",
        "scripts/publication_candidate_benchmark_v13.py",
        "tests/integration/test_data_publication.py",
        "tests/integration/test_ab_merge_read_v14.py",
        "tests/integration/m16_6_support.py",
    ]
    result = {}
    entries = [
        e for e in git(root, "ls-tree", "-r", "-z", baseline, "--", *paths).split(b"\0") if e
    ]
    blobs = git_blobs(
        root,
        [
            rev + ":" + e.split(b"\t", 1)[1].decode()
            for e in entries
            for rev in (baseline, HISTORICAL_SOURCE)
        ],
    )
    for entry in entries:
        metadata, raw_path = entry.split(b"\t", 1)
        path = raw_path.decode()
        old = blobs[baseline + ":" + path]
        if old != blobs[HISTORICAL_SOURCE + ":" + path]:
            raise ValueError("A42_FROZEN_SOURCE_CHANGED")
        result[path] = dict(
            git_blob=metadata.split()[2].decode(),
            historical_sha256=hashlib.sha256(old).hexdigest(),
            evidence_kind="HISTORICAL_NOT_CURRENT_PERFORMANCE",
        )
    return result


def bind_current_diagnostic_contract(patch):
    """Explicit ordinary-test route, not a relaxation of real CLI admission.

    Existing small PG tests exercise current read/timeout/cancel behavior. Their
    static contract validates BOTH immutable history and exact current bytes;
    it cannot certify the current source against old performance measurements.
    Only a test's restoring monkeypatch can install this local diagnostic route.
    """
    from scripts import ab_read_experiment_v14_a4_2 as experiment

    def receipt():
        return dict(
            purpose="CURRENT_STATIC_TEST_DIAGNOSTIC_ONLY",
            historical_files=a42_static_contract(),
            **source_versions(["backend/app/services/data_publication.py"]),
        )

    receipt()  # Refuse before any fixture or diagnostic read is created.
    patch.setattr(experiment, "source_contract", receipt)


def versioned_frozen_files(root, frozen):
    """Keep old manifests intact; compare their blobs at the immutable old source.

    The caller still validates current files with its original independent reader.
    Current changed bytes must additionally match the exact BIZ manifest.
    """
    root = Path(root)
    if not (root / MANIFEST).exists():
        return frozen
    from scripts import a4235_capability_guard as g

    # definitions() historically checks only its frozen files. Keep that scope
    # and its independent reader; full HEAD/FD validation remains in verify().
    # Never cache current manifest/files, raw inputs, row hashes or Job evidence.
    g.require(g.path_sha(root / MANIFEST) == g.BUSINESS_MANIFEST_SHA, "A4235_LIVE_OVERLAY_INVALID")
    patches = json.loads((root / MANIFEST).read_bytes())["patch_sha256"]
    from scripts.a42365_source_guard import MANIFEST as runtime_manifest

    if (root / runtime_manifest).is_file():
        g.require(
            g.path_sha(root / runtime_manifest) == g.A42365_MANIFEST_SHA,
            "A4235_LIVE_OVERLAY_INVALID",
        )
        patches.update(json.loads((root / runtime_manifest).read_bytes())["patch_sha256"])
    from scripts.a42366_source_guard import MANIFEST as closure_manifest

    if (root / closure_manifest).is_file():
        g.require(g.path_sha(root / closure_manifest) == A42366_MANIFEST_SHA,
                  "A4235_LIVE_OVERLAY_INVALID")
        patches.update(json.loads((root / closure_manifest).read_bytes())["patch_sha256"])
    baseline_hashes = immutable_frozen_hashes(root, tuple(sorted(frozen.items())))
    return {path: patches.get(path, sha) for path, sha in baseline_hashes.items()}


@lru_cache(maxsize=8)
def immutable_frozen_hashes(root, frozen):
    """Cache only literal immutable Git objects, never the current worktree."""
    blobs = git_blobs(
        root, [rev + ":" + p for p, _ in frozen for rev in (HISTORICAL_SOURCE, BASELINE)]
    )
    result = {}
    for path, expected in frozen:
        old = hashlib.sha256(blobs[HISTORICAL_SOURCE + ":" + path]).hexdigest()
        if old != expected:
            raise ValueError("BUSINESS_HISTORICAL_SOURCE_CHANGED")
        result[path] = hashlib.sha256(blobs[BASELINE + ":" + path]).hexdigest()
    return result


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root)


def git_blobs(root, objects):
    """Batch immutable Git reads; current files are always checked independently."""
    import re

    names = list(dict.fromkeys(objects))
    if any(not re.fullmatch(r"[0-9a-f]{40}:[^\r\n]+", name) for name in names):
        raise ValueError("BUSINESS_INVALID_SOURCE_OBJECT")
    raw = subprocess.check_output(
        ["git", "cat-file", "--batch"], cwd=root, input=("\n".join(names) + "\n").encode()
    )
    result, offset = {}, 0
    for name in names:
        end = raw.index(b"\n", offset)
        fields = raw[offset:end].split()
        if len(fields) != 3 or fields[1] != b"blob":
            raise ValueError("BUSINESS_SOURCE_OBJECT_MISSING")
        count = int(fields[2])
        result[name] = raw[end + 1 : end + 1 + count]
        offset = end + count + 2
    if offset != len(raw):
        raise ValueError("BUSINESS_SOURCE_OBJECT_INVALID")
    return result


def historical_bytes(path, *, revision=HISTORICAL_SOURCE, root=ROOT):
    # Revision must be explicit; it is never derived from current HEAD or a receipt.
    if revision not in {
        HISTORICAL_SOURCE,
        "4b158c10f22119374c2e0891308ba935ff91d4ca",
        "4a095883bff09e0e5da6fe5fcf308f8206651f35",
        "73a3273301502822dc7a881a64dfdca45db4d063",
    }:
        raise ValueError("BUSINESS_UNREGISTERED_HISTORICAL_SOURCE")
    if path.startswith("/") or ".." in Path(path).parts:
        raise ValueError("BUSINESS_INVALID_SOURCE_PATH")
    return git(root, "show", revision + ":" + path)


def source_versions(paths, *, historical_revision=HISTORICAL_SOURCE, root=ROOT):
    def record(raw):
        return hashlib.sha256(raw).hexdigest()

    old = {p: record(historical_bytes(p, revision=historical_revision, root=root)) for p in paths}
    current = {p: record((root / p).read_bytes()) for p in paths}
    return dict(
        schema_version=VERSION,
        historical_source=dict(
            commit_sha=historical_revision,
            files=old,
            evidence_kind="HISTORICAL_NOT_CURRENT_PERFORMANCE",
        ),
        current_source=dict(
            commit_sha=git(root, "rev-parse", "HEAD").decode().strip(),
            files=current,
            evidence_kind="CURRENT_SOURCE_NOT_PERFORMANCE_ACCEPTANCE",
        ),
        performance_eligible=False,
        production_read_authorized=False,
        capacity_ready=False,
        g1_authorized=False,
    )


def verify_test_adaptation(before, after, names):
    def signatures(raw):
        return {
            node.name: (
                ast.dump(node.args),
                [ast.dump(d) for d in node.decorator_list],
                sum(isinstance(n, ast.Assert) for n in ast.walk(node)),
            )
            for node in ast.parse(raw).body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
        }

    old, new = signatures(before), signatures(after)
    if old.keys() != new.keys() or any(
        old[name][:2] != new[name][:2] or new[name][2] < old[name][2] for name in old
    ):
        raise ValueError("BUSINESS_TEST_CASE_OR_ASSERTION_REMOVED")

    def remove(raw):
        lines = raw.decode().splitlines(keepends=True)
        found = set()
        for node in reversed(ast.parse(raw).body):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
                found.add(node.name)
                start = min([node.lineno, *[d.lineno for d in node.decorator_list]])
                del lines[start - 1 : node.end_lineno]
        if found != set(names):
            raise ValueError("BUSINESS_TEST_ADAPTATION_INVALID")
        return "".join(lines)

    if remove(before) != remove(after):
        raise ValueError("BUSINESS_UNREVIEWED_TEST_CHANGE")


def verify(root=ROOT):
    from scripts import a4235_capability_guard as g
    from scripts import a42361_source_guard as fd_guard
    from scripts import a42364_source_guard as legacy
    from scripts import a42366_source_guard as closure
    from scripts.a42365_source_guard import MANIFEST as runtime_manifest
    from scripts.a42365_source_guard import verify as runtime_verify

    if (Path(root) / closure.MANIFEST).is_file():
        return closure.verify(g, root, g.git(root, "rev-parse", "HEAD").decode().strip())

    if (Path(root) / runtime_manifest).is_file():
        return runtime_verify(g, root, g.git(root, "rev-parse", "HEAD").decode().strip())

    head = g.git(root, "rev-parse", "HEAD").decode().strip()
    import re

    g.require(re.fullmatch(r"[0-9a-f]{40}", head) is not None, "A4235_FULL_SHA_REQUIRED")
    g.require(head == git(root, "rev-parse", "HEAD").decode().strip(), "A4235_HEAD_MISMATCH")
    g.require(not g.git(root, "status", "--porcelain").strip(), "A4235_DIRTY_TREE")
    g.require(g.path_sha(root / MANIFEST) == g.BUSINESS_MANIFEST_SHA, "A4235_LIVE_OVERLAY_INVALID")
    raw = (root / MANIFEST).read_bytes()
    data = json.loads(raw)
    g.require(
        set(data)
        == {
            "version",
            "baseline_sha",
            "historical_source",
            "stage_paths",
            "patch_sha256",
            "normalized_guard_sha256",
            "historical_manifest_sha256",
        }
        and data["version"] == VERSION
        and data["baseline_sha"] == BASELINE
        and data["historical_source"] == HISTORICAL_SOURCE,
        "A4235_LIVE_OVERLAY_INVALID",
    )
    changed = set(g.git(root, "diff", "--name-only", "-z", BASELINE).decode().split("\0")) - {""}
    g.require(
        not any(
            p.startswith(
                (
                    ".github/",
                    "infra/",
                    "config/",
                    "migrations/",
                    "docs/acceptance/a4",
                    "docs/acceptance/biz_perf_01/",
                )
            )
            for p in changed
        ),
        "A4235_FROZEN_FILE_CHANGED",
    )
    g.require(changed == set(data["stage_paths"]), "A4235_FROZEN_FILE_CHANGED")
    g.require(
        set(data["patch_sha256"]) == changed - {MANIFEST, GUARD}, "A4235_LIVE_OVERLAY_INVALID"
    )
    for p, digest in data["patch_sha256"].items():
        g.require(
            hashlib.sha256((root / p).read_bytes()).hexdigest() == digest,
            "A4235_HEAD_BYTES_MISMATCH",
        )
    guard = (root / GUARD).read_bytes()
    pattern = rb"BUSINESS_MANIFEST_SHA = '[0-9a-f]{64}'"
    g.require(len(re.findall(pattern, guard)) == 1, "A4235_LIVE_OVERLAY_INVALID")
    guard = re.sub(pattern, b"BUSINESS_MANIFEST_SHA = '" + b"0" * 64 + b"'", guard)
    g.require(
        hashlib.sha256(guard).hexdigest() == data["normalized_guard_sha256"],
        "A4235_LIVE_OVERLAY_INVALID",
    )
    # Read every original manifest and each original pin at its own immutable commit.
    histories = {**legacy.HISTORICAL, legacy.MANIFEST: HISTORICAL_SOURCE}
    g.require(
        set(data["historical_manifest_sha256"]) == set(histories), "A4235_LIVE_OVERLAY_INVALID"
    )
    previous_blobs = git_blobs(root, [HISTORICAL_SOURCE + ":" + p for p in histories])
    pin_blobs = git_blobs(
        root,
        [
            closing + ":" + p
            for path, closing in histories.items()
            for p in json.loads(previous_blobs[HISTORICAL_SOURCE + ":" + path])["patch_sha256"]
        ],
    )
    for path, closing in histories.items():
        previous = previous_blobs[HISTORICAL_SOURCE + ":" + path]
        g.require(
            previous == (root / path).read_bytes()
            and g.path_sha(root / path) == data["historical_manifest_sha256"][path]
            and hashlib.sha256(previous).hexdigest() == data["historical_manifest_sha256"][path],
            "A4235_OVERLAY_BYTES_MISMATCH",
        )
        for p, digest in json.loads(previous)["patch_sha256"].items():
            g.require(
                hashlib.sha256(pin_blobs[closing + ":" + p]).hexdigest() == digest,
                "A4235_OVERLAY_BYTES_MISMATCH",
            )
    # Preserve the original independent read boundaries and first-error taxonomy.
    # These are additive checks, including the historical negative injection APIs.
    original_paths = g.PATCH_PATHS | g.NEXT_PATCH_PATHS
    original_blobs = git_blobs(root, [HISTORICAL_SOURCE + ":" + p for p in original_paths])
    for path in original_paths:
        old = original_blobs[HISTORICAL_SOURCE + ":" + path]
        g.require(
            g.git(root, "show", HISTORICAL_SOURCE + ":" + path) == old
            and g.path_sha(root / path)
            == data["patch_sha256"].get(path, hashlib.sha256(old).hexdigest()),
            "A4235_OVERLAY_BYTES_MISMATCH",
        )
    g.require(
        g.git(root, "ls-tree", "-r", head, "--", "infra")
        == git(root, "ls-tree", "-r", head, "--", "infra"),
        "A4235_HEAD_BYTES_MISMATCH",
    )
    old_files = {}
    for row in git(root, "ls-tree", "-r", "-z", BASELINE, "--", "tests").split(b"\0"):
        if row:
            metadata, path = row.split(b"\t", 1)
            old_files[path.decode()] = metadata.split()[2]
    for path, oid in old_files.items():
        current = (root / path).read_bytes()
        if path in TEST_ADAPTATIONS and path in changed:
            verify_test_adaptation(
                git(root, "show", BASELINE + ":" + path), current, TEST_ADAPTATIONS[path]
            )
        elif path in APPEND_ONLY_TESTS and path in changed:
            old = git(root, "show", BASELINE + ":" + path)
            g.require(current.startswith(old), "A4235_FROZEN_FILE_CHANGED")
            old_nodes, new_nodes = ast.parse(old).body, ast.parse(current).body
            g.require(
                len(new_nodes) > len(old_nodes)
                and all(
                    isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
                    for n in new_nodes[len(old_nodes) :]
                )
                and len({n.name for n in new_nodes if isinstance(n, ast.FunctionDef)})
                == sum(isinstance(n, ast.FunctionDef) for n in new_nodes),
                "A4235_FROZEN_FILE_CHANGED",
            )
        else:
            g.require(
                hashlib.sha1(b"blob " + str(len(current)).encode() + b"\0" + current)
                .hexdigest()
                .encode()
                == oid,
                "A4235_FROZEN_FILE_CHANGED",
            )
    # Same complete no-follow HEAD, hidden index and inode-race protection as G1.
    fd_guard.verify_full_worktree(g, root, head)
    g.require(
        head == g.git(root, "rev-parse", "HEAD").decode().strip()
        and not g.git(root, "status", "--porcelain").strip(),
        "A4235_DIRTY_TREE",
    )
    return hashlib.sha256(
        json.dumps(
            dict(
                domain="BIZ_CURRENT_STATIC_ONLY",
                head_sha=head,
                manifest_sha256=g.BUSINESS_MANIFEST_SHA,
            ),
            sort_keys=True,
        ).encode()
    ).hexdigest()
