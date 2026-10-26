"""AT01–04,35: fresh Git bindings, precise overlay and unchanged legacy reviewer."""

import ast
import copy
import hashlib
import json

import pytest

from scripts import a4235_capability_guard as g
from scripts import a4236_cli as cli
from scripts import a4236_evidence as e
from scripts import a4236_mock as m
from scripts.a4235_calibration_adapter_contract import ROOT
from scripts.a4235_calibration_adapter_contract import Fault as OldFault
from scripts.a4236_g1_harness_contract import Fault


def test_AT01_AT02_actual_history_unchanged_and_new_source_distinct():
    identity = g.expected_identity()
    assert identity.head_sha == g.git(ROOT, "rev-parse", "HEAD").decode().strip()
    assert (
        identity.frozen_sha256 == "b7aecb955fb32bf285ae71ff3bdf6cfdc6aa15828e70bb46c507d31bfc1418e9"
    )
    assert (
        identity.source_sha256 != "43765d891dc0f30270d4ad5ffc035df72b031758797fee7153fb56366b777404"
    )
    assert len(g.overlay_fingerprint()) == 64
    assert g.path_sha(ROOT / g.OVERLAY_MANIFEST) == g.OVERLAY_MANIFEST_SHA
    for path in g.PATCH_PATHS | {g.OVERLAY_MANIFEST}:
        assert (ROOT / path).read_bytes() == g.git(ROOT, "show", f"{g.NEXT_BASE}:{path}")
    assert not g.git(
        ROOT,
        "diff",
        "--name-only",
        g.NEXT_BASE,
        "--",
        "backend",
        "config",
        "migrations",
        "frontend",
        ".github",
        "requirements.lock",
        "requirements-dev.txt",
        "pyproject.toml",
        "scripts/a42341_calibration_runner.py",
        "scripts/a42341_contract.py",
        "scripts/a42341_calibration_guard.py",
    )
    from scripts import a42341_contract as old

    assert old.definitions()["effective_warmups_total"] == 8
    assert len(old.schedule()) == 128
    assert {p["block"] for p in old.schedule()} == {0, 1, 2, 3}
    assert len({(p["block"], p["variant"], p["pair"]) for p in old.schedule()}) == 64


def test_AT03_actual_exact_26_path_delta_and_pinned_14_patch_blobs():
    from scripts import a42361_source_guard as live

    changed = set(g.git(ROOT, "diff", "--name-only", "-z", g.NEXT_BASE).decode().split("\0")) - {""}
    authority = {
        "README.md",
        "PROJECT_RULES.md",
        "docs/股票机会发现系统_PRD_V1.0.md",
        "docs/股票机会发现系统_系统设计_V1.0.md",
    }
    historical = set(
        g.git(ROOT, "diff", "--name-only", "-z", g.NEXT_BASE, live.BASELINE)
        .decode().split("\0")
    ) - {""}
    assert historical == g.NEXT_STAGE_PATHS | authority and len(historical) == 26
    from scripts import a42362_source_guard as services

    assert changed == historical | live.STAGE_PATHS | services.STAGE_PATHS
    live.validate_paths(
        set(g.git(ROOT, "diff", "--name-only", "-z", live.BASELINE, services.BASELINE)
            .decode().split("\0")) - {""}
    )
    services.validate_paths(set(g.git(ROOT, "diff", "--name-only", "-z", services.BASELINE)
                                .decode().split("\0")) - {""})
    manifest = json.loads((ROOT / g.NEXT_MANIFEST).read_bytes())
    assert len(manifest["patch_sha256"]) == 14
    assert len(g.NEXT_STAGE_PATHS) == 22
    for name in g.NEXT_PATCH_PATHS:
        original = hashlib.sha256(g.git(ROOT, "show", f"{live.BASELINE}:{name}")).hexdigest()
        assert manifest["patch_sha256"][name] == original
        if name != live.OLD_TEST:
            assert original == g.path_sha(ROOT / name)
        else:
            overlay = json.loads((ROOT / live.MANIFEST).read_bytes())
            assert original == overlay["old_sha256"][name]
            assert hashlib.sha256(g.git(ROOT, "show", f"{services.BASELINE}:{name}")).hexdigest() \
                == overlay["patch_sha256"][name]
            latest = json.loads((ROOT / services.MANIFEST).read_bytes())
            assert g.path_sha(ROOT / name) == latest["patch_sha256"][name]
    assert hashlib.sha256((ROOT / g.NEXT_MANIFEST).read_bytes()).hexdigest() == g.NEXT_MANIFEST_SHA


@pytest.mark.parametrize(
    "path",
    [
        "backend/app/extra.py",
        "scripts/a4236_backdoor.py",
        ".github/workflows/new.yml",
        "tests/unit/old.py",
        "docs/acceptance/a4235_closeout.md",
    ],
)
def test_AT03_no_directory_or_name_prefix_exemption(path):
    with pytest.raises(OldFault, match="FROZEN_FILE_CHANGED"):
        g.validate_next_paths(g.NEXT_STAGE_PATHS | {path})
    with pytest.raises(OldFault, match="FROZEN_FILE_CHANGED"):
        g.validate_next_paths(g.NEXT_STAGE_PATHS - {g.NEXT_MANIFEST})


@pytest.mark.parametrize(
    "change",
    [
        "manifest",
        "patch",
        "head_blob",
        "extra_path",
        "short_head",
        "dirty",
        "head_race",
        "hidden_index",
    ],
)
def test_AT04_independent_overlay_rejects_tampering_without_editing_source(monkeypatch, change):
    original_git, original_sha = g.git, g.path_sha
    rev_calls = 0

    def fake_git(root, *args):
        nonlocal rev_calls
        if args[:2] == ("rev-parse", "HEAD"):
            rev_calls += 1
            if change == "short_head":
                return b"abc"
            if change == "head_race" and rev_calls > 1:
                return b"f" * 40
        if change == "dirty" and args[0] == "status":
            return b" M anything"
        if change == "head_blob" and args[0] == "show" and "a4236_mock.py" in args[1]:
            return b"fake-committed-bytes"
        if change == "extra_path" and args[0] == "diff":
            return original_git(root, *args) + b"scripts/new_not_whitelisted.py\n"
        if change == "hidden_index" and args[0] == "ls-tree":
            return b"100644 blob " + b"0" * 40 + b"\tbackend/app/__init__.py\n"
        return original_git(root, *args)

    def fake_sha(path):
        if change == "manifest" and str(path).endswith(g.NEXT_MANIFEST):
            return "f" * 64
        if change == "patch" and str(path).endswith("a4236_mock.py"):
            return "f" * 64
        return original_sha(path)

    monkeypatch.setattr(g, "git", fake_git)
    monkeypatch.setattr(g, "path_sha", fake_sha)
    with pytest.raises(OldFault, match="^A4235_"):
        g.overlay_fingerprint()


def test_AT05_AT36_real_git_independent_expected_and_owner_only_offline_bundle(tmp_path):
    c = cli.expected_from_git()
    assert c.evidence_kind == "OFFLINE_DESIGN"
    assert e.independent_expected(c) == c
    path = tmp_path / "offline"
    e.write_bundle(path, m.offline_design(c), c)
    assert e.review_bundle(path, c)["physical_capabilities"] == "NOT_PROVEN"
    with pytest.raises(Fault, match="UNTRUSTED_EXPECTED"):
        e.review_bundle(path, c.model_copy(update={"overlay_sha256": "f" * 64}))


def test_AT35_no_new_real_adapters_collectors_or_workflow_entrypoints():
    # Imports are limited to data, safe artifact IO, and existing independent Git guard.
    allowed = {
        "re",
        "dataclasses",
        "typing",
        "pydantic",
        "hashlib",
        "copy",
        "decimal",
        "os",
        "stat",
        "time",
        "pathlib",
        "json",
        "sys",
        "scripts",
        "scripts.a4235_calibration_adapter_contract",
        "scripts.a4235_prepared_probe",
        "scripts.a4235_resource_bridge",
        "scripts.a4235_capability_review",
        "scripts.a4235_capability_guard",
    } | {s[:-3].replace("/", ".") for s in g.NEXT_SOURCES}
    for path in g.NEXT_SOURCES:
        tree = ast.parse((ROOT / path).read_bytes())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert {x.name for x in node.names} <= allowed
            if isinstance(node, ast.ImportFrom):
                assert node.module in allowed
    from scripts.a4236_g1_probe import TEMPLATES

    assert set(TEMPLATES) == {"I4", "I8", "PROJECTION"}
    assert all(
        b"PREPARE " not in row[0]
        and b"EXPLAIN" not in row[0]
        and b"pg_stat_clear_snapshot" not in row[0]
        for row in TEMPLATES.values()
    )


def test_AT35_legacy_observer_false_join_exact_error_and_valid_failures_preserved():
    from scripts import a42341_calibration_review as reviewer
    from scripts import a42341_contract as c
    from scripts.a42341_calibration_runner import MockObserver, MockResources, simulate

    expected = c.identity()
    complete = simulate(expected)
    invalid = simulate(
        expected, observer=MockObserver(fail_at=1, failure_code="A42341_OBSERVER_INVALID")
    )
    forged = copy.deepcopy(invalid)
    forged["failed_point"]["partial_sample"]["observation"]["joined"] = True
    forged["failed_point"]["partial_sample"]["cleanup_complete"] = True
    forged["cleanup_complete"], forged["cleanup_failure_codes"] = True, []
    with pytest.raises(c.Fault, match="^A42341_FAILED_POINT_INVALID$"):
        reviewer.review(c.seal(forged), expected)
    point = invalid["failed_point"]["partial_sample"]
    point["observation"] = copy.deepcopy(complete["samples"][1]["observation"])
    point["observation"]["ticks"][-1]["partial"] = True
    point["resources"] = copy.deepcopy(complete["samples"][1]["resources"])
    point["cleanup_complete"] = invalid["cleanup_complete"] = True
    invalid["cleanup_failure_codes"] = []
    reviewed = reviewer.review(c.seal(invalid), expected)
    assert reviewed["collection_status"] == "INCOMPLETE"
    assert reviewed["first_failure_code"] == "A42341_OBSERVER_INVALID"
    cleanup_only = simulate(expected, resources=MockResources(cleanup_failure=True))
    reviewed = reviewer.review(cleanup_only, expected)
    assert len(cleanup_only["samples"]) == 128
    assert reviewed["collection_status"] == "INCOMPLETE"
    assert reviewed["cleanup_failure_codes"] == ["A42341_CLEANUP_FAILED"]
    assert reviewed["first_failure_code"] == "A42341_CLEANUP_FAILED"
