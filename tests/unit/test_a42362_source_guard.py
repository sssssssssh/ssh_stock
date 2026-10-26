"""Exact overlay/identity checks; physical source-FD race coverage remains in legacy Linux tests."""

import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import a42362_source_guard as g
from scripts.a4235_calibration_adapter_contract import Fault
from scripts.a4235_calibration_adapter_contract import require as legacy_require

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "name",
    [
        "scripts/extra.py",
        "infra/g1_harness/other.sql",
        "backend/app/unsafe.py",
        ".github/workflows/other.yml",
        "tests/unit/other.py",
    ],
)
def test_AT02_no_directory_or_prefix_exemptions(name):
    with pytest.raises(Fault, match="FROZEN_FILE_CHANGED"):
        g.validate_paths(g.STAGE_PATHS | {name})
    with pytest.raises(Fault, match="FROZEN_FILE_CHANGED"):
        g.validate_paths(g.STAGE_PATHS - {g.MANIFEST})


def test_AT01_AT06_final_commit_has_exact_paths_and_historical_manifests_unchanged():
    from scripts import a42363_complete_guard as complete
    from scripts import a42363_source_guard as closeout

    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    historical_head = closeout.BASELINE
    changed = set(
        subprocess.check_output(
            ["git", "diff", "--name-only", "-z", g.BASELINE, historical_head], cwd=ROOT)
        .decode()
        .split("\0")
    ) - {""}
    g.validate_paths(changed)
    for name in (
        "docs/acceptance/a42351_reviewer_overlay_manifest.json",
        "docs/acceptance/a4236_overlay_manifest.json",
        "docs/acceptance/a42361_overlay_manifest.json",
    ):
        assert subprocess.check_output(
            ["git", "show", f"{head}:{name}"], cwd=ROOT
        ) == subprocess.check_output(["git", "show", f"{g.BASELINE}:{name}"], cwd=ROOT)
    manifest = json.loads(
        subprocess.check_output(["git", "show", f"{historical_head}:{g.MANIFEST}"], cwd=ROOT)
    )
    assert manifest["stage_paths"] == sorted(g.STAGE_PATHS)
    assert set(manifest["patch_sha256"]) == g.PINNED
    for name in g.PINNED:
        actual = subprocess.check_output(["git", "show", f"{historical_head}:{name}"], cwd=ROOT)
        assert hashlib.sha256(actual).hexdigest() == manifest["patch_sha256"][name]
        current = subprocess.check_output(["git", "show", f"{head}:{name}"], cwd=ROOT)
        if name in closeout.PINNED:
            latest = json.loads((ROOT / closeout.MANIFEST).read_bytes())
            closing = subprocess.check_output(
                ["git", "show", f"{complete.BASELINE}:{name}"], cwd=ROOT)
            assert hashlib.sha256(closing).hexdigest() == latest["patch_sha256"][name]
            if name in complete.PINNED:
                final = json.loads((ROOT / complete.MANIFEST).read_bytes())
                assert hashlib.sha256(current).hexdigest() == final["patch_sha256"][name]
            else:
                assert current == closing
        else:
            assert current == actual


def test_AT04_normalization_excludes_only_the_new_self_reference_literal():
    old = b"OLD_ASSERTION = True\nSERVICE_MANIFEST_SHA = '" + b"a" * 64 + b"'\n"
    value = g.normalize_guard(old)
    assert b"OLD_ASSERTION = True" in value and b"0" * 64 in value
    assert g.normalize_guard(old.replace(b"True", b"False")) != value
    with pytest.raises(ValueError):
        g.normalize_guard(b"unrecognized source")


@pytest.mark.parametrize("threat", ["committed_patch", "hidden_infra"])
def test_AT03_inherited_checks_remain_independent_before_full_fd_walk(tmp_path, threat):
    patch, manifest = "immutable.py", "manifest.json"
    (tmp_path / patch).write_bytes(b"APPROVED")
    (tmp_path / manifest).write_text(
        json.dumps({"patch_sha256": {patch: hashlib.sha256(b"APPROVED").hexdigest()}})
    )
    (tmp_path / "infra").mkdir()
    (tmp_path / "infra/immutable.sql").write_bytes(b"APPROVED_INFRA")

    def path_sha(path):
        if threat == "committed_patch" and path.name == patch:
            return hashlib.sha256(b"UNAPPROVED").hexdigest()
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def git(root, *args):
        assert args == ("ls-tree", "-r", "f" * 40, "--", "infra")
        return b"100644 blob " + b"0" * 40 + b"\tinfra/immutable.sql\n"

    guard = SimpleNamespace(
        require=legacy_require,
        path_sha=path_sha,
        git=git,
        PATCH_PATHS={patch},
        OVERLAY_MANIFEST=manifest,
        OVERLAY_MANIFEST_SHA=path_sha(tmp_path / manifest),
    )
    code = "OVERLAY_BYTES_MISMATCH" if threat == "committed_patch" else "HEAD_BYTES_MISMATCH"
    with pytest.raises(Fault, match=code):
        g.verify_inherited_checks(guard, tmp_path, "f" * 40)


def test_AT70_no_production_migrations_workflows_dependencies_or_old_protocol_changes():
    protected = [
        "backend",
        "config",
        "frontend",
        "migrations",
        ".github",
        "requirements.lock",
        "requirements-dev.txt",
        "pyproject.toml",
        "docs/acceptance/evidence",
        "scripts/a42341_calibration_runner.py",
        "scripts/a42341_calibration_review.py",
        "docs/acceptance/v14_a4_2_3_4_calibration_protocol.md",
    ]
    assert not subprocess.check_output(
        ["git", "diff", "--name-only", g.BASELINE, "--", *protected], cwd=ROOT
    ).strip()
